#!/usr/bin/env python3
"""Inspect project environment metadata without running engineering commands."""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import urlsplit

import entry_budget


POLICY = 'Docs/ai/access-policy.json'
PROFILE = 'Docs/ai/project-profile.json'
CONTEXT = 'Docs/ai/context-index.json'
TASKS = 'Tasks/index.json'
STATUSES = {'proposed', 'ready', 'in_progress', 'blocked', 'review', 'completed', 'cancelled'}
CORE = ('AGENTS.md', 'Docs/ai/README.md', 'Docs/ai/project-rules.md', PROFILE,
        POLICY, CONTEXT, 'Docs/ai/task-template.md', 'Docs/ai/rules.json',
        'Docs/ai/configuration.md', 'Docs/ai/tool-integrations.md', 'Docs/ai/quality-workflows.md',
        'Docs/ai/architecture-policy.json', 'Docs/ai/evals.json', 'Docs/ai/gitleaks.toml',
        TASKS, 'tools/ai/check_env.py', 'tools/ai/environment.py', 'tools/ai/quality.py',
        'tools/ai/evaluate.py', 'tools/ai/baseline.py', 'tools/ai/entry_budget.py',
        'Docs/ai/entry-budget.json', 'Docs/ai/project-baseline.json',
        'Docs/ai/project-adaptation.md', '.ai-environment.json')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def project_path(root, relative, pattern=False):
    if (not isinstance(relative, str) or not relative or '\\' in relative
            or ':' in relative or '\x00' in relative):
        raise ValueError(f'Invalid relative path: {relative!r}')
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'Path escapes project: {relative}')
    if not pattern and any(c in relative for c in '*?'):
        raise ValueError(f'Expected a concrete relative path: {relative}')
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError(f'Linked path escapes project: {relative}')
    return target


def read_json(root, relative):
    data = json.loads(project_path(root, relative).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'{relative} must contain an object')
    return data


def fields(data, known, location, warnings, errors=None):
    for key in sorted(data.keys() - set(known)):
        (errors if errors is not None else warnings).append(f'Unknown configuration field: {location}.{key}')


def path_list(root, value, location, errors, pattern=False, exists=False):
    if not isinstance(value, list):
        errors.append(f'{location} must be a list')
        return
    for item in value:
        try:
            path = project_path(root, item, pattern)
            if exists and not path.exists():
                errors.append(f'Missing referenced path: {item}')
        except (OSError, ValueError) as error:
            errors.append(f'{location}: {error}')


def validate_policy(root, policy, errors, warnings):
    fields(policy, ('schema_version', 'mode', 'roles', 'users', 'governance_paths',
                    'critical_paths', 'generated_paths', 'code_extensions', 'owned_paths'),
           POLICY, warnings, errors)
    if policy.get('schema_version') != 1:
        errors.append('Unsupported access-policy schema_version')
    if policy.get('mode') not in ('audit', 'enforce'):
        errors.append('access-policy mode must be audit or enforce')
    roles, users = policy.get('roles'), policy.get('users')
    if not isinstance(roles, dict) or not isinstance(users, dict):
        errors.append('access-policy roles and users must be objects')
        return
    optional = ('denied_extensions', 'file_grants', 'code_paths', 'generated_extensions')
    for group, entries in (('roles', roles), ('users', users)):
        for name, entry in entries.items():
            location = f'{group}.{name}'
            if not isinstance(name, str) or not name or not isinstance(entry, dict):
                errors.append(f'Invalid permission entry: {location}')
                continue
            known = ('paths', 'elevated_paths', 'denied_paths', *optional,
                     'governance' if group == 'roles' else 'role')
            fields(entry, known, location, warnings, errors)
            for field in ('paths', 'elevated_paths', 'denied_paths', 'code_paths'):
                if field in entry or (group == 'roles' and field != 'code_paths'):
                    path_list(root, entry.get(field), f'{location}.{field}', errors, pattern=True)
            if group == 'roles':
                if not isinstance(entry.get('governance'), bool):
                    errors.append(f'{location}.governance must be boolean')
            elif not isinstance(entry.get('role'), str) or entry['role'] not in roles:
                errors.append(f'Invalid user registration: {name}')
            for field in ('denied_extensions', 'generated_extensions'):
                values = entry.get(field, [])
                if (not isinstance(values, list) or not all(
                        isinstance(value, str) and re.fullmatch(r'\.[^/\\:*?\[\]\s]+', value)
                        for value in values)):
                    errors.append(f'{location}.{field} must contain exact suffixes')
            grants = entry.get('file_grants', [])
            if not isinstance(grants, list):
                errors.append(f'{location}.file_grants must be a list')
                continue
            for grant in grants:
                if not isinstance(grant, dict):
                    errors.append(f'Invalid file grant: {location}')
                    continue
                fields(grant, ('paths', 'suffixes'), location + '.file_grants', warnings, errors)
                path_list(root, grant.get('paths'), location + '.file_grants.paths', errors, pattern=True)
                suffixes = grant.get('suffixes')
                if (not isinstance(suffixes, list) or not suffixes or not all(
                        isinstance(value, str) and re.fullmatch(r'\.[^/\\:*?\[\]\s]+', value)
                        for value in suffixes)):
                    errors.append(f'{location}.file_grants.suffixes must contain exact suffixes')
    for field in ('governance_paths', 'critical_paths'):
        path_list(root, policy.get(field), field, errors, pattern=True)
    if 'generated_paths' in policy:
        path_list(root, policy['generated_paths'], 'policy.generated_paths', errors, pattern=True)
        warnings.append('Deprecated policy.generated_paths is ignored; use profile.generated_paths')
    extensions = policy.get('code_extensions', [])
    if (not isinstance(extensions, list) or not all(
            isinstance(value, str) and re.fullmatch(r'\.[^/\\:*?\[\]\s]+', value)
            for value in extensions)):
        errors.append('code_extensions must contain exact suffixes')
    owned = policy.get('owned_paths', [])
    if not isinstance(owned, list):
        errors.append('owned_paths must be a list')
    else:
        for restriction in owned:
            if not isinstance(restriction, dict):
                errors.append('Invalid owned_paths entry')
                continue
            fields(restriction, ('paths', 'roles'), 'owned_paths', warnings, errors)
            path_list(root, restriction.get('paths'), 'owned_paths.paths', errors, pattern=True)
            if (not isinstance(restriction.get('roles'), list) or not all(
                    isinstance(role, str) and role in roles for role in restriction['roles'])):
                errors.append('owned_paths.roles must contain registered roles')
    if not users:
        warnings.append('No project users are registered; editing remains unconfigured')


