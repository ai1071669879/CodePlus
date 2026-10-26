#!/usr/bin/env python3
"""Inventory a workspace without executing its code or reading sensitive files."""
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

from check_env import Parser, project_path, read_json

try:
    import tomllib
except ImportError:  # Python 3.10 still inventories TOML without a parser dependency.
    tomllib = None


LIMIT = 1048576
MANIFEST = '.ai-environment.json'
BASELINE = 'Docs/ai/project-baseline.json'
PRUNED = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.vs'}
UNITY_CACHE = {'library', 'temp', 'obj', 'logs', 'usersettings'}
LANGUAGES = {
    '.py': 'Python', '.pyi': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript',
    '.mjs': 'JavaScript', '.cjs': 'JavaScript', '.ts': 'TypeScript', '.tsx': 'TypeScript',
    '.cs': 'C#', '.c': 'C', '.h': 'C', '.cc': 'C++', '.cpp': 'C++', '.cxx': 'C++',
    '.hpp': 'C++', '.hh': 'C++', '.go': 'Go', '.rs': 'Rust', '.java': 'Java',
    '.kt': 'Kotlin', '.kts': 'Kotlin', '.swift': 'Swift', '.m': 'Objective-C',
    '.mm': 'Objective-C++', '.rb': 'Ruby', '.php': 'PHP', '.lua': 'Lua',
    '.sh': 'Shell', '.bash': 'Shell', '.ps1': 'PowerShell', '.psm1': 'PowerShell',
    '.bat': 'Batch', '.cmd': 'Batch', '.sql': 'SQL', '.r': 'R', '.dart': 'Dart',
    '.scala': 'Scala', '.vue': 'Vue', '.svelte': 'Svelte', '.html': 'HTML',
    '.css': 'CSS', '.scss': 'SCSS', '.sass': 'Sass', '.shader': 'ShaderLab',
    '.hlsl': 'HLSL', '.glsl': 'GLSL', '.compute': 'HLSL', '.cginc': 'HLSL',
    '.ex': 'Elixir', '.exs': 'Elixir', '.erl': 'Erlang', '.clj': 'Clojure',
    '.fs': 'F#', '.fsx': 'F#', '.vb': 'Visual Basic', '.pl': 'Perl',
}
TEXT_SUFFIXES = set(LANGUAGES) | {
    '.json', '.jsonc', '.toml', '.xml', '.yaml', '.yml', '.ini', '.cfg', '.conf',
    '.lock', '.md', '.mdx', '.rst', '.txt', '.csv', '.tsv', '.editorconfig',
    '.csproj', '.fsproj', '.vbproj', '.sln', '.props', '.targets', '.gradle',
    '.meta', '.asmdef', '.asmref', '.unity', '.prefab', '.asset', '.mat',
    '.uxml', '.uss', '.dockerfile', '.cmake', '.gitattributes', '.gitignore', '.mdc',
}
TEXT_NAMES = {'makefile', 'gnumakefile', 'dockerfile', 'cmakelists.txt', '.editorconfig',
              '.gitignore', '.gitattributes', 'jenkinsfile', 'gemfile', 'rakefile',
              'license', 'contributing', '.eslintrc', '.prettierrc', 'cargo.lock',
              'go.mod', 'go.sum', 'gradlew', 'gradlew.bat'}
MANIFEST_NAMES = {
    'package.json': 'node', 'package-lock.json': 'node', 'npm-shrinkwrap.json': 'node',
    'yarn.lock': 'node', 'pnpm-lock.yaml': 'node', 'bun.lock': 'node', 'bun.lockb': 'node',
    'pyproject.toml': 'python', 'poetry.lock': 'python', 'uv.lock': 'python',
    'go.mod': 'go', 'go.sum': 'go', 'cargo.toml': 'rust', 'cargo.lock': 'rust',
    'pom.xml': 'jvm', 'build.gradle': 'jvm', 'build.gradle.kts': 'jvm',
    'cmakelists.txt': 'cmake', 'makefile': 'make', 'gnumakefile': 'make',
}


def sensitive(relative):
    parts = PurePosixPath(relative).parts
    name = parts[-1].casefold()
    return (any(part.casefold() == '.aws' for part in parts)
            or name == '.env' or name.startswith('.env.')
            or name.startswith('.credentials') or name in {'auth.json', '.npmrc', '.netrc', '.pypirc'}
            or name.startswith('.ai-local') or PurePosixPath(name).suffix in {'.key', '.pem', '.pfx'})


