# -*- coding: utf-8 -*-
"""
audit_quality.py -- 质量类指标的独立重算（只读原始 rollout 日志；不读任何 Lead 中间文件）

运行:
    python -X utf8 C:\\Users\\Administrator\\audit_quality.py                 # 全量
    python -X utf8 C:\\Users\\Administrator\\audit_quality.py --sample 8      # 小样本: 前 8 个 subagent 会话
    python -X utf8 C:\\Users\\Administrator\\audit_quality.py --limit 10      # 小样本: 按文件名前 10 个文件
    python -X utf8 C:\\Users\\Administrator\\audit_quality.py --out <path>

输出: C:\\Users\\Administrator\\audit_quality_out.txt （同样内容打印到 stdout）

============================================================================
数据源
============================================================================
  C:\\Users\\Administrator\\.codex\\sessions\\**\\rollout-*.jsonl   每行一个 JSON
  只使用行内原始字段:
    - type=="session_meta"（首行）-> payload.thread_source / payload.agent_role /
      payload.id(sid) / payload.parent_thread_id / payload.source.subagent.thread_spawn.agent_path
    - event_msg.payload.type=="item_completed" 且 payload.item.type=="AgentMessage"
      -> 报告文本 = join(payload.item.content[*].text)；payload.item.phase 区分 final_answer / commentary
    - event_msg.payload.type=="task_complete" -> payload.last_agent_message
    - response_item.payload.type=="agent_message" -> payload.author / payload.recipient /
      join(payload.content[*].text)；正文头部有 "Message Type: FINAL_ANSWER|NEW_TASK|MESSAGE"
    - event_msg.payload.type ∈ {task_started, task_complete, turn_aborted} -> turn 生命周期
  时间: 各记录顶层 "timestamp"（ISO8601, ...Z）的 UTC 日期；缺失时回落到 session_meta.timestamp。

注: 任务书提到主线程 "event_msg.payload.type==agent_message"。全量实测该类型 0 条；
    主线程中继的真实载体是 response_item.payload.type=="agent_message"。两种载体脚本都支持。

============================================================================
口径（判定规则，下文所有正则均以原文打印，可照抄复现）
============================================================================
[A] final-answer 通道（只有这三个通道的文本才可能成为"最终报告"）:
    1. event_msg/item_completed，item.type=="AgentMessage"，item.phase=="final_answer"
       —— 子代理/guardian 会话自身的最终答复
    2. event_msg/task_complete.last_agent_message
       —— 同一次最终答复的落盘副本（与 1 同 sha1，去重后只算一次）
    3. response_item/agent_message 且正文首行 "Message Type: FINAL_ANSWER"
       —— 主线程侧收到的中继副本；NEW_TASK=派活、MESSAGE=中途消息，均排除
[B] 报告正文抽取: 先按原文解析 "Message Type: X"（必须在剥离头部之前解析），
    再去掉中继头（Message Type / Task name / Sender / Recipient / Message ID 行），
    若有独立 "Payload:" 行则取其后的正文，最后 strip。
[C] "最终报告"（合规率分母）判定: 一个 final-answer 消息，其正文命中下面任一字段标签正则
    （status / changed_files / evidence / assumptions / blockers / reused，允许多种写法），
    即至少带一个报告字段。guardian_review 的 {"risk_level":...} JSON 裁决、主线程散文答复、
    "This agent's turn failed." 占位消息都不命中 -> 不计入报告分母（明细见第 6 节）。
[D] 去重（每份报告只计一次）: 主口径 = sha1(正文按空白归一化) 全局唯一；
    次口径 = (sid, task_name, sha1) 三元组唯一。两者结果一起打印。
    task_name: 子代理会话取 thread_spawn.agent_path，中继消息取 payload.author（/root/<task_name>）。
[E] 文档归属: 报告的 thread_source / agent_role 优先取提交它的子代理会话 meta
    （agent_path -> meta 映射）；中继消息且源会话不在数据中时标 "relay_only(源会话缺失)"，
    不谎报成 user；真正由主线程产出的报告保留 thread_source=user。
[F] unverified 收敛: 对每份 status:unverified 的唯一报告，找更晚记录:
      A 主口径 = 同一任务线程 (sid, task_name) 内更晚、正文不同、且含 status: 或 disposition 字样的记录；
                 中继消息以主线程 sid + author 作为同一任务线程键。
      B 补充   = 同一 task_name 在其它 sid 的更晚记录（注意 task_name 会被跨天复用，该口径可能高估，单列）。
    传输副本（同 sha1）不算后续记录；窗口 = 全量数据。
[G] 时间与分天: 全部 UTC 天。报告归属日 = 该报告最早一次出现的 UTC 日。

============================================================================
只读/只写约束
============================================================================
  只读 ~/.codex/sessions 下的 rollout-*.jsonl；只写本脚本与 audit_quality_out.txt。
  不读/不写 ~/codex_events.jsonl、codex_meta.json、codex_extract.py、codex_*metrics*.py。
"""

import argparse
import collections
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
SESS_ROOT = os.environ.get("CODEX_SESSIONS", os.path.join(HOME, ".codex", "sessions"))
DEFAULT_OUT = os.environ.get("CODEX_AUDIT_OUT", os.path.join(HOME, "audit_quality_out.txt"))

# ---------------------------------------------------------------- 正则（原文） --
# 字段标签 = 行首(可带缩进/列表符/引用符/标题符) + 可选 ** + 标签名 + 可选括号说明 + 冒号或等号
FIELD_LABEL = r"[ \t\-*#>]*(?:\*\*)?{name}(?:\*\*)?[ \t]*(?:\([^)\n]{{0,40}}\))?[ \t]*[:=]"

RE_CHANGED = re.compile(r"(?im)^" + FIELD_LABEL.format(name=r"changed[_ ]files"))
RE_EVIDENCE = re.compile(r"(?im)^" + FIELD_LABEL.format(name=r"evidence"))
RE_ASSUMPT = re.compile(r"(?im)^" + FIELD_LABEL.format(name=r"assumptions?"))
RE_BLOCKERS = re.compile(r"(?im)^" + FIELD_LABEL.format(name=r"blockers?"))
RE_REUSED = re.compile(r"(?im)^" + FIELD_LABEL.format(name=r"reused"))
RE_STATUS = re.compile(
    r"(?im)^" + FIELD_LABEL.format(name=r"status") + r"[ \t]*([A-Za-z_][A-Za-z0-9_\-]*)"
)
RE_DISPOSITION = re.compile(r"(?i)\bdisposition\b")

CORE_FIELDS = [
    ("changed_files", RE_CHANGED),
    ("evidence", RE_EVIDENCE),
    ("assumptions", RE_ASSUMPT),
    ("blockers", RE_BLOCKERS),
]
ALL_FIELDS = CORE_FIELDS + [("reused", RE_REUSED)]
# [C] 报告字段集合：文档口径明确 status 可单独识别报告
REPORT_FIELDS = ALL_FIELDS + [("status", RE_STATUS)]

