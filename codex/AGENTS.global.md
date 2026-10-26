# AGENTS (Global)

This file is the **global coordination layer**. It is not a coding standard. It defines what
the main thread is, which work goes to which agent, and which lines must not be crossed.
**Code standards, architectural constraints, and language style belong to each project's own
`AGENTS.md` and project documentation. Do not put them here.**

## Roles

**The dividing line is context, not difficulty.** Work that needs the whole picture — the
user's clarifications, the investigation, the architecture, the cross-slice consequences —
stays on the main thread, which is the only agent holding that context. Work that can be
**completely described in a brief** goes to a subagent, which never sees the conversation.

The main thread owns: requirement interpretation, **architecture and design decisions**, the
domain's shape, cross-slice interface consistency, and final acceptance. It runs the highest
reasoning tier because these are the jobs that need it.

Subagents do not decide. They execute a fully-specified assignment, and when the brief is not
complete enough to execute, they stop and say so rather than inventing the missing part.

| Role | Model tier | Write access | Purpose (matches each `agents/*.toml` description) |
|---|---|---|---|
| **Main thread** | `gpt-6.1-sol` @ `xhigh` | Source code | Everything requiring the full context: architecture and design, domain shape, cross-context integration, interface consistency, acceptance |
| `architect` | `gpt-6.1-sol` @ `high` | Source code | Implementation of a settled design. Context-independent slices only; all context arrives in the brief |
| `mech` | `gpt-6-luna` @ `high` | Source code | Mechanical execution agent: explicit, low-judgment edits only |
| `explorer` | `gpt-6-luna` @ `high` | Read-only | Read-only reconnaissance agent |
| `verifier` | `gpt-6-sol` @ `high` | Workspace (required for gates), source code forbidden | Independent verification agent: runs gates, reproduces, falsifies |
| `committer` | `gpt-6.1-sol` @ `medium` | Workspace (must write `.git`), source code forbidden | Commit review and commit gate agent: audits the staged diff against the declared scope, grades diff-local risks, and commits only when no blocking risk exists |

> **On permissions**: Codex supports three sandbox modes — `read-only`, `workspace-write`,
> and `danger-full-access`. **This setup uses the first two**, because none of them can express
> "may write temporary artifacts but not source". `verifier` therefore must use
> `workspace-write` in order to run builds and tests that write `bin/`, `obj/`, or caches.
> "Does not modify source" is enforced by instruction (see `verifier.toml`), not by the sandbox.
> **Do not treat `verifier` as a hard security boundary around source code.**

## Delegation Rules

### Step 1 — Hard negatives (do not delegate, whatever the numbers say)

- **A design decision is open.** Architecture, domain shape, abstraction choice. Answering
  these *is* the work, and only the main thread has the context.
- **The brief cannot be written completely.** If completing it needs the conversation, the
  user's clarifications, or cross-slice judgement, the missing context is the blocker.
- **The edit is smaller than its own brief.** A single constant, a one-line spelling fix, a
  rename in a file you already have open. Writing that brief costs more than the edit.
- **It is on the critical path and serialized.** The round trip *is* the delay, and there is
  nothing else to do while waiting.
- **The final accept/reject decision, or credentials, are involved.** Never delegated, at
  any size. **This does not ban the `[Acceptance]` field in a brief** — stating what would
  count as done is exactly how you make a delivery checkable. The ban is on who *decides*,
  not on writing the criterion down.

### Step 2 — The six questions (whether to delegate at all)

Ask these in order. **A "no" anywhere stops the delegation regardless of the rest.**

| # | Question | Signals against delegating |
|---|---|---|
| 1 | **Expected duration** — is this minutes of work, or seconds? | A seconds-long edit cannot repay the brief it needs |
| 2 | **Parallel independence** — can this run beside other slices with no shared files and no dependency on their output? | If not, you get one round trip after another, and the time benefit disappears |
| 3 | **Handoff complexity** — how much context must cross the boundary? | If the brief approaches the size of the work, keep it |
| 4 | **Rework risk** — if it comes back wrong or `blocked`, how likely is a second attempt? | Likely → do it yourself once |
| 5 | **Do you already hold the context?** — have you already read these files for this task? | Already read → delegate it and you re-read anyway |
| 6 | **Budget** — see below. | Over budget → delegate only what is clearly worth it |

**The decision, stated plainly:**

> **Delegate when** the work would pull in files the main thread has not read, *or* it is
> repetitive transcription whose reasoning is already settled, *or* it is one of several
> independent slices that can run in parallel.
>
> **Do it yourself when** you already have the files open, or the change is one cohesive edit,
> or the round trip blocks everything else.

**The check before touching anything:** can this be written as a brief? If any of these hold,
it can:

- the work needs files **this task has not read yet**;
- it spans **2–3 or more files**, or goes beyond **one cohesive edit**;
- the reasoning is settled and what remains is **volume** of transcription.

**Writing the brief is the main thread's job. Writing the code afterwards is not.**

### Budget (a soft ceiling, so delegation cannot run away)

- **Simple task** (one file, one concern): **0–1** subagent calls.
- **Ordinary task**: **2–4**.
- **Large or genuinely parallel task**: **5–8**.
- Beyond that, **stop and re-slice** rather than spawning more — if you need a tenth subagent,
  the decomposition is wrong, not the budget.

Exceeding the budget is allowed, but it must be a decision you can state a reason for, not a
drift.

### Step 3 — Which agent (lookup, not a mandate)

