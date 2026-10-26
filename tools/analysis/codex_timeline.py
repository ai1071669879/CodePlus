# -*- coding: utf-8 -*-
"""
codex_timeline.py —— 阶段 2：定位配置改动的实际生效日（行为突变 + AGENTS.md 内容 sha 变动）
数据源: ~/codex_events_main.jsonl（由 codex_extract.py --prefix main 从原始 rollout jsonl 生成）
口径:
  * 日期一律用 UTC 日（记录 ts 为 UTC；本地=UTC+8），另外单列+8 本地日供对照
  * "主线程" = meta.thread_source == 'user'；子代理 = 'subagent'；审批 = 'guardian_review'
  * spawn/复用/wait 计数用 k=='fc' 的 name
  * 自执行用 k=='item' 且 it=='CommandExecution'
  * AGENTS.md 内容变动用 k=='wstate' 的 agents_md_sha（同 sha 视为未变）
  * 模型档位用 k=='tctx' 的 model / effort
输出: 控制台（分天表 + sha 时间线 + 模型档位时间线）
用法: python -X utf8 ~/codex_timeline.py
"""
import json, os, collections
from datetime import datetime, timedelta

HOME = os.path.expanduser("~")
EV = os.path.join(HOME, "codex_events_main.jsonl")

def utc_date(ts, offset=0):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    return (d + timedelta(hours=offset)).date().isoformat()

meta = {}
rows = []
for line in open(EV, encoding="utf-8"):
    o = json.loads(line)
    k = o["k"]
    if k == "meta":
        meta[o["f"]] = o
    rows.append(o)

print("events =", len(rows), " sessions =", len(meta))

# ---------- 1) 分天：会话数 / spawn / 复用 / wait / 自执行 ----------
day = collections.defaultdict(lambda: collections.Counter())
for o in rows:
    k = o["k"]
    sid = o.get("sid")
    m = meta.get(o["f"]) or {}
    ts = o.get("ts")
    du = utc_date(ts)
    dl = utc_date(ts, 8)
    if k == "meta":
        day[utc_date(o["ts"])]["sess_" + str(o["thread_source"])] += 1
        continue
    if not du:
        continue
    d = day[du]
    d["dl_" + str(dl)] += 0  # 占位
    if k == "fc":
        if m.get("thread_source") == "user":
            d["main_" + str(o["name"])] += 1
    elif k == "item":
        if o["it"] == "CommandExecution":
            d["cmd_" + str(m.get("thread_source"))] += 1
        elif o["it"] == "FileChange":
            d["filechange_" + str(m.get("thread_source"))] += 1
        elif o["it"] == "SubAgentActivity" and o.get("kind") == "started":
            d["subagent_started_" + str(m.get("thread_source"))] += 1
    elif k == "tur":
        d["tur_n"] += 1
        d["tur_in"] += (o.get("in") or 0)
        d["tur_cached"] += (o.get("cached") or 0)
        d["tur_out"] += (o.get("out") or 0)
        d["tur_by_src_" + str(m.get("thread_source")) + "_in"] += (o.get("in") or 0)
    elif k == "tstart":
        d["tstart_" + str(m.get("thread_source"))] += 1
    elif k == "tdone":
        d["tdone_" + str(m.get("thread_source"))] += 1
    elif k == "tabort":
        d["tabort_" + str(m.get("thread_source"))] += 1

print("\n" + "=" * 150)
print("分天表（UTC 日）—— 主线程协作工具调用 / 自执行命令 / token")
print("=" * 150)
hdr = ["date_utc", "sess_user", "sess_sub", "sess_guard",
       "spawn", "send_msg", "followup", "wait_agent", "list_agents",
       "cmd_main", "cmd_sub", "fc_main", "tur_n", "tur_in(M)", "cached%"]
print(" ".join(f"{h:>12}" for h in hdr))
for du in sorted(day):
    d = day[du]
    ini = d["tur_in"]
    cch = (d["tur_cached"] / ini * 100) if ini else 0
    vals = [du, d["sess_user"], d["sess_subagent"], d["sess_guardian_review"],
            d["main_spawn_agent"], d["main_send_message"], d["main_followup_task"],
            d["main_wait_agent"], d["main_list_agents"],
            d["cmd_user"], d["cmd_subagent"], d["filechange_user"],
            d["tur_n"], round(ini / 1e6, 2), round(cch, 1)]
    print(" ".join(f"{str(v):>12}" for v in vals))