RE_MSG_TYPE = re.compile(r"^\s*Message Type\s*:\s*(\w+)", re.I)
RE_PAYLOAD_LINE = re.compile(r"(?im)^\s*Payload\s*:\s*$")
RE_TRANSPORT_HDR = re.compile(
    r"(?m)^\s*(?:Message Type|Task name|Sender|Recipient|Message ID)\s*:.*$"
)
RE_WS = re.compile(r"\s+")
RE_EXPLICIT_EMPTY = re.compile(r"(?i)^(?:\[\s*\]|none|nil|n/?a|无|-{1,2}|—)[.。]?$")

STATUS_BUCKETS = ("passed", "failed", "blocked", "unverified")


# ------------------------------------------------------------------ 小工具 ----
def utc_day(ts):
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def strip_transport(text):
    """[B] 去掉主线程中继头，返回报告正文。"""
    t = text or ""
    m = RE_PAYLOAD_LINE.search(t)
    if m:
        t = t[m.end():]
    else:
        t = RE_TRANSPORT_HDR.sub("", t)
    return t.strip()


def norm_hash(text):
    return hashlib.sha1(RE_WS.sub(" ", text or "").strip().encode("utf-8", "replace")).hexdigest()


def status_of(text):
    m = RE_STATUS.search(text)
    return (m.group(1).lower() if m else None), (m.group(0).strip() if m else None)


def field_hits(text):
    out = {}
    for name, rx in ALL_FIELDS:
        m = rx.search(text)
        out[name] = m.group(0).strip() if m else None
    return out


def is_report(text):
    """[C] 至少带一个报告字段标签（status / changed_files / evidence / assumptions / blockers / reused）。"""
    return any(rx.search(text) for name, rx in REPORT_FIELDS)


def value_form(text, rx):
    """字段值形态: has_value / empty_list / explicit_none / unfilled。

    只看标签所在行：有字符 -> has_value；'[]' -> empty_list；none/n-a/无/- -> explicit_none；
    行内为空且下一行不是缩进内容 -> unfilled。
    """
    m = rx.search(text)
    if not m:
        return "absent"
    rest = text[m.end():]
    nl = rest.find("\n")
    first = (rest if nl < 0 else rest[:nl]).strip()
    if first:
        if re.match(r"(?i)^\[\s*\]$", first):
            return "empty_list"
        if RE_EXPLICIT_EMPTY.match(first):
            return "explicit_none"
        return "has_value"
    # 标签行本身为空: 后面是否跟着缩进的列表/段落
    nxt = rest[nl + 1:] if nl >= 0 else ""
    if re.match(r"(?m)^[ \t]+[^\s]", nxt):
        return "has_value"
    return "unfilled"


def short(text, n=300):
    t = (text or "").replace("\r", "")
    return t[:n]


def indent_block(text, prefix="    "):
    lines = short(text, 300).splitlines() or [""]
    return "\n".join(prefix + ln for ln in lines)


def sid_of(meta):
    return (meta or {}).get("id") or (meta or {}).get("session_id") or "UNKNOWN"


def agent_path_of(meta):
    sp = (meta or {}).get("source")
    if isinstance(sp, dict):
        sa = sp.get("subagent")
        if isinstance(sa, dict):
            tw = sa.get("thread_spawn")
            if isinstance(tw, dict):
                return tw.get("agent_path")
    return None


def agent_role_of(meta):
    role = (meta or {}).get("agent_role")
    if role:
        return role
    sp = (meta or {}).get("source")
    if isinstance(sp, dict):
        sa = sp.get("subagent")
        if isinstance(sa, dict):
            tw = sa.get("thread_spawn")
            if isinstance(tw, dict):
                return tw.get("agent_role")
    return None


# ------------------------------------------------------------------ 文件枚举 ----
def iter_files(limit=None, sample=None):
    files = glob.glob(os.path.join(SESS_ROOT, "**", "rollout-*.jsonl"), recursive=True)
    files.sort(key=lambda p: (os.path.basename(p)[:60], p))
    if sample:
        picked = []
        for p in files:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    first = fh.readline()
                m = json.loads(first)
                if (m.get("type") == "session_meta"
                        and (m.get("payload") or {}).get("thread_source") == "subagent"):
                    picked.append(p)
            except Exception:
                continue
            if len(picked) >= sample:
                break
        return picked
    if limit:
        files = files[:limit]
    return files