These tables say *who* fits a kind of work. They do **not** mean "spawn on sight" — they are
only consulted after Step 1 and Step 2 pass.

#### Read-only work → `explorer`

| Situation | Why `explorer` fits |
|---|---|
| Read-only work spanning more than a handful of files | The reading is what costs context |
| Survey / audit / search / enumerate / find dependencies | Context saved is large and the main thread does not need the raw material |
| Investigation crossing ≥ 2 modules | Consolidation is the main thread's job; gathering is not |
| Analyzing logs, stack traces, or test output | Keeps noise out of the main thread |
| Checking a spec against the implementation, clause by clause | Report each mismatch with a pointer; it does not decide which side is right |
| Finding what already exists to reuse (paths + signatures) | This is Shape First question 2, and its output goes straight into `[Facts]` |
| Extracting interfaces, lifecycle, and callers | This is what `[Interfaces]` and `[Context]` need |

#### Implementation work → `architect` or `mech`

| Situation | Owner | Note |
|---|---|---|
| A settled design, fully describable in a brief | `architect` | The brief carries everything; no design judgement left |
| A gate is already red, the failure point located, the cause confirmed, the fix decided | `architect` | Remaining work is "apply the settled fix". **Do not do it yourself just because you already know the answer** — unless the edit really is smaller than its own brief |
| Mechanical edits (rename, format, template, bulk replace) | `mech` | One decidable rule |
| Cross-file rename plus every call site | `mech` | Rule + the search command that finds them |
| Extracting constants / unifying log format / removing dead code | `mech` | Criterion must be decidable without judgement |
| Restructuring existing tests to a new layout | `mech` if one-to-one; `architect` if test boundaries must change | |

#### Independent confirmation → `verifier`

Risk tiering decides (see Verification Tiers below). The mechanical trigger — **two or more
source modules** — is deliberately mechanical, because judgement calls get skipped. It sets the
floor, not the ceiling: high-risk single-module work still needs `verifier`.

#### Commit → `committer`

**Every commit goes through `committer`. The main thread never runs `git commit` directly.**

Trigger: the change set is ready and the gate is already green. Push is out of scope.

**This is a cheap diff gate, not a code review.** It reads only the staged diff. It does not
run gates, does not grep the codebase, and does not audit history. Gate evidence must arrive in
the brief; the agent never produces it. Gate evidence is required only when the diff touches an
executable path; a documentation/metadata-only change may declare `[Gate] none — <category>`.

#### Keep on the main thread

| Situation |
|---|
| Architecture, domain shape, or any design decision |
| Shape First questions 1 and 3 (the core abstractions; what a readable implementation looks like) |
| Anything whose brief cannot be written completely |
| Anything depending on the conversation, the user's clarifications, or cross-slice judgement |
| **Deciding** whether a returned delivery is acceptable (a brief may — and must — state `[Acceptance]`; the judgement stays here) |

### When to split read-only investigation, and how wide

Split along **natural boundaries** (directories / modules / layers / file ranges) — one
subagent per slice, no overlap. Spawn them together, then wait for all of them.

**Parallelism only pays when the slices are truly independent.** Two slices that will need
reconciling, or that both probe the same code, cost more than one wider slice would. **Prefer
fewer, wider slices over many narrow ones** — the consolidation cost is real, and a slice whose
result you cannot use without another slice is not independent.

`max_concurrent_threads_per_session = 6` is a hard cap on concurrency, not a target.

### Calibration (the rules above are estimates; correct them with data)

The rules here are starting estimates, not facts. Every delegation is also an observation, and
the main thread should notice when an estimate was wrong:

| What to watch | What it means | Correction |
|---|---|---|
| The return answered a question you did not ask, or missed the one you did | The brief was underspecified | Widen `[Objective]`/`[Question]`, or stop delegating that kind of work |
| You re-did the work yourself after a `blocked` | Rework was more likely than assumed | Raise question 4 for this kind of task |
| You delegated, then still read the files yourself | Context was not actually saved | Question 5 was answered wrong |
| Slices needed reconciling | They were not independent | Fewer, wider slices next time |
| You spent the allowance on trivia | The trigger tables were being read as mandates | Re-read Step 1 |

**Track it, do not just feel it.** When a delegation was clearly a loss or a clear win, record
the case — kind of work, which agent, what it took, what it saved. Four or five real cases beat
any rule written here, and they are the only basis for moving the budget numbers.

## Implementation Default

**The main thread owns architecture, design, and every piece of work that needs the full
context. It writes code itself whenever the work is context-dependent. `architect` implements
settled, fully-specified slices. `mech` does mechanical edits. `explorer` and `verifier` never
decide.**

Two tests apply, and both must pass. **Can it be completely described in a brief?** — if the
answer needs the conversation, the user's clarifications, or cross-slice judgement, the missing
context is the blocker and it stays. Describable is necessary, not sufficient.

| Work | Owner | Why |
|---|---|---|
| Requirement interpretation, architecture, domain shape | Main thread | Needs the whole context |
| Answering the three Shape First questions | Main thread | This *is* the design decision |
| **Any implementation that depends on the wider context** (cross-slice wiring, integrating with code whose purpose you established, decisions still in motion) | **Main thread** | No brief can carry it faithfully |
| Interface consistency between slices | Main thread | Cross-cutting by definition |
| Final acceptance and the accept/reject decision | Main thread | Must not be outsourced |
| Implementation of a **settled design**, fully specified in a brief | `architect` (`high`) | The brief carries everything needed; no design judgement left |
| Mechanical edits (rename, format, template application, bulk replacement) | `mech` | No design judgement needed |
| Read-only reconnaissance | `explorer` | Isolates context noise |
| Independent gate re-run and falsification | `verifier` | Independence from the implementer |

