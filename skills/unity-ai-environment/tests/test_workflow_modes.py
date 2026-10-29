"""Black-box initialization choices and exclusive workflow materialization."""
import unittest

import test_environment as common
from upgrade_support import Harness


class WorkflowModeTests(Harness):
    def test_plan_lists_tools_and_modes_without_writing(self):
        before = common.snapshot(self.root)
        result, data = self.bootstrap('plan')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        options = {item['id']: item for item in data['optional_tools']}
        for identifier in ('unity-editor-cli', 'unity-editor-mcp', 'unity-editor-anklebreaker'):
            self.assertTrue(options[identifier]['name'])
            self.assertTrue(options[identifier]['features'])
            self.assertFalse(options[identifier]['enabled'])
        self.assertEqual(data['selected_workflow'], 'native')
        self.assertEqual({item['id'] for item in data['workflow_options']},
                         {'native', 'unity-harness-init'})
        self.assertEqual(common.snapshot(self.root), before)

    def test_selected_tool_is_configured_but_never_verified(self):
        result, data = self.bootstrap('apply', '--tools', 'unity-editor-anklebreaker')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        profile = self.read_json('Docs/ai/project-profile.json')
        item = profile['capabilities']['unity-editor-anklebreaker']
        self.assertTrue(item['integration']['enabled'])
        self.assertEqual(item['state'], 'unconfigured')
        self.assertEqual(item['evidence'], [])
        for identifier in ('unity-editor-cli', 'unity-editor-mcp'):
            self.assertFalse(profile['capabilities'][identifier]['integration']['enabled'])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_none_and_unknown_choices_are_explicit(self):
        result, data = self.bootstrap('plan', '--tools', 'none')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        before = common.snapshot(self.root)
        for choices in (('unknown',), ('none', 'unity-editor-cli')):
            result, data = self.bootstrap('apply', '--tools', *choices)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(common.snapshot(self.root), before)

    def test_editor_provider_conflict_aborts_the_whole_batch(self):
        before = common.snapshot(self.root)
        result, data = self.bootstrap('apply', '--tools', 'unity-editor-cli', 'unity-editor-mcp')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(common.snapshot(self.root), before)

    def test_harness_selects_required_dependencies_and_replaces_native_rules(self):
        result, data = self.bootstrap('apply', '--workflow', 'unity-harness-init')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data['selected_workflow'], 'unity-harness-init')
        self.assertIn('docs/harness/progress.md', {item['path'] for item in data['changes']})
        profile = self.read_json('Docs/ai/project-profile.json')
        for identifier in ('unity-skills-rest', 'unity-harness-init', 'copilot-cli'):
            item = profile['capabilities'][identifier]
            self.assertTrue(item['integration']['enabled'])
            self.assertTrue(item['integration']['required'])
            self.assertEqual(item['state'], 'unconfigured')
        routes = self.read_json('Docs/ai/rules.json')['sources']
        for identifier in ('workflow', 'tracking', 'verification', 'execution', 'intent', 'grading'):
            self.assertEqual(routes[identifier], 'Docs/ai/workflow.md')
        native = (self.root / 'Docs/ai/project-rules.md').read_text(encoding='utf-8')
        self.assertNotIn('独立当次小修复可不建档', native)
        self.assertNotIn('方案以结构差异表提交', native)
        self.assertEqual(self.read_json('Tasks/index.json')['tasks'], [])
        self.assertTrue((self.root / 'docs/harness/progress.md').is_file())
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result, data = self.tool('project_setup.py', 'check')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(data['engineering_verified'])

    def test_harness_never_substitutes_an_optional_editor_bridge(self):
        before = common.snapshot(self.root)
        result, data = self.bootstrap('apply', '--workflow', 'unity-harness-init',
                                      '--tools', 'unity-editor-cli')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(common.snapshot(self.root), before)

    def test_native_mode_does_not_materialize_harness_assets(self):
        self.initialize('--workflow', 'native')
        self.assertFalse((self.root / 'docs/harness').exists())
        self.assertFalse((self.root / '.github').exists())
        profile = self.read_json('Docs/ai/project-profile.json')
        self.assertFalse(profile['capabilities']['unity-skills-rest']['integration']['required'])
        result, data = self.tool('project_setup.py', 'check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_harness_reinitialization_keeps_mode_and_is_byte_identical(self):
        self.initialize('--workflow', 'unity-harness-init')
        before = common.snapshot(self.root)
        result, data = self.bootstrap('apply', '--project-name', 'Portable Example')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data['selected_workflow'], 'unity-harness-init')
        self.assertEqual(common.snapshot(self.root), before)

    def test_mode_switch_and_custom_rules_are_reviewed_conflicts(self):
        self.initialize('--workflow', 'native')
        before = common.snapshot(self.root)
        result, data = self.bootstrap('apply', '--workflow', 'unity-harness-init')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(data['conflicts'])
        self.assertEqual(common.snapshot(self.root), before)

    def test_invalid_existing_workflow_is_rejected_without_writes(self):
        for value in ([], {'schema_version': 1},
                      {'schema_version': True, 'mode': 'native'},
                      {'schema_version': 1, 'mode': 'unknown'}):
            self.write_json('Docs/ai/workflow.json', value)
            before = common.snapshot(self.root)
            for action in ('plan', 'apply'):
                with self.subTest(value=value, action=action):
                    result, data = self.bootstrap(action)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIsInstance(data, dict)
                    self.assertTrue(data['errors'])
                    self.assertNotIn('Traceback', result.stdout + result.stderr)
                    self.assertEqual(common.snapshot(self.root), before)

    def test_invalid_existing_profile_selection_is_rejected_without_writes(self):
        for value in ([], {'capabilities': []},
                      {'capabilities': {'unity-editor-cli': []}},
                      {'capabilities': {'unity-editor-cli': {'integration': []}}}):
            self.write_json('Docs/ai/project-profile.json', value)
            before = common.snapshot(self.root)
            for action in ('plan', 'apply'):
                with self.subTest(value=value, action=action):
                    result, data = self.bootstrap(action)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIsInstance(data, dict)
                    self.assertTrue(data['errors'])
                    self.assertNotIn('Traceback', result.stdout + result.stderr)
                    self.assertEqual(common.snapshot(self.root), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