def validate_profile(root, profile, errors, warnings):
    fields(profile, ('schema_version', 'project', 'commands', 'generated_paths', 'capabilities',
                     'verification', 'unity', 'conventions', 'change_controls'), PROFILE, warnings)
    project = profile.get('project')
    if not isinstance(project, dict):
        errors.append('project-profile project must be an object')
        return
    fields(project, ('name', 'kind', 'root'), 'project', warnings)
    if not isinstance(project.get('name'), str) or project.get('kind') not in ('general', 'unity'):
        errors.append('Invalid project name or kind')
    path_list(root, [project.get('root')], 'project.root', errors)
    commands = profile.get('commands')
    if not isinstance(commands, dict):
        errors.append('project-profile commands must be an object')
    else:
        fields(commands, ('build', 'test', 'lint'), 'commands', warnings)
        for name in ('build', 'test', 'lint'):
            command = commands.get(name)
            if (not isinstance(command, list) or not all(isinstance(item, str) for item in command)
                    or (command and not command[0].strip())):
                errors.append(f'commands.{name} must be an argument list with a nonempty executable')
            elif not command:
                warnings.append(f'Engineering command is unconfigured: {name}')
    path_list(root, profile.get('generated_paths'), 'profile.generated_paths', errors, pattern=True)
    conventions = profile.get('conventions', {})
    if not isinstance(conventions, dict):
        errors.append('conventions must be an object')
    else:
        fields(conventions, ('commit_language',), 'conventions', warnings)
        if not isinstance(conventions.get('commit_language', ''), str):
            errors.append('conventions.commit_language must be a string')
    controls = profile.get('change_controls', [])
    if not isinstance(controls, list):
        errors.append('change_controls must be a list')
    else:
        ids = set()
        for control in controls:
            if not isinstance(control, dict):
                errors.append('Invalid change control')
                continue
            fields(control, ('id', 'paths', 'roles', 'reason'), 'change_controls', warnings)
            identifier = control.get('id')
            if not isinstance(identifier, str) or not identifier or identifier in ids:
                errors.append('Invalid or duplicate change control id')
            else:
                ids.add(identifier)
            path_list(root, control.get('paths'), 'change_controls.paths', errors, pattern=True)
            if not isinstance(control.get('roles'), list) or not all(isinstance(role, str) and role for role in control['roles']):
                errors.append('change_controls.roles must be a list of role names')
            if not isinstance(control.get('reason'), str):
                errors.append('change_controls.reason must be a string')
    capabilities = profile.get('capabilities')
    if not isinstance(capabilities, dict) or not isinstance(profile.get('verification'), dict):
        errors.append('capabilities and verification must be objects')
        capabilities = {} if not isinstance(capabilities, dict) else capabilities
    enabled_groups = {}
    for name, capability in capabilities.items():
        if not isinstance(capability, dict):
            errors.append(f'Invalid capability: {name}')
            continue
        fields(capability, ('state', 'source_paths', 'entrypoints', 'command', 'verified_revision',
                            'evidence', 'skill', 'input_kinds', 'outputs', 'limitations', 'integration'), f'capabilities.{name}', warnings)
        state = capability.get('state')
        if state not in ('unconfigured', 'located', 'verified'):
            errors.append(f'Invalid capability state: {name}')
        elif state == 'unconfigured':
            warnings.append(f'Capability is unconfigured: {name}')
        for field in ('source_paths', 'entrypoints'):
            path_list(root, capability.get(field, []), f'capabilities.{name}.{field}', errors, exists=True)
        command = capability.get('command', [])
        if (not isinstance(command, list) or not all(isinstance(item, str) for item in command)
                or (command and not command[0].strip())):
            errors.append(f'Invalid capability command: {name}')
        for field in ('verified_revision', 'skill'):
            if field in capability and not isinstance(capability[field], str):
                errors.append(f'capabilities.{name}.{field} must be a string')
        for field in ('evidence', 'input_kinds', 'outputs', 'limitations'):
            if field in capability and (not isinstance(capability[field], list) or not all(
                    isinstance(item, str) and item.strip() for item in capability[field])):
                errors.append(f'capabilities.{name}.{field} must be a list of nonempty strings')
        if state == 'verified' and (not isinstance(capability.get('verified_revision'), str)
                                    or not capability.get('verified_revision', '').strip()
                                    or not capability.get('evidence')):
            errors.append(f'Verified capability requires revision and evidence: {name}')
        if 'integration' in capability:
            validate_integration(capability['integration'], name, enabled_groups, errors, warnings)
    warnings.append('Static checks do not verify runtime rule loading, builds, tests, or server enforcement')
    if project.get('kind') == 'unity':
        unity = profile.get('unity')
        if not isinstance(unity, dict):
            errors.append('Unity profile requires a unity object')
            return
        fields(unity, ('root', 'editor_version', 'target_platforms', 'render_pipeline',
                       'config_source', 'event_tools', 'ui_binding'), 'unity', warnings)
        if not unity.get('root'):
            warnings.append('Unity root is unconfigured')
        else:
            try:
                unity_root = project_path(root, unity['root'])
                if not (unity_root / 'Assets').is_dir():
                    errors.append('Unity root is missing Assets')
                version = project_path(root, (unity_root / 'ProjectSettings/ProjectVersion.txt').relative_to(root).as_posix())
                if not version.is_file():
                    errors.append('Unity root is missing ProjectSettings/ProjectVersion.txt')
                else:
                    match = re.search(r'^m_EditorVersion:\s*(\S+)\s*$', version.read_text(encoding='utf-8'), re.MULTILINE)
                    if match and unity.get('editor_version') != match.group(1):
                        warnings.append('Configured Unity editor version differs from ProjectVersion.txt')
            except (OSError, ValueError) as error:
                errors.append(str(error))
        for name in ('editor_version', 'target_platforms', 'render_pipeline'):
            if not unity.get(name):
                warnings.append(f'Unity setting is unconfigured: {name}')
        for name in ('config_source', 'event_tools', 'ui_binding'):
            setting = unity.get(name)
            if not isinstance(setting, dict):
                errors.append(f'unity.{name} must be an object')
            elif 'state' in setting:
                warnings.append(f'Deprecated unity.{name}.state; reference a top-level capability')
                if setting['state'] not in ('unconfigured', 'located', 'verified'):
                    errors.append(f'Invalid legacy Unity capability state: {name}')
            if isinstance(setting, dict) and 'capability' in setting:
                if not isinstance(setting['capability'], str) or setting['capability'] not in capabilities:
                    errors.append(f'Unknown Unity capability reference: {name}')
            elif isinstance(setting, dict) and 'state' not in setting:
                errors.append(f'unity.{name} requires a capability reference')


