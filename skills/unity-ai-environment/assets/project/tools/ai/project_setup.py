#!/usr/bin/env python3
"""List optional tools and check recorded prerequisites without executing them."""
import argparse
import copy
import json
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.dont_write_bytecode = True

from check_env import Parser, PROFILE, project_path, read_json, validate_profile


CATALOG = 'Docs/ai/setup-options.json'
WORKFLOW = 'Docs/ai/workflow.json'
MODES = ('native', 'unity-harness-init')


def _validate_options(profile, catalog, mode):
    if not isinstance(profile, dict) or not isinstance(profile.get('capabilities'), dict):
        raise ValueError('project-profile capabilities must be an object')
    if type(profile.get('schema_version')) is not int or profile['schema_version'] != 1:
        raise ValueError('Unsupported project-profile schema_version')
    if (not isinstance(catalog, dict) or type(catalog.get('schema_version')) is not int
            or catalog['schema_version'] != 1
            or set(catalog) != {'schema_version', 'tools', 'workflows'}):
        raise ValueError('Invalid setup-options schema or fields')
    tools, workflows = {}, {}
    for field, fields, entries in (
            ('tools', {'id', 'name', 'summary', 'features', 'prerequisites', 'setup'}, tools),
            ('workflows', {'id', 'name', 'summary', 'required_tools', 'state_source', 'guide'}, workflows)):
        if not isinstance(catalog.get(field), list):
            raise ValueError(f'setup-options.{field} must be a list')
        for entry in catalog[field]:
            if not isinstance(entry, dict) or set(entry) != fields:
                raise ValueError(f'Invalid setup-options.{field} fields; catalog contains descriptions only')
            for key in fields - {'features', 'prerequisites', 'required_tools'}:
                if not isinstance(entry[key], str) or not entry[key].strip():
                    raise ValueError(f'setup-options.{field}.{key} must be a nonempty string')
            identifier = entry['id']
            if identifier in entries:
                raise ValueError(f'Duplicate setup-options.{field} id: {identifier}')
            for key in fields & {'features', 'prerequisites', 'required_tools'}:
                values = entry[key]
                if not isinstance(values, list) or not all(
                        isinstance(value, str) and value.strip() for value in values):
                    raise ValueError(f'setup-options.{field}.{identifier}.{key} must be a string list')
                if key == 'required_tools' and len(values) != len(set(values)):
                    raise ValueError(f'Duplicate required tool: {identifier}')
            for key in fields & {'setup', 'guide', 'state_source'}:
                relative, separator, anchor = entry[key].partition('#')
                project_path(Path.cwd().resolve(), relative)
                if separator and (not anchor.strip() or '#' in anchor):
                    raise ValueError(f'Invalid documentation anchor: {identifier}.{key}')
            entries[identifier] = entry
    if set(workflows) != set(MODES):
        raise ValueError('setup-options workflows must define native and unity-harness-init')
    if not isinstance(mode, str) or mode not in workflows:
        raise ValueError('Unknown workflow mode')
    capabilities = profile['capabilities']
    for identifier in tools:
        capability = capabilities.get(identifier)
        if not isinstance(capability, dict) or not isinstance(capability.get('integration'), dict):
            raise ValueError(f'Unknown tool capability or missing integration: {identifier}')
    for workflow in workflows.values():
        for identifier in workflow['required_tools']:
            if identifier not in tools:
                raise ValueError(f'Unknown required tool: {identifier}')
    if workflows['native']['required_tools']:
        raise ValueError('native required_tools must be empty')
    if set(workflows['unity-harness-init']['required_tools']) != {
            'unity-skills-rest', 'unity-harness-init', 'copilot-cli'}:
        raise ValueError('unity-harness-init requires exactly unity-skills-rest, unity-harness-init and copilot-cli')
    for identifier, relative in (('native', 'Tasks/index.json'),
                                 ('unity-harness-init', 'docs/harness/progress.md')):
        if workflows[identifier]['state_source'] != relative:
            raise ValueError(f'{identifier}.state_source must be {relative}')
    for identifier, capability in capabilities.items():
        if not isinstance(capability, dict):
            raise ValueError(f'Invalid capability: {identifier}')
        integration = capability.get('integration', {})
        if not isinstance(integration, dict):
            raise ValueError(f'Invalid integration: {identifier}')
        for field in ('enabled', 'required'):
            if type(integration.get(field, False)) is not bool:
                raise ValueError(f'{identifier}.{field} must be boolean')
        if not isinstance(integration.get('group', ''), str):
            raise ValueError(f'{identifier}.group must be a string')
    return tools, workflows


def _validate_groups(profile):
    groups = {}
    for identifier, capability in profile['capabilities'].items():
        integration = capability.get('integration', {})
        group = integration.get('group', '')
        if integration.get('enabled') and group:
            if group in groups:
                raise ValueError(f'Enabled integration group conflict: {group}: {groups[group]}, {identifier}')
            groups[group] = identifier


def select_configuration(profile, catalog, mode, selected_tools=None):
    """Return a separate profile with explicit selection and required mode tools."""
    tools, workflows = _validate_options(profile, catalog, mode)
    if selected_tools is not None:
        if (not isinstance(selected_tools, list)
                or not all(isinstance(identifier, str) for identifier in selected_tools)):
            raise ValueError('selected_tools must be a list of tool IDs')
        if len(selected_tools) != len(set(selected_tools)):
            raise ValueError('selected_tools contains duplicate tool IDs')
        if 'none' in selected_tools and selected_tools != ['none']:
            raise ValueError('none cannot be mixed with other tools')
        for identifier in selected_tools:
            if identifier != 'none' and identifier not in tools:
                raise ValueError(f'Unknown selected tool: {identifier}')
    result = copy.deepcopy(profile)
    if selected_tools is not None:
        for identifier in tools:
            result['capabilities'][identifier]['integration']['enabled'] = identifier in selected_tools
    for identifier in workflows[mode]['required_tools']:
        result['capabilities'][identifier]['integration'].update(enabled=True, required=True)
    _validate_groups(result)
    return result


