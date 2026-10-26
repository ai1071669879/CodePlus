"""Check relative Markdown links in this repository's own documents.

Skill assets are templates for *other* projects, so they are deliberately excluded: their
links resolve inside a generated project, not here.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TARGETS = [REPO / 'README.md', REPO / 'AGENTS.md']
TARGETS += sorted((REPO / 'codex').glob('*.md'))
TARGETS += sorted((REPO / 'skills').glob('*.md'))
TARGETS += sorted((REPO / 'tools').glob('*.md'))
TARGETS += sorted((REPO / 'tools' / 'analysis').glob('*.md'))
TARGETS += sorted((REPO / 'docs').glob('*.md'))
LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"\n]*")?\)')


def main() -> int:
    problems = []
    checked = 0
    for path in TARGETS:
        if not path.is_file():
            problems.append(f'missing document: {path.relative_to(REPO).as_posix()}')
            continue
        for link in LINK.findall(path.read_text(encoding='utf-8')):
            link = link.strip('<>')
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', link) or link.startswith(('#', '//')):
                continue
            target = link.split('#', 1)[0].split('?', 1)[0]
            if not target:
                continue
            checked += 1
            if not (path.parent / target).resolve().exists():
                problems.append(f'{path.relative_to(REPO).as_posix()}: broken link {link}')
    print(f'checked {checked} relative links in {len(TARGETS)} documents')
    for problem in problems:
        print('  ' + problem)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