def validate_integration(setting, name, enabled_groups, errors, warnings):
    location = f'capabilities.{name}.integration'
    if not isinstance(setting, dict):
        errors.append(f'{location} must be an object')
        return
    fields(setting, ('enabled', 'provider', 'group', 'origin', 'version', 'license', 'transport',
                     'endpoint', 'network', 'environment_variables', 'probe', 'version_pattern',
                     'required', 'timeout_seconds', 'writes'), location, warnings, errors)
    for field in ('enabled', 'required', 'writes'):
        if not isinstance(setting.get(field, False), bool):
            errors.append(f'{location}.{field} must be boolean')
    for field in ('provider', 'group', 'origin', 'version', 'license', 'endpoint', 'version_pattern'):
        if not isinstance(setting.get(field, ''), str):
            errors.append(f'{location}.{field} must be a string')
    transport = setting.get('transport', 'command')
    if transport not in ('command', 'stdio', 'http'):
        errors.append(f'{location}.transport must be command, stdio or http')
    timeout = setting.get('timeout_seconds', 5)
    if type(timeout) is not int or not 1 <= timeout <= 30:
        errors.append(f'{location}.timeout_seconds must be between 1 and 30')
    probe = setting.get('probe', [])
    if (not isinstance(probe, list) or not all(isinstance(arg, str) and '\x00' not in arg for arg in probe)
            or (probe and not probe[0].strip())):
        errors.append(f'{location}.probe must be an executable argument array')
    for field in ('network', 'environment_variables'):
        values = setting.get(field, [])
        if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
            errors.append(f'{location}.{field} must be a list of nonempty strings')
            continue
        pattern = r'[A-Za-z_][A-Za-z0-9_]*' if field == 'environment_variables' else r'[A-Za-z0-9.-]+'
        if any(not re.fullmatch(pattern, value) and not (field == 'network' and value == '::1') for value in values):
            errors.append(f'{location}.{field} contains an invalid name')
    for field in ('origin', 'endpoint'):
        value = setting.get(field, '')
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = urlsplit(value)
            local = parsed.hostname in ('localhost', '127.0.0.1', '::1')
            valid_scheme = parsed.scheme == 'https' or (field == 'endpoint' and local and parsed.scheme == 'http')
            if (not valid_scheme or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or parsed.query or parsed.fragment):
                errors.append(f'{location}.{field} must be a credential-free HTTPS URL or loopback endpoint')
            parsed.port  # Reject malformed ports without printing the sensitive input.
        except ValueError:
            errors.append(f'{location}.{field} is invalid')
    expression = setting.get('version_pattern', '')
    if isinstance(expression, str) and expression:
        try:
            re.compile(expression)
        except re.error:
            errors.append(f'{location}.version_pattern is invalid')
    group = setting.get('group', '')
    if setting.get('enabled') is True:
        if isinstance(group, str) and group:
            if group in enabled_groups:
                errors.append(f'Multiple enabled providers in integration group: {group}')
            enabled_groups[group] = name
        if not all(setting.get(field) for field in ('provider', 'origin', 'version')):
            warnings.append(f'Enabled integration still needs provider, origin or pinned version: {name}')


