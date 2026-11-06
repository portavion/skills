#!/usr/bin/env python3
"""Build a visual PR page from a page.json, or rebuild one from an existing page.

    build.py page.json -o out.html [--repo DIR --range BASE..HEAD]
    build.py out.html -o out.html --repo DIR --range BASE..HEAD   # refresh commits
    build.py out.html --dump page.json                            # get the content back to edit

The input is checked first. Every problem is printed and nothing is written
until all of them are fixed.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / 'assets' / 'template.html'
PAGE_TAG = re.compile(r'<script type="application/json" id="page">(.*?)</script>', re.S)

# Each block type and the fields it must have.
BLOCKS = {
    'text': {'paragraphs': list},
    'notes': {'items': list},
    'list': {'items': list},
    'glossary': {'items': list},
    'diagram': {'svg': str},
    'stats': {'items': list},
    'steps': {'steps': list},
    'cards': {'items': list},
    'table': {'columns': list, 'rows': list},
    'commits': {},
    'changes': {'items': list},
    'checklist': {'items': list},
}
ITEM_FIELDS = {
    'notes': ('text',),
    'glossary': ('term', 'meaning'),
    'stats': ('value', 'label'),
    'steps': ('title', 'detail'),
    'cards': ('title', 'body'),
    'changes': ('title', 'built', 'why'),
}
MIN_DIAGRAMS = 2

BANNED_CHARS = {'—': 'long dash', '–': 'en dash', '“': 'curly quote', '”': 'curly quote',
                '‘': 'curly quote', '’': 'curly quote'}
BANNED_WORDS = re.compile(
    r'\b(additionally|crucial|delve|enduring|enhance[sd]?|fostering|garner|interplay|intricate|pivotal|showcas\w*|'
    r'tapestry|testament|underscore[sd]?|vibrant|leverag\w*|utiliz\w*|seamless\w*|serves as|stands as)\b', re.I)


def check_prose(value, where, problems):
    """Flag the writing patterns the unslop skill bans, in every string of the page."""
    if isinstance(value, str):
        for char, name in BANNED_CHARS.items():
            if char in value:
                problems.append(f'{where}: {name} in "{value[:60]}"')
        for match in BANNED_WORDS.finditer(value):
            problems.append(f'{where}: replace "{match.group(0)}" with a plain word')
    elif isinstance(value, list):
        for i, item in enumerate(value):
            check_prose(item, f'{where}[{i}]', problems)
    elif isinstance(value, dict):
        if value.get('type') == 'commits':
            return
        for key, item in value.items():
            if key != 'svg':
                check_prose(item, f'{where}.{key}', problems)


def check_svg(svg, where, problems):
    """Diagrams must scale and follow light and dark mode, so no fixed colours."""
    if not svg.lstrip().startswith('<svg'):
        problems.append(f'{where}: svg must start with <svg')
    if 'viewBox' not in svg:
        problems.append(f'{where}: svg needs a viewBox so it scales')
    if re.search(r'<script|<style|on\w+=', svg, re.I):
        problems.append(f'{where}: svg must not contain scripts, styles or event handlers')
    if re.search(r'(fill|stroke)\s*[:=]\s*"?\s*(#|rgb|hsl)', svg, re.I):
        problems.append(f'{where}: svg uses a fixed colour; use the template classes (box, line, good, bad, hl, muted)')
    rows = set(re.findall(r'<rect\b[^>]*\by="([\d.]+)"', svg))
    if len(re.findall(r'<rect\b', svg)) >= 3 and len(rows) == 1:
        problems.append(f'{where}: all boxes sit in one row, which only repeats the walk-through. '
                        'Show a branch, what is new next to what is unchanged, or what reads or writes what')


def load_diagram(block, base, where, problems):
    svg = block['svg']
    if not svg.lstrip().startswith('<'):
        path = (base / svg).resolve()
        if not path.exists():
            problems.append(f'{where}: diagram file not found: {path}')
            return
        svg = path.read_text()
    svg = re.sub(r'<\?xml[^>]*\?>\s*', '', svg).strip()
    block['svg'] = svg
    check_svg(svg, where, problems)


def git_commits(repo, rev_range):
    """Each commit in the range, oldest first, with its message body and changed files."""
    out = subprocess.check_output(['git', '-C', repo, 'log', '--reverse', '--format=%h%x1f%s%x1f%b%x1e', rev_range], text=True)
    commits = []
    for record in out.split('\x1e'):
        if not record.strip():
            continue
        sha, subject, body = record.strip('\n').split('\x1f')
        stat = subprocess.check_output(['git', '-C', repo, 'show', '--numstat', '--format=', sha], text=True)
        files = []
        for row in stat.splitlines():
            added, removed, path = row.split('\t', 2)
            files.append({'path': path, 'added': int(added) if added != '-' else 0,
                          'removed': int(removed) if removed != '-' else 0})
        paragraphs = [' '.join(p.split()) for p in re.split(r'\n\s*\n', body.strip()) if p.strip()]
        commits.append({'sha': sha, 'subject': subject, 'body': paragraphs, 'files': files})
    return commits


def validate(page, base, args, problems):
    for field in ('id', 'title', 'why', 'sections'):
        if not page.get(field):
            problems.append(f'page: missing "{field}"')
    why = page.get('why', '')
    if why and (not why.rstrip().endswith('.') or re.search(r'[.!?]\s+[A-Z]', why.rstrip()[:-1])):
        problems.append('page.why: must be exactly one sentence')
    ids, diagrams = set(), 0
    for si, section in enumerate(page.get('sections', [])):
        where = f'sections[{si}]'
        if not section.get('id') or not section.get('title'):
            problems.append(f'{where}: needs "id" and "title"')
        if section.get('id') in ids:
            problems.append(f'{where}: duplicate id "{section.get("id")}"')
        ids.add(section.get('id'))
        if not section.get('blocks'):
            problems.append(f'{where}: has no blocks')
        for bi, block in enumerate(section.get('blocks', [])):
            bwhere = f'{where}.blocks[{bi}]'
            kind = block.get('type')
            if kind not in BLOCKS:
                problems.append(f'{bwhere}: unknown type "{kind}". Use one of {", ".join(BLOCKS)}')
                continue
            for field, ftype in BLOCKS[kind].items():
                if not isinstance(block.get(field), ftype) or not block.get(field):
                    problems.append(f'{bwhere}: {kind} needs a non-empty "{field}"')
            for ii, item in enumerate(block.get('items') or block.get('steps') or []):
                for field in ITEM_FIELDS.get(kind, ()):
                    if not item.get(field):
                        problems.append(f'{bwhere}.items[{ii}]: {kind} item needs "{field}"')
            if kind == 'diagram' and isinstance(block.get('svg'), str):
                diagrams += 1
                load_diagram(block, base, bwhere, problems)
            if kind == 'table':
                for ri, row in enumerate(block.get('rows', [])):
                    if len(row) != len(block.get('columns', [])):
                        problems.append(f'{bwhere}.rows[{ri}]: has {len(row)} cells for {len(block["columns"])} columns')
            if kind == 'steps':
                modes = [m.get('id') for m in block.get('modes', [])]
                for st in block.get('steps', []):
                    for m in st.get('skipIn', []):
                        if m not in modes:
                            problems.append(f'{bwhere}: step skips unknown mode "{m}"')
                for m in modes:
                    if all(m in st.get('skipIn', []) for st in block.get('steps', [])):
                        problems.append(f'{bwhere}: mode "{m}" skips every step')
            if kind == 'commits':
                if args.range:
                    block['items'] = git_commits(args.repo, args.range)
                if not block.get('items'):
                    problems.append(f'{bwhere}: no commits. Pass --repo and --range BASE..HEAD')
    if diagrams < MIN_DIAGRAMS:
        problems.append(f'page: has {diagrams} diagrams, needs at least {MIN_DIAGRAMS}')
    check_prose(page, 'page', problems)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', help='page.json, or a page this script built before')
    parser.add_argument('-o', '--output')
    parser.add_argument('--dump', help='write the page data to this JSON file and stop')
    parser.add_argument('--repo', default='.', help='git checkout for the commits block')
    parser.add_argument('--range', help='commit range for the commits block, such as origin/main..HEAD')
    args = parser.parse_args()

    source = Path(args.input)
    text = source.read_text()
    if source.suffix == '.html':
        match = PAGE_TAG.search(text)
        if not match:
            sys.exit(f'{source} has no embedded page data')
        page = json.loads(match.group(1).replace('<\\/', '</'))
    else:
        page = json.loads(text)
    if args.dump:
        Path(args.dump).write_text(json.dumps(page, ensure_ascii=False, indent=2) + '\n')
        print(f'wrote {args.dump}. Diagrams are inline in it.')
        return
    if not args.output:
        parser.error('-o/--output is required')

    problems = []
    validate(page, source.parent, args, problems)
    if problems:
        print(f'{len(problems)} problem(s), nothing written:', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        sys.exit(1)

    data = json.dumps(page, ensure_ascii=False).replace('</', '<\\/')
    title = re.sub(r'[*`]', '', page['title']).replace('&', '&amp;').replace('<', '&lt;')
    html = TEMPLATE.read_text().replace('{{TITLE}}', title).replace('{{PAGE_JSON}}', data)
    Path(args.output).write_text(html)
    blocks = [b['type'] for s in page['sections'] for b in s['blocks']]
    commits = sum(len(b.get('items', [])) for s in page['sections'] for b in s['blocks'] if b['type'] == 'commits')
    print(f'wrote {args.output}: {len(page["sections"])} sections, {blocks.count("diagram")} diagrams, '
          f'{commits} commits, {len(html) // 1024} KB')


if __name__ == '__main__':
    main()