def describe_options(profile, catalog, mode):
    """Merge static descriptions with the profile's current capability records."""
    tools, _ = _validate_options(profile, catalog, mode)
    _validate_groups(profile)
    options = []
    for identifier, description in tools.items():
        capability = profile['capabilities'][identifier]
        integration = capability['integration']
        options.append({**copy.deepcopy(description),
                        'enabled': integration.get('enabled', False),
                        'group': integration.get('group', ''),
                        'state': capability.get('state'),
                        'required': integration.get('required', False)})
    return {'optional_tools': options, 'workflow_options': copy.deepcopy(catalog['workflows']),
            'selected_workflow': mode}


def run(args):
    root = (args.project or Path(__file__).resolve().parents[2]).resolve()
    if not root.is_dir():
        raise ValueError('Project root must be an existing directory')
    profile = read_json(root, PROFILE)
    catalog = read_json(root, CATALOG)
    workflow = read_json(root, WORKFLOW)
    if (type(workflow.get('schema_version')) is not int or workflow['schema_version'] != 1
            or set(workflow) != {'schema_version', 'mode'}):
        raise ValueError('Invalid workflow schema or fields')
    mode = workflow['mode']
    tools, workflows = _validate_options(profile, catalog, mode)
    _validate_groups(profile)
    for entry in (*tools.values(), *workflows.values()):
        for field in ('setup', 'guide', 'state_source'):
            if field in entry:
                project_path(root, entry[field].split('#', 1)[0])
    errors, warnings, unverified = [], [], []
    validate_profile(root, profile, errors, warnings)
    required = workflows[mode]['required_tools']
    if args.command == 'check':
        state_source = workflows[mode]['state_source']
        if not project_path(root, state_source).is_file():
            unverified.append(f'Missing workflow state source: {state_source}')
        for identifier in required:
            capability = profile['capabilities'][identifier]
            integration = capability['integration']
            for field in ('enabled', 'required'):
                if integration.get(field) is not True:
                    unverified.append(f'{identifier}.{field} must be true')
            if capability.get('state') != 'verified':
                unverified.append(f'{identifier}.state must be verified')
            for field, record in (('version', integration), ('verified_revision', capability)):
                if not isinstance(record.get(field), str) or not record[field].strip():
                    unverified.append(f'{identifier}.{field} must be recorded')
            evidence = capability.get('evidence')
            if not isinstance(evidence, list) or not evidence or not all(
                    isinstance(item, str) and item.strip() for item in evidence):
                unverified.append(f'{identifier}.evidence must contain verification records')
            if integration.get('transport', 'command') == 'http':
                if not isinstance(integration.get('endpoint'), str) or not integration['endpoint'].strip():
                    unverified.append(f'{identifier}.endpoint must be recorded')
            elif not capability.get('command'):
                unverified.append(f'{identifier}.command must be a nonempty argument list')
            # A missing verification record blocks this mode; malformed types still remain errors.
            missing_record = f'Verified capability requires revision and evidence: {identifier}'
            if missing_record in errors:
                errors.remove(missing_record)
        if mode == 'unity-harness-init':
            rules = read_json(root, 'Docs/ai/rules.json')
            sources = rules.get('sources')
            if (type(rules.get('schema_version')) is not int or rules['schema_version'] != 1
                    or not isinstance(sources, dict)):
                errors.append('Invalid rules schema or sources')
            else:
                for identifier in ('intent', 'execution', 'tracking', 'grading', 'verification'):
                    if sources.get(identifier) != 'Docs/ai/workflow.md':
                        unverified.append(f'rules.sources.{identifier} must point to Docs/ai/workflow.md')
            for relative in ('.github/copilot-instructions.md',
                             '.github/skills/unity-skills/scripts/unity_skills.py',
                             *(f'.github/agents/{role}.agent.md' for role in
                               ('planner', 'developer', 'reviewer', 'coordinator'))):
                if not project_path(root, relative).is_file():
                    unverified.append(f'Missing Harness prerequisite file: {relative}')
            tasks = read_json(root, 'Tasks/index.json')
            if not isinstance(tasks.get('tasks'), list):
                errors.append('Tasks/index.json.tasks must be a list')
            elif tasks['tasks']:
                unverified.append('Tasks/index.json.tasks must be empty; Harness progress is the state source')
    data = {**describe_options(profile, catalog, mode), 'ok': not errors and not unverified,
            'errors': errors, 'warnings': warnings, 'unverified': unverified,
            'runtime_load_verified': False, 'engineering_verified': False}
    if args.command == 'check':
        data['status'] = ('invalid configuration' if errors else 'unverified prerequisites' if unverified
                          else 'recorded prerequisites satisfied; runtime checks have not run')
    return data, 1 if errors else 2 if unverified else 0


def main():
    parser = Parser(description=__doc__)
    parser.add_argument('--project', type=Path)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for name in ('list', 'check'):
        child = commands.add_parser(name)
        child.add_argument('--project', type=Path, default=argparse.SUPPRESS)
    try:
        data, code = run(parser.parse_args())
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        data, code = {'ok': False, 'errors': [str(error)], 'warnings': [],
                      'runtime_load_verified': False, 'engineering_verified': False}, 1
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