def linked(path, metadata=None):
    metadata = metadata or path.lstat()
    return (stat.S_ISLNK(metadata.st_mode)
            or bool(getattr(metadata, 'st_file_attributes', 0)
                    & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)))


def entry_file(relative):
    return PurePosixPath(relative).name in {'AGENTS.md', 'CLAUDE.md', '.gitignore'}


def rule_file(relative):
    path = PurePosixPath(relative)
    if path.name in {'AGENTS.md', 'CLAUDE.md', 'CONTRIBUTING', 'CONTRIBUTING.md', '.editorconfig'}:
        return True
    location = '/' + relative.casefold()
    return (path.suffix.casefold() in {'.md', '.mdc'} and
            ('/docs/ai/' in location or re.search(r'/\.(?:cursor|trae|workbuddy)/rules/', location)))


def manual_content(text, relative):
    prefix, suffix = ('#', '') if PurePosixPath(relative).name == '.gitignore' else ('<!--', ' -->')
    start = f'{prefix} ai-environment:start{suffix}'
    end = f'{prefix} ai-environment:end{suffix}'
    if start not in text and end not in text:
        return text.strip('\r\n'), True
    # Only a single, correctly ordered pair owns content. Malformed markers are retained.
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) >= text.index(end):
        return text.strip('\r\n'), False
    first, last = text.index(start), text.index(end) + len(end)
    return (text[:first] + text[last:]).strip('\r\n'), True


def manifest_toolchain(relative):
    path = PurePosixPath(relative)
    name = path.name.casefold()
    if name in {'manifest.json', 'packages-lock.json'} and path.parent.name == 'Packages':
        return 'unity'
    if path.suffix.casefold() in {'.csproj', '.fsproj', '.vbproj', '.sln'}:
        return 'dotnet'
    if name == 'requirements.txt' or (name.startswith('requirements') and name.endswith('.txt')):
        return 'python'
    return MANIFEST_NAMES.get(name, '')


def ci_file(relative):
    parts = PurePosixPath(relative).parts
    return (relative.startswith('.github/workflows/') or '.circleci' in parts
            or PurePosixPath(relative).name.casefold() in {
                '.gitlab-ci.yml', '.gitlab-ci.yaml', 'azure-pipelines.yml', 'jenkinsfile'})


def file_kind(relative, language, toolchain):
    name = PurePosixPath(relative).name
    if toolchain:
        return 'manifest'
    if ci_file(relative):
        return 'ci'
    if name == '.editorconfig' or name.startswith(('.eslintrc', '.prettierrc')):
        return 'configuration'
    if PurePosixPath(relative).suffix.casefold() == '.meta':
        return 'meta'
    if language:
        return 'source'
    if PurePosixPath(relative).suffix.casefold() in {'.md', '.mdx', '.rst', '.txt'}:
        return 'documentation'
    if PurePosixPath(relative).suffix.casefold() in TEXT_SUFFIXES or name.casefold() in TEXT_NAMES:
        return 'configuration'
    return 'resource'


def declared_package_commands(relative, text, package, paths, unresolved):
    scripts = package.get('scripts', {})
    if not isinstance(scripts, dict):
        return []
    directory = PurePosixPath(relative).parent.as_posix()
    manager = package.get('packageManager', '')
    match = re.fullmatch(r'(npm|pnpm|yarn|bun)@[^\s/\\]+', manager) if isinstance(manager, str) else None
    locks = [(PurePosixPath(directory) / lock).as_posix() for lock in (
        'pnpm-lock.yaml', 'yarn.lock', 'bun.lock', 'bun.lockb', 'package-lock.json', 'npm-shrinkwrap.json')
        if (PurePosixPath(directory) / lock).as_posix() in paths]
    lock_managers = {('pnpm' if PurePosixPath(lock).name == 'pnpm-lock.yaml' else
                      'yarn' if PurePosixPath(lock).name == 'yarn.lock' else
                      'bun' if PurePosixPath(lock).name in {'bun.lock', 'bun.lockb'} else 'npm')
                     for lock in locks}
    if match:
        manager = match.group(1)
        if lock_managers - {manager}:
            unresolved.append('Package manager declaration conflicts with lock files: ' + ', '.join([relative, *locks]))
    elif len(lock_managers) > 1:
        unresolved.append('Conflicting package manager lock files; commands unresolved: ' + ', '.join(locks))
        return []
    else:
        manager = next(iter(lock_managers), 'npm')
    result = []
    for purpose in ('build', 'test', 'lint'):
        if not isinstance(scripts.get(purpose), str) or not scripts[purpose].strip():
            continue
        signal = re.search(r'"' + purpose + r'"\s*:', text)
        result.append({'purpose': purpose, 'argv': [manager, 'run', purpose],
                       'working_directory': directory,
                       'evidence': {'path': relative, 'line': text.count('\n', 0, signal.start()) + 1 if signal else 1},
                       'status': 'declared'})
    return result


