"""Build deck/FruitFly_Progress.pptx from what the project has logged so far.

    python deck/build.py            (or: python -m flight_simulator.media deck)

Inputs (nothing here is typed by hand except deck/content.json):
  - sim-logs branch runs/: FlightGear sessions, controller runs, their notes
    (feedback.md), airplane.csv, and media/ (screenshots + annotations)
  - main branch git history: who/which agent committed what, and when
  - repo images: cockpit/*/ hotspot captures
  - deck/content.json: the story text (title, rule, architecture, next steps)

Outputs: deck/build/ (manifest.json, rendered annotated images, GIF time-lapses;
git-ignored) and deck/FruitFly_Progress.pptx (via deck/build_deck.js).
"""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from flight_simulator import runlog                     # noqa: E402
from flight_simulator.media import MediaDir, render, timelapse   # noqa: E402

DECK = ROOT / 'deck'
BUILD = DECK / 'build'
OUT = DECK / 'FruitFly_Progress.pptx'
MAX_SESSION_SLIDES = 12


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def notes_from_feedback(path):
    """'- **Who** (time): text' lines under ## Notes."""
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError:
        return []
    out = []
    for m in re.finditer(r'^- \*\*(.+?)\*\* \(([^)]*)\): (.+)$', text, re.M):
        out.append({'who': m.group(1), 'when': m.group(2), 'text': m.group(3).strip()})
    return out


def last_error(run_dir):
    for name in ('console.log', 'events.log'):
        p = run_dir / name
        if p.exists():
            lines = [l for l in p.read_text(encoding='utf-8', errors='replace').splitlines()
                     if re.search(r'\bError\b|Traceback|STOP:', l)]
            if lines:
                return re.sub(r'^\d\d:\d\d:\d\d \[[^]]+\] ', '', lines[-1]).strip()[:200]
    return ''


