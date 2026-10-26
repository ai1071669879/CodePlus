"""Integration acceptance: required baseline and complete-entry budget checks."""
import unittest
from upgrade_support import Harness


class CoreContractTests(Harness):
    def test_literal_bracket_source_names_can_be_navigated(self):
        path = self.root / 'src/[id].tsx'
        path.parent.mkdir()
        path.write_text('export default function Page() { return null; }\n', encoding='utf-8')
        self.initialize()
        baseline = self.read_json('Docs/ai/project-baseline.json')
        self.assertIn('src/[id].tsx', [item['path'] for item in baseline['files']])
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_oversized_complete_agents_is_a_check_error(self):
        self.initialize()
        path = self.root / 'AGENTS.md'
        path.write_text(path.read_text(encoding='utf-8') + '\n' + 'boundary ' * 700, encoding='utf-8')
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_budget_certificate_is_required_even_if_manifest_hides_it(self):
        self.initialize()
        relative = 'Docs/ai/entry-budget.json'
        (self.root / relative).unlink()
        manifest = self.read_json('.ai-environment.json')
        manifest['files'].pop(relative, None)
        self.write_json('.ai-environment.json', manifest)
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_baseline_cannot_claim_full_semantic_or_runtime_verification(self):
        self.initialize()
        baseline = self.read_json('Docs/ai/project-baseline.json')
        baseline['scan']['semantic_complete'] = True
        baseline['engineering_verified'] = True
        self.write_json('Docs/ai/project-baseline.json', baseline)
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_adaptation_route_is_required(self):
        self.initialize()
        routes = self.read_json('Docs/ai/rules.json')
        routes['sources'].pop('adaptation', None)
        self.write_json('Docs/ai/rules.json', routes)
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_generated_baseline_and_adaptation_are_required(self):
        self.initialize()
        for relative in ('Docs/ai/project-baseline.json', 'Docs/ai/project-adaptation.md'):
            self.assertTrue((self.root / relative).is_file(), relative)
        result, data = self.installed('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(data['runtime_load_verified'])
        self.assertFalse(data['engineering_verified'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
