"""Behavior checks for explicit tool selection and recorded prerequisites."""
import contextlib
import copy
import importlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from upgrade_support import Harness
import test_environment as common

sys.path.insert(0, str(common.SKILL / 'assets/project/tools/ai'))
setup = importlib.import_module('project_setup')


class SetupOptionsTests(Harness):
    def setUp(self):
        super().setUp()
        shutil.copytree(common.SKILL / 'assets/project', self.root, dirs_exist_ok=True)
        self.profile = self.read_json('Docs/ai/project-profile.json')
        self.catalog = self.read_json('Docs/ai/setup-options.json')

    def save_selection(self, mode, tools=None):
        profile = setup.select_configuration(self.profile, self.catalog, mode, tools)
        self.write_json('Docs/ai/project-profile.json', profile)
        self.write_json('Docs/ai/workflow.json', {'schema_version': 1, 'mode': mode})
        return profile

    def record_harness(self):
        profile = self.save_selection('unity-harness-init', ['none'])
        for name in ('unity-skills-rest', 'unity-harness-init', 'copilot-cli'):
            capability = profile['capabilities'][name]
            capability.update(state='verified', verified_revision='recorded-release',
                              evidence=['Maintainer recorded a minimal verification'])
            capability['integration']['version'] = '1.0.0'
        profile['capabilities']['unity-skills-rest']['integration']['endpoint'] = 'http://localhost:8090'
        self.write_json('Docs/ai/project-profile.json', profile)
        rules = self.read_json('Docs/ai/rules.json')
        for identifier in ('intent', 'execution', 'tracking', 'grading', 'verification'):
            rules['sources'][identifier] = 'Docs/ai/workflow.md'
        self.write_json('Docs/ai/rules.json', rules)
        progress = self.root / 'docs/harness/progress.md'
        progress.parent.mkdir(parents=True, exist_ok=True)
        progress.write_text('# Harness progress fixture\n', encoding='utf-8')
        for relative in ('.github/copilot-instructions.md',
                         '.github/skills/unity-skills/scripts/unity_skills.py',
                         *(f'.github/agents/{role}.agent.md' for role in
                           ('planner', 'developer', 'reviewer', 'coordinator'))):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('# Recorded fixture only\n', encoding='utf-8')
        return profile

    def test_descriptions_merge_human_options_with_profile_only(self):
        before = copy.deepcopy((self.profile, self.catalog))
        result = setup.describe_options(self.profile, self.catalog, 'native')
        options = {tool['id']: tool for tool in result['optional_tools']}
        for name in ('unity-editor-cli', 'unity-editor-mcp', 'unity-editor-anklebreaker'):
            self.assertTrue(options[name]['name'])
            self.assertTrue(options[name]['summary'])
            self.assertTrue(options[name]['features'])
            self.assertTrue(options[name]['prerequisites'])
            self.assertTrue(options[name]['setup'])
            self.assertEqual(options[name]['group'], 'unity-editor')
            self.assertEqual(options[name]['state'], 'unconfigured')
            self.assertFalse(options[name]['enabled'])
            self.assertFalse(options[name]['required'])
        self.assertEqual(result['selected_workflow'], 'native')
        self.assertEqual({mode['id'] for mode in result['workflow_options']},
                         {'native', 'unity-harness-init'})
        result['optional_tools'][0]['features'].append('caller edit')
        self.assertEqual((self.profile, self.catalog), before)

    def test_selection_is_deep_copy_and_preserves_recorded_evidence(self):
        capability = self.profile['capabilities']['unity-editor-cli']
        capability.update(state='verified', verified_revision='old', evidence=['existing'])
        capability['integration']['version'] = 'old'
        before = copy.deepcopy(self.profile)
        result = setup.select_configuration(self.profile, self.catalog, 'native', ['unity-editor-cli'])
        enabled = {name for name, value in result['capabilities'].items()
                   if value.get('integration', {}).get('enabled')}
        self.assertEqual(enabled, {'unity-editor-cli'})
        self.assertEqual(result['capabilities']['unity-editor-cli']['evidence'], ['existing'])
        self.assertEqual(result['capabilities']['unity-editor-cli']['state'], 'verified')
        result['capabilities']['unity-editor-cli']['evidence'].append('new')
        self.assertEqual(self.profile, before)

    def test_none_preserves_selection_and_explicit_none_disables_catalog_only(self):
        self.profile['capabilities']['unity-editor-cli']['integration']['enabled'] = True
        self.profile['capabilities']['private-capability'] = {
            'state': 'located', 'integration': {'enabled': True, 'group': 'private'}}
        retained = setup.select_configuration(self.profile, self.catalog, 'native')
        self.assertTrue(retained['capabilities']['unity-editor-cli']['integration']['enabled'])
        cleared = setup.select_configuration(self.profile, self.catalog, 'native', ['none'])
        self.assertFalse(cleared['capabilities']['unity-editor-cli']['integration']['enabled'])
        self.assertTrue(cleared['capabilities']['private-capability']['integration']['enabled'])

    def test_harness_forces_dependencies_without_claiming_verification(self):
        result = setup.select_configuration(self.profile, self.catalog, 'unity-harness-init', ['none'])
        enabled = {name for name, value in result['capabilities'].items()
                   if value.get('integration', {}).get('enabled')}
        self.assertEqual(enabled, {'unity-skills-rest', 'unity-harness-init', 'copilot-cli'})
        for name in enabled:
            capability = result['capabilities'][name]
            self.assertTrue(capability['integration']['required'])
            self.assertEqual(capability['state'], 'unconfigured')
            self.assertEqual(capability['verified_revision'], '')
            self.assertEqual(capability['evidence'], [])
        native = setup.select_configuration(self.profile, self.catalog, 'native', [])
        self.assertFalse(any(value.get('integration', {}).get('required')
                             for value in native['capabilities'].values()))

    def test_selection_rejects_unknown_duplicate_and_mixed_none(self):
        for tools in (['unknown'], ['none', 'unity-editor-cli'],
                      ['unity-editor-cli', 'unity-editor-cli'], 'unity-editor-cli', [None]):
            with self.subTest(tools=tools), self.assertRaises(ValueError):
                setup.select_configuration(self.profile, self.catalog, 'native', tools)
        with self.assertRaises(ValueError):
            setup.select_configuration(self.profile, self.catalog, 'other')

    def test_enabled_group_conflicts_include_forced_harness_and_private_tools(self):
        with self.assertRaises(ValueError):
            setup.select_configuration(self.profile, self.catalog, 'native',
                                       ['unity-editor-cli', 'unity-editor-mcp'])
        with self.assertRaises(ValueError):
            setup.select_configuration(self.profile, self.catalog, 'unity-harness-init',
                                       ['unity-editor-anklebreaker'])
        self.profile['capabilities']['private-bridge'] = {
            'state': 'unconfigured', 'integration': {'enabled': True, 'group': 'unity-editor'}}
        with self.assertRaises(ValueError):
            setup.select_configuration(self.profile, self.catalog, 'native', ['unity-editor-cli'])

    def test_catalog_rejects_invalid_shape_references_and_state(self):
        mutations = (
            lambda catalog: catalog.update(schema_version=True),
            lambda catalog: catalog['tools'].append(copy.deepcopy(catalog['tools'][0])),
            lambda catalog: catalog['tools'][0].update(id='missing-capability'),
            lambda catalog: catalog['tools'][0].update(features='not-a-list'),
            lambda catalog: catalog['tools'][0].update(enabled=True),
            lambda catalog: catalog['tools'][0].update(setup='../outside.md'),
            lambda catalog: catalog['workflows'][1].update(required_tools=['missing-capability']),
            lambda catalog: catalog['workflows'].append(copy.deepcopy(catalog['workflows'][0])),
            lambda catalog: catalog['workflows'][0].update(guide='https://example.invalid'),
        )
        for mutate in mutations:
            catalog = copy.deepcopy(self.catalog)
            mutate(catalog)
            with self.subTest(catalog=catalog), self.assertRaises(ValueError):
                setup.select_configuration(self.profile, catalog, 'native')

    def test_catalog_cannot_remove_or_add_workflow_requirements(self):
        for mode, required in (('native', ['copilot-cli']),
                               ('unity-harness-init', []),
                               ('unity-harness-init', ['unity-skills-rest', 'unity-harness-init']),
                               ('unity-harness-init', ['unity-skills-rest', 'unity-harness-init',
                                                       'copilot-cli', 'secret-scan'])):
            catalog = copy.deepcopy(self.catalog)
            workflow = next(entry for entry in catalog['workflows'] if entry['id'] == mode)
            workflow['required_tools'] = required
            with self.subTest(mode=mode, required=required), self.assertRaises(ValueError):
                setup.select_configuration(self.profile, catalog, mode)
        catalog = copy.deepcopy(self.catalog)
        catalog['workflows'][1]['required_tools'].reverse()
        selected = setup.select_configuration(self.profile, catalog, 'unity-harness-init', ['none'])
        self.assertTrue(selected['capabilities']['copilot-cli']['integration']['required'])

    def test_catalog_cannot_redefine_mode_state_sources(self):
        for mode, relative in (('native', 'Tasks/other-index.json'),
                               ('unity-harness-init', 'Tasks/index.json')):
            catalog = copy.deepcopy(self.catalog)
            workflow = next(entry for entry in catalog['workflows'] if entry['id'] == mode)
            workflow['state_source'] = relative
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                setup.select_configuration(self.profile, catalog, mode)

    def test_cli_list_and_native_check_are_read_only(self):
        before = common.snapshot(self.root)
        for command in ('list', 'check'):
            result, data = self.tool('project_setup.py', command)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(data['ok'])
            self.assertFalse(data['runtime_load_verified'])
            self.assertFalse(data['engineering_verified'])
        self.assertEqual(common.snapshot(self.root), before)

    def test_cli_does_not_create_project_bytecode_without_launcher_flags(self):
        before = common.snapshot(self.root)
        environment = self.env.copy()
        environment.pop('PYTHONDONTWRITEBYTECODE', None)
        result = subprocess.run(
            [sys.executable, str(self.root / 'tools/ai/project_setup.py'), 'list',
             '--project', str(self.root)], env=environment, capture_output=True,
            text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(common.snapshot(self.root), before)

    def test_cli_harness_reports_missing_prerequisites_and_does_not_fall_back(self):
        self.save_selection('unity-harness-init', ['none'])
        before = common.snapshot(self.root)
        result, data = self.tool('project_setup.py', 'check')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(data['ok'])
        self.assertEqual(data['selected_workflow'], 'unity-harness-init')
        missing = '\n'.join(data['unverified'])
        self.assertIn('unity-skills-rest', missing)
        self.assertIn('state', missing)
        self.assertIn('version', missing)
        self.assertIn('verified_revision', missing)
        self.assertIn('evidence', missing)
        self.assertIn('endpoint', missing)
        self.assertIn('.github/agents/planner.agent.md', missing)
        self.assertEqual(common.snapshot(self.root), before)

    def test_recorded_harness_metadata_is_not_runtime_verification(self):
        self.record_harness()
        before = common.snapshot(self.root)
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', ['project_setup.py', 'check', '--project', str(self.root)]), \
                mock.patch('subprocess.Popen', side_effect=AssertionError('no child process')), \
                mock.patch('socket.socket', side_effect=AssertionError('no networking')), \
                contextlib.redirect_stdout(output):
            self.assertEqual(setup.main(), 0)
        data = json.loads(output.getvalue())
        self.assertTrue(data['ok'])
        self.assertEqual(data['unverified'], [])
        self.assertIn('recorded prerequisites', data['status'])
        self.assertNotIn('runtime ready', output.getvalue())
        self.assertFalse(data['runtime_load_verified'])
        self.assertFalse(data['engineering_verified'])
        self.assertEqual(common.snapshot(self.root), before)

    def test_required_flags_and_command_are_checked_from_saved_profile(self):
        profile = self.record_harness()
        capability = profile['capabilities']['copilot-cli']
        capability['integration'].update(enabled=False, required=False)
        capability['command'] = []
        capability['verified_revision'] = ''
        capability['evidence'] = []
        self.write_json('Docs/ai/project-profile.json', profile)
        result, data = self.tool('project_setup.py', 'check')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        missing = '\n'.join(data['unverified'])
        for field in ('enabled', 'required', 'command', 'verified_revision', 'evidence'):
            self.assertIn(f'copilot-cli.{field}', missing)

    def test_harness_rejects_second_task_status_source(self):
        self.record_harness()
        tasks = self.read_json('Tasks/index.json')
        tasks['tasks'] = [{'id': 'duplicate-status'}]
        self.write_json('Tasks/index.json', tasks)
        result, data = self.tool('project_setup.py', 'check')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('Tasks/index.json.tasks', '\n'.join(data['unverified']))

    def test_check_requires_selected_mode_state_source_file(self):
        for mode, relative in (('native', 'Tasks/index.json'),
                               ('unity-harness-init', 'docs/harness/progress.md')):
            if mode == 'unity-harness-init':
                self.record_harness()
            target = self.root / relative
            original = target.read_bytes()
            target.unlink()
            with self.subTest(mode=mode):
                result, data = self.tool('project_setup.py', 'check')
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(relative, '\n'.join(data['unverified']))
            target.write_bytes(original)

    def test_verified_metadata_cannot_replace_harness_rule_routing(self):
        self.record_harness()
        rules = self.read_json('Docs/ai/rules.json')
        for identifier in ('intent', 'execution', 'tracking', 'grading', 'verification'):
            invalid = copy.deepcopy(rules)
            invalid['sources'][identifier] = 'Docs/ai/project-rules.md'
            self.write_json('Docs/ai/rules.json', invalid)
            with self.subTest(identifier=identifier):
                result, data = self.tool('project_setup.py', 'check')
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(f'rules.sources.{identifier}', '\n'.join(data['unverified']))

    def test_cli_rejects_invalid_catalog_profile_and_workflow(self):
        for relative, invalid in (
                ('Docs/ai/setup-options.json', {'schema_version': 9}),
                ('Docs/ai/project-profile.json', {'schema_version': 1}),
                ('Docs/ai/workflow.json', {'schema_version': 1, 'mode': 'unknown'})):
            original = self.read_json(relative)
            self.write_json(relative, invalid)
            with self.subTest(relative=relative):
                result, data = self.tool('project_setup.py', 'check')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertTrue(data['errors'])
            self.write_json(relative, original)

    def test_cli_rejects_linked_catalog_escape(self):
        catalog = self.root / 'Docs/ai/setup-options.json'
        catalog.unlink()
        outside = self.case_dir / 'outside.json'
        outside.write_text(json.dumps(self.catalog), encoding='utf-8')
        try:
            catalog.symlink_to(outside)
        except OSError as error:
            if sys.platform != 'win32':
                self.skipTest(f'Symlinks are unavailable: {error}')
            directory = self.case_dir / 'outside-options'
            shutil.move(str(catalog.parent), str(directory))
            (directory / catalog.name).write_text(json.dumps(self.catalog), encoding='utf-8')
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(catalog.parent), str(directory)],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.addCleanup(catalog.parent.rmdir)
        result, data = self.tool('project_setup.py', 'list')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('escapes project', '\n'.join(data['errors']))

    def test_cli_help_is_available(self):
        result, _ = self.command(self.root / 'tools/ai/project_setup.py', '--help')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('list', result.stdout)
        self.assertIn('check', result.stdout)


if __name__ == '__main__':
    unittest.main()