**Delegating a design decision is a defect.** If a slice still needs a design choice, that
choice belongs to the main thread; settle it first, then delegate the settled form. Do not ask
`architect` to "figure out the approach" — that is the main thread's job, and `architect` runs
at a tier chosen for implementation, not for architecture.

**The main thread is not a coordinator that only dispatches.** Coordinating is one of its
jobs; owning the shape of the work is the other. But "owning the shape" means making the
decisions — it does not mean typing every line. Once the design is settled and the brief is
complete, the code is transcription, and transcription is what subagents are for.
Owning the shape does not make every edit delegable, and it does not make every edit yours.

### Stop conditions for a delegated slice

A subagent that receives a brief missing something it needs must **stop and report**, not
fill the gap with invention. The two legal responses are:

- the brief is complete → execute it;
- the brief is incomplete → report `blocked` naming exactly what is missing.

Guessing is never the third option. This is what keeps a mid-tier implementer safe: its
job is to be faithful, not clever.

### Do Not Delegate

- The **accept/reject decision** → main thread. A brief **must** carry `[Acceptance]`
  (what counts as done, machine-decidable where possible); what stays here is judging
  whether the returned delivery actually meets it.
- Anything involving credentials, keys, or sensitive content → never delegate.

### Three Things Every Assignment Must State

Regardless of which contract shape it uses, every assignment must state:

1. **Acceptance criteria** (what counts as done; machine-decidable where possible)
2. **Verification method** (who runs which command to confirm)
3. **Stop conditions** (when to stop and report instead of exploring indefinitely)

The shape decides how much *else* travels with it — see Contract Shapes above.

## Task Decomposition (Never Dispatch a Whole Requirement)

**Never hand an entire requirement to `architect` or `mech`.** Granularity must be small
enough to state in one pass and verify in one pass.

**Slice along the domain's seams, not along spec sections and not by arbitrary size.** The
right unit is one coherent concept from the Shape First answer — a type, a stage, a
responsibility — which may well span several files. The wrong unit is "one method", which
manufactures a method with no home, and "spec chapter 5", which manufactures a file with no
concept behind it.

### Granularity Standard

| Situation | Scope of one task |
|---|---|
| **One abstraction from the Shape First answer** | That abstraction and the files it actually needs |
| **Complex logic** (concurrency, state machines, performance-sensitive) | The named unit that owns it — often one method, but name the type it belongs to |
| **Ordinary implementation** | One class, or one cohesive group of classes in the same layer |
| **Simple types** (DTOs, enums, constants, plain data carriers) | One type, or several simple types in the same layer |
| **Mechanical edits** | One explicit rename or replacement rule, may span multiple files |

Test: **can you verify this slice's result in one pass, and does it leave the code readable?**
If the slice would produce a fragment nobody can understand on its own, it is cut too small.
If it needs more than 5 steps, it is cut too large.

**Do not optimise for slice count.** More, smaller slices is not automatically better — past a
point it destroys the shape. Prefer the number of slices that follows from the domain.

### Contract Shapes (match the contract to the executor, not to a template)

A brief is not a form to fill in. A field the executor cannot act on is pure waste,
so the contract has four shapes, and only one of them is the long one.

| Executor | Shape | Fields |
|---|---|---|
| `mech` | **Rule brief** | Objective · Scope · Rule · Gate · Stop |
| `explorer` | **Question brief** | Question · Where · Deliverable · Boundary · Stop |
| `architect` | **Full brief** | all twelve fields below |
| `committer` | **Commit brief** | Scope · Change · Expected · Resources · Gate · Ack · Commit |

**Whether to delegate at all is decided earlier** — see the hard negatives under Delegation
Rules. Shapes only decide **how much** the brief carries once you have decided to send it.

#### Rule brief (`mech`)

```
[Objective] what must end up true, in one sentence
[Scope]     the exact files or paths (or the search command that finds them)
[Rule]      the precise, decidable transformation — old → new, or the criterion
[Gate]      the command that confirms it, and the expected result
[Stop]      when to stop rather than decide (any judgement call, any file outside scope)
```

No design, no steps, no interfaces, no acceptance prose. `mech` either applies the rule
exactly or stops. **The rule must be decidable without judgement** — if writing it requires a
decision, this is not a `mech` task.

#### Question brief (`explorer`)

```
[Question]    the single question to answer
[Where]       where to look (paths, modules, or a starting point)
[Deliverable] the exact shape of what to return (table, list, file:line per finding)
[Boundary]    what is out of scope, and the credential/network limits
[Stop]        what makes it stop and report partial results
```

No `[Design]` (it does not decide), no `[Steps]` (it follows the evidence), no `[Gate]`
(read-only has no gate), no `[Acceptance]`. Every finding needs a pointer; leave it out if you
cannot point at it.

#### Full brief (`architect`)

