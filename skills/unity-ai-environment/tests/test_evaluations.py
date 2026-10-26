"""Black-box checks for declared skill cases and normalized run evidence."""
import copy
import hashlib
import os
import subprocess
import unittest

from upgrade_support import Harness
from test_environment import snapshot


class EvaluationTests(Harness):
    def setUp(self):
        super().setUp()
        self.initialize()
        self.cases = {'schema_version': 1, 'target_skill': 'example-skill', 'cases': [
            {'id': 'positive', 'prompt': 'Run the requested workflow.', 'should_trigger': True,
             'required_actions': ['inspect'], 'forbidden_actions': ['install'],
             'required_artifacts': ['reports/result.txt'], 'max_commands': 2},
            {'id': 'negative', 'prompt': 'Explain an unrelated topic.', 'should_trigger': False,
             'required_actions': [], 'forbidden_actions': ['install'], 'required_artifacts': []}]}
        trace = self.root / 'runs/raw.log'
        trace.parent.mkdir()
        trace.write_bytes(b'RAW LOG CONTENT MUST NOT BE PRINTED\n')
        artifact = self.root / 'reports/result.txt'
        artifact.parent.mkdir()
        artifact.write_text('result', encoding='utf-8')
        reference = {'path': 'runs/raw.log', 'sha256': hashlib.sha256(trace.read_bytes()).hexdigest()}
        self.observations = {'schema_version': 1, 'cases': [
            {'id': 'positive', 'triggered': True, 'outcome': 'passed', 'actions': ['inspect'],
             'artifacts': ['reports/result.txt'], 'command_count': 2,
             'evidence': ['Observed workflow actions in the attached trace.'], 'trace': reference},
            {'id': 'negative', 'triggered': False, 'outcome': 'passed', 'actions': [],
             'artifacts': [], 'command_count': 0, 'evidence': ['Observed no trigger.'],
             'trace': copy.deepcopy(reference)}]}
        self.write_json('Docs/ai/evals.json', self.cases)
        self.write_json('runs/observations.json', self.observations)

    def score(self):
        self.write_json('runs/observations.json', self.observations)
        return self.tool('evaluate.py', 'score', '--observations', 'runs/observations.json')

    def assert_failed(self, result, data):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIsInstance(data, dict, result.stdout + result.stderr)
        self.assertFalse(data['ok'])
        self.assertFalse(data['runtime_load_verified'])
        self.assertFalse(data['engineering_verified'])
        self.assertNotIn('Traceback', result.stderr)

    def test_validate_is_schema_only_and_read_only(self):
        before = snapshot(self.root)
        result, data = self.tool('evaluate.py', 'validate')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['ok'])
        self.assertEqual(data['total'], 2)
        self.assertFalse(data['observed_evidence'])
        self.assertFalse(data['runtime_load_verified'])
        self.assertTrue(data['limitations'])
        self.assertEqual(snapshot(self.root), before)

    def test_positive_and_negative_runs_pass_without_mutation_or_log_disclosure(self):
        before = snapshot(self.root)
        result, data = self.score()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((data['total'], data['passed'], data['failed']), (2, 2, 0))
        self.assertTrue(all(case['ok'] and not case['findings'] for case in data['cases']))
        self.assertTrue(data['observed_evidence'])
        self.assertTrue(data['limitations'])
        self.assertNotIn('RAW LOG CONTENT', result.stdout + result.stderr)
        self.assertEqual(snapshot(self.root), before)

    def test_project_option_before_subcommand_and_custom_cases(self):
        self.write_json('runs/cases.json', self.cases)
        result, data = self.command(self.root / 'tools/ai/evaluate.py', '--project', self.root,
                                    'validate', '--cases', 'runs/cases.json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['ok'])

    def test_empty_cases_and_invalid_case_schema_fail(self):
        variants = [[], [self.cases['cases'][0], self.cases['cases'][0]], [None]]
        for cases in variants:
            with self.subTest(cases=cases):
                self.write_json('Docs/ai/evals.json', {**self.cases, 'cases': cases})
                self.assert_failed(*self.tool('evaluate.py', 'validate'))
        for field, value in [('should_trigger', 1), ('prompt', ' '), ('id', ''),
                             ('required_actions', ['']), ('forbidden_actions', 'install'),
                             ('max_commands', True), ('max_commands', -1),
                             ('required_artifacts', ['../outside'])]:
            with self.subTest(field=field, value=value):
                cases = copy.deepcopy(self.cases)
                cases['cases'][0][field] = value
                self.write_json('Docs/ai/evals.json', cases)
                self.assert_failed(*self.tool('evaluate.py', 'validate'))

    def test_validate_does_not_require_future_artifacts(self):
        (self.root / 'reports/result.txt').unlink()
        result, data = self.tool('evaluate.py', 'validate')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['ok'])

    def test_missed_and_unwanted_triggers_fail(self):
        for index in (0, 1):
            with self.subTest(index=index):
                self.observations['cases'][index]['triggered'] = not self.cases['cases'][index]['should_trigger']
                result, data = self.score()
                self.assert_failed(result, data)
                self.assertEqual(data['passed'], 1)
                self.assertTrue(data['observed_evidence'])
                self.assertTrue(data['cases'][index]['findings'])
                self.observations['cases'][index]['triggered'] = self.cases['cases'][index]['should_trigger']

    def test_missing_unknown_duplicate_and_empty_observations_fail(self):
        original = copy.deepcopy(self.observations)
        variants = [[], [original['cases'][0]],
                    [*original['cases'], original['cases'][0]],
                    [*original['cases'], {**original['cases'][0], 'id': 'unknown'}]]
        for cases in variants:
            with self.subTest(count=len(cases)):
                self.observations = {**original, 'cases': cases}
                result, data = self.score()
                self.assert_failed(result, data)
                if len(cases) < 2 or cases[-1]['id'] == 'positive':
                    self.assertFalse(data['observed_evidence'])

    def test_required_forbidden_actions_and_cost_budget_fail(self):
        for field, value in [('actions', []), ('actions', ['inspect', 'install']), ('command_count', 3)]:
            with self.subTest(field=field, value=value):
                original = copy.deepcopy(self.observations)
                self.observations['cases'][0][field] = value
                self.assert_failed(*self.score())
                self.observations = original

    def test_failed_and_blocked_outcomes_cannot_pass(self):
        for outcome in ('failed', 'blocked'):
            with self.subTest(outcome=outcome):
                self.observations['cases'][0]['outcome'] = outcome
                self.assert_failed(*self.score())

    def test_required_artifact_must_be_reported_and_exist_as_file(self):
        self.observations['cases'][0]['artifacts'] = []
        self.assert_failed(*self.score())
        self.observations['cases'][0]['artifacts'] = ['reports/result.txt']
        artifact = self.root / 'reports/result.txt'
        artifact.unlink()
        self.assert_failed(*self.score())
        artifact.mkdir()
        self.assert_failed(*self.score())

    def test_missing_invalid_or_mismatched_trace_and_empty_evidence_fail(self):
        original = copy.deepcopy(self.observations)
        variants = [('trace', None), ('trace', {'path': 'runs/missing', 'sha256': 'a' * 64}),
                    ('trace', {'path': 'runs/raw.log', 'sha256': 'a' * 64}),
                    ('trace', {'path': 'runs/raw.log', 'sha256': 'invalid'}),
                    ('evidence', []), ('evidence', [' '])]
        for field, value in variants:
            with self.subTest(field=field, value=value):
                self.observations = copy.deepcopy(original)
                self.observations['cases'][0][field] = value
                result, data = self.score()
                self.assert_failed(result, data)
                self.assertFalse(data['observed_evidence'])

    def test_observation_schema_rejects_wrong_types(self):
        original = copy.deepcopy(self.observations)
        for field, value in [('triggered', 1), ('outcome', 'success'), ('actions', ['']),
                             ('artifacts', 'reports/result.txt'), ('command_count', True),
                             ('command_count', -1), ('evidence', 'log')]:
            with self.subTest(field=field, value=value):
                self.observations = copy.deepcopy(original)
                self.observations['cases'][0][field] = value
                self.assert_failed(*self.score())

    def test_all_input_trace_and_artifact_paths_remain_in_project(self):
        for path in ('../outside.json', str(self.root / 'runs/observations.json')):
            with self.subTest(path=path):
                self.assert_failed(*self.tool('evaluate.py', 'validate', '--cases', path))
                self.assert_failed(*self.tool('evaluate.py', 'score', '--observations', path))
        for field in ('trace', 'artifacts'):
            original = copy.deepcopy(self.observations)
            self.observations['cases'][0][field] = (
                {'path': '../outside.log', 'sha256': 'a' * 64} if field == 'trace' else ['../outside'])
            self.assert_failed(*self.score())
            self.observations = original

    def test_symlink_escape_is_rejected(self):
        outside = self.case_dir / 'outside'
        outside.mkdir()
        (outside / 'raw.log').write_text('outside', encoding='utf-8')
        link = self.root / 'linked'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name != 'nt':
                self.skipTest(f'Host cannot create directory symlinks: {error}')
            self.assertTrue(link.resolve().is_relative_to(self.case_dir.resolve()))
            self.assertTrue(outside.resolve().is_relative_to(self.case_dir.resolve()))
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(link.resolve(), outside.resolve())
        self.observations['cases'][0]['trace']['path'] = 'linked/raw.log'
        self.assert_failed(*self.score())
        self.observations['cases'][0]['trace']['path'] = 'runs/raw.log'
        self.observations['cases'][0]['artifacts'] = ['linked/raw.log']
        self.assert_failed(*self.score())

    def test_malformed_json_and_cli_errors_are_json(self):
        (self.root / 'runs/bad.json').write_text('{bad', encoding='utf-8')
        self.assert_failed(*self.tool('evaluate.py', 'validate', '--cases', 'runs/bad.json'))
        self.assert_failed(*self.tool('evaluate.py', 'score'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
