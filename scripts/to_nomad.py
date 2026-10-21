"""Turn the data sheets of a volume into NOMAD entries of the hackathon schema (schema/schema.archive.yaml).

Usage: uv run python scripts/to_nomad.py SDS-60 boxes.jsonl out_dir [--zip]

One EquilibriumSolution entry per table row of a compilation sheet: temperature
and pressure from the t/°C, T/K and P columns, one Phase per printed component
with its CAS number, name and formula, and the mass or mole fraction of that
component when a `100 w_i` or `10^n x_i` column is printed (prefactor removed).
Columns the schema has no quantity for (Bunsen, Ostwald, Henry, concentrations,
mass ratios) are kept verbatim in `description`, together with the provenance
(volume, page, sheet, raw row, citation, witness), until the schema grows.
Entries are validated with schema/pydantic.py before writing. Output layout:
out_dir/schema.archive.yaml, out_dir/SDS-60/p041-0/r03.archive.json.
"""
import argparse, json, pathlib, re, shutil, sys, zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schema.pydantic import EquilibriumSolution, Phase, PubChemPureSubstanceSection, PublicationReference  # noqa: E402
sys.path.insert(0, str(ROOT / 'scripts'))
from paths import volume_root  # noqa: E402
from textnorm import loose, strict  # noqa: E402

M_DEF = '../upload/raw/schema.archive.yaml#/definitions/section_definitions/EquilibriumSolution'
VAL = re.compile(r'^\s*[<>~≈]?\s*(?P<v>[+-]?\d+(?:[.,]\d+)?)(?:\s*(?:±|\\pm)\s*(?P<e>\d+(?:\.\d+)?))?'
                 r'(?:\s*(?:×|\\times|x)\s*10\^?\{?(?P<x>-?\d+)\}?)?\s*(?:\(\d+\))?\s*[a-z]?\s*$')
PRESSURE_UNITS = {'atm': 101325.0, 'kpa': 1000.0, 'pa': 1.0, 'bar': 1e5, 'mmhg': 133.322, 'torr': 133.322, 'mpa': 1e6}


def tex(s: str) -> str:
    """Strip the LaTeX MinerU puts around symbols: braces, backslash-space, \\circ."""
    s = s.replace('\\ ', ' ').replace('^{\\circ}', '°').replace('^\\circ', '°').replace('\\circ', '°')
    return re.sub(r'[{}$]', '', s).strip()


def value(cell: str):
    m = VAL.match(cell.strip())
    if not m:
        return None
    v = float(m.group('v').replace(',', '.'))
    if m.group('x'):
        v *= 10 ** int(m.group('x'))
    return v


def column(head: str) -> dict:
    """Classify a header cell: kind, component index, prefactor, unit."""
    h = tex(head)
    h = re.sub(r'\(compilers?\)', '', h).strip()
    col = {'raw': head.strip(), 'kind': 'other', 'i': None, 'pre': 1.0, 'unit': None}
    m = re.match(r'^(?:(?P<pre>\d+(?:\^-?\d+)?|10\^-?\d+)\s+)?(?P<body>.*)$', h)
    pre, body = m.group('pre'), m.group('body')
    if pre:
        col['pre'] = float(pre.split('^')[0]) ** int(pre.split('^')[1]) if '^' in pre else float(pre)
    sub = re.search(r'^(?P<sym>[wxgc])_?(?P<i>[12Il])\b(?P<rest>.*)$', body)
    if re.match(r'^t\s*/\s*°?\s*C', body, re.I) or body.lower().startswith('t/°c'):
        col['kind'] = 'temperature_C'
    elif re.match(r'^T\s*/\s*K', body):
        col['kind'] = 'temperature_K'
    elif re.match(r'^[pP]\s*/\s*(?P<u>[A-Za-z]+)', body):
        u = re.match(r'^[pP]\s*/\s*(?P<u>[A-Za-z]+)', body).group('u').lower()
        if u in PRESSURE_UNITS:
            col['kind'], col['unit'] = 'pressure', u
    elif sub and sub.group('sym') in 'wx' and not sub.group('rest').strip():
        col['kind'] = 'mass_fraction' if sub.group('sym') == 'w' else 'molar_fraction'
        col['i'] = 1 if sub.group('i') in '1Il' else 2
    return col