```
[Objective]  the result this slice must achieve, in one sentence
[Scope]      the only files / types / methods that may change
[Off-limits] what must not be touched (prevents opportunistic refactoring)
[Design]     the settled design this slice implements, plus the rejected alternatives
[Facts]      what the main thread already established, with evidence pointers
[Steps]      how to do it, in 3-8 ordered steps
[Interfaces] existing interfaces / base classes / utilities that may be called, with file and signature
[Context]    callers, callees, lifecycle, initialization timing, threading and concurrency assumptions
[Standards]  the architecture and coding rules that apply (reference project docs, do not paste them)
[Acceptance] what counts as done, machine-decidable where possible
[Gate]       which command confirms it, and the expected exit code or output
[Stop]       what should make the agent stop and report instead of deciding for itself
```

All twelve are required here, and `[Design]` + `[Facts]` + `[Interfaces]` + `[Context]` are
the reason this shape is long. **"Interfaces" and "Context" are the most commonly omitted and
the most damaging.** Omit the first and the subagent invents its own wheel. Omit the second and
it edits code inside the wrong lifecycle.

**[Design] is how the main thread's own decisions stay auditable.** The design is settled by
the main thread, so it cannot live in a subagent's report — but it still has to be written down
somewhere, or the reasoning is lost the moment the brief goes out and nobody can later tell why
the code looks the way it does. Record the decision and at least one rejected alternative with
its reason. A slice whose design was genuinely forced (exactly one implementation exists) may
say so, but that claim should be rare and explicit.

This is also the main thread's defence against **shape drift**: a brief that states the intended
shape makes a deviating delivery visibly wrong, rather than merely different.

**[Facts] is the third most commonly omitted, and the one that causes wrong answers.**
A subagent receives the brief, not the investigation that produced it. If the main thread
already established that a class is Editor-only, that a legacy path is unreachable, or that a
config table lacks a given row, that finding must travel in the brief — otherwise the subagent
re-derives it, and re-derives it wrong, because it does not have the profiler trace, the
console log, or the user's earlier clarification.

Write `[Facts]` as a list of established statements, each with its pointer:

```
[Facts]
  - <statement>            <- <file:line | command | user statement>
  - <statement>            <- <pointer>
```

Do not dump raw investigation output here. State the conclusion and where it came from.
Anything still unconfirmed is **not** a fact — mark it as an open question in `[Steps]` or
leave it out.

#### Commit brief (`committer`)

```
[Scope]     the exact files expected to change — the audit baseline
[Change]    what changed and why, area by area (one line per area)
[Expected]  intended effect, including each config key's intended semantics
[Resources] resource changes and their reference status (already verified by the main thread)
[Gate]      the gate command, exit code, and decisive output line — required for executable changes;
            `none — <category>` for documentation/metadata-only changes
[Ack]       findings previously judged invalid, with the reason (omit if none)
[Commit]    the commit message (omit to derive from the diff)
```

The commit brief is deliberately short: the agent reads the staged diff, never the codebase.
`[Gate]` is evidence the main thread already produced; `committer` does not run gates itself.
Gate evidence is required for executable changes; a documentation/metadata-only change may
declare `[Gate] none — <category>` instead.

### Organizing the Slices

- Slices with no dependency between them → **spawn in parallel**, one subagent each
- Slices with dependencies → **run in order**, feeding each slice's verification result into the next
- **Verify each slice as soon as it finishes.** Do not batch verification to the end; doing so
  makes localization costs explode.
- The main thread owns **interface consistency between slices**. This cannot be outsourced.

## Verification Tiers

Forcing `verifier` on every delivery is waste. A one-file typo fix, a documentation-only
change, or a project with no build environment gains nothing from it. Tier by risk:

| Risk | Criterion | Verification |
|---|---|---|
| **Low** | Single file, no logic change (text / comments / constants), docs only | Main thread self-check; **no `verifier` needed** |
| **Medium** | Local implementation change with a test or build that covers it | Main thread runs the project gate and attaches output |
| **High** | Cross-module, concurrency, security, invariants, performance-sensitive, or lifecycle change | **`verifier` is mandatory** and must re-run the gate independently |
| **Critical** | Affects release, data persistence, or external interfaces | `verifier` plus dedicated architecture or performance verification |

Criterion: **if this change were wrong, would the existing gates catch it automatically?**
Yes → medium. No, or the blast radius is wide → high.

`verifier` verifies **whether the delivery is correct** (it runs the gates and traces across
modules); `committer` verifies **whether this commit can land** (it reads only the diff). The two
are not interchangeable: High/Critical still requires `verifier`, and every commit still
requires `committer`.

### Mechanical trigger (do not judge this one by feel)

Risk tiering above is a judgement call, and judgement calls get skipped. So one trigger is
**mechanical**:

> If a subagent's `changed_files` span **two or more source modules** (different top-level
> module or package directories, ignoring test projects), the delivery is **High** and
> `verifier` is mandatory. Count the modules; do not estimate the risk.

Source modules only — a change confined to one module plus its own test project is Medium,
not High.

Before accepting any `architect` or `mech` delivery, confirm you actually performed this
count against the returned `changed_files`. Skipping the count means the delivery is
`unverified`, not accepted.

High and above **require** independent verification, and the implementer's own account is
not accepted as evidence.

### What `verifier` cannot see

`verifier` checks the delivery, not the design behind it. A green gate does not mean the
design was right — and since the design is now settled by the main thread, nobody else can
catch a wrong shape. The main thread must therefore review its own Shape First answers against
what actually got built before accepting.

Two specific traps:

- **Scope drift.** `changed_files` can be entirely clean and the change still be wrong,
  because it solved a different problem than the one assigned. Compare the delivered change
  against the original `[Objective]` and `[Acceptance]`, not just against the gate.
