# -*- coding: utf-8 -*-
"""
codex_probe_items.py —— 阶段 0-c：item_completed 的 item 结构 + credits/usage 字段探明
数据源: ~/.codex/sessions/**/rollout-*.jsonl（抽样若干文件）
口径:   只读，打印各 item.type 的样本与键集合；扫描含 credit 关键字的行
用法:   python -X utf8 ~/codex_probe_items.py
"""
import json, os, sys, collections

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, ".codex", "sessions")
meta = json.load(open(os.path.join(HOME, "codex_meta.json"), encoding="utf-8"))

def files(kind, limit):
    xs = [m["abspath"] for m in meta if m["thread_source"] == kind and 300000 < m["size"] < 4000000]
    xs.sort()
    return xs[:limit]

targets = files("user", 3) + files("subagent", 2) + files("guardian_review", 1)

item_keys = collections.defaultdict(collections.Counter)
signal_keys = collections.Counter()
shown = set()
credit_lines = []
top_keys = collections.Counter()
pay_keys = collections.Counter()

for path in targets:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "credit" in line and len(credit_lines) < 3:
                credit_lines.append((os.path.relpath(path, ROOT), line[:1500]))
            try:
                o = json.loads(line)
            except Exception:
                continue
            top_keys[str(o.get("type"))] += 1
            pl = o.get("payload")
            if isinstance(pl, dict):
                for k in pl:
                    pay_keys[k] += 1
                if pl.get("type") == "item_completed":
                    it = pl.get("item") or {}
                    t = str(it.get("type"))
                    for k in it:
                        item_keys[t][k] += 1
                    if t not in shown:
                        shown.add(t)
                        print("=" * 90)
                        print("ITEM TYPE:", t, " file:", os.path.relpath(path, ROOT))
                        s = json.dumps(it, ensure_ascii=False)
                        print(s[:1800])

print("\n== top-level type counts (sample files) ==")
print(dict(top_keys))
print("\n== payload key counts (sample files) ==")
print(dict(pay_keys))
print("\n== item keys by item.type ==")
for t, c in sorted(item_keys.items()):
    print(f"  {t:20} {dict(c)}")
print("\n== credit-bearing lines ==")
if not credit_lines:
    print("  NONE FOUND in sampled files")
for f, s in credit_lines:
    print("  FILE:", f)
    print("  ", s)
