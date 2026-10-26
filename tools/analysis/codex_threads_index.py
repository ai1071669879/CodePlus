# -*- coding: utf-8 -*-
"""
codex_threads_index.py —— 从 state_5.sqlite 的 threads 表取全量线程索引（含 rollout 文件已丢失的 09-15~10-13）
数据源: <db>（默认 ~/.codex/state_5.sqlite；只读）
口径:
  * 线程类型由 source 字段判定：source 含 {"subagent":{"thread_spawn"...}} => subagent；
    含 {"subagent":{"other":"guardian"}} => guardian_review；其余（vscode 等）=> user
  * 日期用 created_at（本地时间，Codex 写入的 epoch/ISO 混合；统一转 datetime 后取日期）
  * tokens_used 为线程累计 token（不可与 token_usage_record 相加，单位口径不同，只做趋势）
输出: 控制台 + ~/codex_threads_index.json（可用 --out 改路径）
可重跑: 是（已有输出默认拒绝覆盖，需 --force）
用法:
    python -X utf8 codex_threads_index.py --help
    python -X utf8 codex_threads_index.py [--db <path>] [--out <path>] [--dry-run] [--force]
退出码: 0=成功；2=参数或输入库错误；1=输出文件已存在/无法写入
"""
import argparse, sqlite3, os, sys, json, collections
from datetime import datetime

HOME = os.path.expanduser("~")


def build_parser():
    ap = argparse.ArgumentParser(description="从 state_5.sqlite 的 threads 表取全量线程索引（只读）")
    ap.add_argument("--db", default=os.path.join(HOME, ".codex", "state_5.sqlite"),
                    help="state 数据库路径（默认 ~/.codex/state_5.sqlite）")
    ap.add_argument("--out", default=os.path.join(HOME, "codex_threads_index.json"),
                    help="输出 JSON 路径（默认 ~/codex_threads_index.json）")
    ap.add_argument("--dry-run", action="store_true", help="只打印汇总，不写文件")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    return ap


def to_dt(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        if x > 1e15:
            x /= 1e6
        elif x > 1e12:
            x /= 1e3
        try:
            return datetime.fromtimestamp(x)
        except Exception:
            return None
    s = str(v)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def kind_of(source):
    if not source:
        return "user"
    if isinstance(source, dict):
        s = source
    else:
        try:
            s = json.loads(source)
        except Exception:
            return "user"
    if isinstance(s, dict) and isinstance(s.get("subagent"), dict):
        if "guardian" in s["subagent"].get("other", ""):
            return "guardian_review"
        if "thread_spawn" in s["subagent"]:
            return "subagent"
    return "user"


def main():
    ap = build_parser()
    a = ap.parse_args()
    db = os.path.abspath(a.db)
    out_path = os.path.abspath(a.out)
    if not os.path.isfile(db):
        ap.error("--db 不是文件: %s" % db)
    if not a.dry_run and os.path.exists(out_path) and not a.force:
        print("ERROR: 输出文件已存在: %s" % out_path, file=sys.stderr)
        print("       确认覆盖请加 --force；只检查不写请用 --dry-run", file=sys.stderr)
        return 1

    con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = [dict(r) for r in cur.execute(
        "select id, created_at, rollout_path, source, cwd, tokens_used, archived from threads")]
    print("threads total:", len(rows))

    day = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        d = to_dt(r["created_at"])
        if not d:
            continue
        k = kind_of(r["source"])
        ds = d.date().isoformat()
        day[ds][k] += 1
        day[ds]["tok_" + k] += (r["tokens_used"] or 0)
        day[ds]["rollout_" + k + ("_present" if (r["rollout_path"] and os.path.exists(r["rollout_path"])) else "_missing")] += 1

    print("\n按日：user 线程 / subagent 线程 / guardian 线程 / 子代理:主线程比 / tokens_used 合计")
    print(f"{'date':12} {'user':>5} {'sub':>5} {'guard':>6} {'sub:user':>9} {'tok_sum':>15} {'rollout_missing':>15}")
    out = {}
    for ds in sorted(day):
        c = day[ds]
        ratio = (c["subagent"] / c["user"]) if c["user"] else None
        tot = c["tok_user"] + c["tok_subagent"] + c["tok_guardian_review"]
        miss = sum(v for k, v in c.items() if k.startswith("rollout_") and k.endswith("_missing"))
        print(f"{ds:12} {c['user']:5} {c['subagent']:5} {c['guardian_review']:6} "
              f"{(f'{ratio:.2f}' if ratio is not None else '-'):>9} {tot:15,} {miss:15}")
        out[ds] = {"user": c["user"], "subagent": c["subagent"], "guardian": c["guardian_review"],
                   "tok_user": c["tok_user"], "tok_sub": c["tok_subagent"], "tok_guard": c["tok_guardian_review"],
                   "ratio": ratio}

    print("\n按月汇总：")
    bym = collections.defaultdict(lambda: collections.Counter())
    for ds, v in out.items():
        m = ds[:7]
        for k in ("user", "subagent", "guardian", "tok_user", "tok_sub", "tok_guard"):
            bym[m][k] += v[k]
    for m in sorted(bym):
        c = bym[m]
        r = (c["subagent"] / c["user"]) if c["user"] else None
        print(f"  {m}  user={c['user']:4} sub={c['subagent']:4} guard={c['guardian']:4} "
              f"sub:user={r if r is None else round(r,2)}  tok={c['tok_user']+c['tok_sub']+c['tok_guard']:,}")

    if a.dry_run:
        print("\nDRY-RUN: 未写入", out_path)
    else:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"by_day": out, "by_month": {m: dict(v) for m, v in bym.items()}}, f,
                          ensure_ascii=False, indent=1)
        except OSError as e:
            print("ERROR: 无法写入 %s: %s" % (out_path, e), file=sys.stderr)
            con.close()
            return 1
        print("\nWROTE", out_path)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