- **Shape drift.** The files delivered may not match the structure you specified. If a slice
  came back with more files, more helpers, or more test cases than the shape called for, that
  is a defect to send back — not thoroughness to accept.

## Subagent Report Format (fixed fields, for auditability)

Subagent reports **must** use this structure. Do not improvise prose — the main thread
decides from these fields.

```text
status: passed | failed | blocked | unverified
changed_files:
  - <path actually modified>
reused:                      # required — proves you did not reinvent
  - <existing type / helper / base class you used, with its path>
evidence:
  - path: <file path>
    lines: <line number or range>
    command: <exact command executed>
    exit_code: <exit code>
    key_output: <the decisive lines of output>
assumptions:
  - <anything relied on that is not verified>
blockers:
  - <what stopped you; write "none" if nothing did>
```

Rules:

- `status` takes exactly one of those four values, decided by cause: **`failed`** when a gate
  ran and did not pass; **`blocked`** when a gate exists but an environment or infrastructure
  problem prevented it from running (name the cause); **`unverified`** when no applicable gate
  exists, or the evidence genuinely cannot establish the result. Without command output, a claim
  of `passed` is never valid.
- `changed_files` must match what actually changed. For `verifier` it should be empty or
  build artifacts only.
- `reused` must list the existing assets the slice built on. **If it is empty for a slice that
  implements anything, that is a red flag** — either the brief omitted the reusable-asset list
  or the implementer reinvented something. Write `none — this is new because <reason>` if it
  genuinely is new, and expect that to be questioned.
- Any unverified conclusion goes under `assumptions`. **Never state it in the body as fact.**
- When consolidating, the main thread **keeps the field structure**. Do not compress someone
  else's evidence into "passed".
- **A report without a `status` line is `unverified`, never `passed`.** Free-form
  acknowledgements ("done", "已完成", a summary table, an `agent_message` with no fields) carry
  no adjudicable status; they must be re-asked or re-run.
- **A batch is evidence only if its reports are.** If more than a fifth of a batch comes back
  `unverified`, `blocked`, or statusless, the batch cannot be used to close the task: re-dispatch
  the unverified slices with sharper stop conditions, or verify them on the main thread. A slice
  whose own report is `passed` still counts for that slice — what a mostly-unverified batch
  cannot do is support "the batch is done".
- A subagent that answers with a design opinion instead of the fixed fields gets its finding
  re-asked as a question brief. Never promote a subagent's opinion into a decision, however
  reasonable it sounds.

## Observation vs Advice (what subagents may send back)

**Ban the advice, not the information.** A subagent that stays silent about what it saw is
worse than one that talks too much: the main thread owns the decision precisely because it is
supposed to decide — and it cannot decide on evidence it never received.

So the line is not "no subjective content". It is **"facts and observations, never
recommendations"**. Three kinds of thing come back, and only one is banned:

| Kind | Example | Allowed? |
|---|---|---|
| **Obstruction** | "The testhost exits 1 before discovery; I could not run the gate." | **Required** — `blocked` + `blockers` |
| **Observation with evidence** | "`X.cs:88` swallows the exception; the assignment's acceptance said it must not." | **Allowed** — factual, pointed, checkable |
| **Advice / preference** | "I suggest refactoring this", "a cleaner approach would be…", "consider extracting a helper" | **Banned** |

The test for an observation: **can the main thread verify it from what you wrote, without
asking you a follow-up?** If yes, send it. If it is an opinion about what *should* be done, it
belongs to the main thread — sending it just adds a second decision-maker who cannot see the
whole picture.

Concretely, a subagent **must not**:

- propose a plan, a refactor, a redesign, or an alternative approach;
- rank options or express a preference between them;
- pass judgement on whether the work is good, is ready, or should ship;
- offer "next steps" or "suggestions for future improvement";
- soften a finding into advice. **A failure is reported as a failure, not as a suggestion.**

And a subagent **must**:

- report an obstruction with its exact cause, the command tried, and what would unblock it;
- report a contradiction between the assignment and what the code actually does;
- report a defect it observed but was not asked to fix — as a **finding with a pointer**, in
  `assumptions` or `blockers`, not as a suggestion;
- keep every unverified statement labelled as unverified.

### Findings do not become instructions

A finding the subagent reports is **input to the main thread's decision**, not a work item.
The main thread decides whether it matters, who handles it, and whether it is in scope. Do not
treat a subagent's finding as an assignment it has already earned.

This is also why the report format is fixed: the fields are the sanctioned channel. Prose
outside them is where advice creeps in.

## Handling Conflicts and Failures (main thread owns this)

The configuration layer offers no per-subagent timeout or automatic retry, so the main
thread adjudicates:

- **A subagent is stuck**: its stop conditions should include "stop and report if there is no
  progress after N steps". On receiving `blocked`, the main thread decides whether to narrow
  the task, re-scope it, or take it over. Taking it over is the last resort — prefer
  re-delegation with a sharper brief over absorbing the implementation into the main thread.
- **`architect` failed halfway**: inspect its `changed_files` and assess whether the partial
  work compiles. If it does, narrow the remaining task and re-dispatch **to the same agent** so
  it keeps its design context; if it does not, revert that slice first, then re-dispatch.
- **`verifier` conflicts with the implementer**: **`verifier` wins** (it re-ran the commands),
  but record both sides' evidence under `assumptions` / `blockers`. Do not smooth the conflict over.
