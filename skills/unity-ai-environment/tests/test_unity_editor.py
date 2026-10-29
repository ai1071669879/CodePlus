"""Black-box checks for the optional Unity Editor gate driver; no Editor is launched."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

from upgrade_support import Harness


def nunit_xml(cases, root_result='Passed', total=None, passed=None, failed=None):
    """Build a minimal NUnit3 test-run report."""
    rows = []
    for index, (name, result) in enumerate(cases, 1):
        rows.append('    <test-case id="%d" name="%s" fullname="Fixture.%s" result="%s" />'
                    % (index, name, name, result))
    counts = {'total': total if total is not None else len(cases),
              'passed': passed if passed is not None else sum(1 for _, result in cases if result == 'Passed'),
              'failed': failed if failed is not None else sum(1 for _, result in cases if result == 'Failed'),
              'skipped': 0}
    body = '\n'.join(rows)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<test-run id="2" result="%s" total="%d" passed="%d" failed="%d" skipped="0">\n'
            '  <test-suite type="TestSuite" name="Fixture" result="%s">\n%s\n  </test-suite>\n'
            '</test-run>\n') % (root_result, counts['total'], counts['passed'], counts['failed'],
                                root_result, body)


class UnityEditorToolTests(Harness):
    def setUp(self):
        super().setUp()
        (self.root / 'Game/Assets').mkdir(parents=True)
        (self.root / 'Game/ProjectSettings').mkdir()
        (self.root / 'Game/ProjectSettings/ProjectVersion.txt').write_text(
            'm_EditorVersion: 2022.3.62f3\n', encoding='utf-8')
        (self.root / 'Game/Library').mkdir()
        self.write_json(self.root / 'Game/Library/EditorInstance.json', {
            'process_id': 999999, 'version': '2022.3.62f3',
            'app_path': 'D:/Unity/Editor/Unity.exe',
            'app_contents_path': 'D:/Unity/Editor/Data'})
        self.initialize()

    # ---------------------------------------------------------------- helpers --
    def discover(self):
        result, data = self.tool('unity_editor.py', 'discover')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return data

    def gate_root(self):
        root = Path(self.discover()['gate_root'])
        root.mkdir(parents=True, exist_ok=True)
        return root

    def write_json(self, path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def write_status(self, gate, status='ready', **extra):
        receipt = {'schema_version': 1, 'status': status, 'ok': status != 'failed',
                   'ready': status == 'ready', 'active': status == 'started'}
        receipt.update(extra)
        self.write_json(gate / 'status.json', receipt)

    def run_tool(self, *args):
        return self.tool('unity_editor.py', *args)

    def run_raw(self, *args):
        return self.command(self.root / 'tools/ai/unity_editor.py', *args)

    # ------------------------------------------------------------------- tests --
    def test_discover_resolves_nested_unity_root_and_editor_metadata(self):
        self.write_json(self.root / 'Game/Library/EditorInstance.json', {
            'process_id': 999999, 'version': '2022.3.62f3',
            'app_path': 'D:/Unity/Editor/Unity.exe',
            'app_contents_path': 'D:/Unity/Editor/Data'})
        data = self.discover()
        self.assertEqual(Path(data['project']), (self.root / 'Game').resolve())
        self.assertEqual(data['editor_version'], '2022.3.62f3')
        self.assertEqual(data['editor_instance']['process_id'], 999999)
        self.assertFalse(data['editor_instance']['process_alive'])
        self.assertIn('Temp/UnityEditorGate/999999', data['gate_root'].replace('\\', '/'))
        self.assertIn('hint', data)

    def test_status_missing_and_stale_gate(self):
        result, data = self.run_tool('status')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(data['ok'])
        gate = self.gate_root()
        self.write_status(gate)
        result, data = self.run_tool('status', '--stale-after', '60')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(data['stale'])
        old = time.time() - 600
        os.utime(gate / 'status.json', (old, old))
        result, data = self.run_tool('status', '--stale-after', '60')
        self.assertTrue(data['stale'])

    def test_request_id_contract_and_atomic_write(self):
        gate = self.gate_root()
        self.write_status(gate)
        for bad_id in ['bad/id', '地图', '-leading', '', 'x' * 65]:
            result, data = self.run_tool('request', '--id=' + bad_id, '--suite', 'refresh')
            self.assertEqual(result.returncode, 2, bad_id + ': ' + result.stdout + result.stderr)
            self.assertFalse(data['ok'])
        result, data = self.run_tool('request', '--id', 'r1', '--suite', 'invoke')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        result, data = self.run_tool('request', '--id', 'r1', '--suite', 'invoke',
                                     '--type', 'A.B', '--method', 'Run', '--field', 'id=override')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        result, data = self.run_tool('request', '--id', 'r1', '--suite', 'invoke',
                                     '--type', 'A.B', '--method', 'Run', '--arg', 'a', '--arg', 'b')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((gate / 'request.json.tmp' ).exists())
        request = json.loads((gate / 'request.json').read_text(encoding='utf-8'))
        self.assertEqual(request['schema_version'], 1)
        self.assertEqual(request['args'], ['a', 'b'])
        result, data = self.run_tool('request', '--id', 'r1', '--suite', 'refresh')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        (gate / 'r1').mkdir()
        result, data = self.run_tool('request', '--id', 'r1', '--suite', 'refresh')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_wait_success_failure_rejected_and_timeout(self):
        gate = self.gate_root()
        self.write_status(gate)
        run = gate / 'ok1'
        self.write_json(run / 'result.json', {'schema_version': 1, 'status': 'observed',
                                              'ok': True, 'id': 'ok1', 'suite': 'refresh'})
        result, data = self.run_tool('wait', '--id', 'ok1', '--timeout', '3')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['ok'])
        run = gate / 'bad1'
        self.write_json(run / 'result.json', {'schema_version': 1, 'status': 'failed',
                                              'ok': False, 'id': 'bad1', 'suite': 'invoke',
                                              'error': 'boom'})
        result, data = self.run_tool('wait', '--id', 'bad1', '--timeout', '3')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('boom', data['error'])
        self.write_json(gate / 'rejected-1.json', {'id': 'rej1', 'error': 'duplicate id'})
        result, data = self.run_tool('wait', '--id', 'rej1', '--timeout', '3')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('拒绝', data['error'])
        started = time.time()
        result, data = self.run_tool('wait', '--id', 'never', '--timeout', '0.4', '--interval', '0.05')
        self.assertEqual(result.returncode, 1)
        self.assertTrue(data['timed_out'])
        self.assertGreaterEqual(time.time() - started, 0.35)

    def test_run_waits_ready_then_completes_via_gate_simulation(self):
        gate = self.gate_root()
        self.write_status(gate)
        command = [sys.executable, '-B', str(self.root / 'tools/ai/unity_editor.py'), 'run',
                   '--project', str(self.root), '--id', 'run1', '--suite', 'refresh',
                   '--timeout', '10', '--ready-timeout', '5', '--interval', '0.05']
        process = subprocess.Popen(command, cwd=self.root, env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding='utf-8')
        run_dir = gate / 'run1'
        for _ in range(200):
            if (gate / 'request.json').is_file():
                break
            time.sleep(0.02)
        self.assertTrue((gate / 'request.json').is_file(), 'driver did not write request.json')
        run_dir.mkdir()
        (gate / 'request.json').replace(run_dir / 'request.json')
        self.write_json(run_dir / 'result.json', {'schema_version': 1, 'status': 'observed',
                                                  'ok': True, 'id': 'run1', 'suite': 'refresh'})
        stdout, stderr = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertTrue(json.loads(stdout)['ok'])

    def test_tests_dry_run_results_only_and_failure(self):
        editor = self.root / 'fake-unity.exe'
        editor.write_bytes(b'not executed')
        result, data = self.run_tool('tests', '--editor', str(editor), '--platform', 'playmode',
                                     '--filter', 'My.Ns', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        command = data['command']
        self.assertIn('-runTests', command)
        self.assertIn('PlayMode', command)
        self.assertIn('-testResults', command)
        self.assertIn('-testFilter', command)
        self.assertIn('My.Ns', command)
        self.assertNotIn('-nographics', command)
        report = self.root / 'Game/Temp/fixture/results.xml'
        report.parent.mkdir(parents=True)
        report.write_text(nunit_xml([('a', 'Passed'), ('b', 'Passed')]), encoding='utf-8')
        result, data = self.run_tool('tests', '--results-only', str(report), '--exit-code', '0')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data['unity_checks']['passed'], 2)
        self.assertTrue(data['unity_checks']['process_exit_verified'])
        report.write_text(nunit_xml([('a', 'Passed'), ('b', 'Failed')], root_result='Failed'),
                          encoding='utf-8')
        result, data = self.run_tool('tests', '--results-only', str(report), '--exit-code', '0')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        result, data = self.run_tool('tests', '--results-only', str(report), '--exit-code', '3')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_player_dry_run_and_missing_executable(self):
        exe = self.root / 'Game.exe'
        exe.write_bytes(b'not executed')
        result, data = self.run_raw('player', '--exe', str(exe), '--arg', 'smoke', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data['command'][1], 'smoke')
        result, data = self.run_raw('player', '--exe', str(self.root / 'missing.exe'), '--dry-run')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_log_classifies_errors(self):
        log = self.root / 'editor.log'
        log.write_text('hello\nerror CS1002: ; expected\nNullReferenceException: boom\n'
                       'warning CS0168: unused\nTest run failed\n', encoding='utf-8')
        result, data = self.run_raw('log', str(log), '--tail', '2')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data['error_counts']['compile_error'], 1)
        self.assertEqual(data['error_counts']['exception'], 1)
        self.assertFalse(data['clean'])
        self.assertEqual(len(data['tail']), 2)
        result, data = self.run_raw('log', str(log), '--require-clean')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        clean = self.root / 'clean.log'
        clean.write_text('all good\n', encoding='utf-8')
        result, data = self.run_raw('log', str(clean), '--require-clean')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['clean'])

    def test_gate_asset_and_help_are_installed(self):
        gate = self.root / 'Editor/UnityEditorGate/UnityEditorGate.cs'
        self.assertTrue(gate.is_file(), 'gate C# template must ship with the bundle')
        text = gate.read_text(encoding='utf-8')
        for marker in ('[InitializeOnLoad]', 'request.json', 'result.json', 'allowlist.json',
                       'Temp/UnityEditorGate'):
            self.assertIn(marker, text)
        result, data = self.run_tool('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('discover', result.stdout)
        self.assertIn('tests', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
