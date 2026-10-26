#!/usr/bin/env python3
"""Check supplied Unity evidence and explicitly selected asset metadata, read-only."""
import argparse
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import check_env as core


def tests(root, args):
    text = core.project_path(root, args.report).read_text(encoding='utf-8-sig')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', text, re.IGNORECASE):
        raise ValueError('DTD and entity declarations are forbidden in NUnit reports')
    document = ET.fromstring(text)
    if document.tag not in ('test-results', 'test-run'):
        raise ValueError('Expected an NUnit2 test-results or NUnit3 test-run report')
    states = {'passed': 'passed', 'success': 'passed', 'failed': 'failed',
              'failure': 'failed', 'error': 'failed', 'notrunnable': 'failed',
              'skipped': 'skipped', 'ignored': 'skipped', 'inconclusive': 'skipped'}
    counts = dict(total=0, passed=0, failed=0, skipped=0)
    errors = []
    for case in document.iter('test-case'):
        if any(child.tag == 'test-case' for child in case.iter() if child is not case):
            continue
        counts['total'] += 1
        state = states.get(case.get('result', '').casefold())
        if state is None:
            errors.append('Unknown or missing NUnit test-case result')
            counts['failed'] += 1
        else:
            counts[state] += 1
    if counts['failed']:
        errors.append('NUnit report contains failed tests')
    root_state = document.get('result')
    if root_state and states.get(root_state.casefold()) not in ('passed', 'skipped'):
        errors.append('NUnit root reports failure or an unknown result')
    if document.get('success', '').casefold() == 'false':
        errors.append('NUnit root success is false')
    if args.exit_code is not None and args.exit_code != 0:
        errors.append('Test process returned a nonzero exit code')
    warnings = []
    if not counts['passed'] and not counts['failed']:
        warnings.append('No executed NUnit tests: zero tests or all tests skipped')
    return {**counts, 'errors': errors, 'warnings': warnings,
            'process_exit_verified': args.exit_code is not None}, 1 if errors else (2 if warnings else 0)


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def sample_data(root, relative):
    data = core.read_json(root, relative)
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported performance sample schema_version')
    if not isinstance(data.get('source_revision'), str) or not data['source_revision'].strip():
        raise ValueError('Performance samples require source_revision')
    context = data.get('context')
    fields = ('editor_version', 'platform', 'device', 'scenario', 'backend', 'build_mode')
    if not isinstance(context, dict) or any(
            not isinstance(context.get(field), str) or not context[field].strip() for field in fields):
        raise ValueError('Performance context requires all six nonempty environment fields')
    entries = data.get('metrics')
    if not isinstance(entries, list):
        raise ValueError('Performance metrics must be a list')
    metrics = {}
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get('name'), str)
                or not entry['name'].strip() or entry['name'] in metrics):
            raise ValueError('Performance metric names must be nonempty and unique')
        if not isinstance(entry.get('unit'), str) or not entry['unit'].strip():
            raise ValueError('Performance metrics require explicit units')
        if not finite_number(entry.get('value')):
            raise ValueError('Performance metric value must be a finite number')
        count = entry.get('sample_count')
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError('Performance sample_count must be a positive integer')
        metrics[entry['name']] = entry
    return data, metrics