def git_inventory(root, managed):
    result = {'available': False, 'head': '', 'branch': '', 'changes': []}
    git_path = root / '.git'
    try:
        if not git_path.exists() or linked(git_path):
            return result
    except OSError:
        return result
    base = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false']
    try:
        head = subprocess.run(base + ['rev-parse', '--verify', 'HEAD'], cwd=root, shell=False,
                              timeout=10, capture_output=True, text=True, encoding='utf-8', errors='replace')
        branch = subprocess.run(base + ['rev-parse', '--abbrev-ref', 'HEAD'], cwd=root, shell=False,
                                timeout=10, capture_output=True, text=True, encoding='utf-8', errors='replace')
        status = subprocess.run(base + ['status', '--porcelain=v1', '-z', '--untracked-files=all'],
                                cwd=root, shell=False, timeout=10, capture_output=True,
                                text=True, encoding='utf-8', errors='replace')
    except (OSError, subprocess.TimeoutExpired):
        return result
    result['available'] = status.returncode == 0
    if head.returncode == 0 and re.fullmatch(r'[0-9a-f]{40,64}', head.stdout.strip()):
        result['head'] = head.stdout.strip()
    if branch.returncode == 0:
        result['branch'] = branch.stdout.strip()
    entries = status.stdout.split('\0') if status.returncode == 0 else []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        state, relative = entry[:2], entry[3:]
        if 'R' in state or 'C' in state:
            index += 1  # porcelain -z puts the source of a rename/copy in the next record.
        try:
            project_path(root, relative)
        except (ValueError, OSError):
            continue
        if relative in managed or sensitive(relative):
            continue
        result['changes'].append({'path': relative, 'status': state})
    result['changes'].sort(key=lambda change: (change['path'], change['status']))
    return result


