# -*- coding: utf-8 -*-
"""
codex_probe_meta.py  —— 阶段 0-a：会话清单探明（只读首行）
数据源: <root>/**/rollout-*.jsonl（默认 ~/.codex/sessions），每个文件首行为 session_meta
口径:   逐文件读第 1 行 JSON，提取 payload.{id,thread_source,cwd,timestamp,source}
        ts_utc 取自 timestamp 字段；ts_local = ts_utc + 8h（本机 Asia/Shanghai）
输出:   ~/codex_meta.json  (list of dict) + 控制台摘要（可用 --out 改路径）
可重跑: 是（不依赖任何历史中间结论；已有输出默认拒绝覆盖，需 --force）
用法:
    python -X utf8 codex_probe_meta.py --help
    python -X utf8 codex_probe_meta.py
    python -X utf8 codex_probe_meta.py --root <dir> --out <file> [--dry-run] [--force]
退出码: 0=成功；2=参数或输入目录错误；1=输出文件已存在/无法写入
"""
import argparse, json, os, sys, collections
from datetime import datetime, timedelta

HOME = os.path.expanduser("~")


def build_parser():
    ap = argparse.ArgumentParser(description="阶段 0-a：只读每个 rollout 文件首行，列出会话清单")
    ap.add_argument("--root", default=os.path.join(HOME, ".codex", "sessions"),
                    help="rollout 根目录（默认 ~/.codex/sessions）")
    ap.add_argument("--out", default=os.path.join(HOME, "codex_meta.json"),
                    help="输出 JSON 路径（默认 ~/codex_meta.json）")
    ap.add_argument("--dry-run", action="store_true", help="只打印摘要，不写文件")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    return ap


def walk(root):
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.startswith("rollout-") and fn.endswith(".jsonl"):
                yield os.path.join(dirpath, fn)


def parse_ts(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def main():
    ap = build_parser()
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    out = os.path.abspath(a.out)
    if not os.path.isdir(root):
        ap.error("--root 不是目录: %s" % root)
    if not a.dry_run and os.path.exists(out) and not a.force:
        print("ERROR: 输出文件已存在: %s" % out, file=sys.stderr)
        print("       确认覆盖请加 --force；只检查不写请用 --dry-run", file=sys.stderr)
        return 1

    recs = []
    bad = []
    for path in sorted(walk(root)):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                first = f.readline()
        except Exception as e:
            bad.append((path, "open:" + str(e)))
            continue
        try:
            o = json.loads(first)
        except Exception as e:
            bad.append((path, "json:" + str(e)))
            continue
        pl = o.get("payload") or {}
        src = pl.get("source")
        if not isinstance(src, dict):
            src = {"_value": src}
        sub = src.get("subagent")
        if not isinstance(sub, dict):
            sub = {"_value": sub} if sub is not None else {}
        spawn = (sub.get("thread_spawn") or {})
        ts = parse_ts(pl.get("timestamp") or o.get("timestamp"))
        recs.append({
            "file": os.path.relpath(path, root),
            "abspath": path,
            "size": os.path.getsize(path),
            "record_type": o.get("type"),
            "ts_utc": ts.isoformat() if ts else None,
            "date_utc": ts.date().isoformat() if ts else None,
            "date_local": (ts + timedelta(hours=8)).date().isoformat() if ts else None,
            "thread_source": pl.get("thread_source"),
            "id": pl.get("id"),
            "cwd": pl.get("cwd"),
            "originator": pl.get("originator"),
            "cli_version": pl.get("cli_version"),
            "model_provider": pl.get("model_provider"),
            "source_keys": sorted(src.keys()),
            "subagent_keys": sorted(sub.keys()),
            "spawn_keys": sorted(spawn.keys()),
            "agent_role": spawn.get("agent_role"),
            "agent_nickname": spawn.get("agent_nickname"),
            "spawn_parent_thread_id": spawn.get("parent_thread_id"),
            "spawn_depth": spawn.get("depth"),
            "subagent_other": {k: v for k, v in sub.items() if k != "thread_spawn"},
        })

    if a.dry_run:
        print("DRY-RUN: 未写入 %s（解析 %d 个文件）" % (out, len(recs)))
    else:
        try:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(recs, f, ensure_ascii=False, indent=1)
        except OSError as e:
            print("ERROR: 无法写入 %s: %s" % (out, e), file=sys.stderr)
            return 1

    print("files_parsed =", len(recs), " bad =", len(bad))
    for b in bad[:10]:
        print("BAD:", b)

    print("\n== thread_source distribution ==")
    for k, v in collections.Counter(r["thread_source"] for r in recs).most_common():
        print(f"  {k!r:22} {v}")

    print("\n== agent_role distribution (subagent sessions) ==")
    for k, v in collections.Counter(r["agent_role"] for r in recs if r["thread_source"] == "subagent").most_common():
        print(f"  {k!r:22} {v}")

    print("\n== nickname distribution ==")
    for k, v in collections.Counter(r["agent_nickname"] for r in recs).most_common(30):
        print(f"  {k!r:30} {v}")

    print("\n== date_utc distribution ==")
    for k, v in sorted(collections.Counter(r["date_utc"] for r in recs).items()):
        print(f"  {k}  {v}")

    print("\n== source keys (union) ==")
    ks = collections.Counter()
    for r in recs:
        for k in r["source_keys"]:
            ks[k] += 1
    print(" ", dict(ks))
    print("\n== spawn keys (union) ==")
    ks = collections.Counter()
    for r in recs:
        for k in r["spawn_keys"]:
            ks[k] += 1
    print(" ", dict(ks))
    print("\n== subagent non-spawn keys (union) ==")
    ks = collections.Counter()
    for r in recs:
        for k in r["subagent_keys"]:
            if k != "thread_spawn":
                ks[k] += 1
    print(" ", dict(ks))

    print("\n== cwd distribution (top 25) ==")
    for k, v in collections.Counter(r["cwd"] for r in recs).most_common(25):
        print(f"  {str(k):70} {v}")

    print("\n== record_type of first line ==")
    print(" ", dict(collections.Counter(r["record_type"] for r in recs)))

    print("\n== example subagent_other values (5) ==")
    n = 0
    for r in recs:
        if r["subagent_other"] and n < 5:
            print("  ", r["subagent_other"])
            n += 1
    if not a.dry_run:
        print("\nWROTE", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
