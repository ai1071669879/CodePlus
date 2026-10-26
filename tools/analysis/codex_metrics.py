# -*- coding: utf-8 -*-
"""
codex_metrics.py —— 分段指标：A 委派结构 / B 成本 / C 质量 / D 返工
用法:
  python -X utf8 codex_metrics.py --prefix main          # 主数据（~/.codex/sessions，2026-10-14~10-24）
  python -X utf8 codex_metrics.py --prefix backup        # 备份数据（2026-06-05~09-15，方案前）
  python -X utf8 codex_metrics.py --help                 # 查看参数（--prefix 只接受 main / backup）
数据源: ~/codex_events_<prefix>.jsonl（由 codex_extract.py 生成）+ ~/codex_reports_<prefix>.jsonl（子代理完整报告）
口径:
  * 会话身份 = 日志文件 f（有 6 个 sid 存在续接文件，按 sid 合并会把后段线程错绑到首日）
  * 分段 = 按该文件首行 timestamp（UTC）落段，落段后该会话全部事件算入该段
      main: S1 10-14T00:00Z~10-18T00:00Z / S2 10-19T02:33Z~10-22T00:00Z / S3 2026-10-22T02:29Z~
      backup: P0 全部（2026-06-05~09-15）
  * 日期默认 UTC；本地 = UTC+8
  * 工具计数用 k=='fc'；自执行 = k=='item' 且 it=='CommandExecution'（每次一条真实 shell 命令）
  * 成本 = k=='tur'（token_usage_record）。已实测 usage 为单响应用量、turn_token_usage 为该 turn 累计；
    sum(usage.input_tokens) 即计费输入总量（校验：sum(usage.in) == 最后一个 turn_token_usage.in）
输出: 控制台 + ~/codex_metrics_<prefix>.json
"""
import json, os, re, sys, argparse, collections, hashlib, statistics
from datetime import datetime, timedelta

HOME = os.path.expanduser("~")

SEGSETS = {
    "main": [
        ("S1", "基线 10-14~10-17", "2026-10-14T00:00:00+00:00", "2026-10-18T00:00:00+00:00"),
        ("S2", "改写后 10-19~10-21", "2026-10-19T02:33:00+00:00", "2026-10-22T00:00:00+00:00"),
        ("S3", "近期 10-22~10-24", "2026-10-22T02:29:00+00:00", "2026-10-30T00:00:00+00:00"),
    ],
    "backup": [
        ("P0", "方案前 06-05~09-15", "2026-06-01T00:00:00+00:00", "2026-09-16T00:00:00+00:00"),
    ],
}
ALLSEG_ORDER = ["S1", "S2", "S3", "S0", "P0"]


def pct(a, b):
    return (a / b * 100) if b else None


