"""Unity-specific acceptance plus the shared behavior suite."""
import json
import unittest
import test_environment as common
import test_review as review


class UnityTests(review.ReviewTests):
    def make_unity_root(self, name):
        root = self.root / name
        (root / 'Assets').mkdir(parents=True)
        (root / 'ProjectSettings').mkdir()
        (root / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.60f1\n', encoding='utf-8')
        return root

    def test_nested_unity_root_has_thin_platform_entries(self):
        unity = self.make_unity_root('Game')
        (unity / 'AGENTS.md').write_text('# Existing Unity rules\nKeep GUID ownership.\n', encoding='utf-8')
        self.initialize('--platform', 'all')
        self.assertTrue((unity / 'AGENTS.md').is_file())
        entry = (unity / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('# Existing Unity rules\nKeep GUID ownership.', entry)
        self.assertIn('../Docs/ai/README.md', entry)
        self.assertTrue((unity / 'CLAUDE.md').is_file())
        self.assertTrue((unity / '.cursor/rules/project-ai.mdc').is_file())
        before = common.snapshot(self.root)
        self.initialize('--platform', 'all')
        self.assertEqual(before, common.snapshot(self.root))

    def test_multiple_roots_require_explicit_selection(self):
        self.make_unity_root('Alpha')
        self.make_unity_root('Beta')
        before = common.snapshot(self.root)
        result, data = self.bootstrap('plan')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(data['warnings'])
        self.assertEqual(before, common.snapshot(self.root))
        self.initialize('--unity-root', 'Alpha')
        profile = json.loads((self.root / 'Docs/ai/project-profile.json').read_text(encoding='utf-8'))
        self.assertEqual(profile['unity']['root'], 'Alpha')
        self.assertFalse((self.root / 'Beta/AGENTS.md').exists())

    def test_explicit_root_cannot_escape_or_point_to_non_unity_folder(self):
        before = common.snapshot(self.root)
        for target in ['../outside', 'not-a-unity-project']:
            result, data = self.bootstrap('apply', '--unity-root', target)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, common.snapshot(self.root))

    def test_unity_sensitive_patterns_cover_root_and_nested_projects(self):
        self.initialize()
        file, policy = self.register()
        policy['mode'] = 'enforce'
        policy['roles']['developer']['paths'] = ['**']
        policy['roles']['developer']['denied_paths'] = []
        paths = ['Packages/manifest.json', 'Game/Packages/manifest.json',
                 'Assembly.asmdef', 'Game/Assets/Runtime.asmdef', 'ProjectSettings/ProjectSettings.asset']
        file.write_text(json.dumps(policy), encoding='utf-8')
        result, data = self.installed('scope', '--user', 'alice', '--paths', *paths)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(data['violations']), len(paths))
        policy['roles']['developer']['elevated_paths'] = paths
        file.write_text(json.dumps(policy), encoding='utf-8')
        result, data = self.installed('scope', '--user', 'alice', '--paths', *paths)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_identity_cache_preserves_separate_local_tool_paths(self):
        self.initialize()
        self.register()
        local = self.root / '.ai-local/unity.json'
        local.parent.mkdir()
        local.write_text('{"config_source_root": "user-supplied-directory"}\n', encoding='utf-8')
        before = local.read_bytes()
        result, data = self.installed('identity', '--user', 'alice')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(local.read_bytes(), before)
        self.assertIn('.ai-local/', (self.root / '.gitignore').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