def parse_components(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r'\((\d)\)\s*(.*?)(?=\(\d\)\s|$)', text, re.S):
        parts = [p.strip() for p in m.group(2).split(';')]
        name = parts[0] if parts else ''
        formula = tex(parts[1]) if len(parts) > 1 else None
        cas = re.search(r'\[(\d{2,7}-\d{2}-\d)\]', m.group(2))
        formula = re.sub(r'[_\s]', '', formula) if formula else None
        out.append({'i': int(m.group(1)), 'name': re.sub(r'\s+', ' ', name), 'formula': formula or None, 'cas': cas.group(1) if cas else None})
    return out


YEAR = re.compile(r'\b(1[89]\d\d|20\d\d)\b')


def layer_citations(vol: str) -> dict[int, list[str]]:
    """Citation boxes of the text layer per page; they keep the printed line breaks."""
    f = volume_root(vol) / 'boxes' / f'{vol}.jsonl'
    out = {}
    if f.exists():
        for r in map(json.loads, f.open()):
            out.setdefault(r['page'], []).append(r['boxes'].get('original_measurements', ''))
    return out


def parse_citation(text: str, layer: list[str]) -> PublicationReference:
    """Authors, journal and year of a citation string.

    MinerU returns the citation as one line, so the last initial glues to the
    journal ("Rex, A.Z. Phys. Chem."). The text layer prints authors and journal
    on separate lines: the leading lines shaped like "Surname, I." are the authors,
    the first other line starts the journal. That split is transferred to the clean string by
    matching the loose-normalised author text; without a matching layer box the
    split falls back to a regex over "Surname, I. N." groups.
    """
    s = re.sub(r'\s+', ' ', text).strip()
    year = YEAR.search(s)
    cut = None
    def toks(t): return set(re.findall(r'[a-z]{3,}', loose(t) if False else t.lower()))
    best = max(((len(toks(s) & toks(strict(l))), l) for l in layer), default=(0, ''))
    if best[0] >= 2:
        lines = [strict(l) for l in best[1].split('\n') if l.strip()]
        AUTHOR_LINE = re.compile(r"^\s*(?:[A-Z][A-Za-z'\-]+ )*[A-Z][A-Za-z'\-]+\s*,\s*[A-Z]")
        k = next((i for i, l in enumerate(lines) if not AUTHOR_LINE.match(l)), None)   # first non-author line = journal
        if k:
            target = loose(' '.join(lines[:k]))
            acc = ''
            for i, ch in enumerate(s):
                acc += loose(ch)
                if len(acc) >= len(target):
                    cut = i + 1
                    break
            if cut is not None:                                    # land on an initial or author boundary
                m = re.compile(r'[.;]\s*').match(s, cut)
                if m:
                    cut = m.end()
                elif not re.search(r'[.;]\s*$', s[:cut]):
                    cut = None
    if cut is None:
        groups = list(re.finditer(r"[A-Z][A-Za-z'\-]+(?: [A-Z][A-Za-z'\-]+)*, (?:[A-Z]\.\s?)+", s))
        cut = groups[-1].end() if groups else 0
    authors = [x.strip(' ;.') for x in s[:cut].split(';') if x.strip(' ;.')]
    authors = [a + '.' if re.search(r'[A-Z]$', a) else a for a in authors]
    journal = s[cut:year.start()].strip(' ,;') if year else s[cut:].strip(' ,;')
    return PublicationReference(publication_authors=authors, journal=journal or None,
                                publication_date=datetime(int(year.group(1)), 1, 1, tzinfo=timezone.utc) if year else None)


