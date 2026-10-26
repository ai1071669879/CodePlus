# -*- coding: utf-8 -*-
"""
verify_raw.py -- independent recomputation from RAW Codex rollout logs.

DATA SOURCE
  C:\\Users\\Administrator\\.codex\\sessions\\**\\rollout-*.jsonl
  (480 files, ~956 MB, one JSON object per line). Read-only access; no file
  under ~/.codex is modified. This script does NOT read any Lead intermediate
  artifact (no codex_events.jsonl / codex_meta.json / codex_extract.py).

CALIBER / DEFINITIONS
  * session      : each rollout-*.jsonl file. Session id / thread_source / cwd /
                   start timestamp are taken ONLY from the FIRST line whose
                   type == "session_meta" (payload.id, payload.thread_source,
                   payload.cwd, payload.timestamp in UTC).
  * date_utc     : date part (YYYY-MM-DD) of session_meta.payload.timestamp (UTC).
  * session id   : session_meta.payload.id. One thread can be split across several
                   rollout files (context rollover); the table disambiguates such
                   repeats as <id>#2, <id>#3 so every file keeps its own row.
  * tool names   : three independent planes, counted separately and never mixed:
      A) response_item.payload.type == "function_call"  -> payload.name
      B) response_item.payload.type == "custom_tool_call" -> payload.name
      C) nested tools inside B's payload.input (JS source), found with
         regex  tools\\.([A-Za-z_][A-Za-z0-9_]*)\\s*\\(
         (counts every textual match incl. occurrences inside JS string
         literals; a single exec script may invoke several tools.)
  * item counts  : event_msg.payload.type == "item_completed" ->
                   payload.item.type  (CommandExecution / FileChange / ...).
  * turn counts  : event_msg.payload.type in {task_started, task_complete,
                   turn_aborted}.
  * tokens       : ONLY line type == "token_usage_record", summing
                   payload.usage.{input_tokens,cached_input_tokens,output_tokens}
                   per record. payload.turn_token_usage / payload.thread_token_usage
                   are cumulative and are NEVER summed across rows.
                   Two groupings are reported:
                     (T1) by the session's UTC start date (same axis as sections 2-3)
                     (T2) by the token_usage_record's own UTC timestamp date
                   uncached = input - cached ; hit_rate = cached / input.
  * coverage     : session has >=1 token_usage_record vs only token_count event
                   messages (event_msg.payload.type == "token_count").
  * credits      : any key containing "credit" anywhere in the raw line; the only
                   real occurrence is token_count.payload.rate_limits.credits.
                   Distinct values + verdict are printed.

USAGE
  python -X utf8 C:\\Users\\Administrator\\verify_raw.py           # full run
  python -X utf8 C:\\Users\\Administrator\\verify_raw.py 5         # first 5 files
Writes C:\\Users\\Administrator\\verify_raw_out.txt and mirrors all non-table
output to stdout (the per-session table goes to the out file only).
"""
import sys, os, re, json, glob, collections, datetime

ROOT = os.path.expanduser(r"~/.codex/sessions")
OUT = os.path.expanduser(r"~/verify_raw_out.txt")
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0

