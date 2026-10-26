# -*- coding: utf-8 -*-
"""
codex_selfcheck.py —— 口径自检：用互不相同的两条记录路径对同一批动作交叉验证
数据源: ~/codex_events_main.jsonl（由 codex_extract.py 从原始 rollout jsonl 生成）
口径:  同一批动作会在日志里出现两次：response_item(工具调用) 与 event_msg/item_completed(UI 事件)。
        两者必须相等；不相等就说明某一侧漏抓。token 侧则校验 sum(usage.in) == 最后一个 turn 累计。
输出: 5 组交叉校验数字 + 结论
用法: python -X utf8 ~/codex_selfcheck.py
"""
import json, os, collections

HOME = os.path.expanduser("~")
EV = os.path.join(HOME, "codex_events_main.jsonl")

meta, rows = {}, []
for line in open(EV, encoding="utf-8"):
    o = json.loads(line)
    if o["k"] == "meta":
        meta[o["f"]] = o
    else:
        rows.append(o)

src = {f: (m.get("thread_source") or "?") for f, m in meta.items()}


def c(pred):
    n = 0
    for o in rows:
        if pred(o):
            n += 1
    return n


print("=" * 90)
print("自检 1：spawn_agent 的两种记录")
a = c(lambda o: o["k"] == "fc" and o["name"] == "spawn_agent")
b = c(lambda o: o["k"] == "item" and o["it"] == "SubAgentActivity" and o.get("kind") == "started")
print(f"  response_item/function_call  spawn_agent   = {a}")
print(f"  event_msg/item_completed      SubAgentActivity.started = {b}")
print(f"  {'一致' if a == b else '不一致！'}")

print("\n自检 2：wait_agent 的两种记录")
a = c(lambda o: o["k"] == "fc" and o["name"] == "wait_agent")
b = c(lambda o: o["k"] == "item" and o["it"] == "CollabAgentToolCall" and o.get("tool") == "wait")
print(f"  function_call wait_agent = {a} ; CollabAgentToolCall.wait = {b} ; {'一致' if a == b else '不一致！'}")

print("\n自检 3：shell 执行的两种记录（应接近但不必相等）")
nested = sum((o.get("nest") or {}).get("exec_command", 0) for o in rows if o["k"] == "ctc")
items = c(lambda o: o["k"] == "item" and o["it"] == "CommandExecution")
nested_user = sum((o.get("nest") or {}).get("exec_command", 0) for o in rows if o["k"] == "ctc" and src[o["f"]] == "user")
print(f"  exec 的 JS 里嵌套 tools.exec_command 总数 = {nested}（其中主线程 {nested_user}）")
print(f"  item_completed 的 CommandExecution 总数   = {items}")

print("\n自检 4：turn 生命周期闭合")
ts = collections.Counter()
for o in rows:
    if o["k"] == "tstart":
        ts["tstart"] += 1
    elif o["k"] == "tdone":
        ts["tdone"] += 1
    elif o["k"] == "tabort":
        ts["tabort"] += 1
print(f"  {dict(ts)}  -> 未闭合 = {ts['tstart'] - ts['tdone'] - ts['tabort']}")

print("\n自检 5：token 语义（sum(usage.in) 必须等于该 turn 最后一条 turn_in）")
byturn = collections.defaultdict(list)
for o in rows:
    if o["k"] == "tur":
        byturn[(o["f"], o.get("turn_id"))].append(o)
bad = 0
checked = 0
for k, recs in byturn.items():
    s = sum(x.get("in") or 0 for x in recs)
    last = recs[-1].get("turn_in")
    if last is None:
        continue
    checked += 1
    if s != last:
        bad += 1
print(f"  检查 {checked} 个 (文件,turn) -> 不相等 {bad} 个  {'（口径成立）' if bad == 0 else '（需检查）'}")
print(f"  全库 sum(usage.in) = {sum(o.get('in') or 0 for o in rows if o['k']=='tur'):,}")
print(f"  全库 sum(usage.cached) = {sum(o.get('cached') or 0 for o in rows if o['k']=='tur'):,}")
