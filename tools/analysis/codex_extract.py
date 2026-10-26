# -*- coding: utf-8 -*-
"""
codex_extract.py —— 把 rollout jsonl 压缩成统一事件流（唯一的原始提取层）
用法:
    python -X utf8 codex_extract.py --help
    python -X utf8 codex_extract.py --root "C:\\Users\\Administrator\\.codex\\sessions" --prefix main
    python -X utf8 codex_extract.py --root "<backup>" --prefix backup
    python -X utf8 codex_extract.py --root "<backup>" --prefix backup --dry-run   # 只扫描不写
数据源: <root>/**/rollout-*.jsonl（默认 ~/.codex/sessions）
口径:
  * 首行 session_meta -> 会话元数据（thread_source / agent_role / cwd / ts_utc）
  * response_item / payload.type == function_call     -> 原生协作工具调用（name 即工具名）
  * response_item / payload.type == custom_tool_call  -> 自由格式 exec（JS 源码），正则数其中 tools.xxx(
  * event_msg / payload.type == item_completed        -> 结构化动作（CommandExecution/FileChange/CollabAgentToolCall/SubAgentActivity/...）
  * event_msg / payload.type == task_started|task_complete|turn_aborted -> turn 生命周期
  * event_msg / payload.type == token_count           -> 累积 token 快照 + 周配额 used_percent
  * token_usage_record                                -> 每响应 usage（权威成本数据）
  * world_state                                       -> agents_md 全文 sha（配置改动证据）
  * turn_context                                      -> 每 turn 的 model / effort / multi_agent_version
  * function_call.arguments.message 为加密串(gAAAAA)，只保留非加密字段
输出:
  ~/codex_events_<prefix>.jsonl    一行一条紧凑事件，k = 记录种类，f = 源文件相对路径
  ~/codex_reports_<prefix>.jsonl   子代理每个 turn 的完整最终报告（不截断，供质量指标用）
  可用 --out / --reports-out 改路径；已存在的输出默认拒绝覆盖（确认覆盖加 --force）。
可重跑: 是（只读原始 jsonl，不依赖任何历史结论；重跑时已有输出需 --force）
退出码: 0=成功；2=参数或输入目录错误；1=输出文件已存在/无法写入
"""
import argparse, json, os, re, sys, hashlib, collections
from datetime import datetime

HOME = os.path.expanduser("~")
NEST_RE = re.compile(r"tools\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")

CURF = [None]
CURSRC = [None]
CURROLE = [None]
CURPATH = [None]


