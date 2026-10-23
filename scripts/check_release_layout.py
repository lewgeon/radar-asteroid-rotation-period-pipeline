"""Check documentation links and archive the candidate working trees in isolation.

No staging, commits, cleanup, or writes to the source repositories' Git metadata.
The archive check includes tracked and non-ignored untracked files, so it can
validate a release candidate before its first commit. Run in the pytorch env.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = ('.', 'echo', 'inversion', 'observation')
ONLINE_SOURCE = ('https://github.com/lewgeon/'
                 'radar-asteroid-rotation-period-pipeline/')


def git(repo, *args):
    return subprocess.check_output(
        ['git', '-C', str(repo), '-c', f'safe.directory={repo.as_posix()}',
         '-c', 'core.excludesFile=', *args], stderr=subprocess.PIPE)


def candidate_files(repo):
    names = git(repo, 'ls-files', '-z', '--cached', '--others',
                '--exclude-standard').decode('utf-8').split('\0')
    return sorted({name for name in names if name and (repo / name).is_file()})


def markdown_body(text):
    lines = []
    fence = None
    in_math = False
    for line in text.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if fence is None:
                fence = marker.group(1)[0]
            elif fence == marker.group(1)[0]:
                fence = None
            continue
        if fence is None:
            if line.strip() == '$$':
                in_math = not in_math
                continue
            if not in_math:
                lines.append(re.sub(r'\$[^$\n]+\$', '', line))
    return '\n'.join(lines)


def anchors(text):
    found = set(re.findall(r'<a\s+[^>]*id=["\']([^"\']+)', text))
    counts = {}
    for line in markdown_body(text).splitlines():
        heading = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if not heading:
            continue
        label = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', heading.group(1))
        label = re.sub(r'<[^>]+>', '', label).lower()
        slug = re.sub(r'[^\w\-\s]', '', label, flags=re.UNICODE).replace(' ', '-')
        occurrence = counts.get(slug, 0)
        counts[slug] = occurrence + 1
        found.add(slug if occurrence == 0 else f'{slug}-{occurrence}')
    return found


def resolve_target(source, target):
    if target.startswith(ONLINE_SOURCE):
        suffix = target[len(ONLINE_SOURCE):]
        match = re.match(r'(?:blob|tree)/chirp-pulse/(.+)', suffix)
        if match:
            relative, _, fragment = match.group(1).partition('#')
            return ROOT / unquote(relative), unquote(fragment)
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target):
        return None
    relative, _, fragment = unquote(target).partition('#')
    path = (source.parent / relative).resolve() if relative else source
    return path, fragment


def check_links():
    files = [ROOT / name for name in ('README.md', 'README_EN.md', 'EXPERIMENTS.md')]
    files += sorted((ROOT / 'docs/4.3').rglob('*.md'))
    files += sorted((ROOT / 'docs/4.4').rglob('*.md'))
    files += [ROOT / repo / name for repo in REPOSITORIES[1:]
              for name in ('README.md', 'README_EN.md')]
    for repo in REPOSITORIES[1:]:
        files += sorted((ROOT / repo / 'docs').rglob('*.md'))
    issues = []
    checked = 0
    cache = {}
    for source in files:
        if not source.exists():
            continue
        text = markdown_body(source.read_text(encoding='utf-8'))
        for target in re.findall(r'!?\[[^\]\n]*\]\(([^\s)]+)\)', text):
            resolved = resolve_target(source, target)
            if resolved is None:
                continue
            checked += 1
            path, fragment = resolved
            if not path.exists():
                issues.append(f'{source.relative_to(ROOT)}: missing {target}')
            elif fragment and path.suffix.lower() == '.md':
                if path not in cache:
                    cache[path] = anchors(path.read_text(encoding='utf-8'))
                if fragment not in cache[path]:
                    issues.append(f'{source.relative_to(ROOT)}: missing anchor {target}')
    return dict(files=len(files), links=checked, issues=issues)


def archive_candidate(repo, output, label):
    stage = output / label
    stage.mkdir()
    names = candidate_files(repo)
    for name in names:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / name, target)
    git(stage, 'init', '-q')
    git(stage, 'add', '--all', '--force')
    tree = git(stage, 'write-tree').decode().strip()
    archive = output / f'{label}.zip'
    git(stage, 'archive', '--format=zip', f'--output={archive}', tree)
    with zipfile.ZipFile(archive) as stream:
        entries = {name for name in stream.namelist() if not name.endswith('/')}
    assert not any(name.startswith('tests/') for name in entries), label
    if label == 'root':
        assert not any(name.startswith('scripts/') for name in entries)
        assert 'pytest.ini' not in entries
        for required in ('pipeline.py', 'pyside_gui.py',
                         'configs/chirp_point_target_test.json',
                         'docs/4.3/PROJECT_OVERVIEW.md', 'docs/4.4/README.md',
                         'docs/4.3/images/matched_filter_peak_at_leading_edge.svg',
                         'docs/4.3/vs_4.2/experiments/figures/2026-10-16_EV5_400M/period_error_vs_snr.png'):
            assert required in entries, required
        assert 'configs/chirp_mesh_target_test.json' not in entries
        assert not any(name.startswith('docs/4.3/images/range_features_') for name in entries)
        assert not any(name.startswith('docs/4.4/vs_4.3/') for name in entries)
        assert not any(name.startswith('assets/ev5_snr_20261016/') for name in entries)
    elif label == 'inversion':
        assert 'scripts/estimate_period.py' in entries
        assert 'src/inversion.py' in entries
        for name in ('bounded_features.py', 'bounded_period.py', 'gaussian_period.py'):
            assert f'src/{name}' not in entries, name
    elif label == 'echo':
        assert 'simulate_echo.py' in entries
    else:
        assert 'solve_observation_info.py' in entries
    return dict(candidate_files=len(names), archived_files=sum(not name.endswith('/') for name in entries),
                entries=sorted(entries))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives-dir', type=Path, help='new output folder, normally under tmp/')
    args = parser.parse_args()
    result = dict(documentation=check_links())
    if args.archives_dir is not None:
        output = args.archives_dir.resolve()
        output.mkdir(parents=True, exist_ok=False)
        result['archives'] = {}
        for name in REPOSITORIES:
            label = 'root' if name == '.' else name
            result['archives'][label] = archive_candidate(ROOT / name, output, label)
        root_entries = set(result['archives']['root']['entries'])
        combined_entries = set(root_entries)
        for repo in REPOSITORIES[1:]:
            combined_entries.update(f'{repo}/{entry}' for entry in result['archives'][repo]['entries'])
        for entry in sorted(combined_entries):
            if not entry.endswith('.md') or not (entry in ('README.md', 'README_EN.md', 'EXPERIMENTS.md')
                    or entry.startswith(('docs/4.3/', 'docs/4.4/', 'echo/', 'inversion/', 'observation/'))):
                continue
            text = markdown_body((ROOT / entry).read_text(encoding='utf-8'))
            for target in re.findall(r'!?\[[^\]\n]*\]\(([^\s)]+)\)', text):
                if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', target):
                    continue
                path, _ = resolve_target(ROOT / entry, target)
                relative = path.relative_to(ROOT).as_posix()
                if path.is_dir():
                    assert any(n.startswith(relative.rstrip('/') + '/') for n in combined_entries), (entry, target)
                else:
                    assert relative in combined_entries, (entry, target)
        (output / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        result['archives'] = {k: {n: v for n, v in row.items() if n != 'entries'}
                              for k, row in result['archives'].items()}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['documentation']['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
