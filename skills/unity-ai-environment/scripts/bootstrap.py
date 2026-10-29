#!/usr/bin/env python3
"""Preview or install the project environment shipped beside this script."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys


PLATFORMS = ('codex', 'claude', 'cursor', 'trae', 'workbuddy', 'opencode')
MANIFEST = '.ai-environment.json'


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def encoded_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def project_path(root, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative
            or ':' in relative or '\x00' in relative):
        raise ValueError(f'Invalid relative path: {relative!r}')
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'Path escapes project: {relative}')
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError(f'Linked path escapes project: {relative}')
    return target


def merge_entry(existing, content, relative):
    prefix = '#' if relative == '.gitignore' else '<!--'
    suffix = '' if prefix == '#' else ' -->'
    start = f'{prefix} ai-environment:start{suffix}'
    end = f'{prefix} ai-environment:end{suffix}'
    block = start + '\n' + content.decode('utf-8').strip() + '\n' + end
    if existing is None:
        return (block + '\n').encode('utf-8'), 'create'
    text = existing.decode('utf-8')
    if start in text or end in text:
        if text.count(start) != 1 or text.count(end) != 1:
            return existing, 'conflict'
        first, last = text.index(start), text.index(end)
        if first >= last or text[first:last + len(end)] != block:
            return existing, 'conflict'
        return existing, 'unchanged'
    separator = '' if not text or text.endswith('\n\n') else ('\n' if text.endswith('\n') else '\n\n')
    return (text + separator + block + '\n').encode('utf-8'), 'merge'


def unity_settings(root, profile, selection, warnings, baseline):
    if profile['project']['kind'] != 'unity':
        if selection is not None:
            raise ValueError('--unity-root requires a Unity environment package')
        return
    candidates = baseline['facts']['unity_projects']
    if selection is not None:
        selected = project_path(root, selection).relative_to(root).as_posix()
        candidates = [entry for entry in candidates if entry['root'] == selected]
        if not candidates:
            raise ValueError('--unity-root must contain Assets and ProjectSettings/ProjectVersion.txt')
    if len(candidates) != 1:
        warnings.append('Unity root is unconfigured: ' + ('multiple candidates' if candidates else 'no candidate found'))
        return
    profile['unity']['root'] = candidates[0]['root']
    profile['unity']['editor_version'] = candidates[0]['editor_version']
    if not candidates[0]['editor_version']:
        warnings.append('Unity editor version is unconfigured')


def load_manifest(path, root):
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('schema_version') != 1
            or data.get('profile') not in ('general', 'unity')
            or not isinstance(data.get('platforms'), list)
            or not all(p in PLATFORMS for p in data['platforms'])
            or not isinstance(data.get('files'), dict)):
        raise ValueError('Existing manifest has an invalid structure')
    for relative, digest in data['files'].items():
        project_path(root, relative)
        if relative == MANIFEST or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Existing manifest has an invalid file entry')
    return data


def run(args):
    root = args.project.resolve()
    if not root.is_dir():
        raise ValueError('Project root must be an existing directory')
    assets = Path(__file__).resolve().parent.parent / 'assets/project'
    if not assets.is_dir():
        raise ValueError('The package is missing assets/project')
    # Importing the bundled helpers must not leave __pycache__ inside assets/.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(assets / 'tools/ai'))
    from baseline import scan_project, adapt_project, render_adaptation
    from entry_budget import check_entry
    from project_setup import select_configuration, describe_options
    platforms = sorted(set(PLATFORMS if 'all' in args.platform else args.platform))
    warnings = []
    files = {}
    for source in sorted(assets.rglob('*')):
        if source.is_file():
            if not source.resolve().is_relative_to(assets.resolve()):
                raise ValueError('Template link escapes assets/project')
            relative = source.relative_to(assets).as_posix()
            if set(PurePosixPath(relative).parts) & {'__pycache__', '.pytest_cache'} or relative.endswith('.pyc'):
                continue
            files[relative] = source.read_bytes()
    profile_path = 'Docs/ai/project-profile.json'
    profile = json.loads(files[profile_path].decode('utf-8'))
    if profile['project']['kind'] not in ('general', 'unity'):
        raise ValueError('Unknown project kind in package')
    profile['project']['name'] = args.project_name if args.project_name is not None else root.name
    catalog = json.loads(files['Docs/ai/setup-options.json'].decode('utf-8'))
    workflow_path = 'Docs/ai/workflow.json'
    mode = args.workflow
    existing_workflow = project_path(root, workflow_path)
    if existing_workflow.is_file():
        workflow = json.loads(existing_workflow.read_text(encoding='utf-8'))
        if (not isinstance(workflow, dict) or type(workflow.get('schema_version')) is not int
                or workflow['schema_version'] != 1
                or workflow.get('mode') not in ('native', 'unity-harness-init')):
            raise ValueError('Existing workflow must have schema_version 1 and a valid mode')
        if mode is None:
            mode = workflow['mode']
    mode = mode or 'native'
    selected_tools = args.tools
    existing_profile = project_path(root, profile_path)
    if existing_profile.is_file():
        current_profile = json.loads(existing_profile.read_text(encoding='utf-8'))
        if not isinstance(current_profile, dict) or not isinstance(current_profile.get('capabilities'), dict):
            raise ValueError('Existing project profile and capabilities must be objects')
        capabilities = current_profile['capabilities']
        for identifier, capability in capabilities.items():
            if not isinstance(capability, dict):
                raise ValueError(f'Existing capability must be an object: {identifier}')
            if 'integration' in capability and not isinstance(capability['integration'], dict):
                raise ValueError(f'Existing capability integration must be an object: {identifier}')
        if selected_tools is None:
            known = {item['id'] for item in catalog['tools']}
            selected_tools = [identifier for identifier, capability in capabilities.items()
                              if identifier in known and capability.get('integration', {}).get('enabled') is True]
    profile = select_configuration(profile, catalog, mode, selected_tools)
    if mode != 'native':
        overlay = assets.parent / 'workflows' / mode
        if not overlay.is_dir():
            raise ValueError('The package is missing the selected workflow assets')
        for source in sorted(overlay.rglob('*')):
            if source.is_file():
                if not source.resolve().is_relative_to(overlay.resolve()):
                    raise ValueError('Workflow template link escapes its package')
                relative = source.relative_to(overlay).as_posix()
                # The upstream runtime root is lowercase; Windows stores the
                # overlay beside Docs/ai in the same case-insensitive directory.
                if relative.startswith('Docs/harness/'):
                    relative = 'docs/harness/' + relative[len('Docs/harness/'):]
                project_path(root, relative)
                files[relative] = source.read_bytes()
    files[profile_path] = encoded_json(profile)
    files[workflow_path] = encoded_json({'schema_version': 1, 'mode': mode})
    options = describe_options(profile, catalog, mode)
    files.setdefault('.gitignore', b'.ai-local.json\n')
    if 'claude' in platforms:
        files['CLAUDE.md'] = b'Read and follow [AGENTS.md](AGENTS.md) and [the project AI guide](Docs/ai/README.md).\n'
    if 'cursor' in platforms:
        files['.cursor/rules/project-ai.mdc'] = b'---\nalwaysApply: true\n---\nRead and follow AGENTS.md and Docs/ai/README.md at the project root.\n'
    if 'trae' in platforms:
        files['.trae/rules/project_rules.md'] = b'Read and follow AGENTS.md and Docs/ai/README.md at the project root.\n'
    if 'workbuddy' in platforms:
        files['.workbuddy/rules/project-ai.md'] = b'Read and follow AGENTS.md and Docs/ai/README.md at the project root.\n'

    baseline_path = 'Docs/ai/project-baseline.json'
    adaptation_path = 'Docs/ai/project-adaptation.md'
    def scan_outputs():
        # A colliding human file is input, not a generated output. Existing manifest
        # ownership is merged by the scanner; otherwise only absent/identical files
        # can be excluded before the first successful installation.
        owned = {MANIFEST}
        for relative in set(files) | {baseline_path, adaptation_path}:
            target = project_path(root, relative)
            if (PurePosixPath(relative).name in ('AGENTS.md', 'CLAUDE.md', '.gitignore')
                    or not target.exists() or (relative in files and target.is_file()
                    and target.stat().st_size == len(files[relative])
                    and target.read_bytes() == files[relative])):
                owned.add(relative)
                if os.name == 'nt' and relative.startswith('docs/harness/'):
                    # os.walk returns the existing Docs casing on Windows;
                    # both spellings identify this same managed runtime file.
                    owned.add('Docs/harness/' + relative[len('docs/harness/'):])
        return owned

    managed_paths = scan_outputs()
    if args.unity_root is not None:
        project_path(root, args.unity_root)
    baseline = scan_project(root, profile['project']['kind'], args.unity_root, sorted(managed_paths))
    unity_settings(root, profile, args.unity_root, warnings, baseline)
    unity_root = profile.get('unity', {}).get('root')
    if profile['project']['kind'] == 'unity' and unity_root and unity_root != '.':
        nested_root = project_path(root, unity_root)
        nested_entries = ['AGENTS.md']
        for entry in ('CLAUDE.md', '.cursor/rules/project-ai.mdc',
                      '.trae/rules/project_rules.md', '.workbuddy/rules/project-ai.md'):
            if entry in files:
                nested_entries.append(entry)
        for entry in nested_entries:
            relative = (nested_root / entry).relative_to(root).as_posix()
            directory = (nested_root / entry).parent
            rules_link = Path(os.path.relpath(root / 'AGENTS.md', directory)).as_posix()
            guide_link = Path(os.path.relpath(root / 'Docs/ai/README.md', directory)).as_posix()
            content = (f'Read and follow [the repository AI rules]({rules_link}) '
                       f'and [the project AI guide]({guide_link}).\n')
            if entry.endswith('.mdc'):
                content = '---\nalwaysApply: true\n---\n' + content
            files[relative] = content.encode('utf-8')
        policy_path = 'Docs/ai/access-policy.json'
        policy = json.loads(files[policy_path].decode('utf-8'))
        for entry in ('AGENTS.md', 'CLAUDE.md', '.cursor/rules/', '.trae/rules/', '.workbuddy/rules/'):
            relative = (nested_root / entry).relative_to(root).as_posix()
            if entry.endswith('/'):
                relative += '/'
            if relative not in policy['governance_paths']:
                policy['governance_paths'].append(relative)
        files[policy_path] = encoded_json(policy)
        # The first inventory discovers the nested root; exclude its generated entries
        # before persisting the inventory so a later initialization is byte-identical.
        managed_paths = scan_outputs()
        baseline = scan_project(root, profile['project']['kind'], unity_root, sorted(managed_paths))

    profile, context = adapt_project(profile, baseline)
    files[profile_path] = encoded_json(profile)
    files['Docs/ai/context-index.json'] = encoded_json(context)
    files[baseline_path] = encoded_json(baseline)
    files[adaptation_path] = render_adaptation(baseline, profile).encode('utf-8')
    certificate = json.loads(files['Docs/ai/entry-budget.json'].decode('utf-8'))

    changes = []
    output = {}
    entry_budgets = {}
    for relative, content in sorted(files.items()):
        target = project_path(root, relative)
        if target.exists() and not target.is_file():
            changes.append({'path': relative, 'action': 'conflict'})
            continue
        # Checking all ancestors before any mkdir also catches a regular-file parent.
        for parent in target.parents:
            if parent == root:
                break
            if parent.exists() and not parent.is_dir():
                raise ValueError(f'Parent is not a directory: {relative}')
        existing = target.read_bytes() if target.exists() else None
        candidate = content
        if PurePosixPath(relative).name in ('AGENTS.md', 'CLAUDE.md') or relative == '.gitignore':
            content, action = merge_entry(existing, content, relative)
        else:
            action = 'create' if existing is None else ('unchanged' if existing == content else 'conflict')
        if PurePosixPath(relative).name == 'AGENTS.md':
            budget = check_entry(content.decode('utf-8'), certificate,
                                 require_core=(relative == 'AGENTS.md'))
            entry_budgets[relative] = budget
            if not budget['ok']:
                if action != 'conflict':
                    candidate = content
                action = 'conflict'
        change = {'path': relative, 'action': action}
        if args.diff and action != 'unchanged':
            change['diff'] = ''.join(difflib.unified_diff(
                (existing or b'').decode('utf-8').splitlines(keepends=True),
                (candidate if action == 'conflict' else content).decode('utf-8').splitlines(keepends=True),
                fromfile='a/' + relative, tofile='b/' + relative))
        changes.append(change)
        output[relative] = content

    manifest = {'schema_version': 1, 'profile': profile['project']['kind'],
                'platforms': platforms,
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(output.items())}}
    manifest_path = project_path(root, MANIFEST)
    manifest_bytes = encoded_json(manifest)
    if manifest_path.exists():
        load_manifest(manifest_path, root)
        action = 'unchanged' if manifest_path.read_bytes() == manifest_bytes else 'conflict'
    else:
        action = 'create'
    change = {'path': MANIFEST, 'action': action}
    if args.diff and action != 'unchanged':
        change['diff'] = ''.join(difflib.unified_diff(
            (manifest_path.read_text(encoding='utf-8') if manifest_path.exists() else '').splitlines(keepends=True),
            manifest_bytes.decode('utf-8').splitlines(keepends=True),
            fromfile='a/' + MANIFEST, tofile='b/' + MANIFEST))
    changes.append(change)
    output[MANIFEST] = manifest_bytes
    conflicts = [c['path'] for c in changes if c['action'] == 'conflict']
    if args.action == 'apply' and not conflicts:
        for change in changes:
            if change['action'] in ('create', 'merge'):
                target = project_path(root, change['path'])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(output[change['path']])
    return {'ok': not conflicts, 'action': args.action, 'changes': changes,
            'conflicts': conflicts, 'errors': [], 'warnings': warnings,
            **options,
            'entry_budgets': entry_budgets,
            'baseline_scan': {**baseline['scan'], 'file_count': len(baseline['files'])}}, 2 if conflicts else 0


def main():
    parser = Parser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'apply'))
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--project-name')
    parser.add_argument('--platform', nargs='+', choices=(*PLATFORMS, 'all'), default=['codex'])
    parser.add_argument('--unity-root')
    parser.add_argument('--workflow', choices=('native', 'unity-harness-init'),
                        help='Select the workflow; existing mode is retained when omitted')
    parser.add_argument('--tools', nargs='+', metavar='CAPABILITY',
                        help='Select optional tools by catalog ID; use none to skip optional tools')
    parser.add_argument('--diff', action='store_true', help='Include candidate unified diffs in changes')
    try:
        data, code = run(parser.parse_args())
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        data, code = {'ok': False, 'changes': [], 'conflicts': [], 'errors': [str(error)], 'warnings': []}, 2
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