def scan_project(root, kind='general', unity_root=None, managed_paths=()):
    """Return a stable full-tree static inventory; never write or run project code."""
    root = Path(root).resolve()
    if not root.is_dir() or kind not in {'general', 'unity'}:
        raise ValueError('Existing project root and general/unity kind are required')
    if unity_root is not None:
        project_path(root, unity_root)
    managed = {MANIFEST}
    for relative in managed_paths:
        project_path(root, relative)
        managed.add(PurePosixPath(relative).as_posix())
    issues, excluded, unresolved = [], [], []
    complete = True
    old_manifest = root / MANIFEST
    try:
        if old_manifest.exists() and not linked(old_manifest):
            if old_manifest.stat().st_size > LIMIT:
                issues.append({'path': MANIFEST, 'reason': 'too-large'})
            else:
                data = read_json(root, MANIFEST)
                if not isinstance(data.get('files'), dict):
                    raise ValueError('Invalid environment manifest')
                for relative in data['files']:
                    project_path(root, relative)
                    managed.add(PurePosixPath(relative).as_posix())
    except (ValueError, UnicodeError):
        issues.append({'path': MANIFEST, 'reason': 'invalid-format'})
    except OSError:
        issues.append({'path': MANIFEST, 'reason': 'read-error'})
        complete = False
    # Record the entire exclusion contract, including outputs which do not exist yet.
    excluded.extend({'path': relative, 'reason': 'managed-output'} for relative in sorted(managed)
                    if not entry_file(relative))
    files, texts, unity_projects = [], {}, []

    def walk_error(error):
        nonlocal complete
        complete = False
        try:
            relative = Path(error.filename).relative_to(root).as_posix()
        except (TypeError, ValueError):
            relative = '.'
        issues.append({'path': relative, 'reason': 'directory-read-error'})

    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
        directory = Path(directory)
        safe_names = []
        for name in sorted(names):
            target = directory / name
            relative = target.relative_to(root).as_posix()
            try:
                if linked(target):
                    excluded.append({'path': relative, 'reason': 'linked-path'})
                elif sensitive(relative):
                    excluded.append({'path': relative, 'reason': 'sensitive'})
                elif name.casefold() in PRUNED:
                    excluded.append({'path': relative, 'reason': 'dependency-or-cache'})
                else:
                    safe_names.append(name)
            except OSError:
                complete = False
                issues.append({'path': relative, 'reason': 'stat-error'})
        is_unity = False
        if 'Assets' in safe_names and 'ProjectSettings' in safe_names:
            version = directory / 'ProjectSettings/ProjectVersion.txt'
            try:
                is_unity = version.is_file() and not linked(version)
            except OSError:
                complete = False
                issues.append({'path': version.relative_to(root).as_posix(), 'reason': 'stat-error'})
        if is_unity:
            unity_projects.append({'root': directory.relative_to(root).as_posix(), 'editor_version': ''})
            for name in safe_names[:]:
                if name.casefold() in UNITY_CACHE:
                    excluded.append({'path': (directory / name).relative_to(root).as_posix(), 'reason': 'unity-cache'})
                    safe_names.remove(name)
        names[:] = safe_names
        for name in sorted(filenames):
            target = directory / name
            relative = target.relative_to(root).as_posix()
            try:
                metadata = target.lstat()
                if linked(target, metadata):
                    excluded.append({'path': relative, 'reason': 'linked-path'})
                    continue
                if sensitive(relative):
                    excluded.append({'path': relative, 'reason': 'sensitive'})
                    continue
                if relative in managed and not entry_file(relative):
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    excluded.append({'path': relative, 'reason': 'non-regular-file'})
                    continue
                language = LANGUAGES.get(target.suffix.casefold(), '')
                toolchain = manifest_toolchain(relative)
                record = {'path': relative, 'kind': file_kind(relative, language, toolchain),
                          'language': language, 'size': metadata.st_size, 'sha256': '',
                          'content_status': 'metadata-only'}
                is_text = target.suffix.casefold() in TEXT_SUFFIXES or name.casefold() in TEXT_NAMES
                if is_text and metadata.st_size > LIMIT:
                    record['content_status'] = 'too-large'
                    unresolved.append('Text exceeds content limit: ' + relative)
                elif is_text:
                    content = target.read_bytes()
                    if len(content) > LIMIT:
                        record['content_status'] = 'too-large'
                        unresolved.append('Text exceeds content limit: ' + relative)
                    else:
                        try:
                            text = content.decode('utf-8-sig')
                        except UnicodeError:
                            text = None
                        if entry_file(relative) and text is not None:
                            text, valid = manual_content(text, relative)
                            if not valid:
                                issues.append({'path': relative, 'reason': 'invalid-managed-markers'})
                            if not text:
                                continue
                            content = text.encode('utf-8')
                            record['size'] = len(content)
                        record['content_status'] = 'read'
                        record['sha256'] = hashlib.sha256(content).hexdigest()
                        if text is None:
                            issues.append({'path': relative, 'reason': 'unsupported-text-encoding'})
                        elif (target.suffix.casefold() in {'.json', '.toml', '.xml', '.csproj', '.fsproj',
                                                         '.vbproj', '.props', '.targets', '.asmdef', '.asmref'}
                              or name == 'ProjectVersion.txt'):
                            # Ordinary source content is hashed and released in this iteration.
                            texts[relative] = text
                files.append(record)
            except OSError:
                complete = False
                issues.append({'path': relative, 'reason': 'read-error'})

    files.sort(key=lambda record: record['path'])
    paths = {record['path'] for record in files}
    manifests, commands, rules = [], [], []
    adaptations = []
    for record in files:
        relative = record['path']
        name = PurePosixPath(relative).name
        toolchain = manifest_toolchain(relative)
        if toolchain:
            manifests.append({'path': relative, 'toolchain': toolchain})
        text = texts.get(relative)
        parsed = None
        if text is not None:
            try:
                if PurePosixPath(relative).suffix.casefold() in {'.json', '.asmdef', '.asmref'}:
                    parsed = json.loads(text)
                elif PurePosixPath(relative).suffix.casefold() == '.toml':
                    if tomllib is not None:
                        parsed = tomllib.loads(text)
                    else:
                        unresolved.append('TOML syntax not parsed on this Python runtime: ' + relative)
                elif PurePosixPath(relative).suffix.casefold() in {'.xml', '.csproj', '.fsproj', '.vbproj', '.props', '.targets'}:
                    ET.fromstring(text)
            except (ValueError, ET.ParseError):
                issues.append({'path': relative, 'reason': 'invalid-format'})
            if name == 'package.json' and isinstance(parsed, dict):
                commands.extend(declared_package_commands(relative, text, parsed, paths, unresolved))
        if rule_file(relative) and record['sha256']:
            rules.append({'path': relative, 'sha256': record['sha256']})
    for unity in unity_projects:
        version_path = (PurePosixPath(unity['root']) / 'ProjectSettings/ProjectVersion.txt').as_posix()
        match = re.search(r'^m_EditorVersion:\s*([0-9][A-Za-z0-9.]+)\s*$', texts.get(version_path, ''), re.MULTILINE)
        unity['editor_version'] = match.group(1) if match else ''
    languages = sorted({record['language'] for record in files if record['language']})
    if rules:
        adaptations.append({'id': 'existing-rules', 'title': 'Existing project rules',
                            'rule': 'Read the existing project rules before changing their covered paths.',
                            'evidence': [{'path': rule['path'], 'line': 1} for rule in rules]})
    if languages:
        adaptations.append({'id': 'source-languages', 'title': 'Detected source languages',
                            'rule': 'Use the existing source conventions for: ' + ', '.join(languages) + '.',
                            'evidence': [{'path': next(record['path'] for record in files if record['language'] == language), 'line': 1}
                                         for language in languages]})
    if manifests:
        adaptations.append({'id': 'engineering-entrypoints', 'title': 'Engineering entrypoints',
                            'rule': 'Read the detected manifests and confirm their declared gates before execution; inventory does not verify engineering behavior.',
                            'evidence': [{'path': manifest['path'], 'line': 1} for manifest in manifests]})
    policies = [record['path'] for record in files if ci_file(record['path'])
                or PurePosixPath(record['path']).name.startswith(('.eslint', 'eslint.config', '.prettier', 'ruff.toml', '.editorconfig'))]
    if policies:
        adaptations.append({'id': 'existing-policy', 'title': 'Existing lint and CI policy',
                            'rule': 'Read the existing lint, formatting and CI policy before changing its covered files; no pipeline has been executed.',
                            'evidence': [{'path': relative, 'line': 1} for relative in policies]})
    if kind == 'unity' and unity_projects:
        adaptations.append({'id': 'unity-assets', 'title': 'Unity project boundaries',
                            'rule': 'Check Unity lifecycle and serialization effects. Keep assets with their .meta files and preserve existing assembly boundaries; static inventory does not verify runtime loading.',
                            'evidence': [{'path': (PurePosixPath(unity['root']) / 'ProjectSettings/ProjectVersion.txt').as_posix(), 'line': 1}
                                         for unity in unity_projects]})
    module_roots = {}
    for manifest in manifests:
        module_roots.setdefault(PurePosixPath(manifest['path']).parent.as_posix(), []).append(manifest['path'])
    manifest_roots = tuple(PurePosixPath(directory) for directory in module_roots)
    for record in files:
        source = PurePosixPath(record['path'])
        if record['kind'] == 'source' and not any(source.is_relative_to(directory) for directory in manifest_roots):
            module_roots.setdefault(source.parts[0] if len(source.parts) > 1 else '.', []).append(record['path'])
    modules = [{'id': 'module-' + hashlib.sha256(directory.encode('utf-8')).hexdigest()[:16],
                'root': directory, 'entrypoints': sorted(entries)[:5]}
               for directory, entries in sorted(module_roots.items())]
    unresolved.extend(['Module ownership and exporter responsibilities require maintainer confirmation.',
                       'Runtime loading, engineering gates and performance have not been verified.'])
    return {'schema_version': 1, 'project_kind': kind,
            'scan': {'mode': 'static-full-inventory', 'inventory_complete': complete,
                     'semantic_complete': False, 'content_limit_bytes': LIMIT,
                     'managed_paths': sorted(managed),
                     'excluded': sorted(excluded, key=lambda entry: (entry['path'], entry['reason'])),
                     'issues': sorted(issues, key=lambda entry: (entry['path'], entry['reason']))},
            'git': git_inventory(root, managed), 'files': files,
            'facts': {'languages': languages, 'manifests': manifests,
                      'unity_projects': sorted(unity_projects, key=lambda unity: unity['root'])},
            'commands': sorted(commands, key=lambda command: (command['working_directory'], command['purpose'])),
            'modules': modules, 'existing_rules': rules, 'adaptations': adaptations,
            'unresolved': sorted(set(unresolved)), 'runtime_load_verified': False,
            'engineering_verified': False}