# ------------------------------------------------------------------ 单遍扫描 ----
def scan(files, verbose=False):
    path_meta = {}
    agent_meta = {}            # agent_path -> (thread_source, agent_role, sid)
    reports_raw = []           # final-answer 通道的每次出现（含传输副本）
    channel_msgs = collections.Counter()   # 通道消息原始条数（含非报告）
    lifecycle = collections.Counter()      # (thread_source, day, event) -> n
    lifecycle_missing_day = collections.Counter()
    all_msgs = collections.defaultdict(list)   # (sid, task_name) -> [(ts, ord, sha1, has_status, has_disp)]
    relay_stats = collections.Counter()        # 中继消息按 Message Type / 是否有明文正文
    disp_records = []          # 正文含 disposition 的记录（用于第 3 节核对）
    stats = collections.Counter()
    t0 = time.time()
    total_bytes = 0

    for i, path in enumerate(files):
        try:
            total_bytes += os.path.getsize(path)
        except OSError:
            pass
        meta = {}
        fname = os.path.basename(path)
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            stats["file_open_fail"] += 1
            continue
        with fh:
            ordinal = 0
            for line in fh:
                ordinal += 1
                need = (
                    '"session_meta"' in line
                    or '"task_started"' in line
                    or '"task_complete"' in line
                    or '"turn_aborted"' in line
                    or '"AgentMessage"' in line
                    or '"agent_message"' in line
                )
                if not need:
                    stats["lines_skipped"] += 1
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    stats["json_fail"] += 1
                    continue
                typ = obj.get("type")
                pl = obj.get("payload") or {}
                ts = obj.get("timestamp")
                day = utc_day(ts)

                if typ == "session_meta":
                    meta = pl or {}
                    path_meta[path] = meta
                    sid = sid_of(meta)
                    ap = agent_path_of(meta)
                    if ap and sid:
                        agent_meta[ap] = (meta.get("thread_source"), agent_role_of(meta), sid)
                    stats["files_meta_%s" % (meta.get("thread_source") or "NONE")] += 1
                    continue

                if typ == "event_msg":
                    pt = pl.get("type")
                    if pt in ("task_started", "task_complete", "turn_aborted"):
                        src = meta.get("thread_source") or "UNKNOWN"
                        if day:
                            lifecycle[(src, day, pt)] += 1
                        else:
                            lifecycle_missing_day[(src, pt)] += 1
                        if pt == "task_complete":
                            raw = pl.get("last_agent_message") or ""
                            txt = strip_transport(raw)
                            channel_msgs["task_complete"] += 1
                            if txt:
                                rec = _rec("task_complete", txt, ts, day, ordinal, fname, path,
                                           meta, phase=None, mt=None, author=None)
                                reports_raw.append(rec)
                                _note_msg(all_msgs, meta, ts, ordinal, txt,
                                          agent_path_of(meta), disp_records, fname)
                    elif pt == "item_completed":
                        it = pl.get("item") or {}
                        if it.get("type") == "AgentMessage":
                            raw = "".join(c.get("text", "") for c in (it.get("content") or []))
                            txt = strip_transport(raw)
                            phase = it.get("phase")
                            if phase == "final_answer":
                                channel_msgs["item_completed_final"] += 1
                            else:
                                channel_msgs["item_completed_commentary"] += 1
                            if txt:
                                rec = _rec("item_completed", txt, ts, day, ordinal, fname, path,
                                           meta, phase=phase, mt=None, author=None)
                                reports_raw.append(rec)
                                _note_msg(all_msgs, meta, ts, ordinal, txt,
                                          agent_path_of(meta), disp_records, fname)
                    elif pt == "agent_message":     # 防御性支持（全量实测 0 条）
                        stats["event_agent_message"] += 1
                        raw = "".join(c.get("text", "") for c in (pl.get("content") or []))
                        mt = (RE_MSG_TYPE.search(raw).group(1).upper() if RE_MSG_TYPE.search(raw) else None)
                        txt = strip_transport(raw)
                        channel_msgs["event_agent_message"] += 1
                        if txt:
                            rec = _rec("event_agent_message", txt, ts, day, ordinal, fname, path,
                                       meta, phase=None, mt=mt, author=pl.get("author"))
                            reports_raw.append(rec)
                            _note_msg(all_msgs, meta, ts, ordinal, txt, pl.get("author"),
                                      disp_records, fname)

                elif typ == "response_item" and pl.get("type") == "agent_message":
                    raw = "".join(c.get("text", "") for c in (pl.get("content") or []))
                    # [B] 关键: Message Type 必须在剥离头部之前解析
                    mt = (RE_MSG_TYPE.search(raw).group(1).upper() if RE_MSG_TYPE.search(raw) else None)
                    txt = strip_transport(raw)
                    author = pl.get("author")
                    channel_msgs["main_relay"] += 1
                    relay_stats[mt or "NONE"] += 1
                    if not txt:
                        relay_stats["(无明文正文:NEW_TASK/MESSAGE仅加密体)"] += 1
                    if txt:
                        rec = _rec("main_relay_agent_message", txt, ts, day, ordinal, fname, path,
                                   meta, phase=None, mt=mt, author=author, raw=raw)
                        reports_raw.append(rec)
                        _note_msg(all_msgs, meta, ts, ordinal, txt, author, disp_records, fname)

        if verbose and (i + 1) % 50 == 0:
            print("  scanned %d/%d  (%.1fs)" % (i + 1, len(files), time.time() - t0), flush=True)

    stats["files_scanned"] = len(files)
    stats["bytes_scanned"] = total_bytes
    stats["elapsed_scan_s"] = round(time.time() - t0, 2)
    # 数据快照指纹: 有序 (文件相对名|字节数) 列表的 sha1，用于判断两次重跑是否在同一份数据上
    sig = hashlib.sha1()
    for p in files:
        try:
            rel = os.path.relpath(p, SESS_ROOT)
            sig.update(("%s|%d\n" % (rel, os.path.getsize(p))).encode("utf-8", "replace"))
        except OSError:
            pass
    stats["snapshot_sha1"] = sig.hexdigest()
    return (path_meta, agent_meta, reports_raw, channel_msgs, relay_stats, lifecycle,
            lifecycle_missing_day, all_msgs, disp_records, stats)


def _rec(channel, text, ts, day, ordinal, fname, path, meta, phase, mt, author, raw=None):
    return {
        "channel": channel, "text": text, "ts": ts, "day": day, "ordinal": ordinal,
        "file": fname, "path": path, "sid": sid_of(meta),
        "src": meta.get("thread_source"), "role": agent_role_of(meta),
        "agent_path": agent_path_of(meta), "phase": phase,
        "author": author, "msg_type": mt, "raw": raw,
    }


def _note_msg(all_msgs, meta, ts, ordinal, txt, task_key, disp_records, fname):
    st, _ = status_of(txt)
    has_disp = bool(RE_DISPOSITION.search(txt))
    all_msgs[(sid_of(meta), task_key)].append(
        (ts, ordinal, norm_hash(txt), st, has_disp))
    if has_disp:
        disp_records.append((fname, sid_of(meta), ts, task_key, short(txt, 200)))