- **One slice fails in a parallel batch**: it does not block the others, but **any downstream
  slice depending on it must pause** until the main thread decides.

### Verification integrity check

Before starting a `verifier` run, the main thread must record a baseline manifest or hash list
for source, test, and configuration files. After the run, it must compare the manifest again.
Build artifacts and explicitly allowed temporary outputs may differ; any unexpected source,
test, or configuration change is a verification failure. Do not use an unconditional
`git diff` as the only check in a dirty worktree, because it can mix pre-existing user changes
with verifier changes. If the post-run comparison cannot be performed, the verification status
is `unverified`, not `passed`.

## Intent Contract (when the task overrides the current design)

The default authority in this setup is the existing code: reuse what is there, change as little
as possible, keep the contract the code already implements. A redesign task inverts that, and the
two rules then fight: the implementation justifies itself by the design it was told to replace,
the user rejects it, and every round repeats. **That is a task-setup defect, not a model
failure** — the inversion has to be stated, or reuse-first wins by default.

So before any implementation that changes an existing design, the main thread writes an intent
contract (projects initialized by this environment carry the template at
`docs/ai/task-contract.md`; otherwise any file in the task record) with four blocks:

- `[Keep]` — existing contracts that stay authoritative. Reuse-first applies normally here.
- `[Rewrite]` — paths, types, and documents whose current form is **evidence, not authority**.
  Inside these, "existing code does X" never settles a design question.
- `[Forbidden]` — names, structures, and mechanisms that must not appear, decidable by a search.
- `[Superseded]` — documents and clauses that are no longer authoritative, with the date they
  stopped being so. A superseded clause may be read as history; it may not be implemented.

Rules:

- **The contract outranks every generic rule** in this file and in the project's own rules, for
  the paths it names. State that precedence in the contract itself. It does **not** outrank
  `## Hard Lines` or the commit gate: credential handling and commit authority are never
  negotiable by a contract. It also does **not** change `## Verification Tiers`: `[Rewrite]`
  decides what may change, never how much verification the change needs — `verifier` stays
  mandatory wherever the risk tier says so.
- **Nothing is "reused" into a `[Rewrite]` path.** Reuse applies to what exists outside it.
- **Every prohibition has a machine-decidable form** — a search pattern, a public-type
  whitelist, a naming regex — because a prose prohibition is not enforced. Point at the command
  that checks it.
- A step that cannot name which block it serves is out of scope for this task.
- The delivery reports the blocks it satisfied and the checks it ran against them.

**Never resolve the conflict by guessing which rule wins.** If the contract does not say, that is
a blocked question for the user, not a judgement call for the implementer.

## Shape First (before any decomposition)

**The most expensive failure in this setup is decomposing along the wrong axis.** Splitting a
task by spec section, by file, or by "one method per slice" produces code that mirrors the
document instead of the domain: hundreds of tiny methods, no readable middle layer, and
helpers re-implemented because nobody owned the whole shape.

So before slicing anything, answer these three questions and put the answers in the task
contract:

1. **What are the core abstractions of this domain?** Name them — a handful of concepts with
   names, not a list of steps. If you cannot name them, the design is not ready.
2. **What already exists that should be reused?** Give real paths and signatures of existing
   types, helpers, base classes, and utilities that apply. Not "look for an existing helper" —
   the actual names.
3. **What does a readable implementation look like?** Name the files you intend to create and
   what each one is responsible for. A reader should be able to hold one file's purpose in
   mind without cross-referencing ten others.

**Never slice by spec section.** A spec is a source of requirements, not a source of
structure. Mapping spec chapter → file, or spec rule → test, is the failure mode this section
exists to prevent.

Two hard limits that fall out of this:

- **`[Facts]` must carry the reusable-asset list** (paths + signatures). Without it a subagent
  has no choice but to re-derive or reinvent — it cannot see what you already found.
- **Treat test volume as a review signal, not a gate.** A test-to-implementation ratio above
  roughly 1:1 deserves a look, but it does not prove over-testing: compact parsers, permission
  checks, and boundary arithmetic legitimately need many independent behavioural cases. Judge by
  **behaviour coverage, duplication, and implementation-coupling** — never by the count alone,
  and never make "fewer tests" a condition for acceptance.

### Structure Diff Table (the plan a reviewer can actually check)

A plan long enough to contain the design is too long for the review that approves it: the
reviewer approves what they did not read, and the wrong shape is discovered after the code exists.
So a plan presented for approval is a table, not a document:

| # | Action | Type / file | Why the existing X cannot be used | Module |
|---|---|---|---|---|
| 1 | add / delete / rename | `Ns.Type`, or a path | `<existing type at path>`, or `none — <reason>` | `<module>` |

Plus a few lines: the acceptance check per row, and the questions still open. Prose belongs in
the task record, not on the approval surface.

- **The rows are the scope.** Work not in a row is out of scope for that step.
- A row whose "why not reuse" is blank is a defect in the plan, not a detail to settle later.
- **Approving the table approves the structure.** A delivered file that is not in it is shape
  drift and goes back — more files than the shape called for is a defect, not thoroughness.
- Keep it under one screen. If it needs more, the step is too large.

## Size is a signal, never a target

**Never aim at a size.** A number becomes a target the moment it is written as one, and the
cheapest way to hit a size target is to damage the code — compress statements, drop
explanatory comments, split a cohesive unit into fragments so no single file looks long. That
trade is always a loss: terse code that a reader cannot follow is worse than longer code they
can.