def validate_context(root, index, errors, warnings):
    fields(index, ('schema_version', 'entries'), CONTEXT, warnings)
    entries = index.get('entries')
    statuses = {}
    if not isinstance(entries, list):
        errors.append('context-index entries must be a list')
        return statuses
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append('Invalid context entry')
            continue
        fields(entry, ('id', 'aliases', 'roots', 'entrypoints', 'verified_revision'), 'context entry', warnings)
        identifier = entry.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            errors.append(f'Invalid or duplicate context id: {identifier}')
            continue
        ids.add(identifier)
        statuses[identifier] = 'unknown'
        if not isinstance(entry.get('aliases'), list) or not all(isinstance(item, str) for item in entry['aliases']):
            errors.append(f'Invalid aliases for context entry: {identifier}')
        if not isinstance(entry.get('verified_revision'), str):
            errors.append(f'Invalid verified_revision for context entry: {identifier}')
        before = len(errors)
        for field in ('roots', 'entrypoints'):
            path_list(root, entry.get(field), f'context.{identifier}.{field}', errors, exists=True)
        revision = entry.get('verified_revision')
        if before != len(errors) or not isinstance(revision, str) or not revision.strip():
            warnings.append(f'Navigation revision is unknown: {identifier}')
            continue
        paths = entry['roots'] + entry['entrypoints']
        if not paths:
            warnings.append(f'Navigation has no source scope: {identifier}')
            continue
        git = ['git', '--literal-pathspecs', '-C', str(root)]
        try:
            resolved = subprocess.run(git + ['rev-parse', '--verify', '--end-of-options', revision + '^{commit}'],
                                      capture_output=True, text=True, encoding='utf-8', timeout=5)
            if resolved.returncode != 0:
                warnings.append(f'Navigation revision cannot be resolved: {identifier}')
                continue
            commit = resolved.stdout.strip()
            statuses[identifier] = 'current'
            commands = [
                ['diff', '--name-only', '-z', commit, 'HEAD', '--', *paths],
                ['diff', '--name-only', '-z', 'HEAD', '--', *paths],
                ['diff', '--cached', '--name-only', '-z', 'HEAD', '--', *paths],
                ['ls-files', '--others', '--exclude-standard', '-z', '--', *paths],
            ]
            for command in commands:
                result = subprocess.run(git + command, capture_output=True, text=True,
                                        encoding='utf-8', timeout=5)
                if result.returncode != 0:
                    statuses[identifier] = 'unknown'
                    warnings.append(f'Navigation changes cannot be inspected: {identifier}')
                    break
                if result.stdout:
                    statuses[identifier] = 'stale'
            if statuses[identifier] == 'stale':
                warnings.append(f'Navigation source scope changed since verification: {identifier}')
        except (OSError, subprocess.TimeoutExpired) as error:
            statuses[identifier] = 'unknown'
            warnings.append(f'Navigation Git inspection failed for {identifier}: {error}')
    return statuses