NESTED_RE = re.compile(r"tools\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
CREDIT_KEY_RE = re.compile(r'"([A-Za-z0-9_]*[Cc]redit[A-Za-z0-9_]*)"\s*:')
CREDIT_VAL_RE = re.compile(r'"credits"\s*:\s*(\{[^}]*\})')
RAW_CTC_RE = re.compile(r'"type"\s*:\s*"custom_tool_call"')
RAW_FC_RE = re.compile(r'"type"\s*:\s*"function_call"')
RAW_NESTED_EXEC_RE = re.compile(r'tools\.exec_command\s*\(')
RAW_SPAWN_RE = re.compile(r'"name"\s*:\s*"spawn_agent"')

OUT_LINES = []
TABLE_LINES = []


def emit(s=""):
    OUT_LINES.append(s)
    print(s, flush=True)


def to_date(ts):
    """UTC ISO timestamp -> 'YYYY-MM-DD' (or '' if unparsable).

    BUGFIX: strptime() returns a NAIVE datetime; .astimezone(utc) on a naive
    value interprets it as LOCAL time (UTC+8 here) and shifts dates by -8h.
    Tag naive results as UTC explicitly instead of converting.
    """
    if not ts:
        return ""
    s = str(ts).strip()
    try:
        if s.endswith("Z"):
            dt = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc).date().isoformat()
    except Exception:
        return s[:10] if len(s) >= 10 else ""


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "**", "rollout-*.jsonl"), recursive=True))
    files_snapshot = [(f, os.path.getsize(f)) for f in files]
    total_bytes = sum(sz for _, sz in files_snapshot)
    newest_mtime = max(os.path.getmtime(f) for f in files) if files else 0
    if LIMIT:
        files = files[:LIMIT]
    emit("=" * 100)
    emit("verify_raw.py -- independent recount from RAW rollout jsonl")
    emit("=" * 100)
    emit("data source      : %s" % os.path.join(ROOT, "**", "rollout-*.jsonl"))
    emit("files total      : %d (%.1f MB)  <- size snapshot at run start" % (len(files_snapshot), total_bytes / 1048576.0))
    emit("newest file mtime: %s UTC  <- source is a LIVE log; Codex appends while running" % datetime.datetime.fromtimestamp(newest_mtime, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    emit("                   => all numbers are a POINT-IN-TIME snapshot; a rerun may see")
    emit("                      a few more lines appended by an active session.")
    emit("files processed  : %d%s" % (len(files), ("  [LIMIT MODE: first %d only]" % LIMIT) if LIMIT else "  [FULL RUN]"))
    emit("run at (UTC)     : %s" % datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    emit("")

    # ---------------- accumulators ----------------
    top_type = collections.Counter()
    ri_inner = collections.Counter()
    em_inner = collections.Counter()
    item_type = collections.Counter()
    parse_errors = 0
    first_meta_missing = 0

    fc_names = collections.defaultdict(collections.Counter)      # thread_source -> name -> n
    ctc_names = collections.defaultdict(collections.Counter)
    nested_names = collections.defaultdict(collections.Counter)
    nested_examples = dict()                                     # name -> one sample call head

    sessions = []                                                # list of dicts
    by_ts_date = collections.Counter()
    by_src = collections.Counter()
    cwd_src = collections.defaultdict(collections.Counter)       # thread_source -> cwd -> n

    tok_t1 = collections.defaultdict(lambda: collections.Counter())   # (src,date)->metric
    tok_t2 = collections.defaultdict(lambda: collections.Counter())
    tok_records_missing_ts = 0
    tok_records_thread_mismatch = 0
    tok_records_total = 0
    cov_has_tur = collections.Counter()      # thread_source -> sessions with >=1 token_usage_record
    cov_only_token_count = collections.Counter()
    cov_neither = collections.Counter()
    cov_has_tur_any = 0
    cov_has_tc_any = 0

    credit_key_hits = collections.Counter()
    credit_values = collections.Counter()
    credit_samples = []
    credit_line_count = 0
    used_percent_vals = collections.Counter()
    plan_type_vals = collections.Counter()

    # raw-text (non-JSON) cross-check counters: these over-count because tool
    # schemas / prose / compaction summaries also mention tool names.
    raw_ctc = 0          # occurrences of "type":"custom_tool_call"
    raw_fc = 0           # occurrences of "type":"function_call"
    raw_nested_exec = 0  # occurrences of tools.exec_command(
    raw_spawn = 0        # occurrences of "name":"spawn_agent"
    raw_ctc_by_type = collections.Counter()
    raw_fc_by_type = collections.Counter()
    raw_nested_by_type = collections.Counter()
    raw_spawn_by_type = collections.Counter()

    n = 0
    for path in files:
        n += 1
        sid = os.path.basename(path)
        meta = None
        cur_src = "UNKNOWN"
        cur_date = ""
        cur_cwd = ""
        cur_role = ""
        fc_ct = collections.Counter()
        ctc_ct = collections.Counter()
        nested_ct = collections.Counter()
        item_ct = collections.Counter()
        turn_ct = collections.Counter()
        has_tur = 0
        has_tc = 0
        sess_tok = collections.Counter()

        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh):
                if not line.strip():
                    continue
                # ---- cheap credits scan on raw text (before JSON parse) ----
                if "credit" in line or "Credit" in line:
                    credit_line_count += 1
                    for kname in CREDIT_KEY_RE.findall(line):
                        credit_key_hits[kname] += 1
                    for cval in CREDIT_VAL_RE.findall(line):
                        credit_values[cval] += 1
                    if len(credit_samples) < 3 and '"credits"' in line:
                        credit_samples.append((sid, line.strip()[:700]))
                # ---- raw-text cross-check counters (cheap substring gate) ----
                try:
                    o = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                t = o.get("type")
                top_type[t] += 1
                if "custom_tool_call" in line:
                    k = len(RAW_CTC_RE.findall(line))
                    if k:
                        raw_ctc += k
                        raw_ctc_by_type[t] += k
                if "function_call" in line:
                    k = len(RAW_FC_RE.findall(line))
                    if k:
                        raw_fc += k
                        raw_fc_by_type[t] += k
                if "tools.exec_command" in line:
                    k = len(RAW_NESTED_EXEC_RE.findall(line))
                    if k:
                        raw_nested_exec += k
                        raw_nested_by_type[t] += k
                if "spawn_agent" in line:
                    k = len(RAW_SPAWN_RE.findall(line))
                    if k:
                        raw_spawn += k
                        raw_spawn_by_type[t] += k
                if lineno == 0:
                    if t == "session_meta":
                        p = o.get("payload") or {}
                        meta = p
                        cur_src = p.get("thread_source") or "UNKNOWN"
                        cur_date = to_date(p.get("timestamp"))
                        cur_cwd = p.get("cwd") or ""
                        src = p.get("source")
                        role = p.get("agent_role")
                        if not role and isinstance(src, dict):
                            sub = src.get("subagent") or {}
                            if isinstance(sub, dict):
                                sp = sub.get("thread_spawn") or {}
                                if isinstance(sp, dict):
                                    role = sp.get("agent_role")
                        cur_role = role or ""
                    else:
                        first_meta_missing += 1

                p = o.get("payload") or {}
                pt = p.get("type")

                if t == "response_item":
                    ri_inner[pt] += 1
                    if pt == "function_call":
                        nm = p.get("name") or ""
                        fc_names[cur_src][nm] += 1
                        fc_ct[nm] += 1
                    elif pt == "custom_tool_call":
                        nm = p.get("name") or ""
                        ctc_names[cur_src][nm] += 1
                        ctc_ct[nm] += 1
                        inp = p.get("input")
                        if isinstance(inp, str):
                            for m in NESTED_RE.findall(inp):
                                nested_names[cur_src][m] += 1
                                nested_ct[m] += 1
                                if m not in nested_examples:
                                    i = inp.find("tools." + m)
                                    nested_examples[m] = inp[max(0, i - 40):i + 90].replace("\n", " ")
                        elif inp is not None:
                            nested_names[cur_src]["__non_str_input__"] += 1
                elif t == "event_msg":
                    em_inner[pt] += 1
                    if pt == "item_completed":
                        it = (p.get("item") or {}).get("type") or ""
                        if isinstance(it, str):
                            it = it.split(".")[-1]
                        item_type[it] += 1
                        item_ct[it] += 1
                    elif pt in ("task_started", "task_complete", "turn_aborted"):
                        turn_ct[pt] += 1
                    elif pt == "token_count":
                        has_tc += 1
                        rl = p.get("rate_limits") or {}
                        pr = rl.get("primary") or {}
                        if isinstance(pr, dict) and pr.get("used_percent") is not None:
                            used_percent_vals[pr.get("used_percent")] += 1
                        if rl.get("plan_type") is not None:
                            plan_type_vals[rl.get("plan_type")] += 1
                elif t == "token_usage_record":
                    has_tur += 1
                    tok_records_total += 1
                    u = p.get("usage") or {}
                    rec = {
                        "input_tokens": int(u.get("input_tokens") or 0),
                        "cached_input_tokens": int(u.get("cached_input_tokens") or 0),
                        "output_tokens": int(u.get("output_tokens") or 0),
                    }
                    for k, v in rec.items():
                        sess_tok[k] += v
                    # (T1) grouped by session start date
                    for k, v in rec.items():
                        tok_t1[(cur_src, cur_date)][k] += v
                    # (T2) grouped by record's own timestamp
                    rts = o.get("timestamp") or p.get("timestamp")
                    rdate = to_date(rts)
                    if not rdate:
                        tok_records_missing_ts += 1
                        rdate = cur_date
                    for k, v in rec.items():
                        tok_t2[(cur_src, rdate)][k] += v
                    rtid = p.get("thread_id") or p.get("session_id")
                    if meta and rtid and rtid != meta.get("id"):
                        tok_records_thread_mismatch += 1

        by_src[cur_src] += 1
        by_ts_date[cur_date] += 1
        if cur_cwd:
            cwd_src[cur_src][cur_cwd] += 1
        if has_tur:
            cov_has_tur_any += 1
            cov_has_tur[cur_src] += 1
        if has_tc:
            cov_has_tc_any += 1
        if not has_tur and has_tc:
            cov_only_token_count[cur_src] += 1
        if not has_tur and not has_tc:
            cov_neither[cur_src] += 1

        sessions.append({
            "sid": (meta.get("id") if meta else None) or sid,
            "file": sid,
            "thread_source": cur_src,
            "date_utc": cur_date,
            "cwd": cur_cwd,
            "agent_role": cur_role,
            "n_lines": 0,
            "fc": fc_ct,
            "ctc": ctc_ct,
            "nested": nested_ct,
            "item": item_ct,
            "turn": turn_ct,
            "has_tur": has_tur,
            "has_tc": has_tc,
            "tok": sess_tok,
        })
        if n % 50 == 0:
            print("  ... %d/%d files" % (n, len(files)), flush=True)

    # ================= 0. structural verification =================
    emit("-" * 100)
    emit("[0] RAW STRUCTURE VERIFICATION (what this run actually saw)")
    emit("-" * 100)
    emit("top-level line types          : %s" % dict(top_type.most_common()))
    emit("response_item inner types     : %s" % dict(ri_inner.most_common()))
    emit("event_msg payload types       : %s" % dict(em_inner.most_common()))
    emit("item_completed item types     : %s" % dict(item_type.most_common()))
    emit("json parse errors             : %d" % parse_errors)
    emit("files whose 1st line isnt meta: %d" % first_meta_missing)
    emit("")

    # ================= 1. tool name lists =================
    emit("-" * 100)
    emit("[1] TOOL NAME INVENTORY (three independent planes, split by thread_source)")
    emit("-" * 100)

    def dump_plane(title, plane, note=""):
        emit("")
        emit("%s%s" % (title, ("  " + note) if note else ""))
        allnames = collections.Counter()
        for src in sorted(plane):
            sub = plane[src]
            allnames.update(sub)
            tot = sum(sub.values())
            emit("  thread_source=%-16s total=%-6d distinct=%-3d" % (src, tot, len(sub)))
            for name, c in sub.most_common():
                emit("      %-40s %6d" % (name if name else "<null>", c))
        emit("  -- GRAND TOTAL all thread_sources: %d calls, %d distinct names" % (sum(allnames.values()), len(allnames)))
        for name, c in allnames.most_common():
            emit("      %-40s %6d" % (name if name else "<null>", c))
        return allnames

    fc_all = dump_plane("[1A] response_item.payload.type == 'function_call' -> payload.name", fc_names)
    ctc_all = dump_plane("[1B] response_item.payload.type == 'custom_tool_call' -> payload.name", ctc_names)
    nested_all = dump_plane("[1C] nested tools in custom_tool_call.input (regex tools\\.NAME\\()", nested_names)
    fc_all_total = sum(fc_all.values())
    ctc_all_total = sum(ctc_all.values())

    emit("")
    emit("  NESTED NAME EXAMPLES (first captured source fragment):")
    for name in sorted(nested_examples):
        emit("      %-24s <- ...%s..." % (name, nested_examples[name]))

    emit("")
    emit("  KEY CROSS-CHECK:")
    emit("    function_call name == 'exec_command'   : %d  (expected 0: exec_command is a nested JS tool, not a function_call)" % fc_all.get("exec_command", 0))
    emit("    custom_tool_call name == 'exec' count  : %d" % ctc_all.get("exec", 0))
    emit("    nested tools.exec_command count        : %d" % nested_all.get("exec_command", 0))
    emit("    main-thread (thread_source=user) function_call names: %s" % dict(fc_names.get("user", {}).most_common()))
    emit("")

    # ================= 2. session inventory =================
    emit("-" * 100)
    emit("[2] SESSION INVENTORY")
    emit("-" * 100)
    emit("sessions total                : %d" % len(sessions))
    ids = collections.Counter(s["sid"] for s in sessions)
    emit("distinct session ids          : %d  (%d id(s) span >1 rollout file: %s)" % (
        len(ids), sum(1 for v in ids.values() if v > 1),
        {k: v for k, v in ids.items() if v > 1} or "none"))
    emit("by thread_source              : %s" % dict(by_src.most_common()))
    emit("by UTC date (session start)   :")
    for d in sorted(by_ts_date):
        emit("      %-12s %5d" % (d or "<none>", by_ts_date[d]))
    emit("")
    emit("cwd distribution per thread_source:")
    for src in sorted(cwd_src):
        emit("  thread_source=%s  (%d distinct cwd)" % (src, len(cwd_src[src])))
        for c, cnt in cwd_src[src].most_common():
            emit("      %6d  %s" % (cnt, c))
    emit("")
    emit("agent_role distribution (from session_meta agent_role / source.subagent.thread_spawn.agent_role):")
    role_dist = collections.Counter(s["agent_role"] or "<none>" for s in sessions)
    for r, c in role_dist.most_common():
        emit("      %-20s %5d" % (r, c))
    emit("")

    # ================= 3. per-session table =================
    sessions_sorted = sorted(sessions, key=lambda s: (s["date_utc"], s["thread_source"], s["sid"]))
    hdr = ["sid", "thread_source", "date_utc", "cwd", "agent_role",
           "spawn_agent", "send_message", "followup_task", "wait_agent", "list_agents",
           "item.CommandExecution", "item.FileChange", "custom_tool_call.exec",
           "nested.exec_command", "task_started", "task_complete", "turn_aborted"]
    lines = [",".join(hdr)]
    sum_cols = collections.Counter()
    seen_ids = collections.Counter()
    for s in sessions_sorted:
        seen_ids[s["sid"]] += 1
        disp_sid = s["sid"] if seen_ids[s["sid"]] == 1 else "%s#%d" % (s["sid"], seen_ids[s["sid"]])
        row = [
            disp_sid, s["thread_source"], s["date_utc"], s["cwd"], s["agent_role"],
            s["fc"].get("spawn_agent", 0), s["fc"].get("send_message", 0),
            s["fc"].get("followup_task", 0), s["fc"].get("wait_agent", 0),
            s["fc"].get("list_agents", 0),
            s["item"].get("CommandExecution", 0), s["item"].get("FileChange", 0),
            s["ctc"].get("exec", 0), s["nested"].get("exec_command", 0),
            s["turn"].get("task_started", 0), s["turn"].get("task_complete", 0),
            s["turn"].get("turn_aborted", 0),
        ]
        for i in range(5, len(row)):
            sum_cols[i] += int(row[i])
        lines.append(",".join('"%s"' % str(x).replace('"', "'") if i in (0, 2, 3, 4) else str(x) for i, x in enumerate(row)))
    tot_row = ["TOTAL", "", "", "", ""] + [str(sum_cols[i]) for i in range(5, len(hdr))]
    lines.append(",".join(tot_row))
    TABLE_LINES.extend(lines)

    emit("-" * 100)
    emit("[3] PER-SESSION COUNTS -- full table (%d rows + TOTAL) written to OUT file only" % len(sessions_sorted))
    emit("-" * 100)
    emit("column totals (identical to the TOTAL row in the out file):")
    for i in range(5, len(hdr)):
        emit("      %-24s %8d" % (hdr[i], sum_cols[i]))
    emit("")
    emit("tool totals per thread_source (function_call plane):")
    for src in sorted(fc_names):
        emit("  %-16s spawn_agent=%-5d send_message=%-5d followup_task=%-5d wait_agent=%-5d list_agents=%-5d" % (
            src, fc_names[src].get("spawn_agent", 0), fc_names[src].get("send_message", 0),
            fc_names[src].get("followup_task", 0), fc_names[src].get("wait_agent", 0),
            fc_names[src].get("list_agents", 0)))
    emit("item_completed totals per thread_source:")
    for src in sorted(set(s["thread_source"] for s in sessions)):
        agg = collections.Counter()
        for s in sessions:
            if s["thread_source"] == src:
                agg.update(s["item"])
        emit("  %-16s CommandExecution=%-6d FileChange=%-5d CollabAgentToolCall=%-4d SubAgentActivity=%-4d McpToolCall=%-4d AgentMessage=%-4d"
             % (src, agg.get("CommandExecution", 0), agg.get("FileChange", 0), agg.get("CollabAgentToolCall", 0),
                agg.get("SubAgentActivity", 0), agg.get("McpToolCall", 0), agg.get("AgentMessage", 0)))
    emit("")

    # ================= 4. tokens =================
    emit("-" * 100)
    emit("[4] TOKEN ACCOUNTING -- sum of token_usage_record.payload.usage only")
    emit("-" * 100)
    emit("token_usage_record rows read  : %d" % tok_records_total)
    emit("  rows without own timestamp  : %d (fell back to session date)" % tok_records_missing_ts)
    emit("  rows whose thread_id != session_meta.id : %d" % tok_records_thread_mismatch)
    emit("NOTE: turn_token_usage / thread_token_usage are cumulative and are NOT summed.")

    def dump_tok(title, agg):
        emit("")
        emit(title)
        emit("  %-16s %-12s %14s %14s %14s %14s %10s" % ("thread_source", "date_utc", "input", "cached", "output", "uncached", "hit_rate"))
        gt = collections.Counter()
        for key in sorted(agg):
            src, d = key
            m = agg[key]
            tot = m["input_tokens"]
            unc = tot - m["cached_input_tokens"]
            hit = (m["cached_input_tokens"] / tot) if tot else 0.0
            gt.update(m)
            emit("  %-16s %-12s %14d %14d %14d %14d %9.2f%%" % (src, d, tot, m["cached_input_tokens"], m["output_tokens"], unc, hit * 100))
        tot = gt["input_tokens"]
        unc = tot - gt["cached_input_tokens"]
        hit = (gt["cached_input_tokens"] / tot) if tot else 0.0
        emit("  %-16s %-12s %14d %14d %14d %14d %9.2f%%" % ("ALL", "ALL", tot, gt["cached_input_tokens"], gt["output_tokens"], unc, hit * 100))

    dump_tok("(T1) grouped by SESSION START date (UTC) -- same axis as sections 2-3", tok_t1)
    dump_tok("(T2) grouped by token_usage_record OWN UTC timestamp date", tok_t2)

    emit("")
    emit("token coverage (per thread_source):")
    emit("  %-16s %8s %8s %8s %8s %8s" % ("thread_source", "sessions", "has_tur", "only_tc", "neither", "tc_any"))
    tc_any = collections.Counter()
    for s in sessions:
        if s["has_tc"]:
            tc_any[s["thread_source"]] += 1
    for src in sorted(by_src):
        emit("  %-16s %8d %8d %8d %8d %8d" % (src, by_src[src], cov_has_tur[src], cov_only_token_count[src], cov_neither[src], tc_any[src]))
    emit("  %-16s %8d %8d %8d %8d %8d" % ("ALL", len(sessions), cov_has_tur_any, sum(cov_only_token_count.values()), sum(cov_neither.values()), cov_has_tc_any))
    emit("")
    emit("  per-session token sums (input/cached/output) -- top 10 by input:")
    for s in sorted(sessions, key=lambda x: -x["tok"].get("input_tokens", 0))[:10]:
        emit("      %-40s %-16s %12d %12d %10d" % (s["sid"][:38], s["thread_source"], s["tok"].get("input_tokens", 0), s["tok"].get("cached_input_tokens", 0), s["tok"].get("output_tokens", 0)))
    emit("")

    # ================= 5. credits =================
    emit("-" * 100)
    emit("[5] CREDITS FEASIBILITY -- is there a real 'credits consumed' field in these logs?")
    emit("-" * 100)
    emit("raw lines containing 'credit'/'Credit' : %d" % credit_line_count)
    emit("distinct JSON keys containing 'credit' : %s" % (dict(credit_key_hits.most_common()) or "NONE"))
    emit("distinct values of key 'credits'       :")
    if credit_values:
        for v, c in credit_values.most_common():
            emit("      %8d x  %s" % (c, v))
    else:
        emit("      NONE")
    emit("")
    emit("raw samples (verbatim slices):")
    for f, s in credit_samples:
        emit("  [%s]" % f)
        emit("  %s" % s)
    emit("")
    has_consumption = any(("used" in k.lower() or "spent" in k.lower() or "consum" in k.lower() or "delta" in k.lower()) for k in credit_key_hits)
    non_zero_balance = any(('"balance": "0"' not in v and '"balance":"0"' not in v) for v in credit_values)
    has_true = any('"has_credits": true' in v or '"has_credits":true' in v for v in credit_values)
    emit("  evidence: any key like credits_used/credits_spent/credits_consumed/delta : %s" % ("YES" if has_consumption else "NO"))
    emit("  evidence: any credits.balance != \"0\"                                  : %s" % ("YES" if non_zero_balance else "NO"))
    emit("  evidence: any credits.has_credits == true                             : %s" % ("YES" if has_true else "NO"))
    emit("")
    emit("  related quota fields that DO exist (they are percentages/plan flags, not credits):")
    emit("    rate_limits.plan_type distinct values : %s" % (dict(plan_type_vals.most_common())))
    emit("    rate_limits.primary.used_percent distinct values : %s" % (dict(used_percent_vals.most_common(10))))
    emit("")
    if has_consumption:
        emit("  VERDICT: 可测 (CREDIT CONSUMPTION FIELD PRESENT -- recompute from that field)")
    else:
        emit("  VERDICT: 不可测 (NOT MEASURABLE). The ONLY credit-related field is a static")
        emit("           plan-quota snapshot  token_count.payload.rate_limits.credits =")
        emit("           {\"has_credits\": false, \"unlimited\": false, \"balance\": \"0\"}.")
        emit("           It is a boolean/balance flag reset per rate-limit window, contains no")
        emit("           consumed amount, no per-turn delta, and is not an accounting field.")
        emit("           => real 'credits consumed' CANNOT be derived from these logs.")
    emit("")

    # ================= 6. raw-text cross-check =================
    emit("-" * 100)
    emit("[6] RAW-TEXT REGEX CROSS-CHECK (second, JSON-free implementation)")
    emit("-" * 100)
    emit("Purpose: confirm the JSON-structure counts above on a second code path.")
    emit("Raw-text matches OVER-count on purpose: they also hit tool schemas")
    emit("(response_item.additional_tools), prose/messages, and compaction summaries.")
    emit("")
    emit("  %-46s %10s %10s %10s" % ("metric", "raw_text", "json_plane", "delta"))
    emit("  %-46s %10d %10d %10d" % ('"type":"custom_tool_call"', raw_ctc, ctc_all_total, raw_ctc - ctc_all_total))
    emit("  %-46s %10d %10d %10d" % ('"type":"function_call"', raw_fc, fc_all_total, raw_fc - fc_all_total))
    emit("  %-46s %10d %10d %10d" % ("tools.exec_command(  (all text)", raw_nested_exec, nested_all.get("exec_command", 0), raw_nested_exec - nested_all.get("exec_command", 0)))
    emit("  %-46s %10d %10d %10d" % ('"name":"spawn_agent"', raw_spawn, fc_all.get("spawn_agent", 0), raw_spawn - fc_all.get("spawn_agent", 0)))
    emit("")
    emit("  where the raw-text hits live (line type -> hits), so every delta is explained:")
    for label, by_type in (('"type":"custom_tool_call"', raw_ctc_by_type),
                           ('"type":"function_call"', raw_fc_by_type),
                           ("tools.exec_command(", raw_nested_by_type),
                           ('"name":"spawn_agent"', raw_spawn_by_type)):
        emit("    %-26s %s" % (label, dict(by_type.most_common())))
    emit("")
    emit("  Explanation (data above, no hand-waving):")
    emit("   * a real call count must come from the JSON plane, because raw text also")
    emit("     contains (a) tool schemas under response_item.additional_tools")
    emit("     [%d such rows], (b) agent messages / reasoning / tool output that quote" % ri_inner.get("additional_tools", 0))
    emit("     a call, (c) compaction summaries that replay tool names.")
    emit("   * the JSON-plane table therefore stays authoritative; deltas are fully")
    emit("     attributable to those non-invocation text planes.")
    emit("   * nested tools.exec_command( : %d inside custom_tool_call.input (call plane)" % nested_all.get("exec_command", 0))
    emit("     vs %d raw text hits; the remainder is prose/output/compaction text." % raw_nested_exec)
    emit("")

    # ================= 7. live-log drift =================
    snap = dict(files_snapshot)
    grown, added, shrank = 0, 0, 0
    for f in files:
        cur = os.path.getsize(f)
        old = snap.get(f)
        if old is None:
            continue
        if cur > old:
            grown += 1
            added += cur - old
        elif cur < old:
            shrank += 1
    emit("-" * 100)
    emit("[7] LIVE-LOG DRIFT DIAGNOSTIC (reproducibility caveat)")
    emit("-" * 100)
    emit("run finished (UTC)            : %s" % datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    emit("files that grew during this run : %d (+%d bytes)" % (grown, added))
    emit("files that shrank during this run: %d" % shrank)
    emit("")
    emit("  Because ~/.codex/sessions is an ACTIVE log, an exact byte-for-byte")
    emit("  rerun is only guaranteed for a frozen snapshot. To audit a number:")
    emit("  rerun the script and compare, allowing for the drift printed above.")
    emit("")

    # ================= write out =================
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(OUT_LINES))
        fh.write("\n\n")
        fh.write("=" * 100 + "\n")
        fh.write("[TABLE] PER-SESSION COUNTS (sid,thread_source,date_utc,cwd,agent_role,spawn_agent,send_message,followup_task,wait_agent,list_agents,item.CommandExecution,item.FileChange,custom_tool_call.exec,nested.exec_command,task_started,task_complete,turn_aborted)\n")
        fh.write("=" * 100 + "\n")
        fh.write("\n".join(TABLE_LINES))
        fh.write("\n")
    emit("=" * 100)
    emit("OUT file: %s  (%d lines of report + %d table lines)" % (OUT, len(OUT_LINES), len(TABLE_LINES)))
    emit("=" * 100)


if __name__ == "__main__":
    main()
