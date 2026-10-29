"""Read-only navigation selection against the existing context index."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from upgrade_support import Harness
from test_environment import SKILL, snapshot


class ContextRoutesTests(Harness):
    def setUp(self):
        super().setUp()
        self.initialize()
        self.entries = [
            {'id': 'alpha', 'aliases': ['First'], 'roots': ['src/A/'],
             'entrypoints': ['src/A/main.cs', 'Docs/alpha.md'], 'verified_revision': ''},
            {'id': 'beta', 'aliases': ['Second'], 'roots': ['src/AB/'],
             'entrypoints': ['src/AB/main.cs'], 'verified_revision': ''},
            {'id': 'nested', 'aliases': ['Game'], 'roots': ['games/client/Assets/'],
             'entrypoints': ['games/client/Assets/main.cs'], 'verified_revision': ''},
        ]
        for relative in ('src/A/main.cs', 'src/AB/main.cs', 'Docs/alpha.md',
                         'games/client/Assets/main.cs', 'unindexed/file.txt'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('PRIVATE_SOURCE_BODY', encoding='utf-8')
        self.write_json('Docs/ai/context-index.json', {'schema_version': 1, 'entries': self.entries})

    def select(self, *args, code=0):
        result, data = self.tool('context.py', *args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertIsInstance(data, dict, result.stdout + result.stderr)
        self.assertEqual(data['ok'], code == 0)
        self.assertFalse(data['runtime_load_verified'])
        self.assertFalse(data['engineering_verified'])
        return data

    def load_tool(self):
        path = SKILL / 'assets/project/tools/ai/context.py'
        self.assertTrue(path.is_file(), 'The context navigation CLI is required')
        sys.path.insert(0, str(path.parent))
        self.addCleanup(sys.path.remove, str(path.parent))
        spec = importlib.util.spec_from_file_location('context_routes_under_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def invoke(self, module, *args):
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', ['context.py', '--project', str(self.root), *args]), \
                contextlib.redirect_stdout(output):
            code = module.main()
        return code, json.loads(output.getvalue())

    def test_exact_casefold_queries_form_an_index_ordered_union(self):
        data = self.select('--query', 'SECOND', '--query', 'ALPHA', '--query', 'first')
        self.assertEqual(data['entries'], self.entries[:2])
        self.assertEqual(data['context_status'], {'alpha': 'unknown', 'beta': 'unknown'})

    def test_paths_use_directory_boundaries_and_include_entrypoints(self):
        data = self.select('--paths', 'src/A/main.cs')
        self.assertEqual(data['entries'], self.entries[:1])
        data = self.select('--paths', 'Docs/alpha.md', 'games', '--query', 'Second')
        self.assertEqual(data['entries'], self.entries)
        data = self.select('--paths', 'src')
        self.assertEqual(data['entries'], self.entries[:2])

    def test_no_selection_lists_navigation_summaries_without_entrypoints(self):
        data = self.select()
        self.assertEqual(data['entries'], [
            {'id': 'alpha', 'aliases': ['First'], 'roots': ['src/A/']},
            {'id': 'beta', 'aliases': ['Second'], 'roots': ['src/AB/']},
            {'id': 'nested', 'aliases': ['Game'], 'roots': ['games/client/Assets/']},
        ])
        self.assertNotIn('declared_checks', data)

    def test_each_unmatched_selector_fails_without_falling_back(self):
        for args in (('--query', 'alph'), ('--paths', 'unindexed'),
                     ('--query', 'alpha', '--query', 'missing'),
                     ('--paths', 'src/A', 'unindexed')):
            with self.subTest(args=args):
                data = self.select(*args, code=2)
                self.assertEqual(data['entries'], [])
                self.assertEqual(data['context_status'], {})
                self.assertTrue(data['errors'])

    def test_invalid_and_missing_paths_cannot_select_outside_the_workspace(self):
        for path in ('../outside', str(self.case_dir), 'src/A/missing.cs'):
            with self.subTest(path=path):
                result, data = self.tool('context.py', '--paths', path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsInstance(data, dict)
                self.assertFalse(data['ok'])
                self.assertEqual(data['entries'], [])

    def test_linked_path_escape_is_rejected(self):
        outside = self.case_dir / 'outside'
        outside.mkdir()
        try:
            (self.root / 'escaped').symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if sys.platform != 'win32':
                self.skipTest(f'Directory links unavailable: {error}')
            created = subprocess.run(['cmd', '/c', 'mklink', '/J', str(self.root / 'escaped'), str(outside)],
                                     capture_output=True)
            self.assertEqual(created.returncode, 0, created.stderr)
            self.addCleanup((self.root / 'escaped').rmdir)
        else:
            self.addCleanup((self.root / 'escaped').unlink)
        result, data = self.tool('context.py', '--paths', 'escaped')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(data['ok'])
        self.assertEqual(data['entries'], [])

    def test_declared_commands_are_reported_without_execution_or_writes(self):
        probe = self.root / 'probe.py'
        probe.write_text("from pathlib import Path\nPath('executed').write_text('yes')\n", encoding='utf-8')
        profile = self.read_json('Docs/ai/project-profile.json')
        command = [sys.executable, 'probe.py', 'one argument']
        profile['commands'] = {'lint': [], 'build': command, 'test': command}
        self.write_json('Docs/ai/project-profile.json', profile)
        before = snapshot(self.root)
        data = self.select('--query', 'alpha')
        self.assertEqual(data['declared_checks'], [
            {'id': 'lint', 'command': [], 'status': 'not_run', 'configured': False},
            {'id': 'build', 'command': command, 'status': 'not_run', 'configured': True},
            {'id': 'test', 'command': command, 'status': 'not_run', 'configured': True},
        ])
        self.assertFalse((self.root / 'executed').exists())
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(data['required_files'], [
            'Docs/ai/README.md', 'Docs/ai/project-rules.md', 'Docs/ai/project-profile.json',
            'Docs/ai/access-policy.json', 'Docs/ai/workflow.md', 'src/A/main.cs', 'Docs/alpha.md',
        ])

    def test_unknown_navigation_and_legacy_workflow_are_warnings(self):
        workflow = self.root / 'Docs/ai/workflow.md'
        if workflow.exists():
            workflow.unlink()
        data = self.select('--query', 'alpha')
        self.assertEqual(data['context_status'], {'alpha': 'unknown'})
        self.assertTrue(data['warnings'])
        self.assertTrue(any('workflow.md' in warning for warning in data['warnings']))

    def test_plain_python_launch_does_not_write_import_caches(self):
        environment = self.env.copy()
        environment.pop('PYTHONDONTWRITEBYTECODE', None)
        before = snapshot(self.root)
        result = subprocess.run(
            [sys.executable, str(self.root / 'tools/ai/context.py'),
             '--project', str(self.root), '--query', 'alpha'],
            env=environment, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertEqual(snapshot(self.root), before)

    def test_existing_freshness_validation_distinguishes_current_and_stale(self):
        self.entries[0]['verified_revision'] = 'fixture-revision'
        self.write_json('Docs/ai/context-index.json', {'schema_version': 1, 'entries': self.entries})
        module = self.load_tool()
        for diff, expected in (('', 'current'), ('src/A/main.cs\0', 'stale')):
            with self.subTest(expected=expected):
                def git_response(argv, **kwargs):
                    output = '0123456789abcdef\n' if 'rev-parse' in argv else diff
                    return argparse.Namespace(returncode=0, stdout=output, stderr='')
                with mock.patch.object(module.core.subprocess, 'run', side_effect=git_response):
                    code, data = self.invoke(module, '--query', 'alpha')
                self.assertEqual(code, 0, data)
                self.assertEqual(data['context_status'], {'alpha': expected})
                self.assertEqual(data['entries'][0]['verified_revision'], 'fixture-revision')

    def test_selection_reads_only_json_without_source_or_tree_scanning(self):
        module = self.load_tool()
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            self.assertEqual(path.suffix, '.json', f'Unexpected body read: {path}')
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, 'open', guarded_open), \
                mock.patch.object(Path, 'rglob', side_effect=AssertionError('Full scan')), \
                mock.patch.object(Path, 'glob', side_effect=AssertionError('Full scan')), \
                mock.patch.object(module.core.subprocess, 'run', side_effect=AssertionError('Command execution')):
            code, data = self.invoke(module, '--query', 'alpha')
            missing_code, missing = self.invoke(module, '--query', 'not-indexed')
        self.assertEqual(code, 0, data)
        self.assertEqual(data['entries'], self.entries[:1])
        self.assertNotIn('PRIVATE_SOURCE_BODY', json.dumps(data))
        self.assertEqual(missing_code, 2, missing)
        self.assertEqual(missing['entries'], [])

    def test_invalid_json_and_schema_produce_json_failures(self):
        for document in ('not json', '[]', '{"schema_version":2,"entries":[]}',
                         '{"schema_version":1,"entries":[null]}'):
            with self.subTest(document=document):
                (self.root / 'Docs/ai/context-index.json').write_text(document, encoding='utf-8')
                self.select('--query', 'alpha', code=1)

    def test_invalid_profile_commands_do_not_escape_as_tracebacks(self):
        profile = self.read_json('Docs/ai/project-profile.json')
        for commands in ([], {'build': 'shell command', 'test': [], 'lint': []}):
            with self.subTest(commands=commands):
                profile['commands'] = commands
                self.write_json('Docs/ai/project-profile.json', profile)
                self.select('--query', 'alpha', code=1)

    def test_unsupported_profile_schema_is_rejected(self):
        profile = self.read_json('Docs/ai/project-profile.json')
        profile['schema_version'] = 2
        self.write_json('Docs/ai/project-profile.json', profile)
        self.select('--query', 'alpha', code=1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
