#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""slice.py — one task's write-claim ledger and gate recorder.

Replaces three prose rules with one mechanical check:
  * write scope        -> `claim` refuses paths another in-flight slice owns
  * single writer      -> same refusal, by path prefix
  * delivery = gate    -> `done` accepts only gate exit 0 + changed files inside the claim

State lives in <task-dir>/slices.json so a compacted thread can rebuild it by reading.

Exit codes: 0 ok, 1 violation, 2 usage/state error.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

STATE = "slices.json"
ACTIVE = ("claimed", "in_progress")


# ---------------------------------------------------------------- paths
def norm(path):
    p = str(path).strip().replace("\\", "/").lower()
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def overlaps(a, b):
    """True when one path is the other or sits inside its directory."""
    a, b = norm(a), norm(b)
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


# ---------------------------------------------------------------- state
def state_path(task_dir):
    return os.path.join(task_dir, STATE)


def load(task_dir):
    path = state_path(task_dir)
    if not os.path.exists(path):
        sys.stderr.write(f"error: no registry at {path} (run init first)\n")
        raise SystemExit(2)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(task_dir, state):
    path = state_path(task_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def find(state, slice_id):
    for s in state["slices"]:
        if s["id"] == slice_id:
            return s
    return None


def other_claims(state, exclude):
    out = []
    for s in state["slices"]:
        if s["id"] == exclude or s["status"] not in ACTIVE:
            continue
        for p in s.get("paths", []):
            out.append((s["id"], p))
    return out


# ---------------------------------------------------------------- commands
def cmd_init(a):
    os.makedirs(a.task_dir, exist_ok=True)
    if os.path.exists(state_path(a.task_dir)) and not a.force:
        sys.stderr.write("error: registry exists (use --force to reset)\n")
        return 2
    save(a.task_dir, {
        "schema_version": 1,
        "task": a.task,
        "gate": a.gate or "",
        "slices": [],
    })
    print(f"init  {state_path(a.task_dir)}")
    return 0


def cmd_claim(a):
    state = load(a.task_dir)
    sl = find(state, a.id)
    if sl and sl["status"] == "completed":
        sys.stderr.write(f"REFUSED: slice {a.id} is completed\n")
        return 1
    if sl and sl.get("owner") and sl["owner"] != a.owner:
        sys.stderr.write(f"REFUSED: slice {a.id} is owned by {sl['owner']}\n")
        return 1
    targets = [str(p) for p in a.paths]
    for t in targets:
        for sid, op in other_claims(state, a.id):
            if overlaps(t, op):
                sys.stderr.write(f"REFUSED: {t} overlaps {op} (slice {sid})\n")
                return 1
    if sl is None:
        sl = {"id": a.id, "owner": a.owner, "status": "claimed",
              "paths": [], "gate_exit": None, "completed_at": None}
        state["slices"].append(sl)
    sl["owner"] = a.owner
    sl["status"] = "claimed"
    sl["paths"] = sorted(set(targets), key=str.lower)
    save(a.task_dir, state)
    print(f"claim {a.id} <- {a.owner}  paths={len(sl['paths'])}")
    return 0


def scope_violations(sl, changed):
    bad = []
    for c in changed:
        if not any(overlaps(c, p) for p in sl.get("paths", [])):
            bad.append(c)
    return bad


def cmd_verify(a):
    state = load(a.task_dir)
    sl = find(state, a.id)
    if sl is None:
        sys.stderr.write(f"error: unknown slice {a.id}\n")
        return 2
    bad = scope_violations(sl, a.changed)
    if bad:
        for b in bad:
            sys.stderr.write(f"OUTSIDE CLAIM: {b}\n")
        return 1
    print(f"verify {a.id}: {len(a.changed)} changed file(s) inside claim")
    return 0


def cmd_done(a):
    state = load(a.task_dir)
    sl = find(state, a.id)
    if sl is None:
        sys.stderr.write(f"error: unknown slice {a.id}\n")
        return 2
    if sl["status"] == "completed":
        print(f"done {a.id}: already completed")
        return 0
    gate_cmd = a.gate_cmd or state.get("gate") or ""
    if a.gate_exit is not None:
        code = int(a.gate_exit)
        evidence = "gate_exit passed by caller"
    elif gate_cmd:
        proc = subprocess.run(gate_cmd, shell=True, capture_output=True, text=True)
        code = proc.returncode
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()
        evidence = tail[-1] if tail else ""
        print(f"gate  exit={code}  {gate_cmd}")
    else:
        sys.stderr.write("error: no --gate-cmd, --gate-exit, or registry gate\n")
        return 2
    if code != 0:
        sys.stderr.write(f"NOT DONE: gate exit {code}. Status stays claimed.\n")
        return 1
    bad = scope_violations(sl, a.changed)
    if bad:
        for b in bad:
            sys.stderr.write(f"OUTSIDE CLAIM: {b}\n")
        sys.stderr.write(f"NOT DONE: {a.id} touched paths it never claimed.\n")
        return 1
    sl["status"] = "completed"
    sl["gate_exit"] = 0
    sl["completed_at"] = a.timestamp or ""
    sl["gate_evidence"] = evidence
    save(a.task_dir, state)
    print(f"done  {a.id}  gate=0  files={len(a.changed)}")
    return 0


def cmd_status(a):
    state = load(a.task_dir)
    print(f"task: {state.get('task')}   gate: {state.get('gate') or '-'}")
    print(f"{'slice':32s} {'owner':18s} {'status':12s} paths")
    for s in state["slices"]:
        print(f"{s['id'][:32]:32s} {(s.get('owner') or '-')[:18]:18s} "
              f"{s['status']:12s} {len(s.get('paths', []))}")
    return 0


def cmd_selftest(a):
    tmp = tempfile.mkdtemp(prefix="slice-selftest-")
    me = [sys.executable, os.path.abspath(__file__)]
    cases = []

    def run(*args):
        return subprocess.run(me + list(args), capture_output=True, text=True).returncode

    d = tmp
    cases.append(("init", run("init", "--task-dir", d, "--task", "t", "--gate", ""), 0))
    cases.append(("claim A", run("claim", "--task-dir", d, "--id", "a", "--owner", "o1",
                                 "--paths", "Modules/X/A.cs"), 0))
    cases.append(("claim B overlapping", run("claim", "--task-dir", d, "--id", "b",
                                             "--owner", "o2",
                                             "--paths", "modules/x"), 1))
    cases.append(("claim B disjoint", run("claim", "--task-dir", d, "--id", "b",
                                          "--owner", "o2", "--paths", "Modules/Y"), 0))
    cases.append(("done red gate", run("done", "--task-dir", d, "--id", "a", "--gate-exit", "1",
                                       "--changed", "Modules/X/A.cs"), 1))
    cases.append(("done outside claim", run("done", "--task-dir", d, "--id", "a",
                                            "--gate-exit", "0",
                                            "--changed", "Modules/Z/A.cs"), 1))
    cases.append(("done ok", run("done", "--task-dir", d, "--id", "a", "--gate-exit", "0",
                                 "--changed", "Modules/X/A.cs"), 0))
    cases.append(("reclaim completed", run("claim", "--task-dir", d, "--id", "a", "--owner",
                                           "o1", "--paths", "Modules/X/A.cs"), 1))
    failed = 0
    for name, got, want in cases:
        ok = got == want
        failed += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:24s} exit={got} want={want}")
    print(f"selftest: {len(cases) - failed}/{len(cases)} passed")
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------- cli
def main(argv):
    p = argparse.ArgumentParser(prog="slice.py", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("init", help="create <task-dir>/slices.json")
    q.add_argument("--task-dir", required=True)
    q.add_argument("--task", required=True)
    q.add_argument("--gate", default="", help="default gate command for done")
    q.add_argument("--force", action="store_true")
    q.set_defaults(func=cmd_init)

    q = sub.add_parser("claim", help="claim write paths for a slice")
    q.add_argument("--task-dir", required=True)
    q.add_argument("--id", required=True)
    q.add_argument("--owner", required=True)
    q.add_argument("--paths", nargs="+", required=True)
    q.set_defaults(func=cmd_claim)

    q = sub.add_parser("verify", help="check changed files are inside the claim")
    q.add_argument("--task-dir", required=True)
    q.add_argument("--id", required=True)
    q.add_argument("--changed", nargs="+", required=True)
    q.set_defaults(func=cmd_verify)

    q = sub.add_parser("done", help="mark done: gate must be green and scope respected")
    q.add_argument("--task-dir", required=True)
    q.add_argument("--id", required=True)
    q.add_argument("--changed", nargs="+", required=True)
    q.add_argument("--gate-cmd", default="")
    q.add_argument("--gate-exit", default=None)
    q.add_argument("--timestamp", default="")
    q.set_defaults(func=cmd_done)

    q = sub.add_parser("status", help="print the registry table")
    q.add_argument("--task-dir", required=True)
    q.set_defaults(func=cmd_status)

    q = sub.add_parser("selftest", help="run built-in scenarios")
    q.set_defaults(func=cmd_selftest)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
