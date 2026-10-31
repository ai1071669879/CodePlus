# Delegation (main thread only)

Read this when you are about to spawn. A subagent never sees this file, and never sees the
conversation it came from.

## Whether to delegate

**Default: delegate.** If the work can be written as a brief file and split into disjoint
paths, spawn for it — that is the normal case, not the exception. Keeping this thread's
context on design and acceptance is the point.

Delegate when any of these holds:

- the work needs files this thread has not read;
- the reasoning is settled and what remains is volume;
- it is one of several slices that write **disjoint** paths and can run in parallel.

Do it yourself when: you already have the files open; it is one cohesive edit; the round trip
blocks everything else; or the brief would need the conversation to be complete.

The test: **can the brief be a file?** If not, this is not delegable.

## Skill scope (global roles, project allowlist)

Role → skill sets are global (`Skills by role` in `AGENTS.md`); a project only narrows which
skills it may use, never which role gets which skill.

## Role routing

- implementation slice → `architect`; mechanical rename/format → `mech`
- read-only survey / multi-file investigation → `explorer`
- independent check of a delivery → `verifier`
- commit gate / staged-diff audit → `committer`

If the work fits a role and is briefable, hand it over instead of doing it inline.

## Budget

- ordinary task: 2–4 slices; large parallel task: 5–8.
- **hard ceiling 8.** Needing more means the decomposition is wrong: re-slice or keep it.
- One slice = one writer = one gate. If two slices must touch the same path, they are one slice.

## The brief is a file

Write the brief as a file in the project's task directory (its `AGENTS.md` names it); the
spawn message is that path plus the slice id. Six blocks, nothing else:

```
slice: <id>            executor: architect|mech|explorer|verifier
paths:   <path> — add|modify|delete — responsibility (one line each)
reuse:   rg -n "<pattern>" <root>  → hits; disposition per hit (or: 0 hits, exit 1)
interfaces: <Type>.<member>(<sig>) @ <file>:<line>
facts:   <statement> <- <file:line | command+exit | the user's words>
gate:    <command>  → expect exit 0; decisive output line
stop:    the judgement calls you must not make
```

Rules that make this cheap:

- `facts` and `interfaces` are pointers, never summaries; a claim without a pointer is not a fact.
- `reuse` needs the real command and its result. "none" without a command is a defect.
- `paths` is also the write claim: register it in the project's slice registry before spawning.
- Spawn with an explicit `agent_type`: `architect` (implementation), `mech` (mechanical edits),
  `explorer` (read-only survey), `verifier` (independent check), `committer` (commit gate).
  A spawn with no role loses that role's instructions, model and report format.
- `changed_files` in the brief and in the report must be the **actual** set of files touched —
  list every added/modified/deleted path, including the gate log and report files themselves.
- `design` is not in the brief: the shape is already committed as stubs. If the shape is not
  settled, it is not a slice yet.
- Skills: the brief names the skill(s) from the global `Skills by role` map in `AGENTS.md`,
  by absolute path. A project may only narrow that list; role assignment is never a
  project-level decision.

## When it comes back

- The report has fixed fields: `status`, `slice`, `changed_files`, `reused`, `gate`,
  `assumptions`, `blockers`. `status` is exactly one of `passed | failed | blocked |
  unverified` — the same four values the main thread uses in its final answer. Missing
  `status` = `unverified`, never `passed`.
- `passed` is only valid with gate exit 0 recorded; accept it only if `changed_files` are
  inside the claim. Everything else goes to the to-do: re-slice, do it yourself, or record it
  as unverified work.
- A finding from a subagent is information, not a decision. The decision is yours.

## When it goes wrong

- Conflict between slices: re-slice by path ownership. Never let two writers run on one path.
- Gate red: stop the batch, fix the baseline, then resume. A red baseline makes every
  `passed` meaningless.
- Wrong shape coming back: the brief or the stubs were wrong — fix those before re-spawning.
