#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""skill_scope.py — declare the skills this PROJECT may use, and stop catalog injection.

This is project-level scope only. Role → skill sets are global (the `Skills by role` map in
`~/.codex/AGENTS.md`); this script never assigns skills to roles.

Writes, inside the project:
  .codex/config.toml      [skills] include_instructions=false + max_context_tokens=<budget>
  Docs/ai/skill-scope.json    the project allowlist (name, scope, path)
and prints an AGENTS.md snippet.

Commands:
  python <skill-dir>/scripts/skill_scope.py --project <root> --skills a,b,c [--write]
  python <skill-dir>/scripts/skill_scope.py --project <root> --check

Exit codes: 0 ok, 1 unknown skill, 2 usage/IO error.
"""
import argparse
import json
import os
import sys

HOME = os.path.expanduser("~")
GLOBAL_ROOT = os.path.join(HOME, ".codex", "skills")
BEGIN = "# >>> skill-scope (managed by <skill>/scripts/skill_scope.py)"
END = "# <<< skill-scope"


def resolve(project, name):
    """Project skills first, then the user's global skills."""
    local = os.path.join(project, ".codex", "skills", name, "SKILL.md")
    if os.path.exists(local):
        return "project", local
    global_ = os.path.join(GLOBAL_ROOT, name, "SKILL.md")
    if os.path.exists(global_):
        return "global", global_
    return None, None


def block(budget):
    return "\n".join([
        BEGIN,
        "[skills]",
        "# Do not inject every installed skill's name+description into each agent's context.",
        "include_instructions = false",
        "max_context_tokens = %d" % budget,
        "# Role skill sets are global (AGENTS.md: Skills by role); this file only scopes the project.",
        END,
        "",
    ])


def upsert(text, budget):
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        tail = rest.split(END, 1)[1]
        return head + block(budget).lstrip("\n") + tail.lstrip("\n")
    sep = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + block(budget)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True, help="project root")
    ap.add_argument("--skills", default="", help="comma separated project allowlist")
    ap.add_argument("--budget", type=int, default=600, help="max_context_tokens fallback")
    ap.add_argument("--check", action="store_true", help="validate existing files only")
    ap.add_argument("--write", action="store_true", help="write files (default: preview)")
    a = ap.parse_args(argv)

    project = os.path.abspath(a.project)
    if not os.path.isdir(project):
        sys.stderr.write("error: project not found: %s\n" % project)
        return 2
    cfg_path = os.path.join(project, ".codex", "config.toml")
    scope_path = os.path.join(project, "Docs", "ai", "skill-scope.json")

    if a.check:
        if not os.path.exists(scope_path):
            sys.stderr.write("error: missing %s\n" % scope_path)
            return 1
        data = json.load(open(scope_path, encoding="utf-8"))
        bad = [s["name"] for s in data.get("skills", []) if not os.path.exists(s["path"])]
        cfg = open(cfg_path, encoding="utf-8").read() if os.path.exists(cfg_path) else ""
        ok = BEGIN in cfg and "include_instructions = false" in cfg
        if bad:
            sys.stderr.write("error: missing SKILL.md for: %s\n" % bad)
        if not ok:
            sys.stderr.write("error: .codex/config.toml has no skill-scope block\n")
        return 0 if ok and not bad else 1

    names = [n.strip() for n in a.skills.split(",") if n.strip()]
    if not names:
        sys.stderr.write("error: --skills is required (comma separated project allowlist)\n")
        return 2
    entries = []
    for n in names:
        scope, path = resolve(project, n)
        if not path:
            sys.stderr.write("error: unknown skill %r (looked in .codex/skills and ~/.codex/skills)\n" % n)
            return 1
        entries.append({"name": n, "scope": scope, "path": path.replace(os.sep, "/")})

    data = {
        "schema_version": 1,
        "project": project.replace(os.sep, "/"),
        "skills": entries,
        "note": "Project allowlist only. Role skill sets are global: see AGENTS.md 'Skills by role'.",
    }
    print("== project skill allowlist ==")
    for e in entries:
        print("  %-28s %-8s %s" % (e["name"], e["scope"], e["path"]))
    print("\n== AGENTS.md snippet ==")
    print("## Skills (project allowlist)")
    print("This project may use: " + ", ".join("`%s`" % e["name"] for e in entries) + ".")
    print("Role skill sets are global (`AGENTS.md`, Skills by role); read a `SKILL.md` only on demand.")

    if not a.write:
        print("\n(preview; add --write to create/update the files)")
        return 0

    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    os.makedirs(os.path.dirname(scope_path), exist_ok=True)
    old = open(cfg_path, encoding="utf-8").read() if os.path.exists(cfg_path) else ""
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(upsert(old, a.budget))
    with open(scope_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("\nwrote %s\nwrote %s" % (cfg_path, scope_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
