#!/usr/bin/env python3
"""Validate declared skill cases or score externally normalized run observations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import check_env as core


CASES = 'Docs/ai/evals.json'
LIMITATIONS = [
    'Scoring checks supplied normalized observations and referenced log bytes only; '
    'it does not establish log provenance, actual model execution, or truthful normalization.',
    'No model, network, installation, project command, or profile state update is performed.'
]


def validate_cases(root, relative):
    data = core.read_json(root, relative)
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('Unsupported cases schema_version')
    if data.keys() - {'schema_version', 'target_skill', 'cases'}:
        raise ValueError('Unknown cases document field')
    if not isinstance(data.get('target_skill'), str) or not data['target_skill'].strip():
        raise ValueError('target_skill must be a nonempty string')
    cases = data.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('cases must be a nonempty list')
    identifiers = set()
    required = {'id', 'prompt', 'should_trigger', 'required_actions', 'forbidden_actions', 'required_artifacts'}
    for case in cases:
        if not isinstance(case, dict) or not required <= case.keys() or case.keys() - required - {'max_commands'}:
            raise ValueError('Invalid case fields')
        identifier = case['id']
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise ValueError('Case id must be nonempty and unique')
        identifiers.add(identifier)
        if not isinstance(case['prompt'], str) or not case['prompt'].strip():
            raise ValueError(f'{identifier}: prompt must be a nonempty string')
        if not isinstance(case['should_trigger'], bool):
            raise ValueError(f'{identifier}: should_trigger must be boolean')
        for field in ('required_actions', 'forbidden_actions', 'required_artifacts'):
            values = case[field]
            if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
                raise ValueError(f'{identifier}: {field} must be a list of nonempty strings')
        for relative in case['required_artifacts']:
            core.project_path(root, relative)
        if 'max_commands' in case and (type(case['max_commands']) is not int or case['max_commands'] < 0):
            raise ValueError(f'{identifier}: max_commands must be a nonnegative integer')
    return data


def score(root, cases, relative):
    observations = core.read_json(root, relative)
    if type(observations.get('schema_version')) is not int or observations['schema_version'] != 1:
        raise ValueError('Unsupported observations schema_version')
    if observations.keys() - {'schema_version', 'cases'} or not isinstance(observations.get('cases'), list):
        raise ValueError('Invalid observations document fields or cases list')
    errors, indexed, duplicates = [], {}, set()
    expected = {case['id'] for case in cases['cases']}
    for observation in observations['cases']:
        if not isinstance(observation, dict):
            errors.append('Observation must be an object')
            continue
        identifier = observation.get('id')
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append('Observation id must be a nonempty string')
        elif identifier not in expected:
            errors.append(f'Unknown observation case: {identifier}')
        elif identifier in indexed:
            duplicates.add(identifier)
            errors.append(f'Duplicate observation case: {identifier}')
        else:
            indexed[identifier] = observation

    results = []
    observed_evidence = True
    required = {'id', 'triggered', 'outcome', 'actions', 'artifacts', 'command_count', 'evidence', 'trace'}
    for case in cases['cases']:
        identifier, findings = case['id'], []
        observation = indexed.get(identifier)
        trace_valid, evidence_valid = False, False
        if observation is None:
            findings.append('Missing observation')
        else:
            if identifier in duplicates:
                findings.append('Duplicate observations prevent a unique score')
            if not required <= observation.keys() or observation.keys() - required:
                findings.append('Invalid observation fields')
            if not isinstance(observation.get('triggered'), bool):
                findings.append('triggered must be boolean')
            elif observation['triggered'] != case['should_trigger']:
                findings.append('Trigger differs from should_trigger')
            if observation.get('outcome') not in ('passed', 'failed', 'blocked'):
                findings.append('Invalid outcome')
            elif observation['outcome'] != 'passed':
                findings.append(f'Outcome is {observation["outcome"]}')
            for field in ('actions', 'artifacts', 'evidence'):
                values = observation.get(field)
                valid = isinstance(values, list) and all(isinstance(value, str) and value.strip() for value in values)
                if not valid:
                    findings.append(f'{field} must be a list of nonempty strings')
                elif field == 'actions':
                    if set(case['required_actions']) - set(values):
                        findings.append('Missing required actions')
                    if set(case['forbidden_actions']) & set(values):
                        findings.append('Forbidden actions were observed')
                elif field == 'artifacts':
                    if set(case['required_artifacts']) - set(values):
                        findings.append('Missing required artifact declarations')
                    for artifact in set(values) | set(case['required_artifacts']):
                        try:
                            if not core.project_path(root, artifact).is_file():
                                findings.append(f'Artifact is not an existing file: {artifact}')
                        except (OSError, ValueError) as error:
                            findings.append(f'Invalid artifact: {error}')
                else:
                    evidence_valid = bool(values)
                    if not evidence_valid:
                        findings.append('evidence must be nonempty')
            count = observation.get('command_count')
            if type(count) is not int or count < 0:
                findings.append('command_count must be a nonnegative integer')
            elif 'max_commands' in case and count > case['max_commands']:
                findings.append('Command budget exceeded')
            trace = observation.get('trace')
            if (not isinstance(trace, dict) or trace.keys() != {'path', 'sha256'}
                    or not isinstance(trace.get('sha256'), str)
                    or not re.fullmatch(r'[0-9a-fA-F]{64}', trace['sha256'])):
                findings.append('trace requires a relative path and SHA-256 digest')
            else:
                try:
                    path = core.project_path(root, trace['path'])
                    if not path.is_file():
                        findings.append('Trace is not an existing file')
                    else:
                        digest = hashlib.sha256()
                        with path.open('rb') as stream:
                            while chunk := stream.read(1024 * 1024):
                                digest.update(chunk)
                        trace_valid = digest.hexdigest() == trace['sha256'].lower()
                        if not trace_valid:
                            findings.append('Trace SHA-256 mismatch')
                except (OSError, ValueError) as error:
                    findings.append(f'Invalid trace: {error}')
        observed_evidence = observed_evidence and trace_valid and evidence_valid and identifier not in duplicates
        results.append({'id': identifier, 'ok': not findings, 'findings': findings, 'trace_valid': trace_valid})
    passed = sum(result['ok'] for result in results)
    ok = not errors and passed == len(results)
    return {'ok': ok, 'errors': errors, 'cases': results, 'total': len(results),
            'passed': passed, 'failed': len(results) - passed,
            'observed_evidence': observed_evidence, 'limitations': LIMITATIONS}, 0 if ok else 1


def main():
    parser = core.Parser(description=__doc__)
    parser.add_argument('--project', type=Path)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=core.Parser)
    for name in ('validate', 'score'):
        child = commands.add_parser(name)
        child.add_argument('--project', type=Path, default=argparse.SUPPRESS)
        child.add_argument('--cases', default=CASES)
        if name == 'score':
            child.add_argument('--observations', required=True)
    try:
        args = parser.parse_args()
        root = (args.project or Path(__file__).resolve().parents[2]).resolve()
        if not root.is_dir():
            raise ValueError('Project root must be an existing directory')
        cases = validate_cases(root, args.cases)
        if args.command == 'validate':
            data, code = {'ok': True, 'errors': [], 'total': len(cases['cases']),
                          'observed_evidence': False,
                          'limitations': ['Only case structure was validated; no model run was observed.']}, 0
        else:
            data, code = score(root, cases, args.observations)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        data, code = {'ok': False, 'errors': [str(error)], 'observed_evidence': False,
                      'limitations': LIMITATIONS}, 1
    data['runtime_load_verified'] = False
    data['engineering_verified'] = False
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
