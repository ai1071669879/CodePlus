#!/usr/bin/env python3
"""Inspect declared integrations; run version probes only with explicit --probe."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import check_env as core


def load_profile(root):
    profile = core.read_json(root, core.PROFILE)
    errors, warnings = [], []
    core.validate_profile(root, profile, errors, warnings)
    if errors:
        raise ValueError('; '.join(errors))
    return profile


def resolve_command(root, identifier, argv):
    if (not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv)
            or not argv[0].strip()):
        raise ValueError('Expected a nonempty executable argument list')
    command = list(argv)
    local = core.project_path(root, '.ai-local/tools.json')
    if local.exists():
        mappings = core.read_json(root, '.ai-local/tools.json').get('executables', {})
        if not isinstance(mappings, dict):
            raise ValueError('Local executables must be an object')
        if identifier in mappings:
            executable = mappings[identifier]
            if not isinstance(executable, str) or not Path(executable).is_absolute():
                raise ValueError('Local executable mapping must be an absolute path')
            command[0] = executable
    return command


def executable_available(root, executable):
    path = Path(executable)
    if path.is_absolute():
        return path.is_file()
    if '/' in executable or '\\' in executable:
        return core.project_path(root, executable).is_file()
    return shutil.which(executable) is not None


def doctor(root, profile, probe=False, capability_id=None):
    errors, warnings, checks = [], [], []
    python_ok = sys.version_info >= (3, 10)
    checks.append({'id': 'python', 'status': 'available' if python_ok else 'missing'})
    if not python_ok:
        errors.append('Python 3.10 or newer is required')
    for executable in ('git', 'rg'):
        available = shutil.which(executable) is not None
        checks.append({'id': executable, 'status': 'available' if available else 'missing'})
        if not available:
            warnings.append(f'Optional command is unavailable: {executable}')
    capabilities = profile['capabilities']
    if capability_id and capability_id not in capabilities:
        raise ValueError('Unknown capability selection')
    for identifier, capability in capabilities.items():
        if capability_id and identifier != capability_id:
            continue
        integration = capability.get('integration')
        if integration is None:
            continue
        probe_argv, version = integration.get('probe', []), integration.get('version', '')
        probe_configured = bool(probe_argv and version)
        check = {'id': identifier, 'status': 'skipped', 'version_probe_verified': False,
                 'probe_configured': probe_configured}
        checks.append(check)
        if not integration['enabled']:
            continue
        argv = probe_argv if probe else capability.get('command') or probe_argv
        status = 'unconfigured'
        if argv and (not probe or probe_configured):
            command = resolve_command(root, identifier, argv)
            if not executable_available(root, command[0]):
                status = 'missing'
            elif not probe:
                status = 'available'
            else:
                pattern = integration.get('version_pattern', '')
                try:
                    matcher = re.compile(pattern) if pattern else None
                except re.error:
                    raise ValueError(f'Invalid version pattern: {identifier}') from None
                try:
                    result = subprocess.run(command, cwd=root, shell=False, capture_output=True,
                                            timeout=integration.get('timeout_seconds', 30))
                    check['exit_code'] = result.returncode
                    output = (result.stdout + b'\n' + result.stderr).decode('utf-8', errors='replace')
                    matched = bool(matcher.search(output)) if matcher else version in output
                    status = ('failed' if result.returncode != 0 else
                              'ready' if matched else 'mismatch')
                    check['version_probe_verified'] = status == 'ready'
                except (OSError, subprocess.TimeoutExpired):
                    status = 'failed'
        check['status'] = status
        if integration.get('transport') == 'http' and not argv:
            warnings.append(f'Integration {identifier} requires manual HTTP handshake; connection is unverified')
        if status in ('missing', 'unconfigured', 'mismatch', 'failed'):
            target = errors if integration.get('required', False) else warnings
            target.append(f'Integration {identifier}: {status}')
    return {'ok': not errors, 'checks': checks, 'errors': errors, 'warnings': warnings}, 1 if errors else 0


def modules(profile):
    entries = []
    for identifier, capability in profile['capabilities'].items():
        integration = capability.get('integration')
        if integration is None:
            continue
        missing = [field for field in ('provider', 'version', 'probe') if not integration.get(field)]
        if integration.get('transport') == 'http':
            if not integration.get('endpoint'):
                missing.append('endpoint')
        elif not capability.get('command'):
            missing.append('command')
        entries.append({'id': identifier, 'enabled': integration['enabled'],
                        'provider': integration.get('provider', ''),
                        'group': integration.get('group', ''), 'state': capability['state'],
                        'missing': missing,
                        'probe_configured': bool(integration.get('version') and integration.get('probe'))})
    return {'ok': True, 'modules': entries, 'errors': [], 'warnings': []}, 0


def main():
    parser = core.Parser(description=__doc__)
    parser.add_argument('--project', type=Path)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=core.Parser)
    for name in ('doctor', 'modules'):
        child = commands.add_parser(name)
        child.add_argument('--project', type=Path, default=argparse.SUPPRESS)
        if name == 'doctor':
            child.add_argument('--probe', action='store_true')
            child.add_argument('--capability')
    try:
        args = parser.parse_args()
        root = (args.project or Path(__file__).resolve().parents[2]).resolve()
        if not root.is_dir():
            raise ValueError('Project root must be an existing directory')
        profile = load_profile(root)
        data, code = (doctor(root, profile, args.probe, args.capability)
                      if args.command == 'doctor' else modules(profile))
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        data, code = {'ok': False, 'errors': [str(error)], 'warnings': []}, 1
    data.update(runtime_load_verified=False, engineering_verified=False)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
