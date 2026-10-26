#!/usr/bin/env python3
"""Validate supplied dependency graphs and explicitly selected Gitleaks scopes."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

import check_env as core
import environment


def architecture(root, args):
    policy = core.read_json(root, args.policy)
    errors = []
    if policy.get('schema_version') != 1 or not isinstance(policy.get('allow_cycles'), bool):
        raise ValueError('Invalid architecture policy schema or allow_cycles')
    modules = policy.get('modules')
    if (not isinstance(modules, list) or not all(isinstance(item, str) and item.strip() for item in modules)
            or len(set(modules)) != len(modules)):
        raise ValueError('Policy modules must contain unique nonempty identifiers')
    if not modules:
        return {'ok': False, 'status': 'unconfigured', 'coverage': 'declared',
                'errors': [], 'warnings': ['Architecture modules are unconfigured']}, 2
    module_set = set(modules)
    dependencies = {}
    for field in ('allowed_dependencies', 'forbidden_dependencies'):
        pairs = policy.get(field)
        if (not isinstance(pairs, list) or not all(
                isinstance(pair, list) and len(pair) == 2
                and all(isinstance(item, str) and item in module_set for item in pair) for pair in pairs)):
            raise ValueError(f'Invalid architecture policy {field}')
        dependencies[field] = {tuple(pair) for pair in pairs}
    graph = core.read_json(root, args.graph)
    if (graph.get('schema_version') != 1 or not isinstance(graph.get('revision'), str)
            or not isinstance(graph.get('generator'), str) or not graph['generator'].strip()
            or not isinstance(graph.get('complete'), bool)):
        raise ValueError('Invalid dependency graph metadata')
    graph_modules = graph.get('modules')
    if (not isinstance(graph_modules, list) or not all(isinstance(item, str) for item in graph_modules)
            or len(set(graph_modules)) != len(graph_modules) or set(graph_modules) != module_set):
        raise ValueError('Dependency graph has unknown, missing, or duplicate modules')
    if args.expected_revision is not None and graph['revision'] != args.expected_revision:
        errors.append('Dependency graph revision does not match expected revision')
    edges = graph.get('edges')
    if not isinstance(edges, list):
        raise ValueError('Dependency graph edges must be a list')
    adjacency = {module: set() for module in modules}
    for edge in edges:
        if (not isinstance(edge, dict) or not isinstance(edge.get('from'), str)
                or not isinstance(edge.get('to'), str) or edge['from'] not in module_set
                or edge['to'] not in module_set or not isinstance(edge.get('evidence'), str)
                or not edge['evidence'].strip()):
            raise ValueError('Dependency graph edge has invalid modules or missing evidence')
        source, target = edge['from'], edge['to']
        pair = (source, target)
        if pair in dependencies['forbidden_dependencies']:
            errors.append(f'Forbidden dependency: {source} -> {target}')
        elif dependencies['allowed_dependencies'] and pair not in dependencies['allowed_dependencies']:
            errors.append(f'Dependency is not allowed: {source} -> {target}')
        adjacency[source].add(target)
    if not policy['allow_cycles']:
        indegree = {module: 0 for module in modules}
        for targets in adjacency.values():
            for target in targets:
                indegree[target] += 1
        pending = [module for module, degree in indegree.items() if degree == 0]
        visited = 0
        while pending:
            module = pending.pop()
            visited += 1
            for target in adjacency[module]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    pending.append(target)
        if visited != len(modules):
            errors.append('Dependency graph contains a cycle')
    incomplete = not graph['complete']
    status = 'failed' if errors else 'unverified' if incomplete else 'passed'
    return {'ok': status == 'passed', 'status': status, 'coverage': 'declared',
            'revision': graph['revision'], 'errors': errors,
            'warnings': ['Dependency graph is declared incomplete'] if incomplete else []}, (
                1 if errors else 2 if incomplete else 0)


def secrets(root, args):
    if not 1 <= args.timeout <= 30:
        raise ValueError('Scanner timeout must be between 1 and 30 seconds')
    profile = environment.load_profile(root)
    capability = profile['capabilities'].get('secret-scan', {})
    integration = capability.get('integration', {})
    version = integration.get('version', '')
    if (not integration.get('enabled') or integration.get('provider') != 'gitleaks'
            or not re.fullmatch(r'v?8\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?', version)
            or not capability.get('command')):
        return {'ok': False, 'status': 'unconfigured', 'scanner_exit_code': None,
                'findings': [], 'errors': [], 'warnings': ['Gitleaks v8 integration is unconfigured']}, 2
    command = environment.resolve_command(root, 'secret-scan', capability['command'])
    paths = [core.project_path(root, relative) for relative in args.paths]
    if not all(path.is_file() or path.is_dir() for path in paths):
        raise ValueError('Every selected scanner path must be an existing directory or file')
    # Check selected descendants too: an apparently safe directory may contain escaping links.
    for path in paths:
        if path.is_dir():
            for child in path.rglob('*'):
                core.project_path(root, child.relative_to(root).as_posix())
    config = core.project_path(root, 'Docs/ai/gitleaks.toml')
    if not config.is_file():
        raise ValueError('Managed Gitleaks configuration is missing')
    temporary_root = Path(tempfile.gettempdir()).resolve()
    report_dir = temporary_root / ('ai-gitleaks-' + uuid.uuid4().hex)
    report_dir.mkdir()
    findings, errors, exit_codes = [], [], []
    try:
        for index, path in enumerate(paths):
            report = report_dir / f'{index}.json'
            scanner_args = ['dir', str(path)] if path.is_dir() else ['stdin']
            scanner_args.extend(['--config', str(config), '--redact=100', '--report-format', 'json',
                                 '--report-path', str(report), '--exit-code', '1', '--no-banner'])
            try:
                result = subprocess.run(command + scanner_args, cwd=root, shell=False,
                                        input=path.read_bytes() if path.is_file() else None,
                                        capture_output=True, timeout=args.timeout)
            except (OSError, subprocess.TimeoutExpired):
                errors.append('Gitleaks execution failed or timed out; raw output withheld')
                break
            exit_codes.append(result.returncode)
            if result.returncode not in (0, 1):
                errors.append('Gitleaks returned a tool failure; raw output withheld')
                break
            try:
                raw = json.loads(report.read_text(encoding='utf-8-sig'))
                if not isinstance(raw, list):
                    raise ValueError('Expected an array')
                summaries = []
                for finding in raw:
                    if (not isinstance(finding, dict) or not isinstance(finding.get('File'), str)
                            or not isinstance(finding.get('RuleID'), str) or not finding['RuleID'].strip()
                            or type(finding.get('StartLine')) is not int or finding['StartLine'] < 1):
                        raise ValueError('Invalid finding location')
                    summaries.append({'File': path.relative_to(root).as_posix() if path.is_file() else finding['File'],
                                      'StartLine': finding['StartLine'], 'RuleID': finding['RuleID']})
                if (result.returncode == 0 and summaries) or (result.returncode == 1 and not summaries):
                    raise ValueError('Scanner exit code and report disagree')
                findings.extend(summaries)
            except (OSError, ValueError, TypeError, UnicodeError):
                errors.append('Gitleaks report is missing, unreadable, malformed, or inconsistent; raw content withheld')
                break
    finally:
        if (report_dir.parent != temporary_root or report_dir.resolve() != report_dir
                or not report_dir.name.startswith('ai-gitleaks-')
                or not re.fullmatch(r'ai-gitleaks-[0-9a-f]{32}', report_dir.name)):
            raise ValueError('Refused scanner report cleanup outside the allocated directory')
        shutil.rmtree(report_dir)
    scanner_exit_code = (next((code for code in exit_codes if code not in (0, 1)), None)
                         if any(code not in (0, 1) for code in exit_codes)
                         else 1 if 1 in exit_codes else 0 if exit_codes else None)
    ok = not errors and not findings
    return {'ok': ok, 'status': 'clean' if ok else 'failed' if errors else 'findings',
            'scanner_exit_code': scanner_exit_code, 'findings': findings,
            'scope': [path.relative_to(root).as_posix() for path in paths],
            'errors': errors, 'warnings': []}, 0 if ok else 1


def main():
    parser = core.Parser(description=__doc__)
    parser.add_argument('--project', type=Path)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=core.Parser)
    architecture_parser = commands.add_parser('architecture')
    architecture_parser.add_argument('--graph', required=True)
    architecture_parser.add_argument('--policy', default='Docs/ai/architecture-policy.json')
    architecture_parser.add_argument('--expected-revision')
    secrets_parser = commands.add_parser('secrets')
    secrets_parser.add_argument('--paths', nargs='+', required=True)
    secrets_parser.add_argument('--timeout', type=int, default=30)
    for child in (architecture_parser, secrets_parser):
        child.add_argument('--project', type=Path, default=argparse.SUPPRESS)
    try:
        args = parser.parse_args()
        root = (args.project or Path(__file__).resolve().parents[2]).resolve()
        if not root.is_dir():
            raise ValueError('Project root must be an existing directory')
        data, code = architecture(root, args) if args.command == 'architecture' else secrets(root, args)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        data, code = {'ok': False, 'errors': [str(error)], 'warnings': []}, 1
    data.update(runtime_load_verified=False, engineering_verified=False)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