def validate_tasks(root, index, errors, warnings):
    fields(index, ('schema_version', 'tasks'), TASKS, warnings)
    tasks = index.get('tasks')
    statuses = {}
    if not isinstance(tasks, list):
        errors.append('Tasks index tasks must be a list')
        return statuses
    policy = read_json(root, POLICY)
    users, roles = policy.get('users', {}), policy.get('roles', {})
    graph, task_paths = {}, set()
    for task in tasks:
        if not isinstance(task, dict):
            errors.append('Invalid task entry')
            continue
        fields(task, ('id', 'path', 'status', 'owner', 'depends_on', 'source', 'acceptance',
                      'approvals', 'history', 'required_approvals'), 'task entry', warnings)
        identifier = task.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in graph:
            errors.append(f'Invalid or duplicate task id: {identifier}')
            continue
        dependencies = task.get('depends_on')
        if not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies):
            errors.append(f'Invalid dependencies for task: {identifier}')
            dependencies = []
        graph[identifier] = dependencies
        owner = task.get('owner')
        if task.get('status') not in STATUSES or not isinstance(owner, str):
            errors.append(f'Invalid status or owner for task: {identifier}')
        elif owner and owner not in users:
            errors.append(f'Unregistered task owner: {identifier}: {owner}')
        try:
            body = project_path(root, task.get('path'))
            if not body.is_file() or body.suffix.lower() != '.md':
                errors.append(f'Task body must be a Markdown file: {identifier}')
            resolved = body.resolve()
            if resolved in task_paths:
                errors.append(f'Task body is shared by multiple tasks: {identifier}')
            task_paths.add(resolved)
        except (OSError, ValueError) as error:
            errors.append(f'task.{identifier}.path: {error}')
        source = task.get('source', {})
        if not isinstance(source, dict):
            errors.append(f'Invalid task source: {identifier}')
            source = {}
        else:
            fields(source, ('reference', 'revision', 'confirmed_revision'), f'task.{identifier}.source', warnings)
            for field in ('reference', 'revision', 'confirmed_revision'):
                if field in source and not isinstance(source[field], str):
                    errors.append(f'task.{identifier}.source.{field} must be a string')
        revision = source.get('revision', '')
        stale = bool(revision and revision != source.get('confirmed_revision'))
        statuses[identifier] = {'stale_revision': stale}
        if stale:
            warnings.append(f'Task source revision is not confirmed: {identifier}')
        acceptance = task.get('acceptance', {})
        if not isinstance(acceptance, dict):
            errors.append(f'Invalid task acceptance: {identifier}')
            acceptance = {}
        else:
            fields(acceptance, ('by', 'evidence'), f'task.{identifier}.acceptance', warnings)
        accepted_by = acceptance.get('by', '')
        if not isinstance(accepted_by, str) or (accepted_by and accepted_by not in users):
            errors.append(f'Unregistered task acceptance account: {identifier}')
        evidence = acceptance.get('evidence', [])
        if not isinstance(evidence, list) or not all(isinstance(item, str) and item.strip() for item in evidence):
            errors.append(f'Task acceptance evidence must be a list of nonempty strings: {identifier}')
        if task.get('status') == 'completed' and (not owner or accepted_by != owner or not evidence):
            errors.append(f'Completed task requires owner acceptance and evidence: {identifier}')
        required = task.get('required_approvals', [])
        if not isinstance(required, list) or not all(isinstance(role, str) and role in roles for role in required):
            errors.append(f'Invalid required approval roles: {identifier}')
            required = []
        approvals = task.get('approvals', [])
        approved_roles = set()
        if not isinstance(approvals, list):
            errors.append(f'Task approvals must be a list: {identifier}')
        else:
            for approval in approvals:
                if not isinstance(approval, dict):
                    errors.append(f'Invalid task approval: {identifier}')
                    continue
                fields(approval, ('by', 'role', 'revision', 'evidence'), f'task.{identifier}.approval', warnings)
                by, role = approval.get('by'), approval.get('role')
                valid = (isinstance(by, str) and by in users and isinstance(role, str)
                         and isinstance(users[by], dict) and users[by].get('role') == role)
                if not valid:
                    errors.append(f'Task approval account and role must match registration: {identifier}')
                if not isinstance(approval.get('revision'), str):
                    errors.append(f'Invalid task approval revision: {identifier}')
                    valid = False
                proof = approval.get('evidence')
                if not isinstance(proof, list) or not all(isinstance(item, str) and item.strip() for item in proof):
                    errors.append(f'Invalid task approval evidence: {identifier}')
                    valid = False
                if valid and proof and (not revision or revision == approval['revision']):
                    approved_roles.add(role)
        missing = set(required) - approved_roles
        if missing:
            message = f'Task {identifier} is missing current approvals: {", ".join(sorted(missing))}'
            (errors if task.get('status') == 'completed' else warnings).append(message)
        if not isinstance(task.get('history', []), list):
            errors.append(f'Task history must be a list: {identifier}')
    incoming = dict.fromkeys(graph, 0)
    outgoing = {identifier: [] for identifier in graph}
    for identifier, dependencies in graph.items():
        for dependency in dependencies:
            if dependency not in graph:
                errors.append(f'Task {identifier} has missing dependency: {dependency}')
            else:
                incoming[identifier] += 1
                outgoing[dependency].append(identifier)
    ready = [identifier for identifier, count in incoming.items() if count == 0]
    visited = 0
    while ready:
        identifier = ready.pop()
        visited += 1
        for dependent in outgoing[identifier]:
            incoming[dependent] -= 1
            if incoming[dependent] == 0:
                ready.append(dependent)
    if visited != len(graph):
        errors.append('Task dependency cycle detected')

    return statuses