def adapt_project(profile, baseline):
    """Copy facts and unambiguous root commands; never grant permissions."""
    adapted = copy.deepcopy(profile)
    commands = adapted.setdefault('commands', {})
    for purpose in ('build', 'test', 'lint'):
        candidates = [command for command in baseline['commands']
                      if command['purpose'] == purpose and command['working_directory'] == '.']
        if not commands.get(purpose) and len(candidates) == 1:
            commands[purpose] = list(candidates[0]['argv'])
    entries = [{'id': module['id'], 'aliases': [module['root']], 'roots': [module['root']],
                'entrypoints': list(module['entrypoints']), 'verified_revision': ''}
               for module in baseline['modules']]
    return adapted, {'schema_version': 1, 'entries': entries}


def render_adaptation(baseline, profile):
    """Render only evidence-backed static rules and explicit verification limits."""
    lines = ['# Project adaptation', '', '<!-- ai-rule: adaptation -->', '',
             'This full-tree static inventory does not establish semantic completeness, runtime loading or engineering verification.', '',
             'Project kind: ' + baseline['project_kind'] + '.',
             'Inventory complete: ' + str(baseline['scan']['inventory_complete']).lower() + '.', '']
    for adaptation in baseline['adaptations']:
        lines.extend(['## ' + adaptation['title'], '', adaptation['rule'], ''])
        for evidence in adaptation['evidence']:
            lines.append('- Evidence: ' + json.dumps(evidence['path'], ensure_ascii=False) + ':' + str(evidence['line']))
        lines.append('')
    if baseline['commands']:
        lines.extend(['## Declared commands', '', 'Commands are declarations; execution requires the project workflow.', ''])
        for command in baseline['commands']:
            lines.append('- ' + command['purpose'] + ': ' + json.dumps(command['argv'])
                         + '; directory ' + json.dumps(command['working_directory'])
                         + '; evidence ' + json.dumps(command['evidence']['path']) + ':' + str(command['evidence']['line']))
        lines.append('')
    lines.extend(['## Unresolved', ''])
    lines.extend('- ' + item for item in baseline['unresolved'])
    return '\n'.join(lines) + '\n'


