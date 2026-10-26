"""Static inventory contracts; fixtures never execute project commands."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from upgrade_support import Harness
from test_environment import SKILL

TOOLS = SKILL / 'assets/project/tools/ai'
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location('baseline', TOOLS / 'baseline.py')
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


class BaselineTests(Harness):
    def test_manifests_do_not_hide_unowned_source_directories(self):
        self.write('web/package.json', '{"name":"web"}')
        self.write('web/src/main.js', 'export const x = 1;')
        self.write('a/b/c/src/main.py', 'x = 1')
        self.write('src/bin/real.rs', 'fn main() {}')
        self.write('vendor/real.go', 'package real')
        result = self.scan()
        self.assertEqual({item['root'] for item in result['modules']}, {'web', 'a', 'src', 'vendor'})

    def test_existing_rule_documents_and_platform_rules_are_discoverable(self):
        self.write('Docs/ai/project-rules.md', '# Existing scope policy\n')
        self.write('.cursor/rules/team.mdc', 'Always read the existing team policy.\n')
        result = self.scan()
        self.assertEqual({item['path'] for item in result['existing_rules']},
                         {'Docs/ai/project-rules.md', '.cursor/rules/team.mdc'})

    def write(self, relative, content=''):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def scan(self, kind='general', managed=()):
        return BASELINE.scan_project(self.root, kind, None, managed)

    def test_full_depth_languages_manifests_and_metadata(self):
        self.write('a/b/c/d/src/main.py', 'print("not executed")\n')
        self.write('src/bin/real.rs', 'fn main() {}')
        self.write('vendor/real.go', 'package real')
        self.write('build/real.cpp', 'int main() {}')
        self.write('web/package.json', '{"scripts":{"build":"do not execute"}}')
        self.write('py/pyproject.toml', '[project]\nname="example"\n')
        self.write('dotnet/app.csproj', '<Project />')
        self.write('go/go.mod', 'module example')
        self.write('rust/Cargo.toml', '[package]\nname="example"')
        self.write('java/pom.xml', '<project />')
        self.write('native/CMakeLists.txt', 'project(example)')
        image = self.root / 'asset.png'
        image.write_bytes(b'\x89PNG secret binary')
        self.write('asset.png.meta', 'fileFormatVersion: 2')
        result = self.scan()
        files = {f['path']: f for f in result['files']}
        self.assertTrue(result['scan']['inventory_complete'])
        self.assertIn('a/b/c/d/src/main.py', files)
        self.assertEqual(files['asset.png']['content_status'], 'metadata-only')
        self.assertEqual(files['asset.png']['sha256'], '')
        self.assertEqual(files['asset.png.meta']['content_status'], 'read')
        self.assertTrue({'Python', 'Rust', 'Go', 'C++'} <= set(result['facts']['languages']))
        self.assertEqual(len(result['facts']['manifests']), 7)
        self.assertFalse(result['scan']['semantic_complete'])
        self.assertFalse(result['runtime_load_verified'])

    def test_sensitive_cache_and_binary_contents_are_never_opened(self):
        blocked = ['.env', '.env.prod', '.credentials.yaml', 'auth.json', 'cert.key',
                   'cert.pem', 'cert.pfx', '.ai-local.json', '.aws/config',
                   'node_modules/pkg/index.js', '.git/config', 'art.png']
        for name in blocked:
            self.write(name, 'DO_NOT_READ_THIS_VALUE')
        original = Path.open

        def guarded(path, *args, **kwargs):
            if path.is_relative_to(self.root) and path.relative_to(self.root).as_posix() in blocked:
                self.fail('Read forbidden content: ' + str(path))
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, 'open', guarded):
            result = self.scan()
        output = json.dumps(result)
        self.assertNotIn('DO_NOT_READ_THIS_VALUE', output)
        self.assertNotIn(str(self.root), output)
        self.assertTrue(any(e['reason'] == 'sensitive' for e in result['scan']['excluded']))

    def test_large_text_and_io_failure_report_coverage(self):
        self.write('large.py', 'x' * (1048576 + 1))
        failed = self.write('blocked.py', 'pass')
        original = Path.read_bytes

        def guarded(path):
            if path == failed:
                raise PermissionError('private details must not escape')
            return original(path)

        with mock.patch.object(Path, 'read_bytes', guarded):
            result = self.scan()
        files = {f['path']: f for f in result['files']}
        self.assertEqual(files['large.py']['content_status'], 'too-large')
        self.assertFalse(result['scan']['inventory_complete'])
        self.assertIn({'path': 'blocked.py', 'reason': 'read-error'}, result['scan']['issues'])
        self.assertNotIn('private details', json.dumps(result))

    def test_unity_deep_root_prunes_only_identified_project_cache(self):
        self.write('deep/a/b/game/ProjectSettings/ProjectVersion.txt', 'm_EditorVersion: 6000.3.1f1\n')
        self.write('deep/a/b/game/Assets/Scripts/Boot.cs', 'class Boot {}')
        self.write('deep/a/b/game/Library/cache.cs', 'generated')
        self.write('other/Library/real.cs', 'class Real {}')
        result = self.scan('unity')
        self.assertEqual(result['facts']['unity_projects'], [
            {'root': 'deep/a/b/game', 'editor_version': '6000.3.1f1'}])
        paths = [f['path'] for f in result['files']]
        self.assertNotIn('deep/a/b/game/Library/cache.cs', paths)
        self.assertIn('other/Library/real.cs', paths)
        self.assertTrue(any(a['id'] == 'unity-assets' for a in result['adaptations']))
        self.assertFalse(any(a['id'] == 'unity-assets' for a in self.scan()['adaptations']))

    def test_links_are_excluded_without_following(self):
        outside = self.case_dir / 'outside'
        outside.mkdir()
        (outside / 'escape.py').write_text('private', encoding='utf-8')
        link = self.root / 'linked'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
            created = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                                     shell=False, capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)

            def remove_junction():
                if (not link.absolute().is_relative_to(self.case_dir.resolve())
                        or link.resolve() != outside.resolve()
                        or not outside.resolve().is_relative_to(self.case_dir.resolve())):
                    raise RuntimeError('Refuse junction cleanup outside fixture')
                link.rmdir()

            self.addCleanup(remove_junction)
        result = self.scan()
        self.assertIn({'path': 'linked', 'reason': 'linked-path'}, result['scan']['excluded'])
        self.assertFalse(any('escape.py' in f['path'] for f in result['files']))

    def test_managed_manifest_and_manual_rule_parts_are_stable(self):
        self.write('AGENTS.md', '# Human rule\n')
        self.write('.gitignore', 'own-cache/\n')
        before = self.scan(managed=['AGENTS.md', '.gitignore', 'Docs/ai/generated.json'])
        self.write('AGENTS.md', '# Human rule\n\n<!-- ai-environment:start -->\nmanaged\n<!-- ai-environment:end -->\n')
        self.write('.gitignore', 'own-cache/\n\n# ai-environment:start\n.ai-local.json\n# ai-environment:end\n')
        self.write('Docs/ai/generated.json', '{"generated":true}')
        self.write_json('.ai-environment.json', {'files': {'AGENTS.md': 'hash', '.gitignore': 'hash', 'Docs/ai/generated.json': 'hash'}})
        after = self.scan(managed=['AGENTS.md', '.gitignore', 'Docs/ai/generated.json'])
        self.assertEqual(before, after)
        self.write('AGENTS.md', '# Changed human rule\n')
        self.assertNotEqual(before['files'], self.scan()['files'])

    def test_commands_have_evidence_and_adaptation_preserves_authority(self):
        self.write('package.json', '{"packageManager":"pnpm@9.0.0","scripts":{"build":"secret script", "test":"another script"}}')
        self.write('nested/package.json', '{"scripts":{"lint":"nested script"}}')
        result = self.scan()
        profile = {'project': {'kind': 'general'}, 'commands': {'build': [], 'test': ['custom'], 'lint': []},
                   'generated_paths': ['keep/'], 'capabilities': {}, 'users': {'existing': 'retain'}}
        original = copy.deepcopy(profile)
        adapted, context = BASELINE.adapt_project(profile, result)
        self.assertEqual(profile, original)
        self.assertEqual(adapted['commands']['build'], ['pnpm', 'run', 'build'])
        self.assertEqual(adapted['commands']['test'], ['custom'])
        self.assertEqual(adapted['commands']['lint'], [])
        self.assertEqual(adapted['users'], original['users'])
        self.assertEqual(adapted['generated_paths'], original['generated_paths'])
        self.assertTrue(all(e['verified_revision'] == '' for e in context['entries']))
        self.assertIn('<!-- ai-rule: adaptation -->', BASELINE.render_adaptation(result, adapted))
        self.assertNotIn('secret script', json.dumps(result))
        self.assertEqual(result['commands'][0]['evidence']['path'], 'package.json')

    def test_invalid_formats_are_reported_without_content(self):
        self.write('package.json', '{private broken')
        self.write('app.csproj', '<Project>private')
        result = self.scan()
        self.assertTrue(all(i['reason'] == 'invalid-format' for i in result['scan']['issues']))
        self.assertEqual(len(result['scan']['issues']), 2)
        self.assertNotIn('private', json.dumps(result))

    def test_conflicting_locks_do_not_guess_a_command(self):
        self.write('package.json', '{"scripts":{"test":"private script"}}')
        self.write('yarn.lock', '# lock')
        self.write('pnpm-lock.yaml', 'lockfileVersion: 9')
        result = self.scan()
        self.assertEqual(result['commands'], [])
        self.assertTrue(any('Conflicting package manager lock files' in item for item in result['unresolved']))
        self.write('package.json', '{"packageManager":"npm@10","scripts":{"test":"private script"}}')
        result = self.scan()
        self.assertEqual(result['commands'][0]['argv'], ['npm', 'run', 'test'])
        self.assertTrue(any('declaration conflicts' in item for item in result['unresolved']))

    def test_compare_detects_changes_and_invalid_baseline(self):
        script = TOOLS / 'baseline.py'
        self.write('src/main.py', 'pass\n')
        managed = ['Docs/ai/project-baseline.json']
        self.write_json(managed[0], self.scan(managed=managed))
        result, data = self.command(script, 'compare', '--project', self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.write('src/main.py', 'print(1)\n')
        result, data = self.command(script, 'compare', '--project', self.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(data['changed'], ['src/main.py'])
        self.write_json(managed[0], {'schema_version': 9})
        result, data = self.command(script, 'compare', '--project', self.root)
        self.assertEqual(result.returncode, 2)

    def test_git_status_is_local_read_only_and_parses_renames(self):
        self.write('new.py', 'pass')
        self.write('.git/HEAD', 'ref: refs/heads/main\n')
        responses = [subprocess.CompletedProcess([], 0, 'a' * 40 + '\n', ''),
                     subprocess.CompletedProcess([], 0, 'main\n', ''),
                     subprocess.CompletedProcess([], 0, 'R  new.py\0old.py\0?? .env\0', '')]
        with mock.patch.object(BASELINE.subprocess, 'run', side_effect=responses) as run:
            result = self.scan()
        self.assertEqual(result['git']['changes'], [{'path': 'new.py', 'status': 'R '}])
        for call in run.call_args_list:
            self.assertFalse(call.kwargs['shell'])
            self.assertLessEqual(call.kwargs['timeout'], 10)
            self.assertTrue(set(call.args[0]) & {'rev-parse', 'status'})


if __name__ == '__main__':
    unittest.main()