def performance(root, args):
    budget_file = core.project_path(root, args.budgets)
    if not budget_file.exists():
        return {'errors': [], 'warnings': ['Performance budgets are unconfigured']}, 2
    budget = core.read_json(root, args.budgets)
    if budget.get('schema_version') != 1 or not isinstance(budget.get('performance'), dict):
        raise ValueError('Invalid performance budget schema')
    settings = budget['performance']
    context, entries = settings.get('context'), settings.get('metrics')
    if not isinstance(context, dict) or not isinstance(entries, list):
        raise ValueError('Performance budget requires context object and metrics list')
    if not entries:
        return {'errors': [], 'warnings': ['Performance metric budgets are unconfigured']}, 2
    rules = {}
    for rule in entries:
        if (not isinstance(rule, dict) or not isinstance(rule.get('name'), str)
                or not rule['name'].strip() or rule['name'] in rules):
            raise ValueError('Budget metric names must be nonempty and unique')
        if not isinstance(rule.get('unit'), str) or not rule['unit'].strip():
            raise ValueError('Each budget requires explicit units')
        count = rule.get('min_samples')
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError('Budget min_samples must be a positive integer')
        constraints = [key for key in ('min', 'max', 'max_regression_pct') if key in rule]
        if not constraints or any(not finite_number(rule[key]) for key in constraints):
            raise ValueError('Each budget needs at least one finite numeric constraint')
        if 'max_regression_pct' in rule and rule['max_regression_pct'] < 0:
            raise ValueError('max_regression_pct must be nonnegative')
        if 'min' in rule and 'max' in rule and rule['min'] > rule['max']:
            raise ValueError('Budget minimum exceeds maximum')
        rules[rule['name']] = rule
    samples, metrics = sample_data(root, args.samples)
    if any(key not in samples['context'] or not isinstance(value, str) or not value.strip()
           for key, value in context.items()):
        raise ValueError('Budget context must contain nonempty supported environment fields')
    errors, warnings, checks = [], [], []
    if any(samples['context'][key] != value for key, value in context.items()):
        errors.append('Sample environment differs from budget context')
    if args.expected_revision is not None and samples['source_revision'] != args.expected_revision:
        errors.append('Sample source_revision differs from expected revision')
    baseline, previous = None, {}
    if args.baseline:
        baseline, previous = sample_data(root, args.baseline)
        if baseline['context'] != samples['context']:
            errors.append('Baseline and samples require identical complete context')
    for name, rule in rules.items():
        metric = metrics.get(name)
        if metric is None:
            warnings.append(f'Missing required metric evidence: {name}')
            continue
        if metric['unit'] != rule['unit']:
            errors.append(f'Metric unit differs from budget: {name}')
        if metric['sample_count'] < rule['min_samples']:
            warnings.append(f'Insufficient samples: {name}')
        value = metric['value']
        for limit in ('min', 'max'):
            if limit in rule and ((limit == 'min' and value < rule[limit])
                                  or (limit == 'max' and value > rule[limit])):
                errors.append(f'Metric violates {limit} budget: {name}')
        check = {'name': name, 'value': value, 'unit': metric['unit'], 'sample_count': metric['sample_count']}
        if 'max_regression_pct' in rule:
            prior = previous.get(name)
            if baseline is None or prior is None:
                warnings.append(f'Regression requires baseline metric: {name}')
            elif prior['unit'] != rule['unit'] or prior['value'] <= 0:
                errors.append(f'Baseline requires matching units and a positive value: {name}')
            elif prior['sample_count'] < rule['min_samples']:
                warnings.append(f'Insufficient baseline samples: {name}')
            else:
                regression = (value / prior['value'] - 1) * 100
                check['increase_pct'] = regression if math.isfinite(regression) else None
                if not math.isfinite(regression) or regression > rule['max_regression_pct']:
                    errors.append(f'Metric increase exceeds regression budget: {name}')
        checks.append(check)
    return {'errors': errors, 'warnings': warnings, 'checks': checks,
            'context': samples['context'], 'source_revision': samples['source_revision'],
            'coverage': 'supplied normalized measurements',
            'regression_direction': 'lower-is-better; only increases are constrained'}, 1 if errors else (2 if warnings else 0)


def diagnostics(root, args):
    report = core.read_json(root, args.report)
    if report.get('version') != '2.1.0' or not isinstance(report.get('runs'), list):
        raise ValueError('Expected SARIF 2.1.0 with a runs list')
    errors, warnings = [], []
    if not report['runs']:
        warnings.append('SARIF contains no analyzer runs')
    count = 0
    for index, run in enumerate(report['runs']):
        if not isinstance(run, dict) or not isinstance(run.get('tool'), dict):
            raise ValueError('SARIF run requires a tool object')
        tool = run['tool']
        driver, extensions = tool.get('driver', {}), tool.get('extensions', [])
        if (not isinstance(driver, dict) or not isinstance(extensions, list)
                or any(not isinstance(extension, dict) for extension in extensions)):
            raise ValueError('Malformed SARIF tool components')
        if not any(component.get('name') == args.require_tool for component in (driver, *extensions)):
            warnings.append(f'Run {index} does not establish required analyzer: {args.require_tool}')
        invocations = run.get('invocations', [])
        if not isinstance(invocations, list) or any(not isinstance(item, dict) for item in invocations):
            raise ValueError('SARIF invocations must be objects')
        if not invocations or any('executionSuccessful' not in item for item in invocations):
            warnings.append(f'Run {index} is missing analyzer execution evidence')
        for invocation in invocations:
            success = invocation.get('executionSuccessful')
            if success is False:
                errors.append(f'Analyzer invocation failed in run {index}')
            elif success is not None and success is not True:
                raise ValueError('SARIF executionSuccessful must be boolean')
            elif success is None:
                warnings.append(f'Run {index} has incomplete execution evidence')
        results = run.get('results', [])
        if not isinstance(results, list):
            raise ValueError('SARIF results must be a list')
        for result in results:
            if not isinstance(result, dict) or not isinstance(result.get('message'), dict):
                raise ValueError('Malformed SARIF result or message')
            level = result.get('level', 'warning')
            if level not in ('none', 'note', 'warning', 'error'):
                raise ValueError('Unknown SARIF result level')
            count += 1
            if level == 'error' or (args.level == 'warning' and level == 'warning'):
                errors.append(f'Analyzer result reaches {args.level} threshold in run {index}')
    return {'errors': errors, 'warnings': warnings, 'result_count': count,
            'required_tool': args.require_tool, 'coverage': 'supplied SARIF runs'}, 1 if errors else (2 if warnings else 0)


