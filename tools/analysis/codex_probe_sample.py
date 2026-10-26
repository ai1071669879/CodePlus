# -*- coding: utf-8 -*-
"""
codex_probe_sample.py —— 阶段 0-b：事件行结构探明（抽样若干文件，不做全量统计）
数据源: ~/.codex/sessions/**/rollout-*.jsonl
口径:   逐行 json.loads，统计 type / payload.type / payload.name 的出现次数，
        并打印 function_call、token_usage 类事件的原始结构样本
输出:   控制台
用法:   python -X utf8 ~/codex_probe_sample.py [每类抽样文件数]
"""
import json, os, sys, collections, random

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, ".codex", "sessions")
meta = json.load(open(os.path.join(HOME, "codex_meta.json"), encoding="utf-8"))

def pick(kind, n):
    xs = [m["abspath"] for m in meta if m["thread_source"] == kind]
    xs.sort()
    random.seed(7)
    return random.sample(xs, min(n, len(xs)))

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
samples = [("user", p) for p in pick("user", N)] + [("subagent", p) for p in pick("subagent", N)] + [("guardian_review", p) for p in pick("guardian_review", N)]

for kind, path in samples:
    print("=" * 100)
    print(f"[{kind}] {os.path.relpath(path, ROOT)}  size={os.path.getsize(path)}")
    top_types = collections.Counter()
    pay_types = collections.Counter()
    names = collections.Counter()
    nlines = 0
    shown_fc = 0
    shown_other = collections.Counter()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            nlines += 1
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                top_types["<BADJSON>"] += 1
                continue
            t = o.get("type")
            top_types[str(t)] += 1
            pl = o.get("payload")
            if isinstance(pl, dict):
                pt = str(pl.get("type"))
                pay_types[pt] += 1
                if pt == "function_call":
                    names[str(pl.get("name"))] += 1
                    if shown_fc < 2:
                        s = json.dumps(pl, ensure_ascii=False)
                        print("  FC SAMPLE:", s[:900])
                        shown_fc += 1
                elif pt not in ("function_call_output", "reasoning", "message") and shown_other[pt] < 1:
                    shown_other[pt] += 1
                    s = json.dumps(pl, ensure_ascii=False)
                    print(f"  PL.{pt} SAMPLE:", s[:1200])
            else:
                if shown_other[str(t) + "/<nopayload>"] < 1:
                    shown_other[str(t) + "/<nopayload>"] += 1
                    print("  TOP SAMPLE:", json.dumps(o, ensure_ascii=False)[:800])
    print("  lines =", nlines)
    print("  top-level type:", dict(top_types))
    print("  payload.type  :", dict(pay_types))
    print("  function_call names:", dict(names))