def series(run_dir, points=80):
    p = run_dir / 'airplane.csv'
    if not p.exists():
        return None
    rows = list(csv.DictReader(p.open(encoding='utf-8')))
    if len(rows) < 3:
        return None
    step = max(1, len(rows) // points)
    rows = rows[::step]
    t0 = datetime.fromisoformat(rows[0]['wall_utc'])

    def num(r, k):
        try:
            v = round(float(r[k]), 1)
        except (KeyError, TypeError, ValueError):
            return None
        # FlightGear reports junk (e.g. -12000 ft) for a few samples while it initialises
        return None if (k == 'alt_ft' and v < -500) or (k == 'ias_kt' and v < 0) else v
    return {'t_s': [round((datetime.fromisoformat(r['wall_utc']) - t0).total_seconds()) for r in rows],
            'alt_ft': [num(r, 'alt_ft') for r in rows], 'ias_kt': [num(r, 'ias_kt') for r in rows]}


def started(run_id):
    m = re.match(r'(\d{4}-\d\d-\d\dT\d{6}Z)', run_id)
    return datetime.strptime(m.group(1), '%Y-%m-%dT%H%M%SZ').replace(tzinfo=timezone.utc) if m else None


def media_for(run_dir, title, tag):
    """Render annotated stills + a time-lapse for one run; returns manifest entries."""
    m = MediaDir(run_dir)
    imgs = m.images()
    if not imgs:
        return {}
    outdir = BUILD / 'media' / tag
    outdir.mkdir(parents=True, exist_ok=True)
    rendered = []
    for r in imgs:
        out = outdir / f"{Path(r['file']).stem}.jpg"
        render(m.dir / r['file'], r, title).save(out, quality=88)
        rendered.append({'path': str(out), 'kind': r['kind'], 'caption': r.get('caption', ''),
                         'telemetry': r.get('telemetry') or {},
                         'utc': r['utc'], 'annotated': bool(r.get('notes') or r.get('boxes')),
                         'w': r['w'], 'h': r['h']})
    fg = [r for r in imgs if r['kind'] == 'fg']
    gif = None
    if len(fg) >= 4:
        gif = timelapse([(m.dir / r['file'], r, title) for r in fg], outdir / 'timelapse.gif')
    # hero: a human-annotated FlightGear frame, else an event frame, else the middle frame
    pick = ([r for r in rendered if r['kind'] == 'fg' and r['annotated']]
            or [r for r in rendered if r['kind'] == 'fg' and r['caption']]
            or [r for r in rendered if r['kind'] == 'fg'] or rendered)
    hero = pick[len(pick) // 2] if not pick[0]['annotated'] else pick[-1]
    return {'images': rendered, 'hero': hero, 'gif': str(gif) if gif else None,
            'pages': [r for r in rendered if r['kind'] == 'page'],
            'agents': [r for r in rendered if r['kind'] in ('agent', 'screen')]}


def collect_runs():
    base = runlog.ensure_worktree()
    subprocess.run(['git', 'pull', '-q', '--ff-only'], cwd=base, capture_output=True, timeout=60)
    sessions, runs, loose = [], [], []
    for d in sorted((base / runlog.RUNS).iterdir()):
        if not d.is_dir():
            continue
        meta, result = read_json(d / 'meta.json'), read_json(d / 'result.json')
        when = started(d.name)
        entry = {'id': d.name, 'utc': when.isoformat() if when else None,
                 'who': meta.get('who') or d.name.split('_')[1].replace('-', ' ').title(),
                 'notes': notes_from_feedback(d / 'feedback.md')}
        if d.name.endswith('_media'):
            entry.update(media_for(d, 'Project media', d.name))
            loose.append(entry)
        elif meta.get('kind') == 'flightgear-session':
            title = meta.get('name') or 'UNNAMED session'
            fg = meta.get('flightgear') or {}
            code = meta.get('fgfs_exit_code')
            entry.update({'name': title, 'aircraft': meta.get('aircraft') or fg.get('aircraft'),
                          'duration_s': meta.get('duration_s'), 'exit_code': code,
                          'outcome': 'closed normally' if code in (0, None) else 'crashed / force-closed',
                          'samples': meta.get('airplane_samples'), 'series': series(d),
                          'controller_runs': list((meta.get('controller_runs') or {}).keys())})
            entry.update(media_for(d, title, d.name))
            sessions.append(entry)
        else:
            args = meta.get('args') or {}
            entry.update({'backend': args.get('backend') or result.get('backend'),
                          'brain': args.get('brain') or result.get('brain'),
                          'command': meta.get('command'), 'exit_code': result.get('exit_code', meta.get('exit_code')),
                          'collision': result.get('collision'),
                          'min_clearance_m': result.get('minimum_clearance_m'),
                          'activations': result.get('avoidance_activations'),
                          'elapsed_s': result.get('elapsed_s'), 'error': last_error(d)})
            entry.update(media_for(d, f"{entry['backend']}/{entry['brain']}", d.name))
            runs.append(entry)
    return sessions, runs, loose


def collect_git():
    fmt = '%x1e%H%x1f%an%x1f%aI%x1f%s%x1f%b'
    out = subprocess.run(['git', 'log', '--no-merges', f'--format={fmt}'], cwd=ROOT,
                         capture_output=True, text=True, encoding='utf-8').stdout
    commits = []
    for rec in out.split('\x1e')[1:]:
        h, an, date, subj, body = (rec.split('\x1f') + [''] * 5)[:5]
        claude = bool(re.search(r'Co-Authored-By: Claude', body, re.I))
        commits.append({'hash': h[:7], 'author': an, 'utc': date.strip(), 'subject': subj, 'claude': claude})
    commits.reverse()
    return commits


def tickets():
    try:
        out = subprocess.run([sys.executable, str(ROOT / 'tickets.py'), 'list', '--all'], cwd=ROOT,
                             capture_output=True, text=True, timeout=20).stdout
        if not out.strip():
            out = subprocess.run([sys.executable, str(ROOT / 'tickets.py'), 'list'], cwd=ROOT,
                                 capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        m = re.match(r'#(\d+)\s+(\w+)\s+(?:(\S+) \([^)]*\)\s+)?(.+?)(?:\s+\[.*\])?$', line)
        if m:
            rows.append({'id': int(m.group(1)), 'state': m.group(2), 'agent': m.group(3), 'task': m.group(4)})
    return rows


def repo_images():
    out = []
    for p in sorted(ROOT.glob('cockpit/*/hotspots.json')):
        info = read_json(p)
        views = info.get('views') or []
        if not views:
            continue
        v = views[0]
        img = p.parent / (v.get('boxes_image') or v.get('hotspot_image'))
        if img.exists():
            out.append({'kind': 'cockpit', 'aircraft': info.get('aircraft'), 'path': str(img),
                        'count': sum(len(x.get('hotspots', [])) for x in views),
                        'clean': str(p.parent / v['image']) if v.get('image') else None})
    return out


def main():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    sessions, runs, loose = collect_runs()
    commits = collect_git()
    content = read_json(DECK / 'content.json')
    sessions_with_media = [s for s in sessions if s.get('hero')]
    manifest = {
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'commit': subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True,
                                 text=True).stdout.strip(),
        'content': content,
        'sessions': sessions[-MAX_SESSION_SLIDES:],
        'all_sessions': len(sessions),
        'runs': runs,
        'loose_media': loose,
        'commits': commits,
        'tickets': tickets(),
        'repo_images': repo_images(),
        'people': sorted({c['author'] for c in commits} | {s['who'] for s in sessions + runs}),
        'hero': (sessions_with_media[-1]['hero']['path'] if sessions_with_media else
                 (repo_images()[0]['clean'] if repo_images() else None)),
    }
    (BUILD / 'manifest.json').write_text(json.dumps(manifest, indent=1, default=str), encoding='utf-8')
    print(f"manifest: {len(sessions)} sessions ({len(sessions_with_media)} with media), {len(runs)} runs, "
          f"{len(commits)} commits")
    node_modules = DECK / 'node_modules' / 'pptxgenjs'
    if not node_modules.exists():
        subprocess.run('npm install --no-audit --no-fund --silent', cwd=DECK, shell=True, check=True)
    subprocess.run(['node', str(DECK / 'build_deck.js'), str(BUILD / 'manifest.json'), str(OUT)],
                   cwd=DECK, check=True)
    print(OUT)


if __name__ == '__main__':
    main()