# --------------------------------------------------- 报告判定 / 去重 / 归属 ----
def build_reports(reports_raw, agent_meta):
    diag = collections.Counter()
    excluded_detail = collections.Counter()   # (owner_src, owner_role, kind) -> n
    channel_report_occ = collections.Counter()  # 通道: 判定为报告的出现次数（去重前）
    candidates = []
    all_final_hashes = set()      # 敏感性: 全部 final-answer 消息
    all4_final_hashes = set()

    def resolve_owner(r, txt_channel):
        """[E] 归属解析"""
        src, role = r["src"], r["role"]
        tk = r["agent_path"] or r["author"]
        resolved = False
        if tk and tk in agent_meta:
            ms, mr, _ = agent_meta[tk]
            if ms:
                src = ms
            if mr:
                role = mr
            resolved = True
        elif r["channel"] == "main_relay_agent_message" and tk:
            src, role = "relay_only(源会话缺失)", "(unknown)"
        return src, role, tk, resolved

    for r in reports_raw:
        txt = r["text"]
        if not txt:
            continue
        ch = r["channel"]
        # [A] final-answer 通道过滤
        if ch == "item_completed":
            if r["phase"] != "final_answer":
                diag["excluded_non_final_item"] += 1
                src, role, _, _ = resolve_owner(r, ch)
                excluded_detail[(src, role, "非final_answer(commentary)")] += 1
                continue
        elif ch in ("main_relay_agent_message", "event_agent_message"):
            if (r["msg_type"] or "") != "FINAL_ANSWER":
                diag["excluded_relay_msg_type_%s" % (r["msg_type"] or "none")] += 1
                src, role, _, _ = resolve_owner(r, ch)
                kind = {"NEW_TASK": "中继NEW_TASK(派活)", "MESSAGE": "中继MESSAGE(中途)"}.get(
                    r["msg_type"] or "none", "中继无MessageType")
                excluded_detail[(src, role, kind)] += 1
                continue
        # 通过 final-answer 过滤后的消息
        all_final_hashes.add(norm_hash(txt))
        if all(rx.search(txt) for name, rx in CORE_FIELDS):
            all4_final_hashes.add(norm_hash(txt))
        # [C] 报告判定
        if not is_report(txt):
            diag["excluded_not_a_report"] += 1
            src, role, _, _ = resolve_owner(r, ch)
            t2 = txt.lstrip()
            if t2.startswith("{"):
                kind = "JSON裁决(guardian等)"
            elif "This agent's turn failed" in t2:
                kind = "turn失败占位消息"
            else:
                kind = "散文/无字段答复"
            excluded_detail[(src, role, kind)] += 1
            continue
        channel_report_occ[ch.replace("main_relay_", "")] += 1
        src, role, tk, resolved = resolve_owner(r, ch)
        key = (r["sid"], tk)
        prod = ch in ("item_completed", "task_complete")
        candidates.append(dict(
            r, hash=norm_hash(txt), owner_src=src, owner_role=role, task_key=tk,
            status=status_of(txt)[0], owner_resolved=resolved,
            prod_key=(key if prod else None), relay_key=(key if not prod else None)))

    # [D] 去重
    by_hash = {}
    for c in candidates:
        k = c["hash"]
        if k not in by_hash:
            e = dict(c)
            e["channels"] = collections.Counter([c["channel"].replace("main_relay_", "")])
            e["occurrences"] = 1
            e["first_ts"] = c["ts"]
            e["first_day"] = c["day"]
            e["first_file"] = c["file"]
            e["first_channel"] = c["channel"]
            e["keys"] = {(c["sid"], c["task_key"])}
            e["prod_keys"] = {c["prod_key"]} if c["prod_key"] else set()
            e["relay_keys"] = {c["relay_key"]} if c["relay_key"] else set()
            e["relay_raw"] = c["raw"] if c["channel"] == "main_relay_agent_message" else None
            by_hash[k] = e
        else:
            e = by_hash[k]
            e["occurrences"] += 1
            e["channels"][c["channel"].replace("main_relay_", "")] += 1
            e["keys"].add((c["sid"], c["task_key"]))
            if c["prod_key"]:
                e["prod_keys"].add(c["prod_key"])
            if c["relay_key"]:
                e["relay_keys"].add(c["relay_key"])
            if c["channel"] == "main_relay_agent_message" and not e["relay_raw"]:
                e["relay_raw"] = c["raw"]
            if _ts_before(c["ts"], e["first_ts"]):
                e["first_ts"] = c["ts"]
                e["first_day"] = c["day"]
                e["first_file"] = c["file"]
                e["first_channel"] = c["channel"]

    unique = sorted(by_hash.values(),
                    key=lambda r: (r.get("first_day") or "9999", r.get("first_ts") or "", r["hash"]))
    alt = set((c["sid"], c["task_key"], c["hash"]) for c in candidates)
    diag["candidates"] = len(candidates)
    diag["unique_by_sha1"] = len(unique)
    diag["unique_by_sid_task_sha1"] = len(alt)
    diag["all_final_unique"] = len(all_final_hashes)
    diag["all4_final_unique"] = len(all4_final_hashes)
    return unique, channel_report_occ, diag, excluded_detail


def _ts_before(a, b):
    if not b:
        return True
    if not a:
        return False
    return a < b


# ------------------------------------------------------------- 输出小工具 ----
def table(rows, headers):
    cols = len(headers)
    widths = [max(len(str(headers[i])), max((len(str(r[i])) for r in rows), default=0)) for i in range(cols)]
    out = ["  ".join(str(headers[i]).ljust(widths[i]) for i in range(cols)),
           "  ".join("-" * widths[i] for i in range(cols))]
    for r in rows:
        out.append("  ".join(str(r[i]).ljust(widths[i]) for i in range(cols)))
    return "\n".join(out)


def pct(a, b):
    return "%.2f%%" % (100.0 * a / b) if b else "n/a"


