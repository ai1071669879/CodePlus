"""Regression tests for the second rule/tool coverage review."""
import copy
import json
import os
import shutil
import stat
from pathlib import Path
import subprocess
import test_environment as common
import unittest


class ReviewTests(common.EnvironmentTests):
    def cleanup_case(self):
        if not self.case_dir.resolve().is_relative_to(common.RUNS.resolve()):
            raise RuntimeError('Refuse cleanup outside isolated test root')
        def remove_read_only(function, path, error):
            if not Path(path).resolve().is_relative_to(self.case_dir.resolve()):
                raise RuntimeError('Refuse cleanup outside this case')
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
            function(path)
        shutil.rmtree(self.case_dir, onerror=remove_read_only)

    def write_policy(self, policy):
        path = self.root / 'Docs/ai/access-policy.json'
        path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding='utf-8')

    def read_profile(self):
        return json.loads((self.root / 'Docs/ai/project-profile.json').read_text(encoding='utf-8'))

    def write_profile(self, profile):
        (self.root / 'Docs/ai/project-profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')

    def test_file_type_denial_includes_unity_metadata_partner(self):
        self.initialize()
        _, policy = self.register()
        policy['mode'] = 'enforce'
        policy['roles']['developer']['denied_extensions'] = ['.cs']
        self.write_policy(policy)
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'src/Bad.cs', 'src/Bad.cs.meta', 'src/data.txt')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(data['violations']), 2)

    def test_file_grant_cannot_expand_to_other_file_types(self):
        self.initialize()
        _, policy = self.register()
        policy['mode'] = 'enforce'
        role = policy['roles']['developer']
        role['paths'] = []
        role['file_grants'] = [{'paths': ['Art/'], 'suffixes': ['.prefab', '.prefab.meta']}]
        self.write_policy(policy)
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'Art/Button.prefab', 'Art/Button.prefab.meta', 'Art/Injected.cs')
        self.assertEqual(result.returncode, 1)
        self.assertEqual([item['path'] for item in data['violations']], ['Art/Injected.cs'])

    def test_code_paths_are_an_additional_constraint(self):
        self.initialize()
        _, policy = self.register()
        policy['mode'] = 'enforce'
        policy['code_extensions'] = ['.cs']
        role = policy['roles']['developer']
        role['paths'] = ['Art/']
        role['code_paths'] = ['Art/Renderer/']
        self.write_policy(policy)
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'Art/Other.cs', 'Art/Renderer/Allowed.cs', 'Elsewhere/Renderer.cs')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(data['violations']), 2)

    def test_content_owner_applies_inside_a_broad_role_path(self):
        self.initialize()
        _, policy = self.register()
        policy['mode'] = 'enforce'
        policy['roles']['developer']['paths'] = ['**']
        policy['roles']['content_owner'] = copy.deepcopy(policy['roles']['developer'])
        policy['users']['bob'] = {'role': 'content_owner'}
        policy['owned_paths'] = [{'paths': ['Data/'], 'roles': ['content_owner']}]
        self.write_policy(policy)
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'Data/row.json')
        self.assertEqual(result.returncode, 1)
        result, data = self.installed('scope', '--user', 'bob', '--paths', 'Data/row.json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generated_exception_uses_profile_as_single_source(self):
        self.initialize()
        _, policy = self.register()
        policy['mode'] = 'enforce'
        role = policy['roles']['developer']
        role['paths'] = ['src/', 'Generated/']
        role['denied_extensions'] = ['.cs']
        role['generated_extensions'] = ['.cs']
        self.write_policy(policy)
        profile = self.read_profile()
        profile['generated_paths'] = ['Generated/']
        self.write_profile(profile)
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'Generated/Table.cs', 'src/Handwritten.cs')
        self.assertEqual(result.returncode, 1)
        self.assertEqual([item['path'] for item in data['violations']], ['src/Handwritten.cs'])

    def test_unknown_permission_field_fails_closed(self):
        self.initialize()
        _, policy = self.register()
        policy['roles']['developer']['denied_extensons'] = ['.cs']
        self.write_policy(policy)
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_change_confirmation_applies_only_to_configured_roles(self):
        self.initialize()
        self.register()
        profile = self.read_profile()
        profile['change_controls'] = [{'id': 'shared-contract', 'paths': ['src/'],
                                       'roles': ['maintainer'], 'reason': 'shared interface review'}]
        self.write_profile(profile)
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'src/Feature.cs')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any('shared-contract' in warning for warning in data['warnings']))
        profile['change_controls'][0]['roles'] = ['developer']
        self.write_profile(profile)
        result, data = self.installed('scope', '--user', 'alice', '--paths', 'src/Feature.cs')
        self.assertTrue(any('shared-contract' in warning for warning in data['warnings']))

    def test_project_skill_discovery_is_separate_from_actual_loading(self):
        self.initialize()
        skill = self.root / '.codex/skills/example/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: example\ndescription: Example local capability\n---\n', encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('example', data.get('repository_skills', {}).get('codex', []))
        self.assertFalse(data['runtime_load_verified'])

    def test_cached_role_declaration_detects_registry_change(self):
        self.initialize()
        _, policy = self.register()
        result, data = self.installed('identity', '--user', 'alice', '--role', 'developer')
        self.assertEqual(result.returncode, 0)
        policy['users']['alice']['role'] = 'maintainer'
        policy['roles']['maintainer']['paths'] = ['src/']
        self.write_policy(policy)
        result, data = self.installed('whoami')
        self.assertEqual(result.returncode, 0)
        self.assertFalse(data['can_edit'])
        self.assertFalse(data['role_matches_policy'])

    def test_clear_identity_only_removes_local_cache(self):
        self.initialize()
        file, _ = self.register()
        before = file.read_bytes()
        self.installed('identity', '--user', 'alice')
        result, data = self.installed('clear-identity')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / '.ai-local.json').exists())
        self.assertEqual(file.read_bytes(), before)

    def task_index(self, tasks):
        (self.root / 'Tasks/index.json').write_text(json.dumps({'schema_version': 1, 'tasks': tasks}), encoding='utf-8')

    def test_pending_revision_does_not_block_proposal_but_completion_needs_evidence(self):
        self.initialize()
        self.register()
        (self.root / 'Tasks/a.md').write_text('Actual task', encoding='utf-8')
        task = {'id': 'a', 'path': 'Tasks/a.md', 'status': 'proposed', 'owner': 'alice', 'depends_on': [],
                'source': {'reference': 'requirement document', 'revision': 'r2', 'confirmed_revision': 'r1'}}
        self.task_index([task])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data.get('task_status', {}).get('a', {}).get('stale_revision'))
        task['status'] = 'completed'
        self.task_index([task])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)
        task['acceptance'] = {'by': 'alice', 'evidence': ['target behavior was verified']}
        self.task_index([task])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_task_owner_must_be_registered(self):
        self.initialize()
        (self.root / 'Tasks/a.md').write_text('A', encoding='utf-8')
        self.task_index([{'id': 'a', 'path': 'Tasks/a.md', 'status': 'in_progress', 'owner': 'unregistered', 'depends_on': []}])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_task_body_cannot_be_a_directory(self):
        self.initialize()
        self.task_index([{'id': 'a', 'path': 'Tasks/', 'status': 'proposed', 'owner': '', 'depends_on': []}])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_selected_platform_cannot_disappear_from_manifest(self):
        self.initialize('--platform', 'all')
        (self.root / 'CLAUDE.md').unlink()
        path = self.root / '.ai-environment.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['files'].pop('CLAUDE.md')
        path.write_text(json.dumps(manifest), encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_manifest_kind_must_match_project_profile(self):
        self.initialize()
        path = self.root / '.ai-environment.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['profile'] = 'unity' if manifest['profile'] == 'general' else 'general'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_rule_entry_route_cannot_be_removed(self):
        self.initialize()
        (self.root / 'AGENTS.md').write_text('Unrelated text\n', encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_duplicate_rule_definition_is_an_error(self):
        self.initialize()
        (self.root / 'Docs/ai/duplicate.md').write_text('<!-- ai-rule: identity -->\nA second definition\n', encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_navigation_distinguishes_current_stale_and_unknown_revisions(self):
        self.initialize()
        (self.root / 'src').mkdir()
        source = self.root / 'src/core.py'
        source.write_text('VALUE = 1\n', encoding='utf-8')
        git = ['git', '-c', 'safe.directory=' + str(self.root)]
        for args in [['init', '-q'], ['add', 'src/core.py'],
                     ['-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-q', '-m', 'fixture baseline']]:
            r = subprocess.run(git + args, cwd=self.root, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        revision = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=self.root, text=True).strip()
        path = self.root / 'Docs/ai/context-index.json'
        entry = {'id': 'core', 'aliases': ['core'], 'roots': ['src/'], 'entrypoints': ['src/core.py'], 'verified_revision': revision}
        path.write_text(json.dumps({'schema_version': 1, 'entries': [entry]}), encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data.get('context_status', {}).get('core'), 'current')
        source.write_text('VALUE = 2\n', encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(data.get('context_status', {}).get('core'), 'stale')
        entry['verified_revision'] = 'missing-revision'
        path.write_text(json.dumps({'schema_version': 1, 'entries': [entry]}), encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(data.get('context_status', {}).get('core'), 'unknown')

    def test_verified_capability_requires_actual_evidence_metadata(self):
        self.initialize()
        profile = self.read_profile()
        profile['capabilities']['example-tool'] = {'state': 'verified', 'source_paths': [], 'entrypoints': [], 'command': ['tool'], 'verified_revision': '', 'evidence': []}
        self.write_profile(profile)
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_empty_executable_is_not_a_configured_gate(self):
        self.initialize()
        profile = self.read_profile()
        profile['commands']['build'] = ['']
        self.write_profile(profile)
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1)

    def test_plan_can_show_actual_conflicting_content_without_writing(self):
        path = self.root / 'Docs/ai/access-policy.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"existing":true}\n', encoding='utf-8')
        before = common.snapshot(self.root)
        result, data = self.bootstrap('plan', '--diff')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Docs/ai/access-policy.json', [item['path'] for item in data['changes']])
        change = next(item for item in data['changes'] if item['path'] == 'Docs/ai/access-policy.json')
        self.assertIn('existing', change.get('diff', ''))
        self.assertIn('schema_version', change.get('diff', ''))
        self.assertEqual(before, common.snapshot(self.root))


if __name__ == '__main__':
    unittest.main(verbosity=2)
