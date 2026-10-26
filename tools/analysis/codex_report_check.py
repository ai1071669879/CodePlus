# -*- coding: utf-8 -*-
"""
codex_report_check.py —— 报告数字守门员：把 docs/CODEX-MULTIAGENT-BENEFIT.md（本仓库）里引用的关键数字
从机读指标 JSON 重新算一遍并逐条断言，防止报告手抄错。
数据源: codex_metrics_main.json + codex_metrics_backup.json（由 codex_metrics.py 生成）——
        缺任一份都不是"报告出错"，而是输入链没跑完，按用法错误处理（exit 2）。
输出: 每条断言的 PASS/FAIL + 末尾汇总；有 FAIL 时退出码 1；输入缺失/非法时退出码 2
用法:
    python -X utf8 codex_report_check.py --help
    python -X utf8 codex_report_check.py
    python -X utf8 codex_report_check.py --main <main.json> --backup <backup.json>
"""
import argparse, json, os, sys

HOME = os.path.expanduser("~")
DEFAULT_MAIN = os.path.join(HOME, "codex_metrics_main.json")
DEFAULT_BACKUP = os.path.join(HOME, "codex_metrics_backup.json")


def build_parser():
    ap = argparse.ArgumentParser(
        description="把报告引用的关键数字从 codex_metrics 机读结果重算并逐条断言",
        epilog="退出码: 0=全部 PASS；1=有 FAIL；2=输入缺失/非法。")
    ap.add_argument("--main", default=DEFAULT_MAIN,
                    help="main 指标 JSON（默认 ~/codex_metrics_main.json）")
    ap.add_argument("--backup", default=DEFAULT_BACKUP,
                    help="backup 指标 JSON（默认 ~/codex_metrics_backup.json）")
    return ap


def load_metrics(path, flag):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        print("ERROR: 无法读取 %s %s: %s" % (flag, path, e), file=sys.stderr)
        print("       守门员需要 main 与 backup 两份指标，请先跑完整输入链：", file=sys.stderr)
        print("         python -X utf8 codex_extract.py --prefix main", file=sys.stderr)
        print("         python -X utf8 codex_metrics.py --prefix main", file=sys.stderr)
        print("         python -X utf8 codex_extract.py --root <backup-root> --prefix backup", file=sys.stderr)
        print("         python -X utf8 codex_metrics.py --prefix backup", file=sys.stderr)
        sys.exit(2)
    except ValueError as e:
        print("ERROR: %s %s 不是合法 JSON: %s" % (flag, path, e), file=sys.stderr)
        sys.exit(2)


ARGS = build_parser().parse_args()
M = load_metrics(ARGS.main, "--main")
B = load_metrics(ARGS.backup, "--backup")

fails = []
n = 0


def chk(label, got, want, tol=0.0):
    global n
    n += 1
    ok = (abs(got - want) <= tol) if isinstance(want, (int, float)) and isinstance(got, (int, float)) else (got == want)
    if not ok:
        fails.append((label, got, want))
    print(f"  {'PASS' if ok else 'FAIL'}  {label:52} got={got!r:>18}  want={want!r}")


def seg(prefix, s):
    d = (M if prefix == "main" else B)["segments"][s]
    return d


print("=" * 100)
print("1. 样本量")
print("=" * 100)
for s, files, u, sub, g in [("S1", 141, 10, 88, 43), ("S2", 212, 12, 113, 87), ("S3", 124, 4, 93, 27),
                            ("P0", 428, 230, 182, 16)]:
    p = "main" if s.startswith("S") else "backup"
    ss = seg(p, s)["sessions"]
    chk(f"{s} 日志文件数", ss["files"], files)
    chk(f"{s} 主线程会话", ss["user"], u)
    chk(f"{s} 子代理会话", ss["subagent"], sub)
    chk(f"{s} 审批会话", ss["guardian_review"], g)

print("=" * 100)
print("2. A 委派结构")
print("=" * 100)
for s, spawn, send, fol, wait, ex in [("S1", 106, 271, 154, 95, 3075), ("S2", 115, 293, 308, 169, 4361),
                                      ("S3", 80, 102, 65, 40, 1332), ("P0", 61, 72, 190, 262, 16615)]:
    p = "main" if s.startswith("S") else "backup"
    a = seg(p, s)["A"]
    chk(f"{s} spawn", a["spawn"], spawn)
    chk(f"{s} send_message", a["send_message"], send)
    chk(f"{s} followup_task", a["followup_task"], fol)
    chk(f"{s} wait_agent", a["wait_agent"], wait)
    chk(f"{s} 主线程自执行 CommandExecution", a["exec_main"], ex)
    chk(f"{s} 委派占比%", round(a["spawn"] / (a["spawn"] + a["exec_main"]) * 100, 2),
        {"S1": 3.33, "S2": 2.57, "S3": 5.67, "P0": 0.37}[s], 0.01)
    chk(f"{s} 复用/spawn", round(a["reuse"] / a["spawn"], 2),
        {"S1": 4.01, "S2": 5.23, "S3": 2.09, "P0": 4.3}[s], 0.005)
    fs = seg(p, s)["A_sub"]["filechange_items"]
    fm = a["filechange_items"]
    chk(f"{s} FileChange 子代理占比%", round(fs / (fs + fm) * 100, 2),
        {"S1": 32.06, "S2": 36.8, "S3": 46.85, "P0": 5.17}[s], 0.01)