def assets(root, args):
    profile = core.read_json(root, core.PROFILE)
    unity = profile.get('unity')
    if not isinstance(unity, dict) or not unity.get('root'):
        return {'errors': [], 'warnings': ['Unity project root is unconfigured']}, 2
    unity_root = core.project_path(root, unity['root'])
    asset_root = unity_root / 'Assets'
    if not asset_root.resolve().is_relative_to(unity_root.resolve()):
        raise ValueError('Assets root escapes configured Unity root')
    if not asset_root.is_dir():
        raise ValueError('Configured Unity root is missing Assets')
    if not args.paths and not args.all_assets:
        return {'errors': [], 'warnings': ['Explicit --paths or --all-assets is required']}, 2
    selected = args.paths or [asset_root.relative_to(root).as_posix()]
    errors, warnings, visited, meta_files = [], [], set(), set()
    for relative in selected:
        path = core.project_path(root, relative)
        if not path.is_relative_to(asset_root) or not path.resolve().is_relative_to(asset_root.resolve()):
            raise ValueError('Asset selection must remain inside configured Assets')
        if not path.exists():
            raise ValueError(f'Missing selected asset path: {relative}')
        # A selected .meta also checks its corresponding asset without traversing siblings.
        pending = [path]
        if path.name.endswith('.meta'):
            pending.append(path.with_name(path.name[:-5]))
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            label = current.relative_to(root).as_posix()
            if not current.resolve().is_relative_to(asset_root.resolve()):
                errors.append(f'Linked asset escapes Assets: {label}')
                continue
            parts = current.relative_to(asset_root).parts
            if any(part.startswith('.') or part in ('Library', 'Packages') for part in parts):
                warnings.append(f'Excluded hidden or generated scope: {label}')
                continue
            attributes = getattr(current.lstat(), 'st_file_attributes', 0) if current.exists() else 0
            if current.is_symlink() or attributes & 0x400:
                warnings.append(f'Linked asset scope was not traversed: {label}')
                continue
            if current.name.endswith('.meta'):
                meta_files.add(current)
                if not current.with_name(current.name[:-5]).exists():
                    errors.append(f'Orphan metadata: {label}')
                continue
            if not current.exists():
                errors.append(f'Missing asset: {label}')
                continue
            if current != asset_root:
                meta = Path(str(current) + '.meta')
                if not meta.resolve().is_relative_to(asset_root.resolve()):
                    errors.append(f'Linked metadata escapes Assets: {label}.meta')
                elif not meta.is_file():
                    errors.append(f'Missing metadata: {label}')
                elif meta.is_symlink() or getattr(meta.lstat(), 'st_file_attributes', 0) & 0x400:
                    warnings.append(f'Linked metadata was not inspected: {label}.meta')
                else:
                    meta_files.add(meta)
            if current.is_dir():
                pending.extend(sorted(current.iterdir(), reverse=True))
            elif not current.is_file():
                errors.append(f'Unsupported asset type: {label}')
    guids = {}
    for meta in sorted(meta_files):
        label = meta.relative_to(root).as_posix()
        declarations = re.findall(r'^\s*guid\s*:(.*)$', meta.read_text(encoding='utf-8-sig'), re.MULTILINE)
        if len(declarations) != 1 or not re.fullmatch(r'[0-9a-fA-F]{32}', declarations[0].strip()):
            errors.append(f'Metadata requires exactly one 32-hex GUID: {label}')
            continue
        guid = declarations[0].strip().lower()
        if guid in guids:
            errors.append(f'Duplicate GUID in selected scope: {guids[guid]} and {label}')
        else:
            guids[guid] = label
    return {'errors': errors, 'warnings': warnings, 'scope': selected,
            'coverage': 'partial' if warnings else 'selected scope', 'metadata_count': len(meta_files),
            'references_verified': False,
            'limitations': ['GUID duplicates are checked only within the selected scope; asset references are not validated']}, 1 if errors else (2 if warnings else 0)


def main():
    parser = core.Parser(description=__doc__)
    parser.add_argument('--project', type=Path)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=core.Parser)
    for name in ('tests', 'performance', 'diagnostics', 'assets'):
        child = commands.add_parser(name)
        child.add_argument('--project', type=Path, default=argparse.SUPPRESS)
        if name in ('tests', 'diagnostics'):
            child.add_argument('--report', required=True)
        if name == 'tests':
            child.add_argument('--exit-code', type=int)
        elif name == 'performance':
            child.add_argument('--samples', required=True)
            child.add_argument('--budgets', default='Docs/ai/unity-validation.json')
            child.add_argument('--baseline')
            child.add_argument('--expected-revision')
        elif name == 'diagnostics':
            child.add_argument('--require-tool', default='Microsoft.Unity.Analyzers')
            child.add_argument('--level', choices=('error', 'warning'), default='error')
        else:
            selection = child.add_mutually_exclusive_group()
            selection.add_argument('--paths', nargs='+')
            selection.add_argument('--all-assets', action='store_true')
    try:
        args = parser.parse_args()
        root = (args.project or Path(__file__).resolve().parents[2]).resolve()
        if not root.is_dir():
            raise ValueError('Project root must be an existing directory')
        data, code = {'tests': tests, 'performance': performance, 'diagnostics': diagnostics, 'assets': assets}[args.command](root, args)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError, ET.ParseError) as error:
        data, code = {'errors': [str(error)], 'warnings': []}, 1
    data.update(ok=code == 0, runtime_load_verified=False, engineering_verified=False)
    print(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
