# Project skill allowlist (project-level only)

The Codex runtime injects the name+description of every installed skill into every agent.
With a large library that fixed catalog is the biggest fixed context cost, and most of it is
irrelevant to one project.

## The boundary

- **Role → skill sets are global.** They live in `~/.codex/AGENTS.md` under `Skills by role`
  (main/architect/mech/explorer/verifier/committer). Roles are global objects, so their skill
  sets are global too; they are not configured by a project.
- **Project scope is a project allowlist.** This skill writes which skills the project may
  use at all, and turns off catalog injection. It does not assign skills to roles.

## What initialization writes

- `.codex/config.toml`:
  ```
  [skills]
  include_instructions = false
  max_context_tokens = 600
  ```
- `Docs/ai/skill-scope.json`: `{project, skills:[{name, scope, path}], note}` where `scope`
  is `project` (`.codex/skills/<name>)` or `global` (`~/.codex/skills/<name>`).
- an `## Skills (project allowlist)` section for the project `AGENTS.md`.

## Commands

```text
python <skill-dir>/scripts/skill_scope.py --project <root> --check
python <skill-dir>/scripts/skill_scope.py --project <root> --skills a,b,c --write
```

Preview by default. Exit codes: 0 ok, 1 unknown skill / missing file, 2 usage.

## Adjusting

Add or remove names and rerun `--write`; the block is replaced in place. Removing a name only
stops it being allowlisted — nothing on disk is deleted. If a skill exists both in the project
(`.codex/skills/…`) and globally, the project copy wins and is recorded as scope `project`.