def main():
    ap = argparse.ArgumentParser(
        description="按分段计算 A 委派结构 / B 成本 / C 质量 / D 返工（数据源由 codex_extract.py 生成）")
    ap.add_argument("--prefix", default="main", choices=sorted(SEGSETS),
                    help="main=方案期主数据（默认），backup=方案前备份数据")
    a = ap.parse_args()
    prefix = a.prefix
    EV = os.path.join(HOME, f"codex_events_{prefix}.jsonl")
    REPS = os.path.join(HOME, f"codex_reports_{prefix}.jsonl")
    OUT = os.path.join(HOME, f"codex_metrics_{prefix}.json")
    if not os.path.isfile(EV):
        print(f"ERROR: 缺少输入文件 {EV}", file=sys.stderr)
        print(f"       请先运行: python -X utf8 codex_extract.py --prefix {prefix}", file=sys.stderr)
        sys.exit(2)
    SEGMENTS = SEGSETS[prefix]
    names = [s[0] for s in SEGMENTS]
    print(f"### prefix={prefix}  segments={names}")

    def seg_of(ts):
        if not ts:
            return "S0"
        d = datetime.fromisoformat(ts)
        for code, name, lo, hi in SEGMENTS:
            if datetime.fromisoformat(lo) <= d < datetime.fromisoformat(hi):
                return code
        return "S0"

    meta, rows = {}, []
    for line in open(EV, encoding="utf-8"):
        o = json.loads(line)
        if o["k"] == "meta":
            meta[o["f"]] = o
        else:
            rows.append(o)
    seg = {f: seg_of(m.get("ts")) for f, m in meta.items()}
    src = {f: (m.get("thread_source") or "?") for f, m in meta.items()}
    role = {f: (m.get("agent_role") or "-") for f, m in meta.items()}
    cwd = {f: (m.get("cwd") or "?") for f, m in meta.items()}
    segs = [s[0] for s in SEGMENTS] + ["S0"]

    # ---------- 0 工具名清单 ----------
    inv = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for o in rows:
        s = src[o["f"]]
        if o["k"] == "fc":
            inv[s]["function_call"][str(o["name"])] += 1
        elif o["k"] == "ctc":
            inv[s]["custom_tool_call"][str(o["name"])] += 1
            for n, c in (o.get("nest") or {}).items():
                inv[s]["nested_tools"][n] += c
        elif o["k"] == "item":
            inv[s]["item_types"][str(o["it"])] += 1
    print("\n" + "=" * 120)
    print("0. 工具名实际取值（先打印名字，再计数）")
    print("=" * 120)
    for s in ("user", "subagent", "guardian_review"):
        if not inv[s]["function_call"] and not inv[s]["item_types"]:
            continue
        print(f"\n[{s}]")
        for kk in ("function_call", "custom_tool_call", "nested_tools", "item_types"):
            print(f"  {kk:16}: {dict(inv[s][kk])}")

    # ---------- 1 样本量 ----------
    ss = {s: collections.Counter() for s in ALLSEG_ORDER}
    for f, m in meta.items():
        s = seg[f]
        ss[s]["files"] += 1
        ss[s][src[f]] += 1
        ss[s]["cwd_" + str(cwd[f])] += 1
    print("\n" + "=" * 120)
    print("1. 分段样本量（会话 = 日志文件数）")
    print("=" * 120)
    for s, name, lo, hi in SEGMENTS + [("S0", "边界外残余", "", "")]:
        d = ss[s]
        if not d["files"]:
            continue
        print(f"  {s} {name:18} 文件={d['files']:3} 主线程={d['user']:3} 子代理={d['subagent']:3} "
              f"审批={d['guardian_review']:3} | RxToolkits={d['cwd_D:\\ProjRx\\RxToolkits']} "
              f"seawar={d['cwd_D:\\GYYX\\seawar']} 其它={d['files'] - d['cwd_D:\\ProjRx\\RxToolkits'] - d['cwd_D:\\GYYX\\seawar']}")

    # ---------- 2 A 委派结构 ----------
    A = {s: collections.Counter() for s in ALLSEG_ORDER}
    Asub = {s: collections.Counter() for s in ALLSEG_ORDER}
    for o in rows:
        f, s = o["f"], seg[o["f"]]
        if src[f] == "user":
            c = A[s]
            if o["k"] == "fc":
                nm = str(o["name"])
                if nm == "spawn_agent":
                    c["spawn"] += 1
                elif nm in ("send_message", "followup_task"):
                    c["reuse"] += 1
                    c[nm] += 1
                elif nm in ("wait_agent", "wait"):
                    c["idle"] += 1
                    c[nm] += 1
                elif nm == "list_agents":
                    c["list_agents"] += 1
                elif nm == "sleep":
                    c["sleep"] += 1
                else:
                    c["other_" + nm] += 1
            elif o["k"] == "item":
                if o["it"] == "CommandExecution":
                    c["exec_main"] += 1
                elif o["it"] == "FileChange":
                    c["filechange_items"] += 1
                    c["filechange_files"] += o.get("nfiles") or 0
                elif o["it"] == "CollabAgentToolCall":
                    c["item_collab_" + str(o.get("tool"))] += 1
                elif o["it"] == "SubAgentActivity":
                    c["item_subagent_" + str(o.get("kind"))] += 1
        elif src[f] == "subagent":
            c = Asub[s]
            if o["k"] == "item":
                if o["it"] == "CommandExecution":
                    c["exec_sub"] += 1
                elif o["it"] == "FileChange":
                    c["filechange_items"] += 1
                    c["filechange_files"] += o.get("nfiles") or 0
                elif o["it"] == "AgentMessage":
                    c["agent_message_items"] += 1
            elif o["k"] == "ctc":
                c["apply_patch"] += (o.get("nest") or {}).get("apply_patch", 0)

    print("\n" + "=" * 120)
    print("2. A 委派结构（主线程会话内计数；spawn=新建子代理，reuse=对已存在代理复用，空转=wait_agent+wait）")
    print("=" * 120)
    hdr = ["seg", "spawn", "send_msg", "followup", "reuse", "wait_agent", "wait", "sleep",
           "list_agents", "exec_main", "委派占比", "复用/spawn", "空转/spawn"]
    print(" | ".join(f"{h:>11}" for h in hdr))
    for s, name, lo, hi in SEGMENTS:
        c = A[s]
        sp, ex = c["spawn"], c["exec_main"]
        reuse = c["reuse"]
        print(" | ".join(f"{str(v):>11}" for v in [
            s, sp, c["send_message"], c["followup_task"], reuse, c["wait_agent"], c["wait"], c["sleep"],
            c["list_agents"], ex,
            f"{sp/(sp+ex)*100:.2f}%" if (sp + ex) else "-",
            f"{reuse/sp:.2f}" if sp else "-",
            f"{c['idle']/sp:.2f}" if sp else "-"]))
        print(f"    交叉校验（同批动作的 UI 事件副本）：CollabAgentToolCall.wait={c.get('item_collab_wait',0)}  "
              f"SubAgentActivity.started={c.get('item_subagent_started',0)}（应等于 spawn={sp}）")
    for s, name, lo, hi in SEGMENTS:
        print(f"  子代理会话 {s}: {dict(Asub[s])}")
        fs, fm = Asub[s]["filechange_items"], A[s]["filechange_items"]
        tot = fs + fm
        print(f"    FileChange 子代理占比(项)={pct(fs,tot) if tot else 0:.2f}%  "
              f"(文件数)={pct(Asub[s]['filechange_files'], Asub[s]['filechange_files']+A[s]['filechange_files']) or 0:.2f}%  "
              f"[sub {fs} 项 / main {fm} 项]")

    # ---------- 3 B 成本 ----------
    B = {s: collections.defaultdict(collections.Counter) for s in ALLSEG_ORDER}
    turns = {s: collections.Counter() for s in ALLSEG_ORDER}
    resp_in = {s: collections.defaultdict(list) for s in ALLSEG_ORDER}
    turn_acc = collections.Counter()
    for o in rows:
        f, s = o["f"], seg[o["f"]]
        if o["k"] == "tur":
            t = src[f]
            B[s][t]["resp"] += 1
            B[s][t]["in"] += o.get("in") or 0
            B[s][t]["cached"] += o.get("cached") or 0
            B[s][t]["out"] += o.get("out") or 0
            resp_in[s][t].append(o.get("in") or 0)
            turn_acc[(s, t, o.get("turn_id"))] += (o.get("in") or 0)
        elif o["k"] == "tstart":
            turns[s][src[f]] += 1
        elif o["k"] == "tdone":
            turns[s][src[f] + "_done"] += 1
        elif o["k"] == "tabort":
            turns[s][src[f] + "_abort"] += 1

    print("\n" + "=" * 120)
    print("3. B 成本（token_usage_record 逐响应累加 = 计费量；turn = task_started）")
    print("=" * 120)
    for s, name, lo, hi in SEGMENTS:
        print(f"\n--- {s} {name} ---")
        for t in ("user", "subagent", "guardian_review"):
            c, nt = B[s][t], turns[s][t]
            if not c or not nt:
                continue
            inn, cch = c["in"], c["cached"]
            pt = [turn_acc[(s, t, tid)] for (s2, t2, tid) in list(turn_acc) if s2 == s and t2 == t]
            print(f"  {t:15} turn={nt:5} resp={c['resp']:6} 计费输入={inn:13,} 缓存={cch:13,} 输出={c['out']:9,}")
            print(f"  {'':15} (a)每响应输入 均值={inn/c['resp']:9,.0f} 中位={statistics.median(resp_in[s][t]):9,.0f} | "
                  f"(b)每turn计费输入 均值={inn/nt:12,.0f} 中位={statistics.median(pt):11,.0f} | "
                  f"(c)每turn未缓存={(inn-cch)/nt:10,.0f} | (d)缓存命中={pct(cch,inn):6.2f}% | "
                  f"响应/turn={c['resp']/nt:5.1f}")
    print("\n  子代理/审批 token 占比 + 每单位工作量的成本：")
    for s, name, lo, hi in SEGMENTS:
        tot = sum(B[s][x]["in"] for x in B[s])
        work = A[s]["filechange_items"] + Asub[s]["filechange_items"]
        cmds = A[s]["exec_main"] + Asub[s]["exec_sub"]
        print(f"    {s}: 计费输入合计={tot:14,} 子代理={pct(B[s]['subagent']['in'],tot) or 0:6.2f}% "
              f"审批={pct(B[s]['guardian_review']['in'],tot) or 0:5.2f}% | "
              f"每 FileChange 项={tot/work/1e6 if work else 0:7.2f}M | 每 shell 命令={tot/cmds/1e3 if cmds else 0:8.1f}K")

    # ---------- 4 C turn ----------
    print("\n" + "=" * 120)
    print("4. C 质量：turn 生命周期")
    print("=" * 120)
    for s, name, lo, hi in SEGMENTS:
        for t in ("user", "subagent"):
            nt, dn, ab = turns[s][t], turns[s][t + "_done"], turns[s][t + "_abort"]
            if not nt:
                continue
            print(f"  {s} {t:9} tstart={nt:5} tdone={dn:5} aborted={ab:3} 未闭合={nt-dn-ab:3} "
                  f"完成率={pct(dn,nt):6.2f}% 中断率={pct(ab,nt):5.2f}%")

    # ---------- 5 C 报告（完整正文） ----------
    STAT = re.compile(r"^\s*status\s*:\s*([A-Za-z_]+)", re.M)
    FLD = {
        "changed_files": re.compile(r"changed[ _]files", re.I),
        "evidence": re.compile(r"^\s*evidence\s*:", re.I | re.M),
        "assumptions": re.compile(r"^\s*assumptions\s*:", re.I | re.M),
        "blockers": re.compile(r"^\s*blockers\s*:", re.I | re.M),
        "reused": re.compile(r"^\s*reused\s*:", re.I | re.M),
    }
    reports = []
    if os.path.exists(REPS):
        for line in open(REPS, encoding="utf-8"):
            r = json.loads(line)
            txt = r.get("text") or ""
            m = STAT.search(txt)
            head = txt.lstrip()[:40]
            r["status"] = m.group(1).lower() if m and txt.lstrip().startswith("status") else None
            r["fields"] = {k: bool(rx.search(txt)) for k, rx in FLD.items()}
            r["len"] = len(txt)
            r["seg"] = seg.get(r["f"], "S0")
            r["head"] = head
            reports.append(r)
    byseg = collections.defaultdict(list)
    for r in reports:
        byseg[r["seg"]].append(r)

    print("\n" + "=" * 120)
    print(f"5. C 质量：子代理最终报告（来源 {os.path.basename(REPS)}，每 turn 一条，完整正文未截断）")
    print("=" * 120)
    for s, name, lo, hi in SEGMENTS:
        rs = byseg[s]
        if not rs:
            continue
        cnt = collections.Counter(r["status"] for r in rs)
        n4 = sum(1 for r in rs if all(r["fields"][k] for k in ("changed_files", "evidence", "assumptions", "blockers")))
        byrole = collections.defaultdict(collections.Counter)
        for r in rs:
            byrole[r["role"]][r["status"]] += 1
        print(f"\n--- {s} 报告数={len(rs)}（中位长度 {statistics.median([r['len'] for r in rs]):.0f} 字符）---")
        print(f"  status: {dict(cnt)}")
        print(f"  四项齐全 = {n4}/{len(rs)} = {pct(n4,len(rs)):.1f}%   单字段: "
              + str({k: f"{pct(sum(1 for r in rs if r['fields'][k]), len(rs)):.1f}%" for k in FLD}))
        for rl in sorted(byrole, key=lambda x: str(x)):
            print(f"    role={str(rl):12} {dict(byrole[rl])}")
    print("\n  报告开头是否以 status 起首（校验正文未被截断/污染）：")
    for s, name, lo, hi in SEGMENTS:
        rs = byseg[s]
        if rs:
            ok = sum(1 for r in rs if r["status"])
            print(f"    {s}: {ok}/{len(rs)}")

    # unverified 收敛
    print("\n  unverified 收敛（同 agent_path 后续 turn 是否出现非 unverified 的最终状态）：")
    bypath = collections.defaultdict(list)
    for r in reports:
        bypath[(r["f"], r["agent_path"])].append(r)
    for s, name, lo, hi in SEGMENTS:
        rs = sorted(byseg[s], key=lambda r: r["ts"] or "")
        pend = conv = 0
        for r in rs:
            if r["status"] != "unverified":
                continue
            pend += 1
            later = [x for x in bypath[(r["f"], r["agent_path"])] if (x["ts"] or "") > (r["ts"] or "")]
            if any(x["status"] and x["status"] != "unverified" for x in later):
                conv += 1
        print(f"    {s}: unverified={pend} 有后续非 unverified 记录={conv} 未收敛={pend-conv}")

    # ---------- 6 D 返工 ----------
    print("\n" + "=" * 120)
    print("6. D 返工")
    print("=" * 120)
    spawn_by_file = collections.defaultdict(list)
    fc_events = collections.defaultdict(list)
    filechange_paths = collections.defaultdict(collections.Counter)
    for o in rows:
        f, s = o["f"], seg[o["f"]]
        if src[f] != "user":
            continue
        if o["k"] == "fc" and o["name"] == "spawn_agent":
            spawn_by_file[f].append((o["ts"], (o.get("args") or {}).get("task_name"),
                                     (o.get("args") or {}).get("agent_type")))
        if o["k"] == "fc" and o["name"] in ("send_message", "followup_task", "spawn_agent"):
            fc_events[f].append((o["ts"], o["name"], (o.get("args") or {}).get("target") or (o.get("args") or {}).get("task_name")))
        if o["k"] == "item" and o["it"] == "FileChange":
            for p in (o.get("paths") or []):
                filechange_paths[f][p] += 1
    D = {s: collections.Counter() for s in ALLSEG_ORDER}
    for f, lst in spawn_by_file.items():
        c = collections.Counter(tn for _, tn, _ in lst)
        s = seg[f]
        D[s]["spawn"] += len(lst)
        D[s]["distinct_task_name"] += len(c)
        D[s]["dup_task_name"] += sum(1 for v in c.values() if v > 1)
        D[s]["dup_spawn_extra"] += sum(v - 1 for v in c.values() if v > 1)
    for f, cnt in filechange_paths.items():
        s = seg[f]
        D[s]["paths_touched"] += len(cnt)
        D[s]["paths_touched_gt1"] += sum(1 for v in cnt.values() if v > 1)
    # blocked 报告 → 同主线程 30 分钟内再次派发（推断）
    main_first = {}
    for f, m in meta.items():
        if src[f] == "user":
            main_first.setdefault(m.get("sid"), f)
    blocked_by_main = collections.Counter()
    redispatch = collections.Counter()
    for r in reports:
        if r["status"] != "blocked":
            continue
        parent = meta.get(r["f"], {}).get("parent_thread_id")
        mf = main_first.get(parent)
        if not mf:
            continue
        s = seg[mf]
        blocked_by_main[s] += 1
        t0 = datetime.fromisoformat(r["ts"])
        for (ts, nm, tgt) in fc_events.get(mf, []):
            if ts and datetime.fromisoformat(ts) >= t0 and (datetime.fromisoformat(ts) - t0) <= timedelta(minutes=30):
                redispatch[s] += 1
                break
    for s, name, lo, hi in SEGMENTS:
        d = D[s]
        print(f"  {s}: spawn={d['spawn']} 不同task_name={d['distinct_task_name']} "
              f"重复task_name={d['dup_task_name']} 额外重复spawn={d['dup_spawn_extra']}")
        print(f"      同一主线程内被改动>1 次的文件路径: {d['paths_touched_gt1']}/{d['paths_touched']} "
              f"= {pct(d['paths_touched_gt1'], d['paths_touched']) or 0:.1f}%")
        print(f"      blocked 子代理报告数={blocked_by_main[s]}  其中 30 分钟内主线程再次派发/发消息={redispatch[s]}")

    # ---------- 7 主线程明细 ----------
    print("\n" + "=" * 120)
    print("7. 主线程会话明细（用于核对样本量与离散度）")
    print("=" * 120)
    pf = collections.defaultdict(collections.Counter)
    first_msg = {}
    for o in rows:
        f = o["f"]
        c = pf[f]
        if o["k"] == "fc" and src[f] == "user":
            c["fc_" + str(o["name"])] += 1
        elif o["k"] == "item":
            if o["it"] == "CommandExecution":
                c["exec"] += 1
            elif o["it"] == "UserMessage" and f not in first_msg and src[f] == "user":
                first_msg[f] = (o.get("text") or "").replace("\n", " ")[:60]
        elif o["k"] == "tur":
            c["in"] += o.get("in") or 0
            c["resp"] += 1
        elif o["k"] == "tstart":
            c["turns"] += 1
    print(f"{'start_utc':20} {'seg':3} {'cwd':14} {'spawn':5} {'reuse':5} {'idle':4} {'exec':5} {'turns':5} {'resp':5} {'Mtok':7} task")
    for f, m in sorted(meta.items(), key=lambda kv: kv[1].get("ts") or ""):
        if src[f] != "user":
            continue
        c = pf[f]
        print(f"{(m.get('ts') or '')[:19]:20} {seg[f]:3} {str(cwd[f])[-14:]:14} {c['fc_spawn_agent']:5} "
              f"{c['fc_send_message']+c['fc_followup_task']:5} {c['fc_wait_agent']+c['fc_wait']:4} "
              f"{c['exec']:5} {c['turns']:5} {c['resp']:5} {c['in']/1e6:7.1f} {first_msg.get(f,'')}")

    # ---------- 8 模型档位 ----------
    print("\n" + "=" * 120)
    print("8. 模型档位（k=='tctx' 的 model@effort，按分段×thread_source×role）")
    print("=" * 120)
    mt = collections.defaultdict(collections.Counter)
    for o in rows:
        if o["k"] != "tctx":
            continue
        mt[(seg[o["f"]], src[o["f"]], role[o["f"]])][f"{o.get('model')}@{o.get('effort')}"] += 1
    for key in sorted(mt, key=lambda k: str(k)):
        print(f"  {key[0]} {key[1]:16} {str(key[2]):12} {dict(mt[key])}")

    # ---------- dump ----------
    res = {
        "prefix": prefix,
        "segments": {s: {"sessions": dict(ss[s]), "A": dict(A[s]), "A_sub": dict(Asub[s]), "D": dict(D[s]),
                         "turns": dict(turns[s]),
                         "B": {k: dict(v) for k, v in B[s].items()},
                         "reports": {"n": len(byseg[s]),
                                     "status": dict(collections.Counter(r["status"] for r in byseg[s])),
                                     "full4": sum(1 for r in byseg[s] if all(r["fields"][k] for k in ("changed_files", "evidence", "assumptions", "blockers")))},
                         "blocked_redispatch": [blocked_by_main[s], redispatch[s]]}
                     for s in segs},
        "tool_inventory": {s: {k: dict(v) for k, v in inv[s].items()} for s in inv},
        "files": len(meta),
    }
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nWROTE", OUT)


if __name__ == "__main__":
    main()
