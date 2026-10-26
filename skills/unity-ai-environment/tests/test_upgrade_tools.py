"""Black-box contracts for opt-in environment and quality evidence tools."""
import json
from pathlib import Path
import sys
import unittest

from upgrade_support import Harness


class UpgradeToolsTests(Harness):
    def setUp(self):
        super().setUp()
        self.initialize()

    def capability(self, name='sample', **overrides):
        integration = {
            'enabled': True, 'provider': 'fixture', 'group': '',
            'origin': 'https://example.org/tool', 'version': '8.24.2',
            'license': 'MIT', 'transport': 'command', 'endpoint': '',
            'network': [], 'environment_variables': [],
            'probe': [sys.executable, 'probe.py'], 'version_pattern': '',
            'required': True, 'timeout_seconds': 5, 'writes': False,
        }
        integration.update(overrides)
        profile = self.read_json('Docs/ai/project-profile.json')
        profile['capabilities'][name] = {
            'state': 'unconfigured', 'command': [sys.executable, 'scanner.py'],
            'integration': integration,
        }
        self.write_json('Docs/ai/project-profile.json', profile)
        return profile

    def probe(self, output='fixture 8.24.2', code=0):
        (self.root / 'probe.py').write_text(
            "from pathlib import Path\nPath('executed').write_text('yes')\n"
            f'print({output!r})\nraise SystemExit({code})\n', encoding='utf-8')

    def assert_result(self, name, code, *args):
        result, data = self.tool(name, *args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertIsInstance(data, dict)
        self.assertFalse(data['runtime_load_verified'])
        self.assertFalse(data['engineering_verified'])
        return data

    def test_doctor_default_never_executes_probe_or_project_commands(self):
        self.probe()
        profile = self.capability()
        profile['commands']['build'] = [sys.executable, 'probe.py']
        profile['capabilities']['sample']['integration']['probe'] = ['no-such-fixture-tool']
        self.write_json('Docs/ai/project-profile.json', profile)
        data = self.assert_result('environment.py', 0, 'doctor')
        self.assertFalse((self.root / 'executed').exists())
        self.assertTrue(any(item['id'] == 'sample' for item in data['checks']))
        check = next(item for item in data['checks'] if item['id'] == 'sample')
        self.assertTrue(check['probe_configured'])
        self.assertFalse(check['version_probe_verified'])
        profile['capabilities']['sample']['command'] = []
        profile['capabilities']['sample']['integration']['probe'] = [sys.executable, 'probe.py']
        self.write_json('Docs/ai/project-profile.json', profile)
        data = self.assert_result('environment.py', 0, 'doctor')
        self.assertEqual(data['checks'][-1]['status'], 'available')
        self.assertFalse((self.root / 'executed').exists())

    def test_doctor_default_finds_command_without_configured_probe(self):
        self.probe()
        self.capability(version='', probe=[])
        data = self.assert_result('environment.py', 0, 'doctor')
        check = next(item for item in data['checks'] if item['id'] == 'sample')
        self.assertEqual(check['status'], 'available')
        self.assertFalse(check['probe_configured'])
        self.assertFalse(check['version_probe_verified'])
        self.assert_result('environment.py', 1, 'doctor', '--probe')
        self.assertFalse((self.root / 'executed').exists())

    def test_doctor_default_reports_missing_command_without_configured_probe(self):
        profile = self.capability(version='', probe=[])
        profile['capabilities']['sample']['command'] = ['no-such-fixture-tool']
        self.write_json('Docs/ai/project-profile.json', profile)
        data = self.assert_result('environment.py', 1, 'doctor')
        check = next(item for item in data['checks'] if item['id'] == 'sample')
        self.assertEqual(check['status'], 'missing')
        self.assertFalse(check['probe_configured'])
        self.assertFalse(check['version_probe_verified'])

    def test_doctor_disabled_and_optional_missing_do_not_fail(self):
        self.probe()
        self.capability('disabled', enabled=False)
        self.capability('optional', required=False, probe=['no-such-fixture-tool'])
        data = self.assert_result('environment.py', 0, 'doctor', '--probe')
        statuses = {item['id']: item['status'] for item in data['checks']}
        self.assertEqual(statuses['disabled'], 'skipped')
        self.assertEqual(statuses['optional'], 'missing')
        self.assertTrue(data['warnings'])
        self.assertFalse((self.root / 'executed').exists())

    def test_doctor_required_missing_unconfigured_mismatch_and_failed(self):
        cases = [
            ({'probe': ['no-such-fixture-tool']}, 'missing', 'fixture 8.24.2', 0),
            ({'version': ''}, 'unconfigured', 'fixture 8.24.2', 0),
            ({'probe': []}, 'unconfigured', 'fixture 8.24.2', 0),
            ({}, 'mismatch', 'fixture 7.0.0', 0),
            ({}, 'failed', 'fixture 8.24.2', 9),
        ]
        for options, expected, output, code in cases:
            with self.subTest(expected=expected, options=options):
                self.probe(output, code)
                self.capability(**options)
                data = self.assert_result('environment.py', 1, 'doctor', '--probe')
                check = next(item for item in data['checks'] if item['id'] == 'sample')
                self.assertEqual(check['status'], expected)

    def test_doctor_probe_matches_version_without_exposing_output(self):
        self.probe('fixture v8.24.2 PRIVATE_PROBE_OUTPUT')
        self.capability(version_pattern=r'v8\.24\.2')
        data = self.assert_result('environment.py', 0, 'doctor', '--probe', '--capability', 'sample')
        self.assertEqual(data['checks'][-1]['status'], 'ready')
        self.assertNotIn('PRIVATE_PROBE_OUTPUT', json.dumps(data))
        self.assertTrue((self.root / 'executed').exists())

    def test_doctor_invalid_regex_and_unknown_capability_fail(self):
        self.probe()
        self.capability(version_pattern='[')
        self.assert_result('environment.py', 1, 'doctor', '--probe')
        self.assert_result('environment.py', 1, 'doctor', '--capability', 'unknown')

    def test_modules_are_read_only_and_mutually_exclusive_groups_fail(self):
        self.capability('one', group='editor', enabled=False, version='')
        data = self.assert_result('environment.py', 0, 'modules')
        item = next(item for item in data['modules'] if item['id'] == 'one')
        self.assertFalse(item['enabled'])
        self.assertIn('version', item['missing'])
        profile = self.capability('manual-http', transport='http', endpoint='http://localhost:8765',
                                  probe=[], version='', required=False)
        profile['capabilities']['manual-http']['command'] = []
        self.write_json('Docs/ai/project-profile.json', profile)
        data = self.assert_result('environment.py', 0, 'modules')
        manual = next(item for item in data['modules'] if item['id'] == 'manual-http')
        self.assertNotIn('command', manual['missing'])
        self.assertNotIn('endpoint', manual['missing'])
        self.assertEqual(manual['state'], 'unconfigured')
        self.assertFalse(manual['probe_configured'])
        data = self.assert_result('environment.py', 0, 'doctor', '--capability', 'manual-http')
        self.assertEqual(data['checks'][-1]['status'], 'unconfigured')
        self.assertFalse(data['checks'][-1]['version_probe_verified'])
        self.capability('one', group='editor')
        self.capability('two', group='editor')
        self.assert_result('environment.py', 1, 'modules')

    def test_local_mapping_preserves_executable_and_argument_spaces(self):
        mapped = str((self.root / 'tool bin' / 'python.exe').resolve())
        self.write_json('.ai-local/tools.json', {'executables': {'sample': mapped}})
        query = self.root / 'query.py'
        query.write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent / 'tools/ai'))\n"
            "import environment\n"
            "print(json.dumps({'argv': environment.resolve_command(Path(__file__).parent, "
            "'sample', ['placeholder', 'one argument', '--flag'])}))\n", encoding='utf-8')
        result, data = self.command(query)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data['argv'], [mapped, 'one argument', '--flag'])
        self.probe()
        self.capability(probe=['placeholder', 'probe.py'])
        self.write_json('.ai-local/tools.json', {'executables': {'sample': sys.executable}})
        self.assert_result('environment.py', 0, 'doctor', '--probe')

    def graph(self, edges=None, **overrides):
        policy = {'schema_version': 1, 'modules': ['ui', 'domain'],
                  'allowed_dependencies': [['ui', 'domain']],
                  'forbidden_dependencies': [['domain', 'ui']], 'allow_cycles': False}
        graph = {'schema_version': 1, 'revision': 'abc123', 'generator': 'fixture',
                 'complete': True, 'modules': ['ui', 'domain'],
                 'edges': edges if edges is not None else [
                     {'from': 'ui', 'to': 'domain', 'evidence': 'src/ui.py:1'}]}
        graph.update(overrides)
        self.write_json('Docs/ai/architecture-policy.json', policy)
        self.write_json('graph.json', graph)
        return policy, graph

    def test_architecture_valid_graph_and_empty_edges_have_declared_coverage(self):
        for edges in (None, []):
            with self.subTest(edges=edges):
                self.graph(edges)
                data = self.assert_result('quality.py', 0, 'architecture', '--graph', 'graph.json',
                                          '--expected-revision', 'abc123')
                self.assertEqual(data['coverage'], 'declared')

    def test_architecture_forbidden_edge_allowed_list_and_cycles(self):
        policy, graph = self.graph([
            {'from': 'domain', 'to': 'ui', 'evidence': 'src/domain.py:2'}])
        self.assert_result('quality.py', 1, 'architecture', '--graph', 'graph.json')
        policy['forbidden_dependencies'] = []
        self.write_json('Docs/ai/architecture-policy.json', policy)
        self.assert_result('quality.py', 1, 'architecture', '--graph', 'graph.json')
        policy['allowed_dependencies'] = []
        graph['edges'].append({'from': 'ui', 'to': 'domain', 'evidence': 'src/ui.py:1'})
        self.write_json('Docs/ai/architecture-policy.json', policy)
        self.write_json('graph.json', graph)
        data = self.assert_result('quality.py', 1, 'architecture', '--graph', 'graph.json')
        self.assertTrue(any('cycle' in error.lower() for error in data['errors']))

    def test_architecture_incomplete_unconfigured_and_revision_statuses(self):
        self.graph(complete=False)
        data = self.assert_result('quality.py', 2, 'architecture', '--graph', 'graph.json')
        self.assertEqual(data['status'], 'unverified')
        self.graph()
        self.assert_result('quality.py', 1, 'architecture', '--graph', 'graph.json',
                           '--expected-revision', 'different')
        self.write_json('Docs/ai/architecture-policy.json', {
            'schema_version': 1, 'modules': [], 'allowed_dependencies': [],
            'forbidden_dependencies': [], 'allow_cycles': False})
        self.assert_result('quality.py', 2, 'architecture', '--graph', 'graph.json')

    def test_architecture_rejects_unknown_missing_modules_and_missing_evidence(self):
        for changes in ({'modules': ['ui']}, {'modules': ['ui', 'domain', 'unknown']},
                        {'edges': [{'from': 'ui', 'to': 'domain'}]},
                        {'edges': [{'from': 'unknown', 'to': 'ui', 'evidence': 'x:1'}]}):
            with self.subTest(changes=changes):
                self.graph(**changes)
                self.assert_result('quality.py', 1, 'architecture', '--graph', 'graph.json')

    def scanner(self, mode='clean', file_mode=False):
        self.capability('secret-scan', provider='gitleaks')
        (self.root / 'Docs/ai/gitleaks.toml').write_text('title = "Fixture"\n', encoding='utf-8')
        (self.root / 'selected').mkdir(exist_ok=True)
        (self.root / 'selected/input.txt').write_bytes(b'FILE_CONTENT_TOKEN')
        script = (
            'import json, pathlib, sys\n'
            "args = sys.argv[1:]\npathlib.Path('scanner-call.json').write_text(json.dumps(args))\n"
            "assert '--redact=100' in args and '--no-banner' in args\n"
            "assert args[args.index('--exit-code') + 1] == '1'\n"
            "assert args[args.index('--report-format') + 1] == 'json'\n"
            "assert pathlib.Path(args[args.index('--config') + 1]).name == 'gitleaks.toml'\n"
            f"assert args[0] == {'stdin' if file_mode else 'dir'!r}\n"
            + ("assert sys.stdin.buffer.read() == b'FILE_CONTENT_TOKEN'\n" if file_mode else '')
            + "report = pathlib.Path(args[args.index('--report-path') + 1])\n"
            + "print('PRIVATE_STDOUT_SECRET')\nprint('PRIVATE_STDERR_SECRET', file=sys.stderr)\n"
        )
        if mode == 'clean':
            script += "report.write_text('[]')\n"
        elif mode == 'findings':
            script += "report.write_text(json.dumps([{'File':'selected/input.txt', 'StartLine':3, 'RuleID':'fixture-rule', 'Secret':'PRIVATE_SECRET', 'Match':'PRIVATE_MATCH'}]))\nraise SystemExit(1)\n"
        elif mode == 'invalid':
            script += "report.write_text('PRIVATE_INVALID_JSON')\n"
        elif mode == 'malformed':
            script += "report.write_text('{}')\n"
        elif mode == 'failed':
            script += "report.write_text('[]')\nraise SystemExit(9)\n"
        elif mode == 'missing':
            pass
        (self.root / 'scanner.py').write_text(script, encoding='utf-8')

    def test_secrets_unconfigured_and_non_v8_scanner_never_runs(self):
        (self.root / 'selected').mkdir()
        self.assert_result('quality.py', 2, 'secrets', '--paths', 'selected')
        self.capability('secret-scan', provider='gitleaks', version='7.0.0')
        self.assert_result('quality.py', 2, 'secrets', '--paths', 'selected')
        self.assertFalse((self.root / 'scanner-call.json').exists())

    def test_secrets_clean_directory_and_explicit_file_stdin(self):
        for file_mode in (False, True):
            with self.subTest(file_mode=file_mode):
                self.scanner(file_mode=file_mode)
                data = self.assert_result('quality.py', 0, 'secrets', '--paths',
                                          'selected/input.txt' if file_mode else 'selected')
                self.assertEqual(data['scanner_exit_code'], 0)
                self.assertEqual(data['findings'], [])
                args = self.read_json('scanner-call.json')
                self.assertFalse(Path(args[args.index('--report-path') + 1]).exists())

    def test_secrets_findings_only_expose_redacted_location_summary(self):
        self.scanner('findings')
        data = self.assert_result('quality.py', 1, 'secrets', '--paths', 'selected')
        self.assertEqual(data['scanner_exit_code'], 1)
        self.assertEqual(data['findings'], [{'File': 'selected/input.txt', 'StartLine': 3,
                                            'RuleID': 'fixture-rule'}])
        output = json.dumps(data)
        for token in ('PRIVATE_SECRET', 'PRIVATE_MATCH', 'PRIVATE_STDOUT_SECRET', 'PRIVATE_STDERR_SECRET'):
            self.assertNotIn(token, output)

    def test_secrets_failure_missing_and_malformed_reports_cannot_be_clean(self):
        for mode in ('failed', 'missing', 'invalid', 'malformed'):
            with self.subTest(mode=mode):
                self.scanner(mode)
                result, data = self.tool('quality.py', 'secrets', '--paths', 'selected')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertFalse(data['ok'])
                self.assertTrue(data['errors'])
                self.assertNotIn('PRIVATE_', result.stdout + result.stderr)

    def test_paths_and_timeout_cannot_escape_contract(self):
        self.graph()
        self.assert_result('quality.py', 1, 'architecture', '--graph', '../outside.json')
        self.scanner()
        for args in (('--paths', '../outside'), ('--paths', 'missing'),
                     ('--paths', 'selected', '--timeout', '31')):
            with self.subTest(args=args):
                self.assert_result('quality.py', 1, 'secrets', *args)
        self.assertFalse((self.root / 'scanner-call.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