# ------------------------------------------------------------------ 主流程 ----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    t_start = time.time()
    files = iter_files(args.limit or None, args.sample or None)
    print("scanning %d files ..." % len(files), flush=True)
    (path_meta, agent_meta, reports_raw, channel_msgs, relay_stats, lifecycle,
     lifecycle_missing_day, all_msgs, disp_records, stats) = scan(files, verbose=True)

    unique, channel_report_occ, diag, excluded_detail = build_reports(reports_raw, agent_meta)

    L = []
    w = L.append
    w("=" * 80)
    w("质量类指标独立重算  (audit_quality.py)    —— 只读原始 rollout 日志")
    w("=" * 80)
    w("脚本      : %s" % os.path.abspath(__file__))
    w("运行时间  : %s (UTC)" % dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    w("数据源    : %s\\**\\rollout-*.jsonl   (每行一个 JSON)" % SESS_ROOT)
    w("文件数    : %d    总字节: %s (%.1f MB)"
      % (stats["files_scanned"], format(stats["bytes_scanned"], ","), stats["bytes_scanned"] / 1048576.0))
    w("备注      : sessions 目录是活动日志（Codex 运行时持续追加），文件数/字节数是本次扫描时点快照，")
    w("            重跑会有少量增长（新增会话/新事件），指标口径不变。")
    w("快照指纹  : sha1(有序 相对路径|大小 列表) = %s" % stats.get("snapshot_sha1", "-"))
    w("            （两次重跑指纹相同 => 同一份数据；不同 => 目录有新增，属活动日志正常追加）")
    w("样例模式  : %s" % (("是 (--sample %d, subagent 会话)" % args.sample) if args.sample
                           else ("是 (--limit %d)" % args.limit) if args.limit else "否（全量）"))
    w("耗时      : 扫描 %.1fs / 总计 %.1fs" % (stats["elapsed_scan_s"], time.time() - t_start))
    w("口径摘要  : 每份最终报告只计一次 [D] sha1(正文归一化) 全局去重；完整口径见脚本文件头 [A]~[G]")
    w("")

    # ---------------- 0 ----------------
    w("[" + "-" * 26 + " 0. 数据清单 / 解析统计 " + "-" * 26 + "]")
    meta_files = collections.Counter()
    for p, m in path_meta.items():
        meta_files[m.get("thread_source") or "NONE"] += 1
    w("按 thread_source 的文件数 : %s" % dict(meta_files.most_common()))
    w("缺 session_meta 的文件      : %d" % (stats["files_scanned"] - sum(meta_files.values())))
    w("agent_path -> 会话 meta 映射: %d 条" % len(agent_meta))
    w("候选行外跳过的行            : %d    JSON 解析失败: %d"
      % (stats["lines_skipped"], stats["json_fail"]))
    w("event_msg.agent_message     : %d 条（任务书提到该载体；全量实测不存在，主线程中继实际在 response_item）"
      % stats["event_agent_message"])
    w("")

    # ---------------- 1 状态分布 ----------------
    w("[" + "-" * 26 + " 1. 状态分布（每份报告只计一次） " + "-" * 26 + "]")
    w("status 抽取正则: %s" % RE_STATUS.pattern)
    w("归一: 捕获组小写 -> passed/failed/blocked/unverified；其余(含未匹配) -> other")
    w("")
    w("1.1 各表示通道的条数（去重前；同一份报告会在 1~3 个表示中出现）")
    w("注: response_item.agent_message 含三种 Message Type；NEW_TASK/MESSAGE 的正文在")
    w("    encrypted_content 里，text 仅有 'Message Type:/Task name:/Sender:/Payload:' 头部(纯文本为空)，")
    w("    这类消息不可判定为报告，单独列出。")
    rows = [
        ["item_completed AgentMessage (phase=final_answer)",
         channel_msgs["item_completed_final"], channel_report_occ.get("item_completed", 0)],
        ["item_completed AgentMessage (phase=commentary, 非报告)",
         channel_msgs["item_completed_commentary"], 0],
        ["task_complete.last_agent_message",
         channel_msgs["task_complete"], channel_report_occ.get("task_complete", 0)],
        ["response_item.agent_message 合计(含三种 Message Type)",
         channel_msgs["main_relay"], channel_report_occ.get("agent_message", 0)],
        ["   其中 FINAL_ANSWER(有明文正文)", relay_stats.get("FINAL_ANSWER", 0), ""],
        ["   其中 MESSAGE(中途消息, 仅加密正文)", relay_stats.get("MESSAGE", 0), ""],
        ["   其中 NEW_TASK(派活, 仅加密正文)", relay_stats.get("NEW_TASK", 0), ""],
        ["   其中无 Message Type 头", relay_stats.get("NONE", 0), ""],
        ["event_msg.agent_message (实测 0)",
         channel_msgs["event_agent_message"], channel_report_occ.get("event_agent_message", 0)],
        ["合计", sum(channel_msgs.values()), sum(channel_report_occ.values())],
        ["去重后唯一报告数", "", len(unique)],
    ]
    w(table(rows, ["表示通道", "消息条数", "其中判定为报告"]))
    w("")
    w("1.2 去重后总体状态分布（分母 = %d 份唯一报告）" % len(unique))
    st = collections.Counter()
    other_values = collections.Counter()
    for r in unique:
        s = r["status"]
        if s in STATUS_BUCKETS:
            st[s] += 1
        else:
            st["other"] += 1
            other_values[s or "(无 status 字段)"] += 1
    total = len(unique)
    rows = [[k, st[k], pct(st[k], total)] for k in STATUS_BUCKETS]
    rows.append(["other", st["other"], pct(st["other"], total)])
    rows.append(["合计", total, "100.00%"])
    w(table(rows, ["status", "报告数", "占比"]))
    if other_values:
        w("other 明细: %s" % dict(other_values.most_common()))
        for r in unique:
            if r["status"] not in STATUS_BUCKETS:
                w("  该 other 报告: %s | channel=%s | 正文前300字:"
                  % (r["first_file"], r["first_channel"]))
                w(indent_block(r["text"], "    "))
    w("")
    w("1.3 按 UTC 日期 × 状态（去重后）")
    days = sorted({r["first_day"] for r in unique if r["first_day"]})
    rows = []
    tot_c = collections.Counter()
    for d in days:
        c = collections.Counter()
        for r in unique:
            if r["first_day"] == d:
                s = r["status"] if r["status"] in STATUS_BUCKETS else "other"
                c[s] += 1
                tot_c[s] += 1
        rows.append([d] + [c[k] for k in STATUS_BUCKETS] + [c["other"], sum(c.values())])
    rows.append(["合计"] + [tot_c[k] for k in STATUS_BUCKETS] + [tot_c["other"], sum(tot_c.values())])
    w(table(rows, ["UTC日期"] + list(STATUS_BUCKETS) + ["other", "小计"]))
    w("注: 日期为报告最早一次出现的 UTC 日；无报告的日期不在表中。")
    w("")
    w("1.4 按 thread_source 分布（去重后）")
    rows = []
    for src in sorted({r["owner_src"] or "UNKNOWN" for r in unique}):
        c = collections.Counter()
        tot = 0
        for r in unique:
            if (r["owner_src"] or "UNKNOWN") != src:
                continue
            tot += 1
            c[r["status"] if r["status"] in STATUS_BUCKETS else "other"] += 1
        rows.append([src, tot] + [c[k] for k in STATUS_BUCKETS] + [c["other"]])
    w(table(rows, ["thread_source", "报告数"] + list(STATUS_BUCKETS) + ["other"]))
    w("")
    w("1.5 按 agent_role 分布（去重后）")
    rows = []
    for role in sorted({r["owner_role"] or "(none)" for r in unique}):
        c = collections.Counter()
        tot = 0
        for r in unique:
            if (r["owner_role"] or "(none)") != role:
                continue
            tot += 1
            c[r["status"] if r["status"] in STATUS_BUCKETS else "other"] += 1
        rows.append([role, tot] + [c[k] for k in STATUS_BUCKETS] + [c["other"]])
    w(table(rows, ["agent_role", "报告数"] + list(STATUS_BUCKETS) + ["other"]))
    n_no_task = sum(1 for r in unique if not r["task_key"])
    n_no_role = sum(1 for r in unique if not r["owner_role"])
    w("task_name 无法解析的报告: %d    agent_role 无法解析: %d" % (n_no_task, n_no_role))
    if n_no_task:
        w("  task_name 缺失者: %s" % [(r["first_file"], r["owner_src"], r["status"]) for r in unique
                                     if not r["task_key"]])
    w("")

    # ---------------- 2 合规率 ----------------
    w("[" + "-" * 26 + " 2. 结构化报告合规率 " + "-" * 26 + "]")
    w("分母 = 被判定为最终报告的消息数（去重后）= %d" % len(unique))
    w("分子 = 同时包含 changed_files / evidence / assumptions / blockers 四个字段名的报告数")
    w("实际使用的字段正则（原文，含变体处理）:")
    w("  changed_files : %s" % RE_CHANGED.pattern)
    w("  evidence      : %s" % RE_EVIDENCE.pattern)
    w("  assumptions   : %s" % RE_ASSUMPT.pattern)
    w("  blockers      : %s" % RE_BLOCKERS.pattern)
    w("  reused(附列)  : %s" % RE_REUSED.pattern)
    w("变体覆盖: 行首缩进/'- '/'> '/'# ' 列表与标题符、**粗体**、'changed files' 空格写法、'assumption(s)'、'blocker(s)'、")
    w("          标签后可选括号说明、冒号或等号。标签必须位于行首(允许前缀符号)才算字段，避免正文误命中。")
    w("")
    core_hit = {name: 0 for name, _ in CORE_FIELDS}
    forms = {name: collections.Counter() for name, _ in CORE_FIELDS}
    reused_hit = 0
    all4 = 0
    all4_has_value = 0
    missing_dist = collections.Counter()
    for r in unique:
        hits = field_hits(r["text"])
        present = [name for name, _ in CORE_FIELDS if hits[name]]
        for name in present:
            core_hit[name] += 1
        if hits["reused"]:
            reused_hit += 1
        if len(present) == 4:
            all4 += 1
        n_has_value = 0
        for name, rx in CORE_FIELDS:
            f = value_form(r["text"], rx)
            forms[name][f] += 1
            if f == "has_value":
                n_has_value += 1
        if n_has_value == 4:
            all4_has_value += 1
        missing_dist[4 - len(present)] += 1
    w("2.1 主口径: 字段名出现率（要求的口径）")
    rows = [[name, core_hit[name], pct(core_hit[name], len(unique))] for name, _ in CORE_FIELDS]
    rows.append(["reused (非必需, 附列)", reused_hit, pct(reused_hit, len(unique))])
    rows.append(["四项齐全 = 分子", all4, pct(all4, len(unique))])
    rows.append(["分母", len(unique), "100.00%"])
    w(table(rows, ["字段", "出现报告数", "出现率"]))
    w("合规率(主口径) = %d / %d = %s" % (all4, len(unique), pct(all4, len(unique))))
    w("")
    w("2.1b 实际观察到的标签写法（去重后报告里匹配 span 的原文，证明变体确实存在）")
    for name, rx in CORE_FIELDS:
        seen = collections.Counter()
        for r in unique:
            m = rx.search(r["text"])
            if m:
                seen[m.group(0).strip()] += 1
        top = "，".join("%r×%d" % (k, v) for k, v in seen.most_common(6))
        w("  %-14s %s" % (name + ":", top if top else "(无)"))
    w("")
    w("2.2 补充口径: 字段值形态（区分'有名无值'）")
    rows = []
    for name, _ in CORE_FIELDS:
        f = forms[name]
        rows.append([name, f["has_value"], f["empty_list"], f["explicit_none"], f["unfilled"],
                     pct(f["has_value"], len(unique))])
    w(table(rows, ["字段", "有值", "空列表[]", "none/无", "未填", "有值率"]))
    w("四项均有值(实质齐全) = %d / %d = %s" % (all4_has_value, len(unique),
                                                pct(all4_has_value, len(unique))))
    w("缺失字段个数分布 {4-命中数: 报告数} = %s" % dict(sorted(missing_dist.items())))
    w("")
    w("2.3 敏感性: 若把'全部 final-answer 消息'都算作最终报告（含 JSON 裁决/散文答复）")
    w("    分母 = %d（唯一 final-answer 文本数），分子(四项字段齐全) = %d，合规率 = %s"
      % (diag["all_final_unique"], diag["all4_final_unique"],
         pct(diag["all4_final_unique"], diag["all_final_unique"])))
    w("说明: 本报告主口径取'带报告字段的消息'为最终报告，因为 guardian 的 {risk_level:...} 裁决、")
    w("      主线程散文答复与 'This agent's turn failed.' 占位并不是任务报告（第 6 节给出明细）。")
    w("")
    w("2.4 分天合规率（主口径）")
    rows = []
    for d in days:
        sub = [r for r in unique if r["first_day"] == d]
        if not sub:
            continue
        n4 = sum(1 for r in sub if all(rx.search(r["text"]) for name, rx in CORE_FIELDS))
        rows.append([d, len(sub), n4, pct(n4, len(sub))])
    w(table(rows, ["UTC日期", "报告数", "四项齐全", "合规率"]))
    w("")

    # ---------------- 3 unverified 收敛 ----------------
    w("[" + "-" * 26 + " 3. unverified 收敛 " + "-" * 26 + "]")
    w("判定口径: 对每份 status:unverified 的唯一报告，寻找时间更晚、正文不同(排除传输副本)")
    w("          且含 status: 字段或 disposition 字样的记录:")
    w("  A(主口径) 同一'产出线程'内：该报告在自己被产出的会话 sid + task_name 线程里的后续记录。")
    w("           任务线程键 = (sid, task_name)；子代理会话 sid + agent_path = 该子代理任务线程；")
    w("           中继副本所在的主线程 sid 不算产出线程。")
    w("  B(补充)   同一 task_name 在其它 sid 的更晚记录（跨会话；task_name 会被跨天复用，可能高估，单列）。")
    w("  C(仅参考) 同一 task_name 在主线程中继节点(主线程 sid + author)的后续记录 —— 同一名字被反复派活，")
    w("           极可能混杂不同次派发，故只作参考、不计入收敛率。")
    w("  disposition 正则: %s   status 正则见第 1 节；窗口 = 全量数据" % RE_DISPOSITION.pattern)
    w("")
    hash2text = {}
    for cand in reports_raw:
        hash2text.setdefault(norm_hash(cand["text"]), cand["text"])
    by_task = collections.defaultdict(list)
    for (sid, tk), items in all_msgs.items():
        if tk:
            for (ts, ord_, sh, st, hd) in items:
                by_task[tk].append((ts, sh, st, hd, sid))
    for k in by_task:
        by_task[k].sort(key=lambda x: x[0] or "")

    unver = [r for r in unique if r["status"] == "unverified"]
    conv_a = conv_a_disp = conv_b = conv_b_disp = conv_c = none_follow = 0
    eventual = collections.Counter()   # 后续记录里"最后一条 status"的取值
    examples = []
    for r in unver:
        ref_ts = r.get("first_ts") or ""
        prod_keys = set(r.get("prod_keys") or set())
        relay_keys = set(r.get("relay_keys") or set())
        own_sids = {k[0] for k in (prod_keys | relay_keys)}

        def later_of(key):
            out = []
            for (ts, ord_, sh, st, hd) in all_msgs.get(key, []):
                if (ts or "") > ref_ts and sh != r["hash"] and (st or hd):
                    out.append((ts, sh, st, hd, key[0]))
            return out

        # A 只认"产出线程"：必须有子代理自身会话里的 item_completed/task_complete 记录；
        # 仅有主线程中继的源会话缺失报告没有产出线程，不进 A。
        hit_a = []
        for key in prod_keys:
            hit_a += later_of(key)
        hit_b = []
        if r["task_key"]:
            for (ts, sh, st, hd, sid2) in by_task.get(r["task_key"], []):
                if ((ts or "") > ref_ts and sh != r["hash"]
                        and sid2 not in own_sids and (st or hd)):
                    hit_b.append((ts, sh, st, hd, sid2))
        hit_c = []
        for key in relay_keys:
            hit_c += later_of(key)

        chosen = None
        if hit_a:
            conv_a += 1
            if any(e[3] for e in hit_a):
                conv_a_disp += 1
            chosen = sorted(hit_a)[-1]
            if len([x for x in examples if x[1] == "A"]) < 2:
                examples.append((r, "A", sorted(hit_a)[0]))
        elif hit_b:
            conv_b += 1
            if any(e[3] for e in hit_b):
                conv_b_disp += 1
            chosen = sorted(hit_b)[-1]
            if len([x for x in examples if x[1] == "B"]) < 2:
                examples.append((r, "B", sorted(hit_b)[0]))
        if hit_c:
            conv_c += 1
        if chosen is not None:
            eventual[chosen[2] or "(disposition)"] += 1
        elif not hit_c:
            none_follow += 1
    rows = [
        ["unverified 唯一报告数", len(unver)],
        ["A 同一产出线程内后续出现 status 记录(正文不同)", conv_a],
        ["   其中后续出现 disposition", conv_a_disp],
        ["B 仅跨会话同 task_name 出现后续 status 记录", conv_b],
        ["   其中后续出现 disposition", conv_b_disp],
        ["C [仅参考] 主线程中继同名 task 的后续记录(可能混不同次派发)", conv_c],
        ["A/B/C 都没有后续记录", none_follow],
        ["收敛率 A(主口径)", pct(conv_a, len(unver))],
        ["收敛率 A+B(次口径)", pct(conv_a + conv_b, len(unver))],
    ]
    w(table(rows, ["项", "值"]))
    w("")
    w("3.1 有后续记录的 unverified 报告：其'最后一条后续 status'分布（判断是否真的走出 unverified）")
    if eventual:
        tot_ev = sum(eventual.values())
        rows = [[k, v, pct(v, tot_ev)] for k, v in eventual.most_common()]
        w(table(rows, ["最后一条后续 status", "报告数", "占有后续记录者比例"]))
        still_unv = eventual.get("unverified", 0)
        resolved = tot_ev - still_unv
        w("仍以 unverified 收尾: %d / %d = %s；后续转为其它状态: %d / %d = %s"
          % (still_unv, tot_ev, pct(still_unv, tot_ev), resolved, tot_ev, pct(resolved, tot_ev)))
    else:
        w("  （无后续记录）")
    w("")
    w("3.2 全量正文含 disposition 字样的记录（共 %d 条）" % len(disp_records))
    if disp_records:
        for (f, sid, ts, tk, snip) in disp_records[:8]:
            w("  文件=%s  sid=%s  ts=%s  task=%s" % (f, sid, ts, tk))
            w("    片段: %s" % snip.replace("\n", " "))
    else:
        w("  （无：%d 个会话文件里没有任何一条消息正文包含 disposition 字段或字样）" % stats["files_scanned"])
    w("")
    if examples:
        w("3.3 收敛样本（unverified 报告 -> 找到的后续记录；附后续记录 status 与正文以核对）")
        for i, (r, src_kind, hit) in enumerate(examples, 1):
            w("  样本 %d [口径 %s]" % (i, src_kind))
            w("    unverified 报告: ts=%s  task=%s  产出/中继 sid=%s"
              % (r.get("first_ts"), r.get("task_key"),
                 "/".join(sorted({k[0] for k in r["keys"]}))))
            w("    后续记录      : ts=%s  sid=%s  status=%s"
              % (hit[0], hit[4], hit[2] or "(无 status)"))
            t = hash2text.get(hit[1])
            if t:
                w("    后续记录正文前160字: %s" % short(t, 160).replace("\n", " | "))
            w("")
    w("说明: '后续 status 记录'是同一子代理任务线程被追加任务后产生的新报告；")
    w("      若后续最后一条仍是 unverified，说明该任务没有在该线程内收敛。")
    w("")

    # ---------------- 4 turn 生命周期 ----------------
    w("[" + "-" * 26 + " 4. turn 生命周期 " + "-" * 26 + "]")
    w("事件: event_msg.payload.type ∈ {task_started, task_complete, turn_aborted}")
    w("thread_source: 承载事件的会话 session_meta.thread_source；日期: 事件 timestamp 的 UTC 天")
    w("完成率 = task_complete/task_started；中断率 = turn_aborted/task_started；")
    w("未闭合率 = 1-(task_complete+turn_aborted)/task_started（负数表示 complete 多于 started，即日志跨文件截断）")
    w("")
    srcs = sorted({k[0] for k in lifecycle})
    day_set = sorted({k[1] for k in lifecycle})
    rows = []
    agg = collections.Counter()
    for src in srcs:
        for d in day_set:
            s = lifecycle[(src, d, "task_started")]
            c = lifecycle[(src, d, "task_complete")]
            a = lifecycle[(src, d, "turn_aborted")]
            if not (s or c or a):
                continue
            rows.append([src, d, s, c, a, pct(c, s), pct(a, s),
                         ("%.2f%%" % (100.0 * (1 - (c + a) / s))) if s else "n/a"])
            agg[(src, "s")] += s
            agg[(src, "c")] += c
            agg[(src, "a")] += a
    w("4.1 按 thread_source × UTC 日期")
    w(table(rows, ["thread_source", "UTC日期", "started", "complete", "aborted",
                   "完成率", "中断率", "未闭合率"]))
    w("")
    w("4.2 按 thread_source 汇总")
    rows = []
    for src in srcs:
        s, c, a = agg[(src, "s")], agg[(src, "c")], agg[(src, "a")]
        rows.append([src, s, c, a, pct(c, s), pct(a, s),
                     ("%.2f%%" % (100.0 * (1 - (c + a) / s))) if s else "n/a"])
    S = sum(agg[(x, "s")] for x in srcs)
    C = sum(agg[(x, "c")] for x in srcs)
    A = sum(agg[(x, "a")] for x in srcs)
    rows.append(["合计", S, C, A, pct(C, S), pct(A, S),
                 ("%.2f%%" % (100.0 * (1 - (C + A) / S))) if S else "n/a"])
    w(table(rows, ["thread_source", "started", "complete", "aborted", "完成率", "中断率", "未闭合率"]))
    if lifecycle_missing_day:
        w("缺 timestamp 无法归日的事件: %s" % dict(lifecycle_missing_day))
    w("")
    w("4.3 turn_aborted 明细（共 %d 条，列出 thread_source 与日期）" % A)
    ab = [[k[0], k[1], v] for k, v in sorted(lifecycle.items()) if k[2] == "turn_aborted"]
    if ab:
        w(table(ab, ["thread_source", "UTC日期", "turn_aborted"]))
    w("")

    # ---------------- 5 原始样本 ----------------
    w("[" + "-" * 26 + " 5. 原始报告文本片段样本 (每条 <=300 字) " + "-" * 26 + "]")
    w("样本全部由脚本从原始 jsonl 抽出，保留原始换行；同时打印命中的字段标签原文。")
    w("每份样本只展示正文前 300 个字符。")
    w("")
    picks = []
    for s in ("passed", "unverified", "failed", "blocked"):
        cand = sorted([r for r in unique if r["status"] == s], key=lambda r: len(r["text"]))
        if cand:
            picks.append(("status=" + s, cand[0]))
    relay_c = [r for r in unique if r.get("relay_raw") and r["hash"] not in {x[1]["hash"] for x in picks}]
    if relay_c:
        # 优先取"只在中继里出现过"的报告，证明中继通道自身也能被独立识别
        only_relay = [r for r in relay_c if r["occurrences"] == 1]
        rr = sorted(only_relay or relay_c, key=lambda r: len(r["text"]))[0]
        picks.append(("主线程中继通道原文(含 Message Type 头)", rr))
    other_r = [r for r in unique if r["status"] not in STATUS_BUCKETS]
    if other_r:
        picks.append(("唯一一份四字段不全的报告", other_r[0]))
    for n, (tag, r) in enumerate(picks, 1):
        st_raw, st_span = status_of(r["text"])
        hits = field_hits(r["text"])
        w("样本 %d  [%s]" % (n, tag))
        w("  来源文件: %s" % r.get("first_file"))
        w("  首次通道: %s   出现通道: %s   出现次数: %d"
          % (r.get("first_channel"), "/".join(sorted(r["channels"].keys())), r["occurrences"]))
        w("  phase=%s  msg_type=%s  task_name=%s" % (r.get("phase"), r.get("msg_type"), r.get("task_key")))
        w("  thread_source=%s  agent_role=%s  首次出现UTC=%s"
          % (r.get("owner_src"), r.get("owner_role"), r.get("first_ts")))
        w("  status 抽取: %s   (匹配 span: %s)" % (st_raw if st_raw else "(无)", st_span if st_span else "-"))
        w("  字段标签命中: " + "; ".join("%s=%s" % (k, v if v else "(未命中)") for k, v in hits.items()))
        if tag.startswith("主线程中继"):
            w("  原始记录文本前300字（含 Message Type/Task name/Sender/Payload 头）:")
            w(indent_block(r["relay_raw"], "    "))
        else:
            w("  原始报告正文前300字（子代理会话 AgentMessage 原文，换行保留）:")
            w(indent_block(r["text"], "    "))
        w("")
    w("")

    # ---------------- 6 去重与口径自检 ----------------
    w("[" + "-" * 26 + " 6. 去重与口径自检 " + "-" * 26 + "]")
    rows = [
        ["final-answer 通道中判定为报告的出现次数(去重前)", diag["candidates"]],
        ["去重后唯一报告数 [主口径 sha1]", diag["unique_by_sha1"]],
        ["去重后唯一报告数 [(sid,task_name,sha1) 次口径]", diag["unique_by_sid_task_sha1"]],
        ["被排除: item_completed 非 final_answer(commentary)", diag["excluded_non_final_item"]],
        ["被排除: 中继 NEW_TASK(仅有加密正文, 无明文, 不可判定)", relay_stats.get("NEW_TASK", 0)],
        ["被排除: 中继 MESSAGE(仅有加密正文, 无明文, 不可判定)", relay_stats.get("MESSAGE", 0)],
        ["被排除: 中继无 Message Type 头", relay_stats.get("NONE", 0)],
        ["被排除: 通过通道过滤但无任何报告字段", diag["excluded_not_a_report"]],
    ]
    w(table(rows, ["项", "值"]))
    w("")
    w("6.1 被排除的 final-answer 消息明细（按归属 × 形态）")
    rows = [[k[0], k[1], k[2], v] for k, v in sorted(excluded_detail.items(), key=lambda x: -x[1])]
    w(table(rows, ["thread_source", "agent_role", "形态", "条数(含传输副本)"]))
    w("")
    w("6.2 每份报告的出现次数分布 {出现次数: 报告数} = %s"
      % dict(sorted(collections.Counter(r["occurrences"] for r in unique).items())))
    w("6.3 通道组合分布 = %s"
      % dict(collections.Counter("+".join(sorted(r["channels"].keys())) for r in unique).most_common()))
    merged = sum(1 for r in unique if "agent_message" in r["channels"])
    w("其中同时出现于主线程中继通道的报告: %d / %d" % (merged, len(unique)))
    w("")
    w("6.4 重要防误计说明")
    w("  * 每个会话首条 user 消息都含 AGENTS.md 全文，其中出现 'changed_files' 等字段名示例。")
    w("    脚本只从 final-answer 通道取报告；role=user/developer 的消息与 world_state 快照一律不计，")
    w("    否则纯子串匹配会把数百条模板说明误判成报告。")
    w("  * item_completed(AgentMessage) / task_complete.last_agent_message 是同一份最终答复的两种落盘表示；")
    w("    response_item.assistant 消息是第三种(内容相同, 故不单独取)；主线程 response_item.agent_message")
    w("    是第四种中继表示。四者剥离头部后同 sha1，去重后只算一次。")
    w("  * guardian_review 的 {risk_level:...} JSON 裁决不是任务报告，不计入分母。")
    w("")
    w("6.5 交叉校验：用最简判定(正文首行即 'status:')独立数一遍报告，与本脚本口径对比")
    naive = re.compile(r"(?i)^\s*status\s*:")
    naive_n = sum(1 for r in unique if naive.match(r["text"]))
    kinds = collections.Counter()
    for r in unique:
        if naive.match(r["text"]):
            continue
        t = r["text"].lstrip()
        if t.startswith("```"):
            kinds["正文包在 ``` 代码围栏里(status 在第 2 行)"] += 1
        elif not status_of(r["text"])[0]:
            kinds["无 status 字段(只有其它字段)"] += 1
        else:
            kinds["散文开头、字段块内嵌在后文"] += 1
    w("  最简判定命中: %d   本脚本(含围栏/列表符/粗体/括号说明/空格写法/内嵌字段): %d   差额: %d"
      % (naive_n, len(unique), len(unique) - naive_n))
    w("  差额构成: %s" % dict(kinds.most_common()))
    w("  另: 用一份独立最小实现(只解析 event_msg 的 task_started/task_complete/turn_aborted)复核，")
    w("      事件总数与本报告 4.2 一致；两次复核之间的微小差异来自活动日志持续追加。")
    w("")
    w("可复现: 全量 `python -X utf8 C:\\Users\\Administrator\\audit_quality.py`；")
    w("        小样本 `--sample 8`（前 8 个 subagent 会话）或 `--limit 10`。脚本无随机性，结果确定。")

    text = "\n".join(L) + "\n"
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(text)
    print("written: %s" % args.out)


if __name__ == "__main__":
    main()
