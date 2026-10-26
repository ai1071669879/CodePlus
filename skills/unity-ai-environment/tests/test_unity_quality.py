"""Black-box checks of supplied Unity evidence; no Editor is invoked."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest

from upgrade_support import Harness


class UnityQualityTests(Harness):
    def setUp(self):
        super().setUp()
        (self.root / 'Game/Assets').mkdir(parents=True)
        (self.root / 'Game/ProjectSettings').mkdir()
        (self.root / 'Game/ProjectSettings/ProjectVersion.txt').write_text(
            'm_EditorVersion: 2022.3.60f1\n', encoding='utf-8')
        self.initialize()

    def check(self, expected, *args):
        result, data = self.tool('unity_checks.py', *args)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertIsNotNone(data)
        self.assertFalse(data['runtime_load_verified'])
        self.assertFalse(data['engineering_verified'])
        self.assertEqual(data['ok'], expected == 0)
        return data

    def xml(self, text):
        (self.root / 'results.xml').write_text(text, encoding='utf-8')

    def performance(self):
        samples = {'schema_version': 1, 'source_revision': 'abc', 'context': {
            'editor_version': '2022.3.60f1', 'platform': 'Windows', 'device': 'fixture',
            'scenario': 'battle', 'backend': 'IL2CPP', 'build_mode': 'Player'},
            'metrics': [{'name': 'frame', 'unit': 'ms', 'value': 10, 'sample_count': 30}]}
        budgets = {'schema_version': 1, 'performance': {'context': {'platform': 'Windows'},
            'metrics': [{'name': 'frame', 'unit': 'ms', 'max': 12, 'min_samples': 20}]}}
        self.write_json('samples.json', samples)
        self.write_json('Docs/ai/unity-validation.json', budgets)
        return samples, budgets

    def sarif(self):
        report = {'version': '2.1.0', 'runs': [{'tool': {
            'driver': {'name': 'compiler'},
            'extensions': [{'name': 'Microsoft.Unity.Analyzers'}]},
            'invocations': [{'executionSuccessful': True}], 'results': []}]}
        self.write_json('analysis.sarif', report)
        return report

    def asset(self, name, guid='a' * 32, directory=False):
        path = self.root / 'Game/Assets' / name
        if directory:
            path.mkdir(parents=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture', encoding='utf-8')
        Path(str(path) + '.meta').write_text('fileFormatVersion: 2\nguid: ' + guid + '\n', encoding='utf-8')
        return path

    def test_nunit_two_and_three_counts(self):
        for wrapper, success in [('test-results', 'Success'), ('test-run', 'Passed')]:
            with self.subTest(wrapper=wrapper):
                self.xml(f'<{wrapper} result="{success}"><test-suite><test-case result="{success}"/>'
                         f'<test-case result="Ignored"/></test-suite></{wrapper}>')
                data = self.check(0, 'tests', '--report', 'results.xml', '--exit-code', '0')
                self.assertEqual([data[x] for x in ('total', 'passed', 'failed', 'skipped')], [2, 1, 0, 1])
                self.assertTrue(data['process_exit_verified'])

    def test_nunit_no_process_claim_without_exit_code(self):
        self.xml('<test-run><test-case result="Passed"/></test-run>')
        self.assertFalse(self.check(0, 'tests', '--report', 'results.xml')['process_exit_verified'])

    def test_nunit_failure_root_failure_and_process_failure(self):
        for text, extra in [('<test-run><test-case result="Failed"/></test-run>', []),
                            ('<test-run result="Failed"><test-case result="Passed"/></test-run>', []),
                            ('<test-run><test-case result="Passed"/></test-run>', ['--exit-code', '3'])]:
            with self.subTest(text=text, extra=extra):
                self.xml(text)
                self.check(1, 'tests', '--report', 'results.xml', *extra)

    def test_nunit_zero_and_all_skipped_are_insufficient(self):
        for text in ('<test-run/>', '<test-results><test-case result="Inconclusive"/></test-results>'):
            with self.subTest(text=text):
                self.xml(text)
                self.check(2, 'tests', '--report', 'results.xml')

    def test_nunit_rejects_dtd_entities_unknown_and_malformed(self):
        for text in ('<!DOCTYPE test-run [<!ENTITY x "Passed">]><test-run/>',
                     '<test-run><test-case result="Mystery"/></test-run>', '<broken',
                     '<other><test-case result="Passed"/></other>'):
            with self.subTest(text=text):
                self.xml(text)
                self.check(1, 'tests', '--report', 'results.xml')

    def test_performance_threshold_and_revision(self):
        self.performance()
        self.check(0, 'performance', '--samples', 'samples.json', '--expected-revision', 'abc')
        self.check(1, 'performance', '--samples', 'samples.json', '--expected-revision', 'other')

    def test_performance_max_and_min_failures(self):
        samples, budgets = self.performance()
        for rule, value in [({'max': 9}, 10), ({'min': 11}, 10)]:
            with self.subTest(rule=rule):
                budgets['performance']['metrics'][0] = dict(name='frame', unit='ms', min_samples=1, **rule)
                samples['metrics'][0]['value'] = value
                self.write_json('samples.json', samples)
                self.write_json('Docs/ai/unity-validation.json', budgets)
                self.check(1, 'performance', '--samples', 'samples.json')

    def test_performance_rejects_nonfinite_bool_and_bad_budget(self):
        samples, budgets = self.performance()
        for value in (float('nan'), float('inf'), True, '10'):
            with self.subTest(value=value):
                invalid = copy.deepcopy(samples)
                invalid['metrics'][0]['value'] = value
                self.write_json('samples.json', invalid)
                self.check(1, 'performance', '--samples', 'samples.json')
        self.write_json('samples.json', samples)
        for rule in ({'max': float('inf')}, {'max': True}, {'max_regression_pct': -1}, {}):
            with self.subTest(rule=rule):
                budgets['performance']['metrics'][0] = dict(name='frame', unit='ms', min_samples=1, **rule)
                self.write_json('Docs/ai/unity-validation.json', budgets)
                self.check(1, 'performance', '--samples', 'samples.json')

    def test_performance_missing_context_unit_and_metric(self):
        samples, _ = self.performance()
        for field in ('context', 'unit', 'metric'):
            with self.subTest(field=field):
                invalid = copy.deepcopy(samples)
                if field == 'context':
                    del invalid['context']['backend']
                elif field == 'unit':
                    del invalid['metrics'][0]['unit']
                else:
                    invalid['metrics'] = []
                self.write_json('samples.json', invalid)
                result, data = self.tool('unity_checks.py', 'performance', '--samples', 'samples.json')
                self.assertIn(result.returncode, (1, 2), result.stdout + result.stderr)
                self.assertFalse(data['ok'])

    def test_performance_samples_and_environment(self):
        samples, _ = self.performance()
        samples['metrics'][0]['sample_count'] = 1
        self.write_json('samples.json', samples)
        self.check(2, 'performance', '--samples', 'samples.json')
        samples['metrics'][0]['sample_count'] = 30
        samples['context']['platform'] = 'other'
        self.write_json('samples.json', samples)
        self.check(1, 'performance', '--samples', 'samples.json')

    def test_performance_regression_requires_matching_baseline(self):
        samples, budgets = self.performance()
        budgets['performance']['metrics'][0]['max_regression_pct'] = 10
        self.write_json('Docs/ai/unity-validation.json', budgets)
        self.check(2, 'performance', '--samples', 'samples.json')
        self.write_json('baseline.json', samples)
        self.check(0, 'performance', '--samples', 'samples.json', '--baseline', 'baseline.json')
        for value, context in [(8, samples['context']), (0, samples['context']),
                               (10, dict(samples['context'], device='different'))]:
            with self.subTest(value=value, context=context):
                baseline = copy.deepcopy(samples)
                baseline['metrics'][0]['value'] = value
                baseline['context'] = context
                self.write_json('baseline.json', baseline)
                self.check(1, 'performance', '--samples', 'samples.json', '--baseline', 'baseline.json')

    def test_performance_empty_budget_is_unconfigured(self):
        self.performance()
        self.write_json('Docs/ai/unity-validation.json', {'schema_version': 1, 'performance': {'context': {}, 'metrics': []}})
        self.check(2, 'performance', '--samples', 'samples.json')

    def test_performance_duplicate_names_and_unit_mismatch(self):
        samples, _ = self.performance()
        samples['metrics'].append(copy.deepcopy(samples['metrics'][0]))
        self.write_json('samples.json', samples)
        self.check(1, 'performance', '--samples', 'samples.json')
        samples['metrics'].pop()
        samples['metrics'][0]['unit'] = 'seconds'
        self.write_json('samples.json', samples)
        self.check(1, 'performance', '--samples', 'samples.json')

    def test_diagnostics_driver_or_extension_and_warning_policy(self):
        report = self.sarif()
        self.check(0, 'diagnostics', '--report', 'analysis.sarif')
        report['runs'][0]['tool'] = {'driver': {'name': 'Microsoft.Unity.Analyzers'}}
        report['runs'][0]['results'] = [{'level': 'warning', 'message': {'text': 'fixture'}}]
        self.write_json('analysis.sarif', report)
        self.check(0, 'diagnostics', '--report', 'analysis.sarif')
        self.check(1, 'diagnostics', '--report', 'analysis.sarif', '--level', 'warning')

    def test_diagnostics_missing_tool_and_execution_evidence(self):
        report = self.sarif()
        for field in ('tool', 'invocations'):
            with self.subTest(field=field):
                invalid = copy.deepcopy(report)
                invalid['runs'][0][field] = {} if field == 'tool' else []
                self.write_json('analysis.sarif', invalid)
                self.check(2, 'diagnostics', '--report', 'analysis.sarif')

    def test_diagnostics_failed_invocation_error_and_empty_run(self):
        report = self.sarif()
        for kind in ('invocation', 'error', 'empty', 'version', 'malformed'):
            with self.subTest(kind=kind):
                invalid = copy.deepcopy(report)
                if kind == 'invocation':
                    invalid['runs'][0]['invocations'][0]['executionSuccessful'] = False
                elif kind == 'error':
                    invalid['runs'][0]['results'] = [{'level': 'error', 'message': {'text': 'failure'}}]
                elif kind == 'empty':
                    invalid['runs'] = []
                elif kind == 'version':
                    invalid['version'] = '1.0.0'
                else:
                    invalid['runs'][0]['results'] = 'bad'
                self.write_json('analysis.sarif', invalid)
                result, data = self.tool('unity_checks.py', 'diagnostics', '--report', 'analysis.sarif')
                self.assertIn(result.returncode, (1, 2), result.stdout + result.stderr)
                self.assertFalse(data['ok'])

    def test_assets_require_explicit_scope_and_unity_root(self):
        self.check(2, 'assets')
        profile = self.read_json('Docs/ai/project-profile.json')
        profile['unity']['root'] = ''
        self.write_json('Docs/ai/project-profile.json', profile)
        self.check(2, 'assets', '--all-assets')

    def test_assets_valid_pair_and_selected_directory_meta(self):
        directory = self.asset('Art', directory=True)
        self.asset('Art/image.png', 'b' * 32)
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root / 'Game').rglob('*') if p.is_file()}
        data = self.check(0, 'assets', '--paths', 'Game/Assets/Art')
        self.assertEqual(data['scope'], ['Game/Assets/Art'])
        self.assertFalse(data['references_verified'])
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})
        Path(str(directory) + '.meta').unlink()
        self.check(1, 'assets', '--paths', 'Game/Assets/Art')

    def test_assets_missing_orphan_and_bad_guid(self):
        path = self.asset('thing.txt')
        meta = Path(str(path) + '.meta')
        for text in ('fileFormatVersion: 2\n', 'guid: invalid\n', 'guid: ' + 'a' * 32 + '\nguid: ' + 'b' * 32 + '\n'):
            with self.subTest(text=text):
                meta.write_text(text, encoding='utf-8')
                self.check(1, 'assets', '--all-assets')
        meta.unlink()
        self.check(1, 'assets', '--all-assets')
        meta.write_text('guid: ' + 'a' * 32 + '\n', encoding='utf-8')
        path.unlink()
        self.check(1, 'assets', '--all-assets')

    def test_assets_duplicate_guid_only_in_selected_scope(self):
        self.asset('a.txt')
        self.asset('b.txt')
        self.check(0, 'assets', '--paths', 'Game/Assets/a.txt')
        self.check(1, 'assets', '--all-assets')

    def test_assets_outside_assets_and_hidden_coverage(self):
        self.check(1, 'assets', '--paths', 'Game/ProjectSettings')
        (self.root / 'Game/Assets/.hidden').mkdir()
        data = self.check(2, 'assets', '--all-assets')
        self.assertTrue(data['warnings'])
        self.assertEqual(data['coverage'], 'partial')

    def test_assets_link_escape_is_failure(self):
        outside = self.case_dir / 'outside'
        outside.mkdir()
        link = self.root / 'Game/Assets/linked'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name != 'nt':
                self.skipTest('Host cannot create symbolic links: ' + str(error))
            junction = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                                      capture_output=True)
            self.assertEqual(junction.returncode, 0, 'Unable to create link escape fixture')
        self.check(1, 'assets', '--all-assets')

    def test_shared_project_position_and_input_escape(self):
        self.xml('<test-run><test-case result="Passed"/></test-run>')
        result, data = self.command(self.root / 'tools/ai/unity_checks.py', '--project', self.root,
                                    'tests', '--report', 'results.xml')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['ok'])
        self.check(1, 'tests', '--report', '../outside.xml')


if __name__ == '__main__':
    unittest.main(verbosity=2)
