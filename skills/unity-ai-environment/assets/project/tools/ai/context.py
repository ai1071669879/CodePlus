#!/usr/bin/env python3
"""Select existing context navigation without reading source or running project gates."""
import json
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.dont_write_bytecode = True

import check_env as core


REQUIRED_FILES = ('Docs/ai/README.md', 'Docs/ai/project-rules.md', core.PROFILE,
                  core.POLICY, 'Docs/ai/workflow.md')


def run(args):
    root = (args.project or Path(__file__).resolve().parents[2]).resolve()
    if not root.is_dir():
        raise ValueError('Project root must be an existing directory')
    errors, warnings = [], []
    result = {'ok': False, 'entries': [], 'context_status': {},
              'required_files': list(REQUIRED_FILES), 'errors': errors, 'warnings': warnings,
              'runtime_load_verified': False, 'engineering_verified': False}
    index = core.read_json(root, core.CONTEXT)
    if index.get('schema_version') != 1:
        errors.append('Unsupported context schema_version')
    statuses = core.validate_context(root, index, errors, warnings)
    if errors:
        return result, 1

    for relative in REQUIRED_FILES:
        if not core.project_path(root, relative).is_file():
            if relative == 'Docs/ai/workflow.md':
                warnings.append(f'Legacy project is missing navigation guide: {relative}')
            else:
                errors.append(f'Missing required navigation file: {relative}')
    if errors:
        return result, 1
    warnings.extend((
        'Source navigation freshness does not verify source behavior; review stale or unknown entries.',
        'Serialized resource contents and references have not been inspected.',
        'Runtime loading and engineering gates have not been executed.',
        'Check write scope with tools/ai/check_env.py scope using Docs/ai/access-policy.json.',
    ))

    selecting = bool(args.query or args.paths)
    entries = index['entries']
    selected_ids = set()
    for query in args.query:
        folded = query.casefold()
        matches = [entry for entry in entries
                   if folded in [entry['id'].casefold(), *(alias.casefold() for alias in entry['aliases'])]]
        if not matches:
            errors.append(f'No context entry matches query: {query}')
        selected_ids.update(entry['id'] for entry in matches)
    for relative in args.paths:
        try:
            path = core.project_path(root, relative)
            if not path.exists():
                raise ValueError(f'Selection path does not exist; select an existing parent: {relative}')
            path = path.resolve()
            matches = []
            for entry in entries:
                for indexed in entry['roots'] + entry['entrypoints']:
                    target = core.project_path(root, indexed).resolve()
                    if (path == target or (target.is_dir() and path.is_relative_to(target))
                            or (path.is_dir() and target.is_relative_to(path))):
                        matches.append(entry)
                        break
            if not matches:
                errors.append(f'No context entry matches path: {relative}')
            selected_ids.update(entry['id'] for entry in matches)
        except (OSError, ValueError) as error:
            errors.append(str(error))
    if errors:
        return result, 2

    selected = [entry for entry in entries if not selecting or entry['id'] in selected_ids]
    result['context_status'] = {entry['id']: statuses[entry['id']] for entry in selected}
    if selecting:
        profile = core.read_json(root, core.PROFILE)
        if profile.get('schema_version') != 1:
            errors.append('Unsupported project-profile schema_version')
        core.validate_profile(root, profile, errors, warnings)
        if errors:
            return result, 1
        result['declared_checks'] = [
            {'id': name, 'command': command, 'status': 'not_run', 'configured': bool(command)}
            for name, command in profile['commands'].items() if name in ('build', 'test', 'lint')
        ]
        result['entries'] = selected
        result['required_files'] = list(dict.fromkeys([
            *REQUIRED_FILES, *(relative for entry in selected for relative in entry['entrypoints'])
        ]))
    else:
        result['entries'] = [{key: entry[key] for key in ('id', 'aliases', 'roots')}
                             for entry in selected]
    result['ok'] = True
    return result, 0


def main():
    parser = core.Parser(description=__doc__)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--query', action='append', default=[])
    parser.add_argument('--paths', nargs='+', action='extend', default=[])
    try:
        data, code = run(parser.parse_args())
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        data, code = {'ok': False, 'entries': [], 'context_status': {},
                      'required_files': list(REQUIRED_FILES), 'errors': [str(error)], 'warnings': [],
                      'runtime_load_verified': False, 'engineering_verified': False}, 1
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
