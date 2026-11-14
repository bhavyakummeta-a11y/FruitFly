"""Neuron positions for the live brain window (session.py /api/brain_map).

Frontal projection of every model neuron (FlyWire pos_x / pos_y from annotations.tsv),
indexed exactly like ConnectomeBrain (Completeness_783.csv row order), so the
spike indices in fly_spikes.jsonl land on the right neuron. Built once and cached
in data/brain/derived/brain_map.json (data/ is git-ignored).
"""
import json
from pathlib import Path

from .brain import INPUTS, READOUTS

GRID = 1000                 # x quantized to 0..GRID, y to the matching aspect
VERSION = 1


def _group(labels, rows, spec):
    column, values, side = spec
    if column == 'root_id':
        return sorted({rows[int(v)] for v in values if int(v) in rows})
    col = labels[column].astype(str)
    mask = col.isin([v for v in values if not v.endswith('*')])
    for v in values:
        if v.endswith('*'):
            mask |= col.str.startswith(v[:-1])
    if side:
        mask &= labels['side'] == side
    return sorted({rows[int(r)] for r in labels.loc[mask, 'root_id'] if int(r) in rows})


def build(directory):
    import pandas as pd
    directory = Path(directory)
    neurons = pd.read_csv(directory / 'Completeness_783.csv', index_col=0)
    labels = pd.read_csv(directory / 'annotations.tsv', sep='\t', low_memory=False,
                         usecols=['root_id', 'pos_x', 'pos_y', 'super_class', 'cell_type',
                                  'cell_sub_class', 'side'])
    rows = {int(root): i for i, root in enumerate(neurons.index)}
    pos = labels.drop_duplicates('root_id').set_index('root_id').reindex(neurons.index)
    x0, x1 = pos.pos_x.min(), pos.pos_x.max()
    y0, y1 = pos.pos_y.min(), pos.pos_y.max()
    scale = GRID / (x1 - x0)
    height = int(round((y1 - y0) * scale))
    xs = ((pos.pos_x - x0) * scale).round().fillna(-1).astype(int).tolist()
    ys = ((pos.pos_y - y0) * scale).round().fillna(-1).astype(int).tolist()
    classes = sorted(pos.super_class.dropna().unique().tolist())
    code = {c: i for i, c in enumerate(classes)}
    cls = [code.get(c, -1) for c in pos.super_class.where(pos.super_class.notna(), None)]
    groups = {}
    for kind, specs in (('input', INPUTS), ('readout', READOUTS)):
        for name, spec in specs.items():
            idx = _group(labels, rows, spec)
            if idx:
                groups[name] = {'kind': kind, 'idx': idx}
    return {'version': VERSION, 'n': len(neurons), 'width': GRID, 'height': height,
            'x': xs, 'y': ys, 'cls': cls, 'classes': classes, 'groups': groups,
            'source': 'FlyWire annotations.tsv pos_x/pos_y (frontal view)'}


def load(directory):
    """Cached map as JSON text, or None if the connectome data isn't downloaded."""
    directory = Path(directory)
    if not (directory / 'annotations.tsv').is_file() or not (directory / 'Completeness_783.csv').is_file():
        return None
    cache = directory / 'derived' / 'brain_map.json'
    if cache.exists():
        text = cache.read_text(encoding='utf-8')
        if f'"version":{VERSION}' in text[:40] or f'"version": {VERSION}' in text[:40]:
            return text
    text = json.dumps(build(directory), separators=(',', ':'))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding='utf-8')
    return text