def validate_manifest(root, manifest, errors, warnings):
    fields(manifest, ('schema_version', 'profile', 'platforms', 'files'), '.ai-environment.json', warnings)
    if manifest.get('profile') not in ('general', 'unity'):
        errors.append('Invalid manifest profile')
    platforms = manifest.get('platforms')
    if not isinstance(platforms, list) or not all(p in ('codex', 'claude', 'cursor', 'trae', 'workbuddy', 'opencode') for p in platforms):
        errors.append('Invalid manifest platforms')
    files = manifest.get('files')
    if not isinstance(files, dict):
        errors.append('Manifest files must be an object')
        return
    for relative, digest in files.items():
        try:
            path = project_path(root, relative)
            if relative == '.ai-environment.json' or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                errors.append(f'Invalid manifest hash entry: {relative}')
            elif not path.is_file():
                errors.append(f'Missing managed file: {relative}')
            elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                warnings.append(f'Managed file has local modifications: {relative}')
        except (OSError, ValueError) as error:
            errors.append(str(error))

    profile = read_json(root, PROFILE)
    project = profile.get('project')
    kind = project.get('kind') if isinstance(project, dict) else None
    if manifest.get('profile') != kind:
        errors.append('Manifest profile does not match project kind')
    required = set(CORE) - {'.ai-environment.json'}
    entries = ['AGENTS.md']
    platform_entries = {'claude': 'CLAUDE.md', 'cursor': '.cursor/rules/project-ai.mdc',
                        'trae': '.trae/rules/project_rules.md', 'workbuddy': '.workbuddy/rules/project-ai.md'}
    if isinstance(platforms, list):
        entries.extend(path for platform, path in platform_entries.items() if platform in platforms)
    if kind == 'unity':
        required.update(('Docs/ai/unity-rules.md', 'Docs/ai/planning-workflows.md', 'Docs/ai/audit-capabilities.md',
                         'Docs/ai/unity-tooling.md', 'Docs/ai/unity-validation.json', 'tools/ai/unity_checks.py'))
        unity = profile.get('unity')
        unity_root = unity.get('root') if isinstance(unity, dict) else None
        if unity_root and unity_root != '.':
            nested = project_path(root, unity_root)
            entries.extend((nested / entry).relative_to(root).as_posix() for entry in tuple(entries))
    required.update(entries)
    for relative in sorted(required):
        if relative not in files:
            errors.append(f'Required file is absent from manifest: {relative}')
        if not project_path(root, relative).is_file():
            errors.append(f'Missing required environment file: {relative}')
    for relative in entries:
        path = project_path(root, relative)
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        guide = 'Docs/ai/README.md' in text
        rules = 'AGENTS.md' in text
        if not guide or (relative != 'AGENTS.md' and not rules):
            errors.append(f'Entry does not route to authoritative rules and guide: {relative}')
        if relative.endswith('.mdc') and not re.search(r'^alwaysApply:\s*true\s*$', text, re.MULTILINE):
            errors.append(f'Cursor entry must set alwaysApply: true: {relative}')
    documents = set(project_path(root, 'Docs/ai').rglob('*.md'))
    documents.update(project_path(root, relative) for relative in entries)
    rule_index = read_json(root, 'Docs/ai/rules.json')
    if rule_index.get('schema_version') != 1 or not isinstance(rule_index.get('sources'), dict):
        errors.append('Invalid rules index schema or sources')
        return
    fields(rule_index, ('schema_version', 'sources'), 'rules index', warnings)
    sources = rule_index['sources']
    rule_ids = {'identity', 'principles', 'grading', 'scope', 'generated', 'commit', 'tracking', 'verification', 'tooling', 'quality', 'adaptation'}
    if kind == 'unity':
        rule_ids.update(('engineering', 'planning', 'unity-tooling'))
    for identifier in sorted(rule_ids - sources.keys()):
        errors.append(f'Missing required rule route: {identifier}')
    expected = {}
    for identifier, relative in sources.items():
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f'Invalid rule id: {identifier}')
            continue
        try:
            path = project_path(root, relative)
            if path.suffix.lower() != '.md' or not path.is_file():
                errors.append(f'Rule source must be an existing Markdown file: {identifier}')
                continue
            expected[identifier] = path.resolve()
            documents.add(path)
        except (OSError, ValueError) as error:
            errors.append(f'Rule source {identifier}: {error}')
    definitions = {}
    for path in sorted(documents):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        project_path(root, relative)
        text = path.read_text(encoding='utf-8')
        for identifier in re.findall(r'<!--\s*ai-rule:\s*(.*?)\s*-->', text, re.DOTALL):
            definitions.setdefault(identifier, []).append(path.resolve())
        for link in re.findall(r'\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"\n]*")?\)', text):
            link = link.strip('<>')
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', link) or link.startswith(('#', '//')):
                continue
            link = link.split('#', 1)[0].split('?', 1)[0]
            if not link:
                continue
            target = (path.parent / link).resolve()
            if ('\\' in link or not target.is_relative_to(root)
                    or not project_path(root, target.relative_to(root).as_posix()).exists()):
                errors.append(f'Broken or escaping Markdown link in {relative}: {link}')
    for identifier, paths in definitions.items():
        if identifier not in expected:
            errors.append(f'Unregistered rule definition: {identifier}')
        elif paths != [expected[identifier]]:
            errors.append(f'Rule must have exactly one definition at its source: {identifier}')
    for identifier in expected.keys() - definitions.keys():
        errors.append(f'Missing rule definition at registered source: {identifier}')


def validate_baseline(root, data, errors, warnings):
    if (type(data.get('schema_version')) is not int or data['schema_version'] != 1
            or data.get('project_kind') not in ('general', 'unity')):
        errors.append('Invalid project baseline schema or project kind')
    scan = data.get('scan')
    if (not isinstance(scan, dict) or scan.get('mode') != 'static-full-inventory'
            or type(scan.get('inventory_complete')) is not bool
            or scan.get('semantic_complete') is not False
            or type(scan.get('content_limit_bytes')) is not int
            or scan.get('content_limit_bytes', 0) < 1):
        errors.append('Invalid baseline scan coverage; semantic verification must remain false')
    else:
        for field in ('managed_paths', 'excluded', 'issues'):
            if not isinstance(scan.get(field), list):
                errors.append(f'Baseline scan.{field} must be a list')
        if scan['inventory_complete'] is False:
            warnings.append('Baseline inventory is incomplete; inspect declared coverage before adapting rules')
        if isinstance(scan.get('issues'), list) and scan['issues']:
            warnings.append(f'Baseline records {len(scan["issues"])} static scan issue(s)')
    for field in ('files', 'commands', 'modules', 'existing_rules', 'adaptations', 'unresolved'):
        if not isinstance(data.get(field), list):
            errors.append(f'Baseline {field} must be a list')
    if not isinstance(data.get('facts'), dict) or not isinstance(data.get('git'), dict):
        errors.append('Baseline facts and git observations must be objects')
    for field in ('runtime_load_verified', 'engineering_verified'):
        if data.get(field) is not False:
            errors.append(f'Static baseline must not claim {field}')
    warnings.append('Project baseline is a static snapshot; source drift requires an explicit baseline compare')


