#!/usr/bin/env python3
"""Drive a running Unity Editor through a file-based gate, or run batchmode/Player evidence.

The gate is a small Editor script (``Editor/UnityEditorGate/UnityEditorGate.cs`` in this
bundle). It polls ``<project>/Temp/UnityEditorGate/<pid>/request.json`` and writes
``status.json`` plus a per-request ``<id>/result.json``. This driver never guesses a gate
root when several Editors could match: it resolves the current Editor from
``Library/EditorInstance.json`` or requires ``--gate-root``.

Subcommands
-----------
discover  project/Editor/version/EditorInstance/Editor.log facts (read-only)
status    latest gate receipt, age and staleness
request   atomically write a gate request (refuses to overwrite evidence)
wait      poll one request until result/failure/timeout
run       request + wait (optionally wait until the gate is ready first)
tests     run Unity Test Framework in batchmode, isolate TEMP/log/results, then parse the
          NUnit report with the bundled ``unity_checks.py`` (single source of truth)
player    launch a built Player/Test exe with timeout and captured stdio
log       summarize a Unity log (compile/runtime error samples + tail)

Gate protocol (schema_version 1)
--------------------------------
request.json: {"schema_version":1, "id":"<ascii>", "suite":"refresh|wait-compile|invoke",
              "type":"<Type>", "method":"<static method>", "args":["..."], "note":"..."}
status.json / <id>/result.json: {"schema_version":1, "status":"ready|busy|started|observed|
              failed", "ok":bool, "id":str, "suite":str, "error":str, "result":str, ...}

Exit codes: 0 = success/ready; 1 = failure (failed result, timeout, nonzero Player, test
failure); 2 = usage/unavailable (bad args, missing gate/project/editor/input).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
SUCCESS_STATUS = {"observed", "completed", "done", "passed"}
FAIL_STATUS = {"failed", "error", "rejected"}
GATE_DIR = ("Temp", "UnityEditorGate")
DEFAULT_TIMEOUT = 600.0
DEFAULT_INTERVAL = 0.5


class UsageError(Exception):
    """Invalid arguments or unavailable prerequisites (exit 2)."""


class OperationalError(Exception):
    """The operation ran but failed (exit 1)."""


# ------------------------------------------------------------------ helpers ----
def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def monotonic():
    return time.monotonic()


def emit(data, code):
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError):
        return None


def write_json_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def find_unity_project(start):
    """Resolve the Unity project root (the folder holding ProjectSettings).

    Accepts either that folder itself, a workspace root with
    ``Docs/ai/project-profile.json`` (``unity.root``), an ancestor of a Unity project,
    or a workspace with exactly one nested Unity project.
    """
    base = Path(start or Path.cwd()).resolve()
    if (base / "ProjectSettings" / "ProjectVersion.txt").is_file():
        return base
    profile = read_json(base / "Docs" / "ai" / "project-profile.json")
    if isinstance(profile, dict):
        unity = profile.get("unity")
        relative = unity.get("root") if isinstance(unity, dict) else None
        if isinstance(relative, str) and relative.strip():
            candidate = (base / relative).resolve()
            if (candidate / "ProjectSettings" / "ProjectVersion.txt").is_file():
                return candidate
    for candidate in (base, *base.parents):
        if (candidate / "ProjectSettings" / "ProjectVersion.txt").is_file():
            return candidate
    found = []
    stack = [(base, 0)]
    while stack and len(found) < 2:
        directory, depth = stack.pop()
        if (directory / "ProjectSettings" / "ProjectVersion.txt").is_file():
            found.append(directory)
            continue
        if depth >= 3:
            continue
        try:
            children = sorted(child for child in directory.iterdir() if child.is_dir())
        except OSError:
            continue
        for child in children:
            if child.name in {"Library", "Temp", "Logs", "obj", "node_modules", ".git"}:
                continue
            stack.append((child, depth + 1))
    if len(found) == 1:
        return found[0]
    return None


def require_project(value):
    root = find_unity_project(value)
    if root is None:
        raise UsageError("找不到 Unity 工程（ProjectSettings/ProjectVersion.txt）；"
                         "用 --project 指定工程或环境根")
    return root


def project_version(root):
    path = root / "ProjectSettings" / "ProjectVersion.txt"
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    data = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return {"editor_version": data.get("m_EditorVersion", ""),
            "editor_version_revision": data.get("m_EditorVersionWithRevision", "")}


def editor_instance(root):
    data = read_json(root / "Library" / "EditorInstance.json")
    if not isinstance(data, dict):
        return None
    pid = data.get("process_id")
    data["process_alive"] = bool(isinstance(pid, int) and pid > 0 and pid_alive(pid))
    return data


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def editor_log_candidates():
    home = Path.home()
    paths = []
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            paths.append(Path(local) / "Unity" / "Editor" / "Editor.log")
    elif sys.platform == "darwin":
        paths.append(home / "Library" / "Logs" / "Unity" / "Editor.log")
    else:
        paths.append(home / ".config" / "unity3d" / "Editor.log")
    return paths


def resolve_gate_root(args):
    if getattr(args, "gate_root", None):
        return Path(args.gate_root).resolve()
    project = require_project(getattr(args, "project", None))
    pid = getattr(args, "pid", None)
    if not pid:
        instance = editor_instance(project)
        pid = instance.get("process_id") if instance else None
    if not isinstance(pid, int) or pid <= 0:
        raise UsageError("无法确定当前 Editor 的进程号；用 --gate-root 或 --pid 指定（先打开 Editor）")
    return project.joinpath(*GATE_DIR, str(pid))


def normalize_suite(value):
    if not isinstance(value, str) or not value.strip():
        raise UsageError("缺少 --suite")
    return value.strip()


def validate_id(value):
    if not isinstance(value, str) or not value.isascii() or not ID_RE.match(value):
        raise UsageError("--id 必须是 1~64 位 ASCII 字母/数字/._-，且以字母或数字开头")
    return value


def kill_tree(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=15, check=False)
        else:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def sibling_tool(name):
    return Path(__file__).resolve().with_name(name)


def run_checked(command, *, cwd=None, env=None, timeout=None, stdout_path=None, stderr_path=None):
    """Run a child process; capture stdio to files (avoids pipe deadlocks on Windows)."""
    stdout_file = open(stdout_path, "wb") if stdout_path else subprocess.DEVNULL
    stderr_file = open(stderr_path, "wb") if stderr_path else subprocess.DEVNULL
    started = monotonic()
    timed_out = False
    try:
        process = subprocess.Popen(command, cwd=str(cwd) if cwd else None, env=env,
                                   stdout=stdout_file, stderr=stderr_file,
                                   stdin=subprocess.DEVNULL)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(process)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
        return {"command": [str(item) for item in command], "returncode": process.returncode,
                "timed_out": timed_out, "duration_s": round(monotonic() - started, 3)}
    finally:
        if stdout_path:
            stdout_file.close()
        if stderr_path:
            stderr_file.close()


def unique_dir(base):
    if not base.exists():
        return base
    for index in range(1, 1000):
        candidate = base.with_name(base.name + "-" + str(index))
        if not candidate.exists():
            return candidate
    raise OperationalError("无法分配唯一证据目录: " + str(base))


def rel_posix(path, root):
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        raise UsageError("路径必须在工程根内: " + str(path))


# ------------------------------------------------------------------ discover ---
def windows_unity_processes():
    if os.name != "nt":
        return [], "process scan is Windows-only"
    command = ["powershell", "-NoProfile", "-Command",
               "Get-CimInstance Win32_Process -Filter \"Name='Unity.exe'\" | "
               "Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress"]
    try:
        result = subprocess.run(command, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return [], "process scan failed: " + str(error)
    text = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    if not text:
        return [], result.stderr.decode("utf-8", errors="replace").strip() or "no output"
    try:
        data = json.loads(text)
    except ValueError:
        return [], "unparsable process scan output"
    items = data if isinstance(data, list) else [data]
    return items, ""


# ------------------------------------------------------------------ commands ---
def cmd_discover(args):
    project = require_project(args.project)
    instance = editor_instance(project)
    logs = [str(path) for path in editor_log_candidates() if path.is_file()]
    gate_pid = getattr(args, "pid", None) or (instance.get("process_id") if instance else None)
    gate_root = None
    if isinstance(gate_pid, int) and gate_pid > 0:
        gate_root = project.joinpath(*GATE_DIR, str(gate_pid))
    editor = args.editor or os.environ.get("UNITY_EDITOR") or (instance or {}).get("app_path")
    workspace = Path(args.project).resolve() if args.project else Path.cwd().resolve()
    data = {"ok": True, "workspace": str(workspace), "project": str(project), **project_version(project),
            "editor_candidates": [{"source": "argument", "path": editor}] if editor else [],
            "editor_instance": instance,
            "gate_root": str(gate_root) if gate_root else None,
            "gate_root_exists": bool(gate_root and gate_root.is_dir()),
            "editor_logs": logs}
    if args.processes:
        processes, scan_error = windows_unity_processes()
        data["unity_processes"] = processes
        data["process_scan_error"] = scan_error
    if not editor:
        data["hint"] = "未找到 Editor 可执行文件：用 --editor 或设置 UNITY_EDITOR（本工具不猜盘符）"
    if instance and not instance.get("process_alive"):
        data["hint"] = "Library/EditorInstance.json 指向的进程未运行；gate 需要打开该工程中的 Editor"
    return emit(data, 0)


def cmd_status(args):
    root = resolve_gate_root(args)
    receipt_path = root / "status.json"
    receipt = read_json(receipt_path)
    age = None
    if receipt_path.is_file():
        age = round(max(0.0, time.time() - receipt_path.stat().st_mtime), 3)
    stale = age is not None and age > args.stale_after
    data = {"ok": receipt is not None, "gate_root": str(root), "exists": root.is_dir(),
            "receipt": receipt, "age_seconds": age, "stale": stale}
    if receipt is None:
        data["error"] = "gate status.json 不存在或不可解析（Editor 未打开/gate 未加载）"
        return emit(data, 2)
    return emit(data, 0)


def build_request(args):
    request = {"schema_version": SCHEMA, "id": validate_id(args.id), "suite": normalize_suite(args.suite)}
    if args.note:
        request["note"] = args.note
    if args.suite == "invoke":
        if not args.type or not args.method:
            raise UsageError("suite=invoke 需要 --type 与 --method")
        request["type"] = args.type
        request["method"] = args.method
        request["args"] = list(args.arg or [])
    for item in args.field or []:
        key, sep, value = item.partition("=")
        if not sep or not key.strip() or key in request:
            raise UsageError("--field 需要 key=value 且不能覆盖保留字段: " + item)
        request[str(key).strip()] = value
    return request


def cmd_request(args):
    root = resolve_gate_root(args)
    if not root.is_dir():
        raise UsageError("gate 根目录不存在: %s（Editor 未打开或 gate 未加载）" % root)
    request = build_request(args)
    run_dir = root / request["id"]
    if run_dir.exists():
        raise UsageError("证据目录已存在，拒绝覆盖: %s（换一个 --id）" % run_dir)
    request_path = root / "request.json"
    if request_path.exists():
        raise UsageError("gate 已有未认领的 request.json: %s" % request_path)
    write_json_atomic(request_path, request)
    return emit({"ok": True, "gate_root": str(root), "id": request["id"],
                 "request_path": str(request_path), "request": request}, 0)


def read_rejected(root, request_id):
    for path in sorted(root.glob("rejected-*.json")):
        payload = read_json(path)
        if isinstance(payload, dict) and payload.get("id") == request_id:
            return {"path": str(path), "request": payload}
    return None


def classify_result(result):
    if not isinstance(result, dict):
        return False, "result.json 不可解析"
    status = str(result.get("status") or "").casefold()
    error = result.get("error")
    if error:
        return False, str(error)
    if result.get("ok") is False or status in FAIL_STATUS:
        return False, "gate result 标记失败（status=%s）" % (status or "?")
    if result.get("ok") is True or status in SUCCESS_STATUS:
        return True, ""
    return True, ""  # a written result.json is final; failures must set ok=false/error


def wait_for_result(root, request_id, timeout, interval):
    started = monotonic()
    last = None
    while True:
        run_dir = root / request_id
        result = read_json(run_dir / "result.json")
        if result is not None:
            ok, error = classify_result(result)
            return {"ok": ok, "id": request_id, "gate_root": str(root),
                    "result": result,
                    "gate_status": read_json(root / "status.json"),
                    "waited_seconds": round(monotonic() - started, 3),
                    "error": error or None}, (0 if ok else 1)
        receipt = read_json(root / "status.json")
        if isinstance(receipt, dict):
            last = receipt
            if receipt.get("id") == request_id and str(receipt.get("status", "")).casefold() in FAIL_STATUS:
                return {"ok": False, "id": request_id, "gate_root": str(root), "gate_status": receipt,
                        "waited_seconds": round(monotonic() - started, 3),
                        "error": str(receipt.get("error") or "gate 标记该请求失败")}, 1
        rejected = read_rejected(root, request_id)
        if rejected:
            return {"ok": False, "id": request_id, "gate_root": str(root),
                    "rejected": rejected, "gate_status": receipt,
                    "waited_seconds": round(monotonic() - started, 3),
                    "error": "gate 拒绝了请求（见 rejected 文件）"}, 1
        if monotonic() - started >= timeout:
            return {"ok": False, "id": request_id, "gate_root": str(root),
                    "gate_status": last, "timed_out": True,
                    "waited_seconds": round(monotonic() - started, 3),
                    "error": "等待超时（%ss）；检查 Editor 是否忙碌/崩溃/gate 是否加载" % timeout}, 1
        time.sleep(interval)


def cmd_wait(args):
    root = resolve_gate_root(args)
    request_id = validate_id(args.id)
    data, code = wait_for_result(root, request_id, args.timeout, args.interval)
    return emit(data, code)


def wait_ready(root, timeout, interval):
    started = monotonic()
    last = None
    while True:
        receipt = read_json(root / "status.json")
        if isinstance(receipt, dict):
            last = receipt
            status = str(receipt.get("status") or "").casefold()
            if receipt.get("ready") is True or status == "ready":
                return True, last
            # failed/busy are transient around a request; keep polling until ready or timeout
        if monotonic() - started >= timeout:
            return None, last
        time.sleep(interval)


def cmd_run(args):
    root = resolve_gate_root(args)
    if not root.is_dir():
        raise UsageError("gate 根目录不存在: %s（Editor 未打开或 gate 未加载）" % root)
    if args.wait_ready:
        ready, receipt = wait_ready(root, args.ready_timeout, args.interval)
        if ready is None:
            return emit({"ok": False, "gate_root": str(root), "gate_status": receipt,
                         "timed_out": True, "error": "等待 gate ready 超时"}, 1)
    request = build_request(args)
    run_dir = root / request["id"]
    if run_dir.exists():
        raise UsageError("证据目录已存在，拒绝覆盖: %s（换一个 --id）" % run_dir)
    if (root / "request.json").exists():
        raise UsageError("gate 已有未认领的 request.json")
    write_json_atomic(root / "request.json", request)
    data, code = wait_for_result(root, request["id"], args.timeout, args.interval)
    data["request"] = request
    return emit(data, code)


def resolve_editor(args, project, instance):
    candidate = args.editor or os.environ.get("UNITY_EDITOR") or (instance or {}).get("app_path")
    if not candidate:
        raise UsageError("找不到 Unity Editor 可执行文件：用 --editor 或设置 UNITY_EDITOR")
    path = Path(candidate)
    if not path.is_file():
        raise UsageError("Unity Editor 可执行文件不存在: %s" % path)
    return path


def unity_checks_path():
    return sibling_tool("unity_checks.py")


def test_platform(value):
    mapping = {"editmode": "EditMode", "playmode": "PlayMode"}
    return mapping.get(str(value).casefold(), value)


def delegate_nunit(project, report, exit_code):
    tool = unity_checks_path()
    if not tool.is_file():
        raise UsageError("缺少同目录 unity_checks.py，无法解析 NUnit 报告")
    report_rel = rel_posix(report, project)
    command = [sys.executable, "-X", "utf8", str(tool), "tests", "--project", str(project),
               "--report", report_rel, "--exit-code", str(exit_code)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperationalError("调用 unity_checks.py 失败: " + str(error))
    text = (result.stdout or b"").decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except ValueError:
        raise OperationalError("unity_checks.py 输出不是 JSON: " + text[-500:])
    return data, result.returncode


def cmd_tests(args):
    project = require_project(args.project)
    if args.results_only:
        report = Path(args.results_only).resolve()
        if not report.is_file():
            raise UsageError("NUnit 报告不存在: %s" % report)
        data, code = delegate_nunit(project, report, args.exit_code)
        return emit({"ok": code == 0, "mode": "results-only", "project": str(project),
                     "report": str(report), "unity_checks": data}, code)
    platform = test_platform(args.platform)
    instance = editor_instance(project)
    editor = resolve_editor(args, project, instance)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = Path(args.evidence_dir) if args.evidence_dir else \
        project / "Temp" / "ai-unity-editor" / ("tests-%s-%d" % (stamp, os.getpid()))
    evidence = base if args.evidence_dir else unique_dir(base)
    if evidence.exists() and args.evidence_dir:
        raise UsageError("证据目录已存在，拒绝覆盖: %s" % evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    results = evidence / "results.xml"
    log = evidence / "unity.log"
    tmp = evidence / "tmp"
    tmp.mkdir(exist_ok=True)
    command = [str(editor), "-batchmode", "-projectPath", str(project), "-runTests",
               "-testPlatform", platform, "-testResults", str(results), "-logFile", str(log)]
    if args.filter:
        command += ["-testFilter", args.filter]
    data = {"ok": None, "mode": "batchmode", "project": str(project), "editor": str(editor),
            "platform": platform, "evidence_dir": str(evidence), "results": str(results),
            "log": str(log), "command": command}
    if args.dry_run:
        data["ok"] = True
        data["dry_run"] = True
        return emit(data, 0)
    env = os.environ.copy()
    env["TEMP"] = env["TMP"] = str(tmp)
    process = run_checked(command, cwd=project, env=env, timeout=args.timeout,
                          stdout_path=evidence / "process.out",
                          stderr_path=evidence / "process.err")
    data["process"] = process
    if not results.is_file():
        data["ok"] = False
        data["error"] = "Unity 未生成 NUnit 报告（编译失败/Editor 授权/平台依赖/超时）"
        return emit(data, 1)
    parsed, code = delegate_nunit(project, results, process["returncode"])
    data["unity_checks"] = parsed
    data["ok"] = code == 0 and not process["timed_out"]
    if process["timed_out"]:
        data["error"] = "Unity 进程超时，已终止进程树"
        code = 1
    return emit(data, code)


def cmd_player(args):
    exe = Path(args.exe).resolve()
    if not exe.is_file():
        raise UsageError("Player 可执行文件不存在: %s" % exe)
    base = Path(args.evidence_dir) if args.evidence_dir else \
        exe.parent / ("player-evidence-%s-%d" % (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), os.getpid()))
    evidence = base if args.evidence_dir else unique_dir(base)
    if evidence.exists() and args.evidence_dir:
        raise UsageError("证据目录已存在，拒绝覆盖: %s" % evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    command = [str(exe), *list(args.arg or [])]
    data = {"ok": None, "mode": "player", "exe": str(exe), "evidence_dir": str(evidence),
            "stdout": str(evidence / "stdout.log"), "stderr": str(evidence / "stderr.log"),
            "command": command}
    if args.dry_run:
        data.update(ok=True, dry_run=True)
        return emit(data, 0)
    process = run_checked(command, cwd=args.cwd or exe.parent, timeout=args.timeout,
                          stdout_path=evidence / "stdout.log",
                          stderr_path=evidence / "stderr.log")
    data["process"] = process
    data["ok"] = process["returncode"] == 0 and not process["timed_out"]
    if process["timed_out"]:
        data["error"] = "Player 超时，已终止进程树"
    return emit(data, 0 if data["ok"] else 1)


ERROR_PATTERNS = [
    ("compile_error", re.compile(r"\berror CS\d+", re.IGNORECASE)),
    ("shader_error", re.compile(r"\bShader error\b", re.IGNORECASE)),
    ("compilation_failed", re.compile(r"Scripts have compiler errors|Compilation failed", re.IGNORECASE)),
    ("exception", re.compile(r"\b(?:NullReferenceException|AssertionException|InvalidOperationException|"
                             r"ArgumentException|Exception:)", re.IGNORECASE)),
    ("crash", re.compile(r"Crash!!!|Aborting batchmode|Fatal error", re.IGNORECASE)),
    ("test_failed", re.compile(r"Test run failed|\bFAIL\b|failed tests?", re.IGNORECASE)),
]


def cmd_log(args):
    path = Path(args.path).resolve()
    if not path.is_file():
        raise UsageError("日志文件不存在: %s" % path)
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as error:
        raise OperationalError("无法读取日志: " + str(error))
    lines = text.splitlines()
    samples = []
    counts = {}
    for index, line in enumerate(lines, 1):
        for name, pattern in ERROR_PATTERNS:
            if pattern.search(line):
                counts[name] = counts.get(name, 0) + 1
                if len(samples) < args.max_samples:
                    samples.append({"line": index, "kind": name, "text": line.strip()[:300]})
    tail = lines[-args.tail:] if args.tail > 0 else []
    data = {"ok": True, "path": str(path), "lines": len(lines),
            "error_counts": counts, "error_samples": samples,
            "tail": tail, "clean": not counts}
    if args.errors_only:
        data.pop("tail")
    if args.require_clean and counts:
        data["ok"] = False
        data["error"] = "日志包含错误/失败标记，--require-clean 判定失败"
        return emit(data, 1)
    return emit(data, 0)


# ------------------------------------------------------------------ parser ----
def project_parent():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", type=Path, help="Unity 工程根（默认向上查找 ProjectVersion.txt）")
    return parser


def gate_parent():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--gate-root", type=Path, help="gate 根目录（默认 <project>/Temp/UnityEditorGate/<pid>）")
    parser.add_argument("--pid", type=int, help="Editor 进程号（默认读 Library/EditorInstance.json）")
    return parser


def build_parser():
    parser = argparse.ArgumentParser(
        description="Unity Editor 文件协议 gate 驱动器 + 批处理测试/Player/日志取证（只读原始输入，除显式证据目录外不写工程）",
        epilog="退出码: 0=成功；1=运行失败/超时/测试失败；2=用法或前置条件不满足。")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=argparse.ArgumentParser)

    discover = commands.add_parser("discover", parents=[project_parent()],
                                   help="只读发现工程/Editor/EditorInstance/Editor.log")
    discover.add_argument("--editor")
    discover.add_argument("--pid", type=int, help="Editor 进程号（默认读 Library/EditorInstance.json）")
    discover.add_argument("--processes", action="store_true", help="Windows: 列出 Unity.exe 进程")
    discover.set_defaults(func=cmd_discover)

    status = commands.add_parser("status", parents=[gate_parent(), project_parent()],
                                 help="gate 最新 receipt 与陈旧判断")
    status.add_argument("--stale-after", type=float, default=120.0)
    status.set_defaults(func=cmd_status)

    request = commands.add_parser("request", parents=[gate_parent(), project_parent()],
                                  help="写入 gate 请求（不覆盖已有证据）")
    request.add_argument("--id", required=True)
    request.add_argument("--suite", required=True)
    request.add_argument("--type")
    request.add_argument("--method")
    request.add_argument("--arg", action="append")
    request.add_argument("--field", action="append", help="附加字符串字段 key=value")
    request.add_argument("--note")
    request.set_defaults(func=cmd_request)

    wait = commands.add_parser("wait", parents=[gate_parent(), project_parent()],
                               help="等待一次 gate 请求完成")
    wait.add_argument("--id", required=True)
    wait.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    wait.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    wait.set_defaults(func=cmd_wait)

    run = commands.add_parser("run", parents=[gate_parent(), project_parent()],
                              help="request + wait；默认先等 gate ready")
    run.add_argument("--id", required=True)
    run.add_argument("--suite", required=True)
    run.add_argument("--type")
    run.add_argument("--method")
    run.add_argument("--arg", action="append")
    run.add_argument("--field", action="append")
    run.add_argument("--note")
    run.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    run.add_argument("--ready-timeout", type=float, default=120.0)
    run.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    run.add_argument("--no-wait-ready", dest="wait_ready", action="store_false")
    run.set_defaults(func=cmd_run, wait_ready=True)

    tests = commands.add_parser("tests", parents=[project_parent()],
                                help="Unity Test Framework 批处理运行 + NUnit 解析")
    tests.add_argument("--editor")
    tests.add_argument("--platform", default="editmode",
                       help="editmode/playmode 或 Unity testPlatform（如 StandaloneWindows64）")
    tests.add_argument("--filter")
    tests.add_argument("--timeout", type=float, default=1800.0)
    tests.add_argument("--evidence-dir", type=Path)
    tests.add_argument("--dry-run", action="store_true")
    tests.add_argument("--results-only", help="不启动 Unity，只解析已有 NUnit 报告")
    tests.add_argument("--exit-code", type=int, help="配合 --results-only 提供真实进程退出码")
    tests.set_defaults(func=cmd_tests)

    player = commands.add_parser("player", help="启动构建产物并采集 stdio/退出码")
    player.add_argument("--exe", required=True)
    player.add_argument("--arg", action="append")
    player.add_argument("--cwd", type=Path)
    player.add_argument("--timeout", type=float, default=300.0)
    player.add_argument("--evidence-dir", type=Path)
    player.add_argument("--dry-run", action="store_true")
    player.set_defaults(func=cmd_player)

    log = commands.add_parser("log", help="汇总 Unity 日志错误样本与尾部")
    log.add_argument("path")
    log.add_argument("--tail", type=int, default=40)
    log.add_argument("--max-samples", type=int, default=10)
    log.add_argument("--errors-only", action="store_true")
    log.add_argument("--require-clean", action="store_true")
    log.set_defaults(func=cmd_log)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except UsageError as error:
        return emit({"ok": False, "error": str(error)}, 2)
    except OperationalError as error:
        return emit({"ok": False, "error": str(error)}, 1)
    except KeyboardInterrupt:
        return emit({"ok": False, "error": "interrupted"}, 1)
    except Exception as error:  # no traceback in CLI output; unexpected errors stay exit 1
        return emit({"ok": False, "error": "%s: %s" % (type(error).__name__, error)}, 1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
