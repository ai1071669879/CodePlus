"""Check a task intent contract against the working tree.

The contract is the project-side half of the global `## Intent Contract` rule: it names what
stays authoritative, what may be replaced, what must not appear, and which documents are
superseded. This module turns the machine-decidable part of that statement into an exit code.

Exit codes (project convention): 0 = pass, 1 = violation, 2 = usage or configuration error.

Contract shape: a Markdown file with five sections and one fenced JSON block.

    ## [Keep]        prose: contracts that stay authoritative
    ## [Rewrite]     prose: paths whose current form is evidence, not authority
    ## [Forbidden]   prose: names and mechanisms that must not appear
    ## [Superseded]  prose: documents/clauses that are no longer authoritative
    ## [Gate]        prose: the commands that close this task

    ```json contract
    {
      "schema_version": 1,
      "task": "short-task-id",
      "rewrite_paths": ["Modules/Exporter"],
      "keep_paths": ["Runtime/Pipeline"],
      "forbidden": [{"pattern": "TypeUse", "reason": "rejected in round 2"}],
      "allowed_new_public_types": ["RuleDeclaration"],
      "public_type_baseline": "docs/ai/public-type-baseline.txt",
      "golden": [{"path": "out/Item.cs", "golden": "docs/ai/golden/Item.cs"}],
      "deferred_gate": false
    }
    ```

Run:

    python tools/ai/contract_check.py check --contract Tasks/example-contract.md
    python tools/ai/contract_check.py check --contract ... --json
    python tools/ai/contract_check.py baseline --paths Modules Runtime --out docs/ai/public-type-baseline.txt
    python tools/ai/contract_check.py selftest
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

REQUIRED_SECTIONS = ('[Keep]', '[Rewrite]', '[Forbidden]', '[Superseded]', '[Gate]')
CONFIG_FENCE = re.compile(r'```json contract\s*\n(.*?)\n```', re.DOTALL)
SCAN_SUFFIXES = {'.cs', '.csproj', '.props', '.targets', '.json', '.md', '.py', '.ps1',
                 '.txt', '.yml', '.yaml', '.toml', '.xml', '.cfg', '.ini'}
SKIP_DIRS = {'.git', 'bin', 'obj', 'node_modules', '.buildtmp', '.vs', 'TestResults'}
MODIFIERS = r'(?:sealed|abstract|static|partial|readonly|unsafe|new|ref|extern|file)\s+'
PUBLIC_TYPE = re.compile(
    r'^\s*public\s+(?:' + MODIFIERS + r')*'
    r'(?:class|struct|interface|enum|record(?:\s+(?:class|struct))?)\s+([A-Za-z_]\w*)',
    re.MULTILINE)
PUBLIC_DELEGATE = re.compile(
    r'^\s*public\s+(?:' + MODIFIERS + r')*delegate\s+[^;{=]*?\b([A-Za-z_]\w*)\s*\(',
    re.MULTILINE)


class ContractError(Exception):
    """The contract itself is malformed; never reported as a tree violation."""


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8').replace('\r\n', '\n')


def parse_contract(path: Path) -> tuple[str, dict]:
    """Return (markdown text, machine config) or raise ContractError."""
    if not path.is_file():
        raise ContractError(f'contract not found: {path}')
    text = read_text(path)
    missing = [section for section in REQUIRED_SECTIONS if f'## {section}' not in text]
    if missing:
        raise ContractError('contract is missing required section(s): ' + ', '.join(missing))
    fences = CONFIG_FENCE.findall(text)
    if len(fences) != 1:
        raise ContractError(
            f'contract must contain exactly one "```json contract" block, found {len(fences)}')
    try:
        config = json.loads(fences[0])
    except json.JSONDecodeError as error:
        raise ContractError(f'contract machine block is not valid JSON: {error}') from error
    if not isinstance(config, dict):
        raise ContractError('contract machine block must be a JSON object')
    if config.get('schema_version') != 1:
        raise ContractError('contract schema_version must be 1')
    if not isinstance(config.get('task'), str) or not config['task'].strip():
        raise ContractError('contract task must be a nonempty string')
    return text, config


def string_list(config: dict, key: str) -> list[str]:
    value = config.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ContractError(f'contract "{key}" must be a list of nonempty strings')
    return value


def resolve_in_root(root: Path, relative: str, label: str) -> Path:
    """Resolve a repo-relative path and refuse anything that leaves the repository."""
    if (not isinstance(relative, str) or not relative or '\\' in relative
            or ':' in relative or relative.startswith('/')
            or '..' in PurePosixPath(relative).parts):
        raise ContractError(f'{label} must be a repo-relative POSIX path without "..": {relative!r}')
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ContractError(f'{label} resolves outside the repository: {relative!r}')
    return resolved


def iter_files(root: Path, relative_paths: list[str]):
    """Yield files under the given repo-relative paths, skipping build output.

    The skip rules apply to an explicitly named file exactly as they do to a directory walk,
    so naming a file directly cannot smuggle an excluded or unlisted-extension path in.
    """
    for relative in relative_paths:
        base = root / relative
        candidates = [base] if base.is_file() else [candidate for candidate in base.rglob('*')
                                                    if candidate.is_file()]
        for candidate in candidates:
            parts = set(candidate.relative_to(root).parts)
            if parts & SKIP_DIRS:
                continue
            if candidate.suffix.lower() in SCAN_SUFFIXES:
                yield candidate


def find_forbidden(root: Path, scope: list[str], rules: list[dict], keep_roots: list[Path]):
    """Return (violations, warnings); a file that cannot be read is a warning, never a pass."""
    violations, warnings = [], []
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get('pattern'), str):
            raise ContractError('each "forbidden" entry must be {"pattern": str, "reason": str}')
        pattern = rule['pattern']
        reason = rule.get('reason', '')
        regex = re.compile(pattern)
        for path in iter_files(root, scope):
            resolved = path.resolve()
            if any(resolved == kept or kept in resolved.parents for kept in keep_roots):
                continue
            try:
                text = read_text(path)
            except (OSError, UnicodeError) as error:
                warnings.append(f'unreadable file skipped during forbidden scan: '
                                f'{path.relative_to(root).as_posix()} ({error})')
                continue
            for match in regex.finditer(text):
                line = text.count('\n', 0, match.start()) + 1
                line_text = text.split('\n', line)[line - 1].strip()
                violations.append((pattern, reason, path.relative_to(root).as_posix(),
                                   line, line_text[:160]))
    return violations, warnings


def declared_public_types(root: Path, scope: list[str]) -> dict[str, list[str]]:
    """Map type name -> ['relative/path:line'] for public declarations in scope."""
    found: dict[str, list[str]] = {}
    for path in iter_files(root, scope):
        if path.suffix != '.cs':
            continue
        try:
            text = read_text(path)
        except (OSError, UnicodeError):
            continue
        relative = path.relative_to(root).as_posix()
        for regex in (PUBLIC_TYPE, PUBLIC_DELEGATE):
            for match in regex.finditer(text):
                line = text.count('\n', 0, match.start()) + 1
                found.setdefault(match.group(1), []).append(f'{relative}:{line}')
    return found


def normalize(text: str) -> str:
    """Line-ending, trailing-whitespace, and trailing-blank-line insensitive form."""
    lines = [line.rstrip() for line in re.split(r'\r\n|\r|\n', text)]
    while lines and not lines[-1]:
        lines.pop()
    return '\n'.join(lines)


def compare_golden(root: Path, entries: list[dict]) -> tuple[list[str], list[str]]:
    """Return (violations, warnings) for golden comparisons."""
    violations, warnings = [], []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get('path') or not entry.get('golden'):
            raise ContractError('each "golden" entry must be {"path": str, "golden": str}')
        target = resolve_in_root(root, entry['path'], 'golden.path')
        golden = resolve_in_root(root, entry['golden'], 'golden.golden')
        optional = bool(entry.get('optional', False))
        if not target.is_file():
            message = f'golden target missing: {entry["path"]}'
            (warnings if optional else violations).append(message)
            continue
        if not golden.is_file():
            message = f'golden file missing: {entry["golden"]}'
            (warnings if optional else violations).append(message)
            continue
        actual, expected = normalize(read_text(target)), normalize(read_text(golden))
        if actual != expected:
            actual_lines, expected_lines = actual.split('\n'), expected.split('\n')
            first = next((index for index, pair in enumerate(zip(actual_lines, expected_lines))
                          if pair[0] != pair[1]), min(len(actual_lines), len(expected_lines)))
            violations.append(
                f'golden mismatch: {entry["path"]} line {first + 1} differs from {entry["golden"]} '
                f'(actual={actual_lines[first][:80]!r}, expected={expected_lines[first][:80]!r})')
    return violations, warnings


def check(root: Path, contract_path: Path) -> dict:
    """Run every contract check; return the structured result."""
    text, config = parse_contract(contract_path)
    rewrite = string_list(config, 'rewrite_paths')
    keep = string_list(config, 'keep_paths')
    allowed = set(string_list(config, 'allowed_new_public_types'))
    if not rewrite:
        raise ContractError('contract "rewrite_paths" must name at least one path')

    violations: list[str] = []
    warnings: list[str] = []

    for relative in rewrite:
        if relative.startswith('new:'):
            continue
        if not (root / relative).exists():
            warnings.append(f'rewrite path does not exist yet: {relative}')

    scope = [item[len('new:'):] if item.startswith('new:') else item for item in rewrite]
    rewrite_roots = [resolve_in_root(root, relative, 'rewrite_paths') for relative in scope]
    keep_roots = [resolve_in_root(root, item, 'keep_paths') for item in keep]
    for kept in keep_roots:
        for rewritten in rewrite_roots:
            if (kept == rewritten or kept in rewritten.parents or rewritten in kept.parents):
                raise ContractError(
                    f'keep_paths overlaps rewrite_paths ({kept.name} vs {rewritten.name}); '
                    'overlapping paths would silently disable the forbidden scan')
    task_index = root / 'Tasks' / 'index.json'
    if task_index.is_file():
        try:
            registered = {entry.get('id') for entry in json.loads(read_text(task_index)).get('tasks', [])}
        except (json.JSONDecodeError, AttributeError) as error:
            raise ContractError(f'Tasks/index.json is not readable as a task index: {error}') from error
        if config['task'] not in registered:
            violations.append(f'task id {config["task"]!r} is not registered in Tasks/index.json')
    forbidden_violations, forbidden_warnings = find_forbidden(
        root, scope, config.get('forbidden', []), keep_roots)
    warnings.extend(forbidden_warnings)
    for pattern, reason, relative, line, source in forbidden_violations:
        suffix = f' ({reason})' if reason else ''
        violations.append(f'forbidden {pattern!r}{suffix}: {relative}:{line}: {source}')

    baseline_file = config.get('public_type_baseline')
    baseline: set[str] = set()
    if baseline_file:
        path = resolve_in_root(root, baseline_file, 'public_type_baseline')
        if not path.is_file():
            warnings.append(f'public type baseline missing: {baseline_file}')
        else:
            baseline = {line.strip() for line in read_text(path).split('\n')
                        if line.strip() and not line.startswith('#')}
    declared = declared_public_types(root, scope)
    unexpected = {name: places for name, places in declared.items()
                  if name not in allowed and name not in baseline}
    for name in sorted(unexpected):
        violations.append(
            f'unexpected new public type {name!r}: {unexpected[name][0]} '
            f'(not in allowed_new_public_types or {baseline_file or "baseline"})')

    golden_violations, golden_warnings = compare_golden(root, config.get('golden', []))
    violations.extend(golden_violations)
    warnings.extend(golden_warnings)

    deferred = bool(config.get('deferred_gate', False))
    gate_section = text.split('## [Gate]', 1)[1]
    if deferred and '<closing gate>' in gate_section:
        violations.append('[Gate] still carries the template placeholder while deferred_gate is true')
    if deferred and 'deferred' not in gate_section:
        violations.append('deferred_gate is true but [Gate] does not name the deferred gate')

    return {
        'contract': contract_path.as_posix(),
        'task': config['task'],
        'ok': not violations,
        'status': 'unverified' if deferred and not violations else ('passed' if not violations else 'failed'),
        'violations': violations,
        'warnings': warnings,
        'checks': {
            'sections': len(REQUIRED_SECTIONS),
            'forbidden_rules': len(config.get('forbidden', [])),
            'public_types_in_scope': len(declared),
            'allowed_new_public_types': len(allowed),
            'golden_entries': len(config.get('golden', [])),
            'deferred_gate': deferred,
        },
    }


def render_human(result: dict) -> str:
    lines = [
        f'contract: {result["contract"]}',
        f'task:     {result["task"]}',
        f'status:   {result["status"]}',
    ]
    if result['violations']:
        lines.append('')
        lines.append(f'violations ({len(result["violations"])}):')
        lines.extend(f'  - {item}' for item in result['violations'])
    if result['warnings']:
        lines.append('')
        lines.append(f'warnings ({len(result["warnings"])}):')
        lines.extend(f'  - {item}' for item in result['warnings'])
    if not result['violations'] and not result['warnings']:
        lines.append('')
        lines.append('contract checks passed; no violations, no warnings.')
    if result['status'] == 'unverified':
        lines.append('')
        lines.append('deferred gate is still open: this task is not done until the closing gate runs.')
    return '\n'.join(lines)


def selftest() -> int:
    """Build two temporary trees and prove the checker accepts one and refuses the other."""
    import shutil

    root = Path(tempfile.mkdtemp(prefix='contract-check-'))
    try:
        (root / 'src').mkdir()
        (root / 'src' / 'Allowed.cs').write_text('public class Allowed { }\n', encoding='utf-8')
        (root / 'docs').mkdir()
        (root / 'docs' / 'baseline.txt').write_text('', encoding='utf-8')
        contract = root / 'contract.md'
        good = '''# contract

## [Keep]

- runtime

## [Rewrite]

- src

## [Forbidden]

- TypeUse

## [Superseded]

- old spec section 7.3

## [Gate]

- `dotnet build` and `python tools/ai/contract_check.py check`

```json contract
{"schema_version": 1, "task": "selftest", "rewrite_paths": ["src"], "keep_paths": [],
 "forbidden": [{"pattern": "TypeUse", "reason": "rejected"}],
 "allowed_new_public_types": ["Allowed"],
 "public_type_baseline": "docs/baseline.txt", "golden": [], "deferred_gate": false}
```
'''
        contract.write_text(good, encoding='utf-8')
        passed = check(root, contract)
        assert passed['ok'] and passed['status'] == 'passed', passed

        (root / 'src' / 'Bad.cs').write_text(
            'public class NotAllowed { }\n// TypeUse was rejected\n', encoding='utf-8')
        failed = check(root, contract)
        assert not failed['ok'] and len(failed['violations']) == 2, failed

        (root / 'src' / 'Bad.cs').unlink()
        (root / 'docs' / 'golden.txt').write_text('alpha\nbeta\n', encoding='utf-8')
        (root / 'src' / 'golden.txt').write_text('alpha\r\nbeta\r\n', encoding='utf-8', newline='')
        good_golden = good.replace('"golden": []',
                                   '"golden": [{"path": "src/golden.txt", "golden": "docs/golden.txt"}]')
        contract.write_text(good_golden, encoding='utf-8')
        assert check(root, contract)['ok'], check(root, contract)
        (root / 'src' / 'golden.txt').write_text('alpha\ngamma\n', encoding='utf-8')
        mismatch = check(root, contract)
        assert not mismatch['ok'] and 'golden mismatch' in mismatch['violations'][0], mismatch

        # public-type modifiers, record-struct naming, and excluded paths
        contract.write_text(good, encoding='utf-8')
        (root / 'src' / 'golden.txt').unlink()
        (root / 'src' / 'Mods.cs').write_text(
            'public unsafe class Sneaky { }\n'
            'public new class Shadow { }\n'
            'public record struct Point(int X);\n', encoding='utf-8')
        modified = check(root, contract)
        names = ' '.join(modified['violations'])
        assert 'Sneaky' in names and 'Shadow' in names, modified
        assert "'struct'" not in names, modified
        (root / 'src' / 'Mods.cs').unlink()

        # a path excluded by directory name stays excluded when named directly
        (root / 'src' / 'bin').mkdir()
        (root / 'src' / 'bin' / 'evil.md').write_text('TypeUse\n', encoding='utf-8')
        direct = good.replace('"rewrite_paths": ["src"]',
                              '"rewrite_paths": ["src/bin/evil.md"]')
        contract.write_text(direct, encoding='utf-8')
        assert check(root, contract)['ok'], check(root, contract)

        # overlapping keep/rewrite is a contract error, not a silent pass
        overlap = good.replace('"keep_paths": []', '"keep_paths": ["src"]')
        contract.write_text(overlap, encoding='utf-8')
        try:
            check(root, contract)
        except ContractError as error:
            assert 'overlaps' in str(error), error
        else:
            raise AssertionError('overlapping keep_paths must be rejected')

        # an unregistered task id is a violation once Tasks/index.json exists
        contract.write_text(good, encoding='utf-8')
        (root / 'Tasks').mkdir()
        (root / 'Tasks' / 'index.json').write_text('{"tasks": [{"id": "other"}]}', encoding='utf-8')
        unregistered = check(root, contract)
        assert not unregistered['ok'], unregistered
        assert any('not registered' in item for item in unregistered['violations']), unregistered
        (root / 'Tasks' / 'index.json').unlink()

        deferred_contract = good.replace(
            '```json contract',
            'deferred until the closing gate runs; `deferred_gate` is recorded below.\n\n'
            '```json contract').replace('"deferred_gate": false', '"deferred_gate": true')
        contract.write_text(deferred_contract, encoding='utf-8')
        deferred = check(root, contract)
        assert deferred['status'] == 'unverified' and deferred['ok'], deferred
        print('selftest passed: pass, forbidden, public-type modifiers, record struct, excluded '
              'paths, keep/rewrite overlap, unregistered task, golden, and deferred-gate cases')
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest='command', required=True)
    check_parser = subparsers.add_parser('check', help='check one contract')
    check_parser.add_argument('--contract', required=True, help='repo-relative contract path')
    check_parser.add_argument('--repo', default='.', help='repository root (default: cwd)')
    check_parser.add_argument('--json', action='store_true', help='print the structured result')
    baseline_parser = subparsers.add_parser(
        'baseline', help='emit the current public-type baseline for the given paths')
    baseline_parser.add_argument('--paths', nargs='+', required=True, help='repo-relative paths')
    baseline_parser.add_argument('--repo', default='.', help='repository root (default: cwd)')
    baseline_parser.add_argument('--out', help='write to this repo-relative file instead of stdout')
    subparsers.add_parser('selftest', help='self-test the checker on temporary fixtures')
    args = parser.parse_args(argv)

    if args.command == 'selftest':
        return selftest()

    root = Path(args.repo).resolve()
    if args.command == 'baseline':
        declared = declared_public_types(root, args.paths)
        lines = ['# public type baseline, one name per line; regenerate with contract_check.py baseline',
                 '# generated from the working tree: do not hand-edit names into existence']
        lines.extend(sorted(declared))
        text = '\n'.join(lines) + '\n'
        if args.out:
            (root / args.out).write_text(text, encoding='utf-8', newline='')
            print(f'wrote {len(declared)} public types to {args.out}')
        else:
            print(text, end='')
        return 0

    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        from_cwd = contract_path.resolve()
        contract_path = from_cwd if from_cwd.is_file() else root / contract_path
    try:
        result = check(root, contract_path)
    except (ContractError, OSError, UnicodeError) as error:
        print(f'contract error: {error}', file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_human(result))
    if not result['ok']:
        return 1
    if result['status'] == 'unverified':
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