def validate_entry_budgets(root, errors):
    certificate = read_json(root, 'Docs/ai/entry-budget.json')
    names = ('cl100k_base', 'o200k_base')
    if (type(certificate.get('schema_version')) is not int or certificate['schema_version'] != 1
            or type(certificate.get('limit')) is not int or certificate['limit'] != 500
            or not isinstance(certificate.get('template_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', certificate['template_sha256'])
            or not isinstance(certificate.get('token_counts'), dict)
            or any(type(certificate['token_counts'].get(name)) is not int
                   or not 0 <= certificate['token_counts'][name] <= 500 for name in names)):
        errors.append('Invalid offline AGENTS token-budget certificate')
    manifest = read_json(root, '.ai-environment.json')
    files = manifest.get('files', {})
    paths = {'AGENTS.md'}
    if isinstance(files, dict):
        paths.update(relative for relative in files if isinstance(relative, str)
                     and PurePosixPath(relative).name == 'AGENTS.md')
    results = {}
    for relative in sorted(paths):
        path = project_path(root, relative)
        if not path.is_file():
            errors.append(f'Missing generated AGENTS entry: {relative}')
            continue
        result = entry_budget.check_entry(path.read_text(encoding='utf-8'), certificate,
                                          require_core=(relative == 'AGENTS.md'))
        results[relative] = result
        errors.extend(f'{relative}: {message}' for message in result['errors'])
    return results


def check(root):
    errors, warnings = [], []
    context_status, task_status = {}, {}
    repository_skills = {'codex': [], 'claude': []}
    for platform in repository_skills:
        try:
            directory = project_path(root, f'.{platform}/skills')
            if not directory.is_dir():
                continue
            for candidate in sorted(directory.iterdir()):
                try:
                    relative = (candidate / 'SKILL.md').relative_to(root).as_posix()
                    skill = project_path(root, relative)
                    if skill.is_file():
                        repository_skills[platform].append(candidate.name)
                except (OSError, ValueError) as error:
                    warnings.append(f'Project skill discovery skipped an unsafe entry: {error}')
        except (OSError, ValueError) as error:
            warnings.append(f'Project skill discovery is unavailable for {platform}: {error}')
    for relative in CORE:
        try:
            if not project_path(root, relative).is_file():
                errors.append(f'Missing core file: {relative}')
        except (OSError, ValueError) as error:
            errors.append(str(error))
    validators = ((POLICY, validate_policy), (PROFILE, validate_profile),
                  (CONTEXT, validate_context), (TASKS, validate_tasks),
                  ('Docs/ai/project-baseline.json', validate_baseline),
                  ('.ai-environment.json', validate_manifest))
    for relative, validate in validators:
        try:
            data = read_json(root, relative)
            if relative != POLICY and data.get('schema_version') != 1:
                errors.append(f'Unsupported schema_version: {relative}')
            status = validate(root, data, errors, warnings)
            if relative == CONTEXT:
                context_status = status
            elif relative == TASKS:
                task_status = status
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f'{relative}: {error}')
    budgets = {}
    try:
        budgets = validate_entry_budgets(root, errors)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        errors.append(f'AGENTS budget: {error}')
    return {'ok': not errors, 'errors': errors, 'warnings': warnings,
            'entry_budgets': budgets,
            'context_status': context_status, 'task_status': task_status,
            'repository_skills': repository_skills,
            'runtime_load_verified': False, 'engineering_verified': False}, 1 if errors else 0


def resolve_identity(root, policy, explicit, warnings, declared_role=None):
    users = policy.get('users', {})
    if not isinstance(users, dict) or not isinstance(policy.get('roles'), dict):
        raise ValueError('Invalid roles or users registry')
    user, source = explicit, 'argument'
    if not user:
        user, source = os.environ.get('AI_PROJECT_USER'), 'environment'
    local = project_path(root, '.ai-local.json')
    if local.is_symlink():
        raise ValueError('Local identity cache must not be a symbolic link')
    cache = read_json(root, '.ai-local.json') if local.is_file() else {}
    if not user and cache:
        user, source = cache.get('user'), 'local_cache'
    if not user:
        try:
            result = subprocess.run(['git', '-C', str(root), 'config', '--get', 'user.name'],
                                    capture_output=True, text=True, encoding='utf-8', timeout=5)
            candidate = result.stdout.strip() if result.returncode == 0 else ''
            if candidate in users:
                user, source = candidate, 'git_user_name'
        except (OSError, subprocess.TimeoutExpired) as error:
            warnings.append(f'Git user.name could not be inspected: {error}')
    if not user:
        source = 'unconfigured'
    if user is not None and not isinstance(user, str):
        raise ValueError('Local identity user must be a string')
    if declared_role is None and user and user == cache.get('user'):
        declared_role = cache.get('declared_role')
    if declared_role is not None and not isinstance(declared_role, str):
        raise ValueError('Declared role must be a string')
    registration = users.get(user, {})
    role_name = registration.get('role') if isinstance(registration, dict) else None
    role = policy['roles'].get(role_name, {})
    grant = {field: registration.get(field, role.get(field, [])) for field in (
        'paths', 'elevated_paths', 'denied_paths', 'denied_extensions', 'file_grants', 'generated_extensions')}
    if 'code_paths' in registration or 'code_paths' in role:
        grant['code_paths'] = registration.get('code_paths', role.get('code_paths'))
    grant['governance'] = role.get('governance', False)
    role_matches = not declared_role or declared_role == role_name
    if not role_matches:
        warnings.append('Declared role does not match project registration; editing is disabled')
    return {'user': user, 'role': role_name, 'declared_role': declared_role,
            'source': source, 'verified': False, 'role_matches_policy': role_matches,
            'can_edit': bool(grant['paths'] or grant['file_grants']) and role_matches,
            'effective_grant': grant}