def compare_project(root):
    stored = read_json(root, BASELINE)
    if (stored.get('schema_version') != 1 or stored.get('project_kind') not in {'general', 'unity'}
            or not isinstance(stored.get('files'), list) or not isinstance(stored.get('scan'), dict)
            or not isinstance(stored['scan'].get('managed_paths'), list)):
        raise ValueError('Invalid project baseline')
    previous = {}
    for record in stored['files']:
        if (not isinstance(record, dict) or not isinstance(record.get('path'), str)
                or not isinstance(record.get('sha256'), str) or not isinstance(record.get('size'), int)
                or not isinstance(record.get('content_status'), str)):
            raise ValueError('Invalid project baseline file record')
        project_path(root, record['path'])
        previous[record['path']] = record
    current = scan_project(root, stored['project_kind'], None, stored['scan']['managed_paths'])
    after = {record['path']: record for record in current['files']}
    added = sorted(after.keys() - previous.keys())
    removed = sorted(previous.keys() - after.keys())
    changed = sorted(path for path in previous.keys() & after.keys() if previous[path] != after[path])
    complete = current['scan']['inventory_complete'] and stored['scan'].get('inventory_complete') is True
    flags = {'runtime_load_verified': False, 'engineering_verified': False, 'semantic_complete': False}
    coverage = {'inventory_complete': complete, 'issues': current['scan']['issues'],
                'excluded': current['scan']['excluded'],
                'content_gaps': [record['path'] for record in current['files'] if record['content_status'] != 'read']}
    return {'added': added, 'removed': removed, 'changed': changed, 'coverage': coverage, 'flags': flags}, (2 if not complete else 1 if added or removed or changed else 0)


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('action', choices=('scan', 'compare'))
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[2])
    try:
        args = parser.parse_args(argv)
        root = args.project.resolve()
        if args.action == 'compare':
            output, code = compare_project(root)
        else:
            profile = {}
            if project_path(root, 'Docs/ai/project-profile.json').is_file():
                profile = read_json(root, 'Docs/ai/project-profile.json')
            output = scan_project(root, profile.get('project', {}).get('kind', 'general'),
                                  profile.get('unity', {}).get('root') or None)
            code = 0 if output['scan']['inventory_complete'] else 2
    except (OSError, ValueError, TypeError, KeyError):
        output, code = {'error': 'Invalid or unavailable project baseline/configuration'}, 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
