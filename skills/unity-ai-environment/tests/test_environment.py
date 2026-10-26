"""Black-box acceptance for either independently installable environment skill."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import unittest
import uuid

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--skill', required=True, type=Path)
ARGS, REST = PARSER.parse_known_args()
SKILL = ARGS.skill.resolve()
sys.argv = [sys.argv[0], *REST]
RUNS = Path(__file__).resolve().parent / 'test-runs'
RUNS.mkdir(exist_ok=True)


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.case_dir = RUNS / uuid.uuid4().hex
        self.root = self.case_dir / 'example project'
        self.root.mkdir(parents=True)
        self.addCleanup(self.cleanup_case)
        self.env = os.environ.copy()
        self.env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        self.env.pop('AI_PROJECT_USER', None)

    def cleanup_case(self):
        if not self.case_dir.resolve().is_relative_to(RUNS.resolve()):
            raise RuntimeError('Refuse cleanup outside test root')
        shutil.rmtree(self.case_dir)

    def command(self, script, *args):
        result = subprocess.run([sys.executable, '-B', str(script), *map(str, args)],
                                env=self.env, capture_output=True, text=True, encoding='utf-8')
        return result, json.loads(result.stdout) if result.stdout.strip().startswith('{') else None

    def bootstrap(self, action='apply', *extra):
        script = SKILL / 'scripts/bootstrap.py'
        self.assertTrue(script.is_file(), 'A self-contained initialization script is required')
        return self.command(script, action, '--project', self.root, *extra)

    def installed(self, *args):
        return self.command(self.root / 'tools/ai/check_env.py', *args, '--project', self.root)

    def initialize(self, *extra):
        result, data = self.bootstrap('apply', '--project-name', 'Portable Example', *extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return data

    def test_dry_run_leaves_existing_project_byte_identical(self):
        (self.root / 'AGENTS.md').write_text('# Existing rules\nKeep this.\n', encoding='utf-8')
        before = snapshot(self.root)
        result, data = self.bootstrap('plan')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['changes'])
        self.assertEqual(snapshot(self.root), before)

    def test_initialize_is_repeatable_and_does_not_auto_grant(self):
        self.initialize()
        before = snapshot(self.root)
        self.initialize()
        self.assertEqual(snapshot(self.root), before)
        policy = json.loads((self.root / 'Docs/ai/access-policy.json').read_text(encoding='utf-8'))
        self.assertEqual(policy['users'], {})
        self.assertEqual(policy['mode'], 'audit')
        self.assertTrue(all(not r['paths'] for r in policy['roles'].values()))
        profile = json.loads((self.root / 'Docs/ai/project-profile.json').read_text(encoding='utf-8'))
        self.assertEqual(profile['project']['name'], 'Portable Example')

    def test_conflict_aborts_whole_install_without_partial_files(self):
        path = self.root / 'Docs/ai/access-policy.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"my_policy": true}\n', encoding='utf-8')
        before = snapshot(self.root)
        result, data = self.bootstrap('apply')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(data['conflicts'])
        self.assertEqual(snapshot(self.root), before)

    def test_preserves_manual_entries_and_operator_settings(self):
        (self.root / 'AGENTS.md').write_text('# Human rules\nDo useful work.\n', encoding='utf-8')
        (self.root / '.gitignore').write_text('custom-cache/\n', encoding='utf-8')
        config = self.root / '.codex/config.toml'
        config.parent.mkdir()
        config.write_text('model = "operator-choice"\n', encoding='utf-8')
        self.initialize('--platform', 'all')
        self.assertIn('# Human rules\nDo useful work.', (self.root / 'AGENTS.md').read_text(encoding='utf-8'))
        self.assertIn('custom-cache/', (self.root / '.gitignore').read_text(encoding='utf-8'))
        self.assertIn('.ai-local.json', (self.root / '.gitignore').read_text(encoding='utf-8'))
        self.assertEqual(config.read_text(encoding='utf-8'), 'model = "operator-choice"\n')
        self.assertTrue((self.root / 'CLAUDE.md').is_file())
        self.assertTrue((self.root / '.cursor/rules/project-ai.mdc').is_file())
        self.assertTrue((self.root / '.trae/rules/project_rules.md').is_file())
        self.assertTrue((self.root / '.workbuddy/rules/project-ai.md').is_file())

    def test_static_check_distinguishes_unconfigured_engineering_gates(self):
        self.initialize()
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['ok'])
        self.assertTrue(data['warnings'])
        self.assertFalse(data['runtime_load_verified'])
        self.assertFalse(data['engineering_verified'])

    def test_unknown_identity_remains_read_only(self):
        self.initialize()
        result, data = self.installed('whoami', '--user', 'unknown-person')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(data['can_edit'])
        self.assertFalse(data['verified'])
        self.assertFalse((self.root / '.ai-local.json').exists())

    def register(self):
        file = self.root / 'Docs/ai/access-policy.json'
        policy = json.loads(file.read_text(encoding='utf-8'))
        policy['roles']['developer']['paths'] = ['src/', 'Docs/ai/']
        policy['roles']['developer']['denied_paths'] = ['src/private/']
        policy['users']['alice'] = {'role': 'developer'}
        file.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding='utf-8')
        return file, policy

    def test_identity_cache_does_not_change_role_or_policy(self):
        self.initialize()
        file, policy = self.register()
        before = file.read_bytes()
        result, data = self.installed('identity', '--user', 'alice')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.root / '.ai-local.json').is_file())
        self.assertEqual(file.read_bytes(), before)
        result, data = self.installed('whoami')
        self.assertEqual(data['user'], 'alice')
        self.assertEqual(data['role'], 'developer')
        result, data = self.installed('identity', '--user', 'unregistered')
        self.assertNotEqual(result.returncode, 0)

    def test_audit_reports_and_enforce_rejects_denied_paths(self):
        self.initialize()
        file, policy = self.register()
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'src/ok.py', 'src/private/key.py', 'Docs/ai/access-policy.json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(data['violations']), 2)
        policy['mode'] = 'enforce'
        file.write_text(json.dumps(policy), encoding='utf-8')
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'src/private/key.py')
        self.assertEqual(result.returncode, 1)
        result, data = self.installed('scope', '--user', 'alice', '--paths', '../escape')
        self.assertNotEqual(result.returncode, 0)

    def test_task_dependency_cycle_and_escape_are_invalid(self):
        self.initialize()
        tasks = self.root / 'Tasks/index.json'
        (self.root / 'Tasks/a.md').write_text('A', encoding='utf-8')
        (self.root / 'Tasks/b.md').write_text('B', encoding='utf-8')
        tasks.write_text(json.dumps({'schema_version': 1, 'tasks': [
            {'id': 'a', 'path': 'Tasks/a.md', 'status': 'proposed', 'owner': '', 'depends_on': ['b']},
            {'id': 'b', 'path': 'Tasks/b.md', 'status': 'proposed', 'owner': '', 'depends_on': ['a']}
        ]}), encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)
        self.assertTrue(data['errors'])
        tasks.write_text(json.dumps({'schema_version': 1, 'tasks': [
            {'id': 'a', 'path': '../outside.md', 'status': 'proposed', 'owner': '', 'depends_on': []}
        ]}), encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_nonportable_policy_path_is_rejected(self):
        self.initialize()
        file, policy = self.register()
        policy['roles']['developer']['paths'] = ['C:/machine-only/src/']
        file.write_text(json.dumps(policy), encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_sensitive_paths_need_both_normal_and_elevated_grants(self):
        self.initialize()
        file, policy = self.register()
        policy['roles']['developer']['paths'] = ['src/']
        policy['roles']['developer']['elevated_paths'] = ['restricted/']
        policy['critical_paths'] = ['restricted/']
        policy['mode'] = 'enforce'
        file.write_text(json.dumps(policy), encoding='utf-8')
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'restricted/data.json')
        self.assertEqual(result.returncode, 1, 'Elevated permission alone must not grant ordinary scope')
        result, data = self.installed('whoami', '--user', 'alice')
        self.assertTrue(data['can_edit'])
        policy['roles']['developer']['paths'] = []
        file.write_text(json.dumps(policy), encoding='utf-8')
        result, data = self.installed('whoami', '--user', 'alice')
        self.assertFalse(data['can_edit'])

    def test_personal_paths_replace_role_paths(self):
        self.initialize()
        file, policy = self.register()
        policy['mode'] = 'enforce'
        policy['roles']['developer']['denied_paths'] = []
        policy['users']['alice']['paths'] = ['src/owned/']
        policy['users']['alice']['elevated_paths'] = []
        policy['users']['alice']['denied_paths'] = []
        file.write_text(json.dumps(policy), encoding='utf-8')
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'src/other/file.py')
        self.assertEqual(result.returncode, 1)
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'src/owned/file.py')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unsupported_policy_schema_does_not_pass_scope(self):
        self.initialize()
        file, policy = self.register()
        policy['schema_version'] = 999
        file.write_text(json.dumps(policy), encoding='utf-8')
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'src/file.py')
        self.assertNotEqual(result.returncode, 0)

    def test_modified_managed_file_is_reported_without_replacement(self):
        self.initialize()
        file = self.root / 'Docs/ai/project-rules.md'
        file.write_text(file.read_text(encoding='utf-8') + '\nLocal amendment.\n', encoding='utf-8')
        before = file.read_bytes()
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['warnings'])
        result, data = self.bootstrap('apply', '--project-name', 'Portable Example')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(file.read_bytes(), before)

    def test_project_kind_bundle_is_independent(self):
        profile = SKILL / 'assets/project/Docs/ai/project-profile.json'
        self.assertTrue(profile.is_file(), 'Complete project profile must ship with skill')
        kind = json.loads(profile.read_text(encoding='utf-8'))['project']['kind']
        if kind == 'general':
            for p in (SKILL / 'assets/project').rglob('*'):
                if p.is_file() and p.suffix in {'.md', '.json'}:
                    content = p.read_text(encoding='utf-8')
                    self.assertNotIn('\u7b56\u5212', content, p)
                    for word in ['SeaWar', 'GYYX', 'BMCSharp']:
                        self.assertNotIn(word, content, p)
        else:
            self.assertEqual(kind, 'unity')
            unity = self.root / 'Game'
            (unity / 'Assets').mkdir(parents=True)
            (unity / 'ProjectSettings').mkdir()
            (unity / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.60f1\n', encoding='utf-8')
            self.initialize()
            result, data = self.installed('check')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            profile_data = json.loads((self.root / 'Docs/ai/project-profile.json').read_text(encoding='utf-8'))
            self.assertEqual(profile_data['unity']['root'], 'Game')
            self.assertEqual(profile_data['unity']['editor_version'], '2022.3.60f1')
            self.assertTrue((self.root / 'Docs/ai/planning-workflows.md').is_file())


if __name__ == '__main__':
    unittest.main(verbosity=2)