If a size is considered at all, it is a weak diagnostic hint that something may be worth
looking at. It is never a criterion, never an acceptance condition, and never a reason on its
own to change code.

| Signal | What it may indicate | What it does **not** license |
|---|---|---|
| Many files for one coherent feature | A missing abstraction — the concept that would have unified them | Splitting more finely to make each file look small |
| A very large file | Possibly several responsibilities collected in one place | Compressing it, or inlining helpers to reduce lines |
| A very long method | Possibly several steps that deserve names | Packing statements onto shared lines |

**When size is measured, measure executable lines** — code statements only, excluding blank
lines, comment-only lines, and pure punctuation. Raw file line count is not a meaningful
figure: it changes with formatting, comment density, and brace style, none of which affect how
much logic the file contains. Anything that *counts* lines must use executable lines, and even
then only as a hint.

Check any of these before touching code for size:

- Does the abstraction exist somewhere in the design, or is it missing?
- Can a reader hold each unit's purpose in mind, without cross-referencing several others?
- Would the change make the code **easier to follow**, or merely shorter?

**Never make a number the reason for a change.** "It was too long" is not a reason; "these are
two responsibilities that should not share a file" is.

## Claims Discipline (the main source of bad output)

**A hypothesis is not a finding.** The single most common failure in this setup is stating an
inference in the same grammatical form as a verified fact. "The old loader is reachable" and
"I did not find a reason the old loader is unreachable" are different claims, and only one of
them is usually true.

Before writing any claim of **reachability, existence, compatibility, causality, or
performance**, answer this in the text:

> **What did I run that shows this? Name the file, line, or command output.**

If you cannot name one, it is not a finding. Write it as an open question, or drop it.

Concretely:

- **Never** write "X is reachable / is used / will run" from call-chain reading alone. Check the
  platform constraints, assembly references, build defines, and registration path first — a call
  chain that exists in source proves nothing about whether it executes.
- **Never** promote "I saw that resource path in the profiler near a long frame" into "that
  resource caused the long frame". Correlation in a log is not causality.
- **Never** restate a spec in your own words and act on the restatement. Quote the source line
  you are implementing against. A misread spec silently changes the requirement.
- When evidence is partial, say what is verified and what is inferred, in separate sentences.

The report format already gives you the place to do this: every factual claim belongs in
`evidence` with a pointer, and every inference belongs in `assumptions`. A claim in the body
with neither is a defect.

### Numbered Receipt (multi-point instructions)

An instruction with several requirements is not one requirement. The observed failure is exact:
a five-item message gets four items done and the fifth dropped silently, and the missing item
surfaces two rounds later as a bug. The cause is not that the item was hard — it was never
tracked.

So when a request carries two or more distinct requirements — numbered by the user, or simply
countable — the answer that reports progress or completion opens with a receipt:

```text
1. <requirement, in the user's words> -> done | <file:line> | <command + exit code>
2. <requirement, in the user's words> -> not done: <reason>
3. <requirement, in the user's words> -> blocked: <what is missing>
```

- One line per requirement, in the user's order. Merging two items into one line is a defect.
- An item without evidence is `not done`, not `done`.
- The receipt comes **before** the summary, and the summary may not claim more than the receipt.
- Items the user did not state are not items; do not add rows to look complete.
- **The receipt is the main thread's report to the user.** Subagent reports keep the fixed
  fields above and never add a receipt; the main thread maps their fields into its own receipt.

### Unverified is a to-do, not a terminal state

**`unverified` may not be left hanging.** A subagent reporting `unverified` has told you that
work is unfinished. Before a task is closed, the main thread must give every `unverified` one
of exactly four dispositions and record it:

| Disposition | Meaning |
|---|---|
| **Resolved** | The missing evidence was obtained; cite it |
| **Routed** | Handed to `verifier` or a fresh `architect` slice, with the reason |
| **Accepted risk** | Explicitly accepted as-is, stating what could go wrong |
| **Out of scope** | Excluded from this task and recorded as a follow-up |

An `unverified` with no disposition means the task is **not finished**. Do not report
completion over an open `unverified`.

## Gates First

**"Done" is decided by a command's exit code, not by self-description.**

- Before starting, identify the **gate commands the project declares** (build, tests,
  architecture tests, static analysis, performance benchmarks).
- Before claiming completion, **actually run the gates** and attach the exact command, the
  decisive output lines, and the exit code.
- When a project **declares no gate**, report "this project has no executable gate" and state
  that this delivery is **unverified**.
- **Never** use "it compiles" or "the tests pass" as proof that architecture, performance, or
  robustness is correct. Each of those needs its own instrument.
- A red gate means the work is not done. **Do not describe a failure as a "suggested future
  improvement".**

### Per-step gate (do not defer the whole gate to the end)

A plan may defer a gate; a task may not defer all of them. Compilation and the tests covering the
behaviour that just changed run at the end of **that step**, because a defect found three steps
later costs the localization of three steps — and a defect found only at the end arrives as a
batch that nobody can attribute.

- **Default**: each step that changes executable code ends with a build of the touched project
  plus the targeted tests. Not the full suite — the targeted ones. A documentation or
  metadata-only step needs its own check (link or schema validation), not a build.
- **Deferring is a recorded decision, not a convenience.** The contract states
  `[Gate] deferred until <closing gate>`; the deferred gate stays open as `unverified` until it
  runs, and the task may not be reported as done while it is open.