print("=" * 100)
print("3. B 成本（主线程）")
print("=" * 100)
for s, per_resp, per_turn, uncached, hit, rpt in [
        ("S1", 188972, 9831864, 220263, 97.76, 52.0),
        ("S2", 200886, 8817443, 178397, 97.98, 43.9),
        ("S3", 203510, 4373937, 77153, 98.24, 21.5),
        ("P0", 152085, 429416, 46949, 89.07, 2.8)]:
    p = "main" if s.startswith("S") else "backup"
    b = seg(p, s)["B"]["user"]
    t = seg(p, s)["turns"]["user"]
    chk(f"{s} 每响应输入均值", round(b["in"] / b["resp"]), per_resp, 1)
    chk(f"{s} 每turn计费输入", round(b["in"] / t), per_turn, 1)
    chk(f"{s} 每turn未缓存", round((b["in"] - b["cached"]) / t), uncached, 1)
    chk(f"{s} 缓存命中率%", round(b["cached"] / b["in"] * 100, 2), hit, 0.005)
    chk(f"{s} 响应/turn", round(b["resp"] / t, 1), rpt, 0.05)
for s, share in [("S1", 36.66), ("S2", 46.78), ("S3", 46.24), ("P0", 6.87)]:
    p = "main" if s.startswith("S") else "backup"
    tot = sum(v["in"] for v in seg(p, s)["B"].values())
    chk(f"{s} 子代理 token 占比%", round(seg(p, s)["B"]["subagent"]["in"] / tot * 100, 2), share, 0.01)

print("=" * 100)
print("4. C 质量")
print("=" * 100)
for s, done, abort, sd, sa in [("S1", 92.96, 7.04, 99.49, 0.51), ("S2", 91.96, 8.04, 99.28, 0.48),
                               ("S3", 89.55, 8.96, 97.80, 1.65), ("P0", 92.61, 6.76, 95.90, 2.55)]:
    p = "main" if s.startswith("S") else "backup"
    c = seg(p, s)["turns"]
    chk(f"{s} 主线程 turn 完成率%", round(c["user_done"] / c["user"] * 100, 2), done, 0.005)
    chk(f"{s} 主线程 turn 中断率%", round(c["user_abort"] / c["user"] * 100, 2), abort, 0.005)
    chk(f"{s} 子代理 turn 完成率%", round(c["subagent_done"] / c["subagent"] * 100, 2), sd, 0.005)
    chk(f"{s} 子代理 turn 中断率%", round(c["subagent_abort"] / c["subagent"] * 100, 2), sa, 0.005)
for s, nrep, passed, unv in [("S1", 192, 91, 44), ("S2", 411, 200, 131), ("S3", 178, 44, 112), ("P0", 755, 0, 0)]:
    p = "main" if s.startswith("S") else "backup"
    r = seg(p, s)["reports"]
    chk(f"{s} 子代理报告数", r["n"], nrep)
    chk(f"{s} passed", r["status"].get("passed", 0), passed)
    chk(f"{s} unverified", r["status"].get("unverified", 0), unv)
chk("S1 四项齐全", seg("main", "S1")["reports"]["full4"], 192)
chk("S2 四项齐全", seg("main", "S2")["reports"]["full4"], 409)
chk("S3 四项齐全", seg("main", "S3")["reports"]["full4"], 178)
chk("P0 四项齐全", seg("backup", "P0")["reports"]["full4"], 0)

print("=" * 100)
print("5. D 返工")
print("=" * 100)
chk("S1 额外重复 spawn", seg("main", "S1")["D"].get("dup_spawn_extra", 0), 0)
chk("P0 重复 task_name", seg("backup", "P0")["D"].get("dup_task_name", 0), 3)

print("=" * 100)
print(f"断言 {n} 条，FAIL {len(fails)} 条")
for f in fails:
    print("  FAIL:", f)
print("=" * 100)
sys.exit(1 if fails else 0)