def matches(path, patterns):
    for pattern in patterns:
        if pattern == '**':
            return True
        if pattern.endswith('/'):
            if path == pattern.rstrip('/') or path.startswith(pattern):
                return True
        elif fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def scope(root, args, policy):
    errors, warnings = [], []
    validate_policy(root, policy, errors, warnings)
    profile = read_json(root, PROFILE)
    validate_profile(root, profile, errors, warnings)
    paths = []
    for path in args.paths:
        try:
            paths.append((path, project_path(root, path).resolve().relative_to(root).as_posix()))
        except (OSError, ValueError) as error:
            errors.append(str(error))
    if errors:
        return {'ok': False, 'errors': errors, 'warnings': warnings, 'violations': []}, 1
    identity = resolve_identity(root, policy, args.user, warnings)
    grant = identity['effective_grant']
    violations = []
    for requested, path in paths:
        reason = None
        classified = path[:-5] if path.lower().endswith('.meta') else path
        extension = PurePosixPath(classified).suffix.lower()
        generated = (extension in [value.lower() for value in grant['generated_extensions']]
                     and matches(path, profile.get('generated_paths', [])))
        file_granted = any(matches(path, item['paths']) and any(path.endswith(suffix) for suffix in item['suffixes'])
                           for item in grant['file_grants'])
        if not identity['can_edit']:
            reason = 'User has no registered writable scope or declared role conflicts'
        elif matches(path, grant['denied_paths']):
            reason = 'Path is explicitly denied'
        elif not matches(path, grant['paths']) and not file_granted:
            reason = 'Path is outside the role scope'
        elif matches(path, policy.get('governance_paths', [])) and not grant['governance']:
            reason = 'Governance permission is required'
        elif matches(path, policy.get('critical_paths', [])) and not matches(path, grant['elevated_paths']):
            reason = 'Critical path requires elevated scope'
        elif extension in [value.lower() for value in grant['denied_extensions']] and not generated:
            reason = 'File type is explicitly denied'
        elif (extension in [value.lower() for value in policy.get('code_extensions', [])]
              and 'code_paths' in grant and not matches(path, grant['code_paths'])):
            reason = 'Code file requires additional code scope'
        elif any(matches(path, item['paths']) and identity['role'] not in item['roles']
                 for item in policy.get('owned_paths', [])):
            reason = 'Content owner role is required'
        if reason:
            violations.append({'path': requested, 'reason': reason})
    for control in profile.get('change_controls', []):
        if ((not control['roles'] or identity['role'] in control['roles'])
                and any(matches(path, control['paths']) for _, path in paths)):
            warnings.append(f'Change control requires project confirmation: {control["id"]}; scope does not verify chat approval')
    return {'ok': not violations, 'mode': policy['mode'], 'identity': identity,
            'violations': violations, 'errors': [], 'warnings': warnings,
            'server_enforcement_verified': False}, 1 if violations and policy['mode'] == 'enforce' else 0


def run(args):
    root = (args.project or Path(__file__).resolve().parents[2]).resolve()
    if not root.is_dir():
        raise ValueError('Project root must be an existing directory')
    if args.command == 'check':
        return check(root)
    if args.command == 'context':
        index = read_json(root, CONTEXT)
        errors, warnings = [], []
        if index.get('schema_version') != 1:
            errors.append('Unsupported context schema_version')
        statuses = validate_context(root, index, errors, warnings)
        query = args.query.casefold()
        entries = [] if errors else [entry for entry in index['entries']
                                    if query in [entry['id'].casefold(), *(alias.casefold() for alias in entry['aliases'])]]
        return {'ok': not errors, 'entries': entries, 'context_status': statuses,
                'errors': errors, 'warnings': warnings}, 1 if errors else 0
    if args.command == 'clear-identity':
        local = project_path(root, '.ai-local.json')
        removed = local.is_file()
        if local.exists():
            if not removed:
                raise ValueError('Local identity cache must be a file')
            local.unlink()
        return {'ok': True, 'removed': removed, 'errors': [], 'warnings': []}, 0
    policy = read_json(root, POLICY)
    if args.command == 'scope':
        return scope(root, args, policy)
    errors, warnings = [], []
    validate_policy(root, policy, errors, warnings)
    if errors:
        return {'ok': False, 'errors': errors, 'warnings': warnings}, 1
    identity = resolve_identity(root, policy, args.user, warnings, args.role)
    if args.command == 'identity':
        if identity['user'] not in policy['users']:
            raise ValueError('Only a registered user can be cached')
        if args.role and args.role != identity['role']:
            raise ValueError('Requested role does not match the project registry')
        local = project_path(root, '.ai-local.json')
        local.write_text(json.dumps({'user': identity['user'], 'declared_role': identity['declared_role']}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {**identity, 'ok': True, 'errors': [], 'warnings': warnings}, 0


def main():
    parser = Parser(description=__doc__)
    parser.add_argument('--project', type=Path)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for command in ('check', 'whoami', 'identity', 'clear-identity', 'scope', 'context'):
        child = commands.add_parser(command)
        child.add_argument('--project', type=Path, default=argparse.SUPPRESS)
        if command in ('whoami', 'identity', 'scope'):
            child.add_argument('--user')
        if command in ('whoami', 'identity'):
            child.add_argument('--role')
        if command == 'scope':
            child.add_argument('--paths', nargs='+', required=True)
        if command == 'context':
            child.add_argument('--query', required=True)
    try:
        data, code = run(parser.parse_args())
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        data, code = {'ok': False, 'errors': [str(error)], 'warnings': [],
                      'runtime_load_verified': False, 'engineering_verified': False}, 1
    data.setdefault('runtime_load_verified', False)
    data.setdefault('engineering_verified', False)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