def walk(root):
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.startswith("rollout-") and fn.endswith(".jsonl"):
                yield os.path.join(dirpath, fn)


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def txt_of(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(c["text"] for c in content if isinstance(c, dict) and isinstance(c.get("text"), str))


def emit(w, rec):
    rec["f"] = CURF[0]
    if w is None:  # --dry-run：只统计不写
        return
    w.write(json.dumps(rec, ensure_ascii=False) + "\n")


def build_parser():
    ap = argparse.ArgumentParser(
        description="把 rollout-*.jsonl 压成统一事件流（唯一的原始提取层）",
        epilog="退出码: 0=成功；2=参数或输入目录错误；1=输出文件已存在/无法写入。")
    ap.add_argument("--root", default=os.path.join(HOME, ".codex", "sessions"),
                    help="rollout 根目录（默认 ~/.codex/sessions）")
    ap.add_argument("--prefix", default="main",
                    help="输出文件名前缀，仅允许字母/数字/点/下划线/连字符（默认 main）")
    ap.add_argument("--out", default=None,
                    help="事件流输出路径（默认 ~/codex_events_<prefix>.jsonl）")
    ap.add_argument("--reports-out", dest="reports_out", default=None,
                    help="报告输出路径（默认 ~/codex_reports_<prefix>.jsonl）")
    ap.add_argument("--dry-run", action="store_true", help="只扫描并打印统计，不写任何文件")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    return ap


def main():
    ap = build_parser()
    a = ap.parse_args()
    prefix = a.prefix
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", prefix):
        ap.error("--prefix 只允许字母/数字/点/下划线/连字符: %r" % prefix)
    root = os.path.abspath(a.root)
    if not os.path.isdir(root):
        ap.error("--root 不是目录: %s" % root)
    OUT = os.path.abspath(a.out) if a.out else os.path.join(HOME, f"codex_events_{prefix}.jsonl")
    REPORTS = (os.path.abspath(a.reports_out) if a.reports_out
               else os.path.join(HOME, f"codex_reports_{prefix}.jsonl"))
    if os.path.normcase(OUT) == os.path.normcase(REPORTS):
        ap.error("--out 与 --reports-out 不能指向同一个文件")
    if not a.dry_run and not a.force:
        existing = [p for p in (OUT, REPORTS) if os.path.exists(p)]
        if existing:
            for p in existing:
                print("ERROR: 输出文件已存在: %s" % p, file=sys.stderr)
            print("       确认覆盖请加 --force；只检查不写请用 --dry-run", file=sys.stderr)
            return 1

    paths = sorted(walk(root))
    stats = collections.Counter()
    rw = None
    w = None
    try:
        if not a.dry_run:
            rw = open(REPORTS, "w", encoding="utf-8")
            w = open(OUT, "w", encoding="utf-8")
    except OSError as e:
        if rw is not None:
            rw.close()
        print("ERROR: 输出文件无法写入: %s" % e, file=sys.stderr)
        return 1
    try:
        for fi, path in enumerate(paths):
            rel = os.path.relpath(path, root)
            CURF[0] = rel
            CURSRC[0] = CURROLE[0] = CURPATH[0] = None
            sid = None
            try:
                f = open(path, "r", encoding="utf-8", errors="replace")
            except Exception:
                stats["open_fail"] += 1
                continue
            first = True
            with f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        stats["badjson"] += 1
                        continue
                    top = o.get("type")
                    ts = parse_ts(o.get("timestamp"))
                    ts_s = ts.isoformat() if ts else None
                    pl = o.get("payload")
                    if not isinstance(pl, dict):
                        pl = {}
                    if first:
                        first = False
                        sid = pl.get("id") or o.get("id")
                        src = pl.get("source")
                        sub = {}
                        if isinstance(src, dict):
                            sub = src.get("subagent") or {}
                        if not isinstance(sub, dict):
                            sub = {}
                        spawn = sub.get("thread_spawn") or {}
                        if not isinstance(spawn, dict):
                            spawn = {}
                        CURSRC[0] = pl.get("thread_source")
                        CURROLE[0] = spawn.get("agent_role") or pl.get("agent_role")
                        CURPATH[0] = spawn.get("agent_path") or pl.get("agent_path")
                        emit(w, {
                            "k": "meta", "sid": sid, "ts": ts_s,
                            "date_utc": ts.date().isoformat() if ts else None,
                            "thread_source": pl.get("thread_source"),
                            "cwd": pl.get("cwd"),
                            "originator": pl.get("originator"),
                            "cli_version": pl.get("cli_version"),
                            "agent_role": CURROLE[0],
                            "agent_nickname": spawn.get("agent_nickname") or pl.get("agent_nickname"),
                            "agent_path": CURPATH[0],
                            "parent_thread_id": spawn.get("parent_thread_id") or pl.get("parent_thread_id"),
                            "depth": spawn.get("depth"),
                            "session_id": pl.get("session_id"),
                            "multi_agent_version": pl.get("multi_agent_version"),
                            "model_provider": pl.get("model_provider"),
                        })
                        stats["meta"] += 1
                        continue
                    if top == "turn_context":
                        emit(w, {"k": "tctx", "sid": sid, "ts": ts_s,
                                 "model": pl.get("model"), "effort": pl.get("effort"),
                                 "multi_agent_version": pl.get("multi_agent_version"),
                                 "collaboration_mode": pl.get("collaboration_mode"),
                                 "approval_policy": pl.get("approval_policy"),
                                 "approvals_reviewer": pl.get("approvals_reviewer")})
                        stats["tctx"] += 1
                    elif top == "world_state":
                        st = pl.get("state") if isinstance(pl.get("state"), dict) else {}
                        am = st.get("agents_md") if isinstance(st.get("agents_md"), dict) else None
                        rec = {"k": "wstate", "sid": sid, "ts": ts_s, "full": bool(pl.get("full")),
                               "state_keys": sorted(st.keys())}
                        if am and isinstance(am.get("text"), str):
                            raw = am["text"].encode("utf-8", "replace")
                            rec["agents_md_sha"] = hashlib.sha1(raw).hexdigest()[:12]
                            rec["agents_md_len"] = len(raw)
                            rec["agents_md_dir"] = am.get("directory")
                            rec["agents_md_head"] = am["text"][:400]
                        emit(w, rec)
                        stats["wstate"] += 1
                    elif top == "token_usage_record":
                        u = pl.get("usage") or {}
                        tu = pl.get("turn_token_usage") or {}
                        emit(w, {"k": "tur", "sid": sid, "ts": ts_s,
                                 "turn_id": pl.get("turn_id"), "root_turn_id": pl.get("root_turn_id"),
                                 "in": u.get("input_tokens"), "cached": u.get("cached_input_tokens"),
                                 "cw": u.get("cache_write_input_tokens"), "out": u.get("output_tokens"),
                                 "reason": u.get("reasoning_output_tokens"), "tot": u.get("total_tokens"),
                                 "turn_in": tu.get("input_tokens"), "turn_cached": tu.get("cached_input_tokens"),
                                 "turn_out": tu.get("output_tokens")})
                        stats["tur"] += 1
                    elif top == "event_msg":
                        pt = pl.get("type")
                        if pt == "task_started":
                            ta = pl.get("turn_attribution") or {}
                            emit(w, {"k": "tstart", "sid": sid, "ts": ts_s, "turn_id": pl.get("turn_id"),
                                     "root_turn_id": pl.get("root_turn_id"), "trigger": ta.get("turn_trigger"),
                                     "collab_mode": pl.get("collaboration_mode_kind"),
                                     "ctx_window": pl.get("model_context_window")})
                            stats["tstart"] += 1
                        elif pt == "task_complete":
                            lm = pl.get("last_agent_message")
                            if rw is not None and CURSRC[0] == "subagent" and isinstance(lm, str) and lm.strip():
                                rw.write(json.dumps({"f": CURF[0], "sid": sid, "ts": ts_s,
                                                     "role": CURROLE[0], "agent_path": CURPATH[0],
                                                     "turn_id": pl.get("turn_id"), "text": lm},
                                                    ensure_ascii=False) + "\n")
                                stats["report"] += 1
                            emit(w, {"k": "tdone", "sid": sid, "ts": ts_s, "turn_id": pl.get("turn_id"),
                                     "root_turn_id": pl.get("root_turn_id"),
                                     "duration_ms": pl.get("duration_ms"),
                                     "ttft_ms": pl.get("time_to_first_token_ms"),
                                     "last_msg": (lm[:400] if isinstance(lm, str) else None)})
                            stats["tdone"] += 1
                        elif pt == "turn_aborted":
                            emit(w, {"k": "tabort", "sid": sid, "ts": ts_s, "turn_id": pl.get("turn_id"),
                                     "root_turn_id": pl.get("root_turn_id"), "reason": pl.get("reason"),
                                     "duration_ms": pl.get("duration_ms")})
                            stats["tabort"] += 1
                        elif pt == "token_count":
                            info = pl.get("info") or {}
                            tt = info.get("total_token_usage") or {}
                            lt = info.get("last_token_usage") or {}
                            rl = pl.get("rate_limits") or {}
                            pri = rl.get("primary") or {}
                            cre = rl.get("credits") or {}
                            emit(w, {"k": "tokc", "sid": sid, "ts": ts_s,
                                     "tot_in": tt.get("input_tokens"), "tot_cached": tt.get("cached_input_tokens"),
                                     "tot_out": tt.get("output_tokens"),
                                     "last_in": lt.get("input_tokens"), "last_cached": lt.get("cached_input_tokens"),
                                     "last_out": lt.get("output_tokens"),
                                     "ctx_window": info.get("model_context_window"),
                                     "used_pct": pri.get("used_percent"), "plan": rl.get("plan_type"),
                                     "credits_has": cre.get("has_credits"), "credits_bal": cre.get("balance")})
                            stats["tokc"] += 1
                        elif pt == "item_completed":
                            it = pl.get("item")
                            if not isinstance(it, dict):
                                continue
                            t = it.get("type")
                            base = {"k": "item", "sid": sid, "ts": ts_s, "it": t, "iid": it.get("id"),
                                    "turn_id": pl.get("turn_id")}
                            if t == "CommandExecution":
                                cmd = it.get("command")
                                cs = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                                base.update({"status": it.get("status"), "exit": it.get("exit_code"),
                                             "cwd": it.get("cwd"), "src": it.get("source"), "cmd": cs[:500]})
                            elif t == "FileChange":
                                ch = it.get("changes") if isinstance(it.get("changes"), dict) else {}
                                base.update({"status": it.get("status"), "nfiles": len(ch),
                                             "paths": list(ch.keys())[:50]})
                            elif t == "CollabAgentToolCall":
                                base.update({"tool": it.get("tool"), "status": it.get("status"),
                                             "receivers": it.get("receiver_agents")})
                            elif t == "SubAgentActivity":
                                base.update({"kind": it.get("kind"), "model": it.get("model"),
                                             "effort": it.get("reasoning_effort"),
                                             "agent_path": it.get("agent_path"),
                                             "agent_thread_id": it.get("agent_thread_id")})
                            elif t == "McpToolCall":
                                base.update({"server": it.get("server"), "tool": it.get("tool"),
                                             "status": it.get("status")})
                            elif t == "AgentMessage":
                                base.update({"text": txt_of(it.get("content"))[:4000], "phase": it.get("phase")})
                            elif t == "UserMessage":
                                base.update({"text": txt_of(it.get("content"))[:1500]})
                            else:
                                base.update({"other_keys": sorted(it.keys())})
                            emit(w, base)
                            stats["item"] += 1
                        elif pt == "agent_message":
                            emit(w, {"k": "amsg", "sid": sid, "ts": ts_s,
                                     "author": pl.get("author"), "recipient": pl.get("recipient"),
                                     "text": txt_of(pl.get("content"))[:4000]})
                            stats["amsg"] += 1
                        elif pt == "thread_settings_applied":
                            tsx = pl.get("thread_settings") or {}
                            emit(w, {"k": "tset", "sid": sid, "ts": ts_s,
                                     "model": tsx.get("model"), "approval_policy": tsx.get("approval_policy"),
                                     "approvals_reviewer": tsx.get("approvals_reviewer"),
                                     "service_tier": tsx.get("service_tier")})
                            stats["tset"] += 1
                    elif top == "response_item":
                        pt = pl.get("type")
                        if pt == "function_call":
                            args = pl.get("arguments")
                            try:
                                a = json.loads(args) if isinstance(args, str) else (args or {})
                            except Exception:
                                a = {}
                            if not isinstance(a, dict):
                                a = {}
                            small = {}
                            for kk in ("task_name", "agent_type", "target", "fork_turns", "timeout"):
                                if kk in a:
                                    v = a[kk]
                                    if isinstance(v, str) and v.startswith("gAAAAA"):
                                        v = "<encrypted>"
                                    small[kk] = v if not isinstance(v, str) else v[:120]
                            emit(w, {"k": "fc", "sid": sid, "ts": ts_s, "name": pl.get("name"),
                                     "ns": pl.get("namespace"), "status": pl.get("status"), "args": small})
                            stats["fc"] += 1
                        elif pt == "custom_tool_call":
                            inp = pl.get("input")
                            if not isinstance(inp, str):
                                inp = json.dumps(inp, ensure_ascii=False) if inp is not None else ""
                            nst = collections.Counter(NEST_RE.findall(inp))
                            emit(w, {"k": "ctc", "sid": sid, "ts": ts_s, "name": pl.get("name"),
                                     "status": pl.get("status"), "nest": dict(nst),
                                     "n_nest": sum(nst.values()), "head": inp[:200]})
                            stats["ctc"] += 1
                    stats["lines"] += 1
            if (fi + 1) % 100 == 0:
                print(f"  ...{fi + 1}/{len(paths)} files", flush=True)
    finally:
        if w is not None:
            w.close()
        if rw is not None:
            rw.close()
    print("STATS:", dict(stats))
    if a.dry_run:
        print("DRY-RUN: 未写入文件（事件流 -> %s，报告 -> %s）" % (OUT, REPORTS))
    else:
        print("WROTE", OUT, os.path.getsize(OUT), "bytes")
        print("WROTE", REPORTS, os.path.getsize(REPORTS), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