def split_table(lines: list[str]):
    """Header cells and data rows of a crop table; two-block tables are unfolded."""
    rows = [[re.sub(r'^\s*EXPERIMENTAL VALUES:?\s*(\(continued\))?\s*', '', c.strip()) for c in l.split(' | ')] for l in lines if l.strip()]
    heads, data = [], []
    for cs in rows:
        if sum(1 for c in cs if VAL.match(c)) >= max(1, (len(cs) + 1) // 2):
            data.append(cs)
        elif not data and len(cs) > 1:
            heads.append(cs)
    if not heads:
        return [], data
    width = max((len(r) for r in data), default=0)
    head = next((h for h in reversed(heads) if len(h) == width), max(heads, key=len))
    if len(heads) > 1 and len(heads[-1]) == width and len(heads[-2]) == width:   # two-line header
        head = [(a + ' ' + b).strip() for a, b in zip(heads[-2], heads[-1])]
    n = len(head)
    if n and n % 2 == 0 and head[:n // 2] == head[n // 2:]:        # same columns printed twice side by side
        head = head[:n // 2]
        data = [r[:n // 2] for r in data] + [r[n // 2:] for r in data if len(r) > n // 2]
    return head, data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume'); ap.add_argument('boxes', type=pathlib.Path); ap.add_argument('out', type=pathlib.Path)
    ap.add_argument('--zip', action='store_true')
    a = ap.parse_args()
    vol = a.volume if a.volume.startswith('SDS-') else f'SDS-{a.volume}'
    records = [json.loads(l) for l in a.boxes.open()]
    out = a.out; (out).mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / 'schema' / 'schema.archive.yaml', out / 'schema.archive.yaml')
    stats = {'sheets': 0, 'rows': 0, 'entries': 0, 'no_components': 0, 'no_header': 0, 'no_temperature': 0, 'unmapped_columns': {}}
    layer = layer_citations(vol)
    for r in records:
        if r['kind'] != 'compilation':
            continue
        stats['sheets'] += 1
        comps = parse_components(r['boxes'].get('components', ''))
        if not any(c['cas'] for c in comps):                      # index pages, evaluation fragments
            stats['no_components'] += 1
            continue
        head, data = split_table(r['boxes'].get('experimental_values', '').split('\n'))
        if not head:
            stats['no_header'] += 1
            continue
        cols = [column(h) for h in head]
        for c in cols:
            if c['kind'] == 'other':
                stats['unmapped_columns'][c['raw'][:40]] = stats['unmapped_columns'].get(c['raw'][:40], 0) + 1
        ref = parse_citation(r['boxes'].get('original_measurements', ''), layer.get(r['page'], []))
        method = re.sub(r'\s+', ' ', r['boxes'].get('method', '')).strip()
        for ri, row in enumerate(data):
            stats['rows'] += 1
            vals = [value(c) for c in row]
            e = EquilibriumSolution(m_def=M_DEF, lab_id=f"{vol}/p{r['page']:03d}/{r['index_on_page']}/r{ri:02d}",
                                    measurement_methods=[method] if method else [], publication_references=[ref])
            extra = []
            phases = {c['i']: Phase(name=c['name'], substance=PubChemPureSubstanceSection(name=c['name'], molecular_formula=c['formula'], cas_number=c['cas'])) for c in comps}
            for col, cell, v in zip(cols, row, vals):
                if v is None:
                    continue
                if col['kind'] == 'temperature_C':
                    e.temperature = v + 273.15
                elif col['kind'] == 'temperature_K':
                    e.temperature = v
                elif col['kind'] == 'pressure':
                    e.pressure = v * PRESSURE_UNITS[col['unit']]
                elif col['kind'] in ('mass_fraction', 'molar_fraction') and col['i'] in phases:
                    setattr(phases[col['i']], col['kind'], v / col['pre'])
                else:
                    extra.append(f"{tex(col['raw'])} = {cell.strip()}")
            if e.temperature is None:
                stats['no_temperature'] += 1
            e.phases = [phases[k] for k in sorted(phases)]
            e.name = f"{vol} p{r['page']} sheet {r['index_on_page']} row {ri}: " + ' / '.join(c['name'] for c in comps)
            e.description = '\n'.join([f"source: IUPAC Solubility Data Series volume {vol[4:]}, page {r['page']}, sheet {r['index_on_page']}, table row {ri}",
                                       f"witness: MinerU 2.5-Pro crop pass; columns: {' | '.join(tex(h) for h in head)}",
                                       f"row: {' | '.join(row)}", f"citation: {r['boxes'].get('original_measurements', '').strip()}"]
                                      + ([f"unmapped: {'; '.join(extra)}"] if extra else []))
            d = out / vol / f"p{r['page']:03d}-{r['index_on_page']}"; d.mkdir(parents=True, exist_ok=True)
            (d / f'r{ri:02d}.archive.json').write_text(json.dumps({'data': e.model_dump(mode='json', exclude_none=True)}, ensure_ascii=False, indent=1))
            stats['entries'] += 1
    stats['unmapped_columns'] = dict(sorted(stats['unmapped_columns'].items(), key=lambda kv: -kv[1])[:12])
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    if a.zip:
        z = out.with_suffix('.zip')
        with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(out.rglob('*')):
                if f.is_file():
                    zf.write(f, f.relative_to(out))
        print(f'-> {z} ({z.stat().st_size // 1024} kB)')


main()