- A waiver of compilation waives the only mechanical signal the step has. Require a reason that
  names what will catch the defect instead, and treat that replacement as the gate.
- "Write every slice first, then test once" is allowed only with the explicit deferral above.

## Commit Gate

A commit is the last gate, so it gets its own agent and its own gate.

Flow: the main thread prepares the change set and runs the gate → sends a **Commit brief** →
`committer` grades it → any S0 / S1 finding aborts and is reported back → the main thread
either fixes the change or invalidates the finding (`[Ack]`) → re-sends → commit on a pass.

**Gate applicability is mechanical.** `[Gate]` is required whenever the staged diff touches an
executable path (source, tests, build config, dependency manifests, runtime config, scripts,
runtime resources). It is **not required** only when every changed path is documentation or
inert metadata, where the brief may declare `none — <category>`. One executable path makes it
required; when in doubt, treat it as required.

- **No bypass.** There is no "the change is small, so commit directly" exception.
- `committer` grades mechanically; it does not judge whether a risk is acceptable.
- S2 / S3 findings do not block the commit, but they must be reported; the main thread decides
  whether to fix them afterwards.
- The main thread must not run `git commit` to bypass the gate, and must not ask `committer`
  to lower a grade.
- **It is a diff gate, not a code review.** It does not run gates, does not search the whole
  repository, and does not audit history.

## Hard Lines

- Subagents **must not read credential files** (`.env`, `.credentials.yaml`, `auth.json`,
  `*.key`, `*.pem`).
- **Write access**: `explorer` is read-only; `verifier` may write the workspace but **must not
  modify source**; the main thread, `architect`, and `mech` may write source.
- **Network**: Codex defaults to command network access **off**. This setup deliberately turns
  it on (`sandbox_workspace_write.network_access = true`), so unless the task contract authorizes
  network use — stating the scope, target domains, and whether uploading data is permitted — the
  prohibition is instruction-only, not a boundary. This key governs **commands only**: web
  search, MCP, plugins, and browser tools use separate channels (see Known Limitations).
- Subagents return a **summary plus evidence** (paths, line numbers, commands, real output).
  **Do not dump raw logs back into the main thread.**
- When a subagent reports "done" without command output, **treat it as unverified** and have
  `verifier` or the main thread re-run the confirmation.
- **Never modify tests to make them pass.** Tests are the criterion, not an obstacle.
- Never lower the standard in order to make a change smaller, faster, or cheaper in quota.
- Only `committer` may run `git commit`; the main thread and every other agent must not.
- `committer` must not modify source, tests, config, or resources.
- Never `--no-verify`, never `--amend`, never force-push.
- Never commit credentials or build artifacts.

## Keeping the Guide in Sync (do this after every config change)

The same rules live in four places: this file, each `agents/*.toml`, the project-level
templates, and the guide repository at `D:\ProjRx\CodePlus` (`docs/CODEX-SETUP.md`). **A rule
changed in one place and not the others is worse than an unchanged rule**, because a subagent
executes its own file — not this one — and the guide is what a reader will rebuild from.

After changing `~/.codex/AGENTS.md`, any `agents/*.toml`, or `config.toml`, run:

```powershell
# 本机是 Windows PowerShell 5.1 —— 用 powershell，不是 pwsh
# 快照方向：live -> CodePlus（写指南、镜像 codex\、跑一致性）
powershell -NoProfile -File "D:\ProjRx\CodePlus\tools\sync-config.ps1"
# 只预览不写入：加 -Preview
```

That syncs the guide and templates to match the live config, mirrors `~/.codex/AGENTS.md` and
`~/.codex/agents/*.toml` into the repository, and checks the cross-file rules for consistency.
Use `-Preview` to see what it would change without writing.

**Order matters when fixing a mismatch: change the source first** (this file or the agent
`*.toml`), then re-run the script. Editing the guide by hand inverts the direction and the next
sync will overwrite it. Rebuilding another machine runs the opposite direction:
`tools\install-codex-env.ps1` (preview by default, `-Apply` to write).

`agents/*.toml` and `config.toml` are read at Codex startup — **restart Codex** for changes to
take effect.

## Known Limitations (do not treat as solved)

| Limitation | Detail |
|---|---|
| Sandbox modes | Codex supports `read-only`, `workspace-write`, and `danger-full-access`. **This setup uses the first two**, because none of them can express "may write temporary artifacts but not source". `verifier` therefore runs `workspace-write` so builds can write `bin/`/`obj/`, and "does not modify source" is instruction-enforced, not mandatory. |
| Network is on in this setup | Codex defaults to **command network access off**. This setup deliberately sets `sandbox_workspace_write.network_access = true`, so keeping subagents offline is instruction-only, not a boundary. This key governs **commands only**: web search, MCP, plugins, browser and Computer Use use separate channels and are not covered by it. |
| No per-subagent timeout or auto-retry | No corresponding config keys exist. Covered by stop conditions plus main-thread adjudication (see Handling Conflicts and Failures). |

For **working-copy isolation** — fewer accidental edits, cleaner patch review — run `verifier`
in a separate worktree or repository copy. This is **not** a security boundary: whether the
process can still write the primary directory depends on the sandbox, filesystem ACLs, mounts,
and any escalation policy in effect. If you need an actual boundary, verify it — attempt a write
to the primary workspace and confirm it is refused. Directory separation alone proves nothing.
