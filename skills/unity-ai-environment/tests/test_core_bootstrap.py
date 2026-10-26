"""Entry budget and automatic static-baseline initialization acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

import test_environment as common
from upgrade_support import Harness


TOOLS = common.SKILL / 'assets/project/tools/ai'
SPEC = importlib.util.spec_from_file_location('entry_budget_under_test', TOOLS / 'entry_budget.py')
BUDGET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUDGET)


class EntryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.block = '<!-- ai-environment:start -->\nRead the project rules.\n<!-- ai-environment:end -->\n'
        self.certificate = {
            'schema_version': 1, 'limit': 500,
            'template_sha256': hashlib.sha256(self.block.encode('utf-8')).hexdigest(),
            'token_counts': {'cl100k_base': 300, 'o200k_base': 310},
        }

    def test_exact_certificate_and_manual_text_use_distinct_bounds(self):
        exact = BUDGET.check_entry(self.block, self.certificate)
        self.assertTrue(exact['ok'])
        self.assertEqual(exact['method'], 'certificate')
        self.assertEqual(exact['token_counts'], self.certificate['token_counts'])
        at_limit = BUDGET.check_entry('a' * 126 + self.block, self.certificate)
        self.assertTrue(at_limit['ok'])
        self.assertEqual(at_limit['method'], 'certificate-plus-utf8-bound')
        self.assertEqual(at_limit['token_counts']['o200k_base'], 500)
        self.assertFalse(BUDGET.check_entry('a' * 127 + self.block, self.certificate)['ok'])

    def test_manual_unicode_is_bounded_by_utf8_bytes(self):
        result = BUDGET.check_entry('界' * 43 + self.block, self.certificate)
        self.assertFalse(result['ok'])
        self.assertEqual(result['token_counts']['o200k_base'], 503)

    def test_unmatched_or_untrusted_certificate_uses_whole_text_bytes(self):
        result = BUDGET.check_entry('x' * 500, self.certificate)
        self.assertTrue(result['ok'])
        self.assertEqual(result['method'], 'utf8-bound')
        self.assertFalse(BUDGET.check_entry('x' * 501, self.certificate)['ok'])
        invalid = dict(self.certificate, token_counts={'cl100k_base': -1, 'o200k_base': 1})
        result = BUDGET.check_entry(self.block, invalid)
        self.assertEqual(result['method'], 'utf8-bound')
        duplicate = BUDGET.check_entry(self.block * 8, self.certificate)
        self.assertFalse(duplicate['ok'])
        self.assertEqual(duplicate['method'], 'utf8-bound')

    def test_certificate_hash_includes_the_exact_trailing_newline(self):
        result = BUDGET.check_entry(self.block.rstrip('\n'), self.certificate)
        self.assertEqual(result['method'], 'utf8-bound')


class CoreBootstrapTests(Harness):
    def test_unmanaged_conflicting_governance_is_scanned_before_abort(self):
        path = self.root / 'Docs/ai/project-rules.md'
        path.parent.mkdir(parents=True)
        path.write_text('# Existing team policy\nKeep the ownership rules.\n', encoding='utf-8')
        before = common.snapshot(self.root)
        result, data = self.bootstrap('plan')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertGreaterEqual(data['baseline_scan']['file_count'], 1)
        self.assertNotIn({'path': 'Docs/ai/project-rules.md', 'reason': 'managed-output'},
                         data['baseline_scan']['excluded'])
        self.assertEqual(common.snapshot(self.root), before)

    def test_plan_scans_without_writing_and_apply_adapts_declared_root_commands(self):
        self.write_json('package.json', {'name': 'fixture', 'scripts': {'test': 'never execute this'}})
        (self.root / 'src').mkdir()
        (self.root / 'src/main.js').write_text('export const value = 1;\n', encoding='utf-8')
        before = common.snapshot(self.root)
        result, data = self.bootstrap('plan')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(common.snapshot(self.root), before)
        self.assertEqual(data['baseline_scan']['mode'], 'static-full-inventory')
        self.assertGreaterEqual(data['baseline_scan']['file_count'], 2)
        self.assertTrue(data['entry_budgets']['AGENTS.md']['ok'])
        self.initialize()
        baseline = self.read_json('Docs/ai/project-baseline.json')
        self.assertIn('src/main.js', [entry['path'] for entry in baseline['files']])
        self.assertFalse(baseline['runtime_load_verified'])
        self.assertFalse(baseline['engineering_verified'])
        self.assertEqual(self.read_json('Docs/ai/project-profile.json')['commands']['test'], ['npm', 'run', 'test'])
        self.assertTrue(self.read_json('Docs/ai/context-index.json')['entries'])
        self.assertIn('<!-- ai-rule: adaptation -->', (self.root / 'Docs/ai/project-adaptation.md').read_text(encoding='utf-8'))
        installed = common.snapshot(self.root)
        self.initialize()
        self.assertEqual(common.snapshot(self.root), installed)

    def test_budget_failure_preserves_manual_rules_and_aborts_entire_batch(self):
        original = '# Human rules\n' + 'preserve this rule\n' * 100
        (self.root / 'AGENTS.md').write_text(original, encoding='utf-8')
        before = common.snapshot(self.root)
        for action in ('plan', 'apply'):
            with self.subTest(action=action):
                result, data = self.bootstrap(action, '--diff')
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('AGENTS.md', data['conflicts'])
                self.assertFalse(data['entry_budgets']['AGENTS.md']['ok'])
                self.assertTrue(data['entry_budgets']['AGENTS.md']['errors'])
                change = next(item for item in data['changes'] if item['path'] == 'AGENTS.md')
                self.assertNotIn('-# Human rules', change['diff'])
                self.assertEqual(common.snapshot(self.root), before)

    def test_short_manual_rules_are_preserved_and_do_not_pollute_repeat_scan(self):
        original = '# Human rules\nKeep this.\n'
        (self.root / 'AGENTS.md').write_text(original, encoding='utf-8')
        self.initialize()
        self.assertTrue((self.root / 'AGENTS.md').read_text(encoding='utf-8').startswith(original))
        baseline = self.read_json('Docs/ai/project-baseline.json')
        self.assertIn('AGENTS.md', [entry['path'] for entry in baseline['existing_rules']])
        before = common.snapshot(self.root)
        self.initialize()
        self.assertEqual(common.snapshot(self.root), before)

    def test_unity_root_selection_and_nested_full_entry_budget(self):
        kind = json.loads((common.SKILL / 'assets/project/Docs/ai/project-profile.json').read_text(encoding='utf-8'))['project']['kind']
        if kind != 'unity':
            before = common.snapshot(self.root)
            result, data = self.bootstrap('apply', '--unity-root', '.')
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn('--unity-root requires a Unity environment package', data['errors'])
            self.assertEqual(common.snapshot(self.root), before)
            return
        relative = 'products/mobile/client/runtime/Game'
        unity = self.root / relative
        (unity / 'Assets').mkdir(parents=True)
        (unity / 'ProjectSettings').mkdir()
        (unity / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.0.1f1\n', encoding='utf-8')
        result, data = self.bootstrap('plan')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(data['entry_budgets'][relative + '/AGENTS.md']['ok'])
        self.initialize()
        self.assertEqual(self.read_json('Docs/ai/project-profile.json')['unity']['root'], relative)
        before = common.snapshot(self.root)
        self.initialize()
        self.assertEqual(common.snapshot(self.root), before)
        (unity / 'AGENTS.md').write_text('Human instructions ' * 100 + (unity / 'AGENTS.md').read_text(encoding='utf-8'), encoding='utf-8')
        before = common.snapshot(self.root)
        result, data = self.bootstrap('apply', '--project-name', 'Portable Example')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(data['entry_budgets'][relative + '/AGENTS.md']['ok'])
        self.assertEqual(common.snapshot(self.root), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
