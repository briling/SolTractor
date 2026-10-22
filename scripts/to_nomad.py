"""Turn the data sheets of a volume into NOMAD entries of the hackathon schema (schema/schema.archive.yaml).

Usage: uv run python scripts/to_nomad.py SDS-60 boxes.jsonl out_dir [--zip]

One EquilibriumSolution entry per table row of a compilation sheet: temperature
and pressure from the t/°C, T/K and P columns, and one Phase (the saturated
solution of the row) whose components are the printed components with CAS
number, name and formula. A component's Amount is, in this order of preference,
its mole fraction, mass fraction (100 w_i, g per 100 g solution, mg/kg solution),
molality (mol/kg) or molarity (mol/L), prefactors and units resolved by
`sdstable.column`; the schema holds one Amount per component, so the other
printed quantities (a second fraction, Bunsen, Ostwald, Henry, mass ratios)
are kept verbatim in `description`, together with the provenance (volume, page,
sheet, raw row, citation, witness), until the schema grows. Rows whose blank
leading conditions mean "as above" are filled from the row above; rows that are
still shorter than the header are skipped (`shifted_rows`).
Entries are validated with schema/pydantic.py before writing. Output layout:
out_dir/schema.archive.yaml, out_dir/SDS-60/p041-0/r03.archive.json.
"""
import argparse, json, pathlib, re, shutil, sys, zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schema.pydantic_schema import Amount, EquilibriumSolution, Phase, PhaseComponent, PubChemPureSubstanceSection, PublicationReference  # noqa: E402
sys.path.insert(0, str(ROOT / 'scripts'))
from paths import volume_root  # noqa: E402
from textnorm import loose, strict  # noqa: E402
from sdstable import BOX_NAME, PRESSURE_UNITS, VAL, column, conditions_from_variables, normalise_rows, parse_components, split_blocks, tex, to_canonical, value  # noqa: E402

M_DEF = '../upload/raw/schema.archive.yaml#/definitions/section_definitions/EquilibriumSolution'
AMOUNT_KINDS = {'molar_fraction': ('molar fraction', 'dimensionless'), 'mass_fraction': ('mass fraction', 'dimensionless'),   # in order of preference
                'molality': ('molality', 'mol/kg'), 'concentration': ('molarity', 'mol/L')}


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume'); ap.add_argument('boxes', type=pathlib.Path); ap.add_argument('out', type=pathlib.Path)
    ap.add_argument('--zip', action='store_true')
    a = ap.parse_args()
    vol = a.volume if a.volume.startswith('SDS-') else f'SDS-{a.volume}'
    records = [json.loads(l) for l in a.boxes.open()]
    out = a.out; (out).mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / 'schema' / 'schema.archive.yaml', out / 'schema.archive.yaml')
    stats = {'sheets': 0, 'rows': 0, 'entries': 0, 'no_components': 0, 'no_header': 0, 'sheet_as_table': 0,
             'no_temperature': 0, 'conditions_from_variables': 0, 'shifted_rows': 0, 'ditto_rows': 0, 'unmapped_columns': {}}
    layer = layer_citations(vol)
    for r in records:
        if r['kind'] != 'compilation':
            continue
        stats['sheets'] += 1
        comps = parse_components(r['boxes'].get('components', ''))
        if not any(c['cas'] for c in comps):                      # index pages, evaluation fragments
            stats['no_components'] += 1
            continue
        blocks = [b for b in split_blocks(r['boxes'].get('experimental_values', '').split('\n')) if b[0]]
        if not blocks:
            stats['no_header'] += 1
            continue
        if any(BOX_NAME.search(h) for head, _ in blocks for h in head):   # the crop caught the whole sheet, not the table
            stats['sheet_as_table'] += 1
            continue
        var_t, var_p = conditions_from_variables(r['boxes'].get('variables', ''))
        table = []                                                 # (header, columns, row) over the sub-tables of the crop
        for head, data in blocks:
            cols = [column(h, comps) for h in head]
            for c in cols:
                if c['kind'] == 'other':
                    stats['unmapped_columns'][c['raw'][:40]] = stats['unmapped_columns'].get(c['raw'][:40], 0) + 1
            table += [(head, cols, row, note) for row, note in normalise_rows(cols, data)]
        ref = parse_citation(r['boxes'].get('original_measurements', ''), layer.get(r['page'], []))
        method = re.sub(r'\s+', ' ', r['boxes'].get('method', '')).strip()
        for ri, (head, cols, row, layout) in enumerate(table):
            if layout == 'shifted':                                # fewer cells than columns: the values cannot be assigned
                stats['shifted_rows'] += 1
                continue
            stats['ditto_rows'] += layout == 'ditto'
            stats['rows'] += 1
            vals = [value(c) for c in row]
            e = EquilibriumSolution(m_def=M_DEF, lab_id=f"{vol}/p{r['page']:03d}/{r['index_on_page']}/r{ri:02d}",
                                    measurement_methods=[method] if method else [], publication_references=[ref])
            extra = []
            parts = {c['i']: PhaseComponent(name=c['name'], substance=PubChemPureSubstanceSection(name=c['name'], molecular_formula=c['formula'], cas_number=c['cas'])) for c in comps}
            fractions = {}                                        # (component, kind) -> value, one Amount per component
            for col, cell, v in zip(cols, row, vals):
                if v is None:
                    continue
                if col['kind'] in ('temperature_C', 'temperature_K', 'temperature_F'):
                    e.temperature = to_canonical(col, v)
                elif col['kind'] == 'pressure':
                    e.pressure = to_canonical(col, v)
                elif col['kind'] in AMOUNT_KINDS and col['i'] in parts and (col['i'], col['kind']) not in fractions:
                    fractions[(col['i'], col['kind'])] = (to_canonical(col, v), col, cell)
                else:
                    extra.append(f"{tex(col['raw'])} = {cell.strip()}")
            if e.temperature is None and var_t is not None:
                e.temperature = var_t
                extra.append(f"temperature from VARIABLES: {r['boxes'].get('variables', '').strip()}")
                stats['conditions_from_variables'] += 1
            if e.pressure is None and var_p is not None:
                e.pressure = var_p
            if e.temperature is None:
                stats['no_temperature'] += 1
            for i in parts:
                picked = next((k for k in AMOUNT_KINDS if (i, k) in fractions), None)
                for k in AMOUNT_KINDS:
                    if (i, k) in fractions and k != picked:
                        extra.append(f"{tex(fractions[(i, k)][1]['raw'])} = {fractions[(i, k)][2].strip()}")
                if picked:
                    parts[i].amount = Amount(type=AMOUNT_KINDS[picked][0], value=fractions[(i, picked)][0], units=AMOUNT_KINDS[picked][1])
            e.phases = [Phase(name='saturated solution', components=[parts[k] for k in sorted(parts)])]
            e.name = f"{vol} p{r['page']} sheet {r['index_on_page']} row {ri}: " + ' / '.join(c['name'] for c in comps)
            e.description = '\n'.join([f"source: IUPAC Solubility Data Series volume {vol[4:]}, page {r['page']}, sheet {r['index_on_page']}, table row {ri}",
                                       f"witness: MinerU 2.5-Pro crop pass; columns: {' | '.join(tex(h) for h in head)}",
                                       f"row: {' | '.join(row)}", f"citation: {r['boxes'].get('original_measurements', '').strip()}"]
                                      + ([f"unmapped: {'; '.join(extra)}"] if extra else []) + (['layout: conditions inherited from the row above (blank in print)'] if layout == 'ditto' else []))
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


if __name__ == '__main__':
    main()
