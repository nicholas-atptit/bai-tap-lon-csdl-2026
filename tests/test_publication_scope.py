"""Publication scope must exclude local runtime without hiding tracked artifacts."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_publication as gate


class PublicationScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(gate, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def put(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture', encoding='utf-8')

    def test_runtime_exclusion_keeps_unreviewed_public_candidates_visible(self):
        for name in ('.env', '.venv/Lib/runtime.py', 'var/private.csv',
                     '.pytest_cache/state', 'tests/runs/run/log.txt',
                     'tests/product_evidence/private/real_prices.csv',
                     '.env.example', '.env.production', 'data/raw/private.csv',
                     'new_unreviewed.py', 'unreviewed.bak'):
            self.put(name)
        self.assertEqual(set(gate.files()), {
            '.env.example', '.env.production', 'data/raw/private.csv',
            'new_unreviewed.py', 'unreviewed.bak',
        })

    def test_tracked_local_files_are_rejected_even_when_excluded_from_walk(self):
        (self.root / '.git').mkdir()
        for name in ('.env', '.venv/runtime.py', 'var/private.csv',
                     'tests/runs/private.log', '__pycache__/secret.pyc',
                     'tests/product_evidence/private/real_prices.csv'):
            with self.subTest(name=name), patch.object(
                gate.subprocess, 'check_output', return_value=(name + '\0').encode()
            ):
                with self.assertRaisesRegex(AssertionError, 'Local-only files are tracked'):
                    gate.files()

    def test_gitignore_does_not_hide_a_public_candidate(self):
        self.put('.gitignore')
        self.put('ignored_by_git.txt')
        (self.root / '.gitignore').write_text('ignored_by_git.txt\n', encoding='utf-8')
        self.assertIn('ignored_by_git.txt', gate.files())


if __name__ == '__main__':
    unittest.main()