# ---------- 2) AGENTS.md 内容 sha 时间线 ----------
print("\n" + "=" * 150)
print("AGENTS.md 内容 sha 变动时间线（k=='wstate'；sha 变 = 配置文本变）")
print("=" * 150)
sha_first = {}
sha_last = {}
sha_dir = collections.defaultdict(collections.Counter)
sha_n = collections.Counter()
for o in rows:
    if o["k"] != "wstate" or not o.get("agents_md_sha"):
        continue
    sha = o["agents_md_sha"]
    ts = o["ts"]
    sha_n[sha] += 1
    sha_dir[sha][str(o.get("agents_md_dir"))] += 1
    if sha not in sha_first or ts < sha_first[sha]:
        sha_first[sha] = ts
    if sha not in sha_last or ts > sha_last[sha]:
        sha_last[sha] = ts
for sha, n in sha_n.most_common():
    print(f"  sha={sha}  first={sha_first[sha]}  last={sha_last[sha]}  n={n}  dirs={dict(sha_dir[sha])}")

print("\n--- 每个 sha 的 AGENTS.md 开头 600 字（去重后展示前 2 个含 multi-agent 字样的）---")
seen = set()
for o in rows:
    if o["k"] != "wstate" or not o.get("agents_md_sha"):
        continue
    sha = o["agents_md_sha"]
    if sha in seen:
        continue
    seen.add(sha)
    head = o.get("agents_md_head") or ""
    print(f"\n### sha={sha} len={o.get('agents_md_len')} dir={o.get('agents_md_dir')}")
    print(head[:600].replace("\r", ""))

# ---------- 3) 模型档位 / multi_agent_version 时间线 ----------
print("\n" + "=" * 150)
print("模型档位与 effort（k=='tctx'），按 UTC 日 × thread_source")
print("=" * 150)
mt = collections.defaultdict(collections.Counter)
for o in rows:
    if o["k"] != "tctx":
        continue
    m = meta.get(o["f"]) or {}  # meta 以 f（源文件相对路径）为键；sid 不是键
    du = utc_date(o["ts"])
    key = (du, str(m.get("thread_source")), str(m.get("agent_role")))
    mt[key][f"{o.get('model')}@{o.get('effort')}"] += 1
for key in sorted(mt):
    print(f"  {key[0]}  {key[1]:15} {str(key[2]):12}  {dict(mt[key])}")

print("\n" + "=" * 150)
print("multi_agent_version（k=='tctx' / meta），按 UTC 日")
print("=" * 150)
mv = collections.defaultdict(collections.Counter)
for o in rows:
    if o["k"] == "tctx":
        du = utc_date(o["ts"])
        mv[du][str(o.get("multi_agent_version"))] += 1
for du in sorted(mv):
    print(f"  {du}  {dict(mv[du])}")

# ---------- 4) agent_role 首次出现 ----------
print("\n" + "=" * 150)
print("子代理角色首次出现时间（按 meta.ts）")
print("=" * 150)
first = {}
for _path, m in meta.items():
    if m.get("thread_source") != "subagent":
        continue
    role = str(m.get("agent_role"))
    ts = m.get("ts")
    if role not in first or ts < first[role][0]:
        first[role] = (ts, m.get("cwd"), m.get("agent_nickname"))
for role in sorted(first):
    print(f"  {role:12} first={first[role][0]} cwd={first[role][1]} nick={first[role][2]}")

# ---------- 5) 主线程会话清单 ----------
main_sessions = sorted(
    (m for m in meta.values() if m.get("thread_source") == "user"),
    key=lambda m: m.get("ts") or "")
print("\n" + "=" * 150)
print(f"主线程会话清单（{len(main_sessions)} 个）")
print("=" * 150)
for m in main_sessions:
    print(f"  {m.get('ts')}  {m.get('sid')}  {m.get('cwd')}  agent_role={m.get('agent_role')} multi_agent_version={m.get('multi_agent_version')}")
