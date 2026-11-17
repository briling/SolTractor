"""Turn the data sheets of a volume into NOMAD entries of the hackathon schema (schema/schema.archive.yaml).

Usage: uv run python scripts/to_nomad.py SDS-60 boxes.jsonl out_dir [--zip] [--yaml-schema]

One EquilibriumSolution entry per table row of a compilation sheet. Temperature
and pressure come from the t/°C, T/K, P columns (T_in/T_fin into temperature_initial
and temperature_final; a single-valued VARIABLES box when the table has none). One
liquid Phase "saturated solution" holds the printed components with CAS number,
name, formula, their SOURCE AND PURITY text, and an Amount with every solubility
quantity the row prints for that component, mapped by `sdstable.column` and
converted to the schema's storage units: mole and mass fraction, molality,
molar and mass concentration, solute-solvent mass ratio, Bunsen, Ostwald and
Kuenen coefficients, Henry's constant in its three conventions, partial pressure.
Columns without a component index (Bunsen, Ostwald, Henry) belong to the gas,
component 1. A solid-phase composition x_i(s) or a gas-phase fraction y_i adds a
solid or gas Phase. Density, salinity and pH go to the component or the phase.
The ESTIMATED ERROR box is split into its temperature and solubility sentences.
Columns the mapper does not know are kept verbatim in `description`, together
with the provenance (volume, page, sheet, raw row, citation, witness), the row's logical id
"id: SDS-60/p041/0/t0/r3" (provenance.py; a continuation page joins the sheet it continues)
and, where the aligner matched the sheet and the row pairs with a NIST row, the line
"nist: <sheet>/t<table>/r<row>", the measurement id of the DISSOLVE ground truth (the same id
nist_to_nomad.py uses). The pairing never looks at the values it will be scored on: it restores
the row mapping from the conditions (temperature, pressure) and the row order alone
(provenance.pair_rows); every decision goes to the trace
<out>.trace.jsonl, and the stats count the NIST rows left unpaired by cause. --pairing value
restores the former test (every number of the NIST row occurs in ours) for comparison. Rows whose
blank leading conditions mean "as above" are filled from the row above; rows
still shorter than the header are skipped (`shifted_rows`).
Entries are validated with schema/pydantic_schema.py (the model of schema.archive.yaml) before writing.
Each entry's `m_def` names the section of the nomad_solubility_plugin installed on the Oasis;
--yaml-schema instead ships schema.archive.yaml in the upload and references it. Output layout:
out_dir/SDS-60/p041-0/r03.archive.json.
"""
import argparse, csv, json, pathlib, re, shutil, sys, zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schema.pydantic_schema import Amount, EquilibriumSolution, Phase, PhaseComponent, PubChemPureSubstanceSection, PublicationReference, StateOfMatter  # noqa: E402
sys.path.insert(0, str(ROOT / 'scripts'))
from paths import NIST, volume_root  # noqa: E402
from textnorm import loose, numbers, strict  # noqa: E402
from sdstable import load_header_map, BOX_NAME, PRESSURE_UNITS, VAL, column, conditions_from_variables, normalise_rows, parse_components, split_blocks, tex, to_canonical, value  # noqa: E402
from provenance import Trace, pair_rows, row_id, sheet_id, sheet_id_of  # noqa: E402

M_DEF = 'nomad_solubility_plugin.schema_packages.schema_package.EquilibriumSolution'   # the plugin installed on the Oasis
M_DEF_YAML = '../upload/raw/schema.archive.yaml#/definitions/section_definitions/EquilibriumSolution'   # --yaml-schema: the schema shipped in the upload
# column kind of sdstable -> (Amount field, factor from the parser's canonical unit to the schema's storage unit)
AMOUNT_FIELDS = {'molar_fraction': ('mole_fraction', 1.0), 'mass_fraction': ('mass_fraction', 1.0), 'molality': ('molality', 1.0),
                 'concentration': ('molar_concentration', 1000.0),           # mol/dm^3 -> mol/m^3
                 'mass_concentration': ('mass_concentration', 1.0),          # g/dm^3 = kg/m^3
                 'mass_ratio': ('solute_solvent_mass_ratio', 1.0), 'bunsen': ('bunsen_coefficient', 1.0), 'ostwald': ('ostwald_coefficient', 1.0),
                 'kuenen': ('kuenen_coefficient', 1e-3),                     # cm^3(STP)/g -> m^3/kg
                 'henry_px': ('henry_constant_p_over_x', 1.0), 'henry_pc': ('henry_constant_p_over_c', 1.0),
                 'henry_cc': ('henry_constant_c_gas_over_c_liquid', 1.0), 'partial_pressure': ('partial_pressure', 1.0)}
GAS_KINDS = ('bunsen', 'ostwald', 'kuenen', 'henry_px', 'henry_pc', 'henry_cc')   # columns without an index belong to the gas, component 1


YEAR = re.compile(r'\b(1[89]\d\d|20\d\d)\b')
def split_by_component(text: str, comps: list[dict]) -> dict[int, str]:
    """The SOURCE AND PURITY box per component, cut at "(1)", "(2)" markers; the whole text for every component when there are none."""
    text = re.sub(r'\s+', ' ', text).strip()
    marks = [(m.start(), int(m.group(1))) for m in re.finditer(r'\((\d)\)', text) if int(m.group(1)) in {c['i'] for c in comps}]
    if not marks:
        return {c['i']: text for c in comps} if text else {}
    out = {}
    for k, (pos, i) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(text)
        out[i] = text[pos:end].strip()
    return out


def split_errors(text: str) -> tuple[str | None, str | None]:
    """The ESTIMATED ERROR box as (temperature part, solubility part): sentences naming the temperature
    (Temperature, Temp., T/K, a kelvin value) against the rest."""
    t = re.sub(r'\s+', ' ', tex(text).replace('\\pm', '±').replace('\\%', '%')).strip()
    if not t:
        return None, None
    parts = [x.strip() for x in re.split(r'(?<=[.;])\s*(?=[A-Z])|\s+(?=(?:Temperature|Temp\.|Solubility|Soly\.)\s*:)', t) if x.strip()]
    temp = [x for x in parts if re.search(r'[Tt]emp|T/K|\bT\b|\d\s*K\b|°C', x)]
    sol = [x for x in parts if x not in temp]
    return (' '.join(temp) or None), (' '.join(sol) or None)


def nist_rows(vol: str, align: pathlib.Path | None) -> dict[tuple[int, int], list[tuple[str, list[str]]]]:
    """(page, sheet) -> [(NIST measurement id, numeric tokens of that NIST row)] for the sheets the aligner matched.

    The alignment CSV maps a NIST sheet to our (page, index_on_page); the NIST tables come from
    ground_truth/nist/SDS-N.json (the DISSOLVE crawl). A row of ours gets the id of the first NIST
    row whose numeric tokens all occur in it, the same test as the aligner's row measure."""
    if align is None or not align.exists():
        return {}
    f = NIST / f'{vol}.json'
    if not f.exists():
        return {}
    tables = {n['sheet_id']: n.get('tables', []) for n in json.load(f.open())}
    out = {}
    for a in csv.DictReader(align.open()):
        if not a['page']:
            continue
        rows = []
        for ti, t in enumerate(tables.get(a['sheet_id'], [])):
            for ri, row in enumerate(t['rows']):
                toks = [x for c in row for x in numbers(str(c))]
                if toks:
                    rows.append((f"{a['sheet_id']}/t{ti}/r{ri}", toks))
        out.setdefault((int(a['page']), int(a['index_on_page'])), []).extend(rows)
    return out


TEMPERATURE_KINDS = ('temperature_C', 'temperature_K', 'temperature_F')


def row_conditions(cols: list[dict], row: list[str], var_t: float | None, var_p: float | None) -> tuple[float | None, float | None]:
    """(temperature, pressure) of a row in canonical units: the first printed column of each kind, else the VARIABLES value.

    Returns:
        The pair; either element is None when the row prints no such column (or an
        unparsable cell) and VARIABLES gives no single value.
    """
    t = p = None
    for col, cell in zip(cols, row):
        v = value(cell)
        if v is None:
            continue
        if t is None and col['kind'] in TEMPERATURE_KINDS:
            t = to_canonical(col, v)
        elif p is None and col['kind'] == 'pressure':
            p = to_canonical(col, v)
    return (var_t if t is None else t), (var_p if p is None else p)


def nist_sheets(vol: str, align: pathlib.Path | None) -> tuple[dict[str, str], dict[str, list[list[tuple]]]]:
    """The ground-truth side of the pairing: which of our sheets the aligner matched to which NIST sheet,
    and the conditions of every row of every NIST table.

    Returns:
        (our sheet id -> NIST sheet id, NIST sheet id -> per table, per row, (temperature, pressure));
        both empty when the volume has no aligner CSV or no NIST file. The second holds every
        NIST sheet with tables, aligned or not, so the unpaired ground truth can be counted.
    """
    f = NIST / f'{vol}.json'
    if align is None or not align.exists() or not f.exists():
        return {}, {}
    conds = {}
    for n in json.load(f.open()):
        comps = parse_components(n.get('components', ''))
        var_t, var_p = conditions_from_variables(n.get('variables', ''))
        tabs = []
        for t in n.get('tables', []):
            # NIST's own "Pressure [MPa]" spelling stays unmapped on purpose: the crawl files the gas
            # partial pressure there where we file the total, so it would contradict correct pairs
            cols = [column(str(h), comps) for h in t['headers']]
            tabs.append([row_conditions(cols, [str(c) for c in row], var_t, var_p) for row in t['rows']])
        if tabs:
            conds[n['sheet_id']] = tabs
    matched = {sheet_id(vol, int(a['page']), int(a['index_on_page'])): a['sheet_id'] for a in csv.DictReader(align.open()) if a['page']}
    return matched, conds


def pair_sheets(prepared: list[tuple], matched: dict[str, str], gold: dict[str, list[list[tuple]]], trace: Trace | None) -> dict[tuple[str, int], tuple[str, str | None, str]]:
    """Logical row ids for every row of the prepared sheets and, where `gold` is given, the NIST row each pairs with.

    A continuation record (`continues`) joins the sheet it continues: its first table
    extends that sheet's last table, further tables follow it. Rows are numbered within
    their logical table, shifted rows included, so positions match the printed table.

    Returns:
        (record sheet id, row index in the record) -> (row id, NIST measurement id or None,
        reason): `conditions` or `position` for a pair (provenance.pair_rows), else
        `sheet_unaligned` (the aligner matched no NIST sheet to this one) or one of
        pair_rows' reasons for an unpaired row. The trace record of each row also carries
        pair_rows' margin.
    """
    groups = {}                                         # sheet id -> [(record sheet id, ri, table index, conditions)]
    for r, comps, var_t, var_p, table in prepared:
        sid = sheet_id_of(r)
        g = groups.setdefault(r.get('continues') or sid, [])
        offset = max(g[-1][2], 0) if g and r.get('continues') else 0
        for ri, (head, cols, row, note, bi) in enumerate(table):
            g.append((sid, ri, offset + bi, (None, None) if note == 'shifted' else row_conditions(cols, row, var_t, var_p)))
    out = {}
    for key, rows in groups.items():
        tables = [[] for _ in range(max(t for _, _, t, _ in rows) + 1)] if rows else []
        at = []
        for sid, ri, t, c in rows:
            at.append((sid, ri, t, len(tables[t])))
            tables[t].append(c)
        nist_sheet = next((matched[s] for s in [key] + [s for s, *_ in rows] if s in matched), None)
        res = pair_rows(tables, gold.get(nist_sheet, [])) if nist_sheet else [[(None, 'sheet_unaligned', None)] * len(t) for t in tables]
        for sid, ri, t, j in at:
            hit, why, margin = res[t][j]
            mid = f'{nist_sheet}/t{hit[0]}/r{hit[1]}' if hit else None
            out[(sid, ri)] = (row_id(key, t, j), mid, why)
            if trace:
                trace.decide('nist_pair', row_id(key, t, j), mid, why, margin=margin)
    return out


def unpaired_gold(gold: dict[str, list[list[tuple]]], matched: dict[str, str], skipped: dict[str, str],
                  ids: dict[tuple[str, int], tuple], exported: set[str]) -> dict[str, int]:
    """Every NIST row of the volume counted once, by the first reason it has no exported partner.

    Returns:
        Counts per reason: `paired` (an exported row carries its id), `sheet_unaligned`
        (no sheet of ours matched), `no_components` / `no_header` / `sheet_as_table` (our
        sheet exports nothing; `no_header` is mostly a sheet without a crop table),
        `row_not_exported` (paired to a row the exporter skips as shifted) and
        `row_unpaired` (our sheet exports rows, none pairs with this one).
    """
    ours = {v: k for k, v in matched.items()}
    claimed = {mid for _, mid, _ in ids.values() if mid}
    out = {}
    for nid, tabs in gold.items():
        for t, rows in enumerate(tabs):
            for r in range(len(rows)):
                mid = f'{nid}/t{t}/r{r}'
                why = ('paired' if mid in exported else 'sheet_unaligned' if nid not in ours
                       else skipped.get(ours[nid]) or ('row_not_exported' if mid in claimed else 'row_unpaired'))
                out[why] = out.get(why, 0) + 1
    return out


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
    ap.add_argument('--header-map', type=pathlib.Path, help='jsonl of mappings for headers the rules leave unmapped (checked by hard constraints)')
    ap.add_argument('--yaml-schema', action='store_true', help='reference schema.archive.yaml shipped in the upload instead of the installed plugin')
    ap.add_argument('--align', type=pathlib.Path, help='aligner CSV for these boxes (default: align-crops.csv next to them, or crops-v2/align.csv for boxes-crops-v2.jsonl)')
    ap.add_argument('--pairing', choices=('position', 'value'), default='position',
                    help='how a row finds its NIST row: by table and row position, conditions as fallback (default), '
                         'or the former test that every number of the NIST row occurs in ours (kept for comparison)')
    ap.add_argument('--trace', type=pathlib.Path, help='decision trace to append to (default: <out>.trace.jsonl)')
    a = ap.parse_args()
    header_map = load_header_map(a.header_map) if a.header_map else None
    vol = a.volume if a.volume.startswith('SDS-') else f'SDS-{a.volume}'
    records = [json.loads(l) for l in a.boxes.open()]
    for r in records:                      # boxes written before ids existed (some also name the volume "boxes-page")
        r.setdefault('sheet_id', sheet_id(vol, r['page'], r['index_on_page']))
    out = a.out; (out).mkdir(parents=True, exist_ok=True)
    m_def = M_DEF_YAML if a.yaml_schema else M_DEF
    if a.yaml_schema:
        shutil.copy(ROOT / 'schema' / 'schema.archive.yaml', out / 'schema.archive.yaml')
    stats = {'sheets': 0, 'rows': 0, 'entries': 0, 'no_components': 0, 'no_header': 0, 'sheet_as_table': 0,
             'no_temperature': 0, 'conditions_from_variables': 0, 'shifted_rows': 0, 'ditto_rows': 0, 'entries_with_amount': 0, 'unmapped_columns': {}}
    layer = layer_citations(vol)
    align = a.align or (a.boxes.parent / 'crops-v2' / 'align.csv' if a.boxes.name.endswith('-v2.jsonl') else a.boxes.parent / 'align-crops.csv')
    nist = nist_rows(vol, align) if a.pairing == 'value' else {}
    matched, gold = nist_sheets(vol, align)
    stats['nist_rows'] = 0
    stats['nist_pairing'] = {}
    trace = Trace(a.trace or out.with_name(out.name + '.trace.jsonl'))
    prepared, skipped = [], {}                                     # sheets that export rows; sheet id -> why one exports none
    for r in records:
        if r['kind'] != 'compilation':
            continue
        stats['sheets'] += 1
        comps = parse_components(r['boxes'].get('components', ''))
        if not any(c['cas'] for c in comps):                      # index pages, evaluation fragments
            stats['no_components'] += 1
            skipped[sheet_id_of(r)] = 'no_components'
            continue
        blocks = [b for b in split_blocks(r['boxes'].get('experimental_values', '').split('\n')) if b[0]]
        if not blocks:
            stats['no_header'] += 1
            skipped[sheet_id_of(r)] = 'no_header'
            continue
        if any(BOX_NAME.search(h) for head, _ in blocks for h in head):   # the crop caught the whole sheet, not the table
            stats['sheet_as_table'] += 1
            skipped[sheet_id_of(r)] = 'sheet_as_table'
            continue
        var_t, var_p = conditions_from_variables(r['boxes'].get('variables', ''))
        table = []                                                 # (header, columns, row, note, sub-table) over the sub-tables of the crop
        for bi, (head, data) in enumerate(blocks):
            cols = [column(h, comps) for h in head]
            for c in cols:
                if c['kind'] == 'other':
                    stats['unmapped_columns'][c['raw'][:40]] = stats['unmapped_columns'].get(c['raw'][:40], 0) + 1
            table += [(head, cols, row, note, bi) for row, note in normalise_rows(cols, data)]
        prepared.append((r, comps, var_t, var_p, table))
    ids = pair_sheets(prepared, matched, gold if a.pairing == 'position' else {}, trace if a.pairing == 'position' else None)
    exported = set()                                               # NIST ids claimed by an exported row
    for r, comps, var_t, var_p, table in prepared:
        ref = parse_citation(r['boxes'].get('original_measurements', ''), layer.get(r['page'], []))
        method = re.sub(r'\s+', ' ', r['boxes'].get('method', '')).strip()
        purity = split_by_component(r['boxes'].get('source_purity', ''), comps)
        err_t, err_s = split_errors(r['boxes'].get('estimated_error', ''))
        gas = comps[0]['i'] if comps else None
        for ri, (head, cols, row, layout, _) in enumerate(table):
            if layout == 'shifted':                                # fewer cells than columns: the values cannot be assigned
                stats['shifted_rows'] += 1
                continue
            stats['ditto_rows'] += layout == 'ditto'
            stats['rows'] += 1
            vals = [value(c) for c in row]
            e = EquilibriumSolution(m_def=m_def, lab_id=f"{vol}/p{r['page']:03d}/{r['index_on_page']}/r{ri:02d}",
                                    measurement_methods=[method] if method else [], publication_references=[ref], estimated_error_temperature=err_t)
            extra = []
            parts = {c['i']: PhaseComponent(name=c['name'], source_purity=purity.get(c['i']),
                                            substance=PubChemPureSubstanceSection(name=c['name'], molecular_formula=c['formula'], cas_number=c['cas'])) for c in comps}
            amounts = {i: {} for i in parts}                      # component -> Amount fields; the first printed column of a kind wins
            solid, gasphase = {}, {}                              # component -> mole fraction in the solid / gas phase
            phase = Phase(name='saturated solution', state_of_matter=StateOfMatter.liquid)
            for col, cell, v in zip(cols, row, vals):
                if v is None:
                    continue
                k, cv = col['kind'], to_canonical(col, v)
                i = col['i'] if col['i'] in parts else (gas if k in GAS_KINDS or k == 'partial_pressure' else None)
                if k in ('temperature_C', 'temperature_K', 'temperature_F'):
                    e.temperature = cv
                elif k == 'temperature_in_K':
                    e.temperature_initial = cv
                elif k == 'temperature_fin_K':
                    e.temperature_final = cv
                elif k == 'pressure':
                    e.pressure = cv
                elif k in AMOUNT_FIELDS and i is not None and AMOUNT_FIELDS[k][0] not in amounts[i]:
                    amounts[i][AMOUNT_FIELDS[k][0]] = cv * AMOUNT_FIELDS[k][1]
                elif k == 'solid_fraction' and i is not None and i not in solid:
                    solid[i] = cv
                elif k == 'gas_fraction' and i is not None and i not in gasphase:
                    gasphase[i] = cv
                elif k == 'density':
                    if col['i'] in parts and parts[col['i']].density is None:
                        parts[col['i']].density = cv
                    elif col['i'] is None and phase.density is None:
                        phase.density = cv
                    else:
                        extra.append(f"{tex(col['raw'])} = {cell.strip()}")
                elif k == 'salinity' and phase.salinity is None:
                    phase.salinity = cv / 1000.0                   # g/kg solution -> ratio
                elif k == 'ph' and phase.ph is None:
                    phase.ph = cv
                else:
                    extra.append(f"{tex(col['raw'])} = {cell.strip()}")
            if e.temperature is None and e.temperature_initial is None and var_t is not None:
                e.temperature = var_t
                extra.append(f"temperature from VARIABLES: {r['boxes'].get('variables', '').strip()}")
                stats['conditions_from_variables'] += 1
            if e.pressure is None and var_p is not None:
                e.pressure = var_p
            if e.temperature is None and e.temperature_initial is None:
                stats['no_temperature'] += 1
            for i, fields in amounts.items():
                if fields:
                    parts[i].amount = Amount(**fields, estimated_error_solubility=err_s)
            if any(p.amount for p in parts.values()):
                stats['entries_with_amount'] += 1
            phase.components = [parts[k] for k in sorted(parts)]
            e.phases = [phase]
            if solid:
                e.phases.append(Phase(name='solid phase', state_of_matter=StateOfMatter.solid,
                                      components=[PhaseComponent(name=parts[i].name, substance=parts[i].substance, amount=Amount(mole_fraction=x)) for i, x in sorted(solid.items())]))
            if gasphase:
                e.phases.append(Phase(name='gas phase', state_of_matter=StateOfMatter.gas,
                                      components=[PhaseComponent(name=parts[i].name, substance=parts[i].substance, amount=Amount(mole_fraction=y)) for i, y in sorted(gasphase.items())]))
            e.name = f"{vol} p{r['page']} sheet {r['index_on_page']} row {ri}: " + ' / '.join(c['name'] for c in comps)
            rid, nist_id, how = ids[(sheet_id_of(r), ri)]
            if a.pairing == 'value':
                row_text = strict(' | '.join(row))
                nist_id = next((mid for mid, toks in nist.get((r['page'], r['index_on_page']), []) if all(t in row_text for t in toks)), None)
                how = 'value' if nist_id else 'no_value_match'
            if nist_id:
                stats['nist_rows'] += 1
                exported.add(nist_id)
            stats['nist_pairing'][how] = stats['nist_pairing'].get(how, 0) + 1
            e.description = '\n'.join([f"source: IUPAC Solubility Data Series volume {vol[4:]}, page {r['page']}, sheet {r['index_on_page']}, table row {ri}",
                                       f"id: {rid}"] + ([f"nist: {nist_id}"] if nist_id else []) + [
                                       f"witness: MinerU 2.5-Pro crop pass; columns: {' | '.join(tex(h) for h in head)}",
                                       f"row: {' | '.join(row)}", f"citation: {r['boxes'].get('original_measurements', '').strip()}"]
                                      + ([f"unmapped: {'; '.join(extra)}"] if extra else []) + (['layout: conditions inherited from the row above (blank in print)'] if layout == 'ditto' else []))
            d = out / vol / f"p{r['page']:03d}-{r['index_on_page']}"; d.mkdir(parents=True, exist_ok=True)
            (d / f'r{ri:02d}.archive.json').write_text(json.dumps({'data': e.model_dump(mode='json', exclude_none=True)}, ensure_ascii=False, indent=1))
            stats['entries'] += 1
    trace.close()
    stats['nist_unpaired'] = unpaired_gold(gold, matched, skipped, ids, exported)
    stats['unmapped_columns'] = dict(sorted(stats['unmapped_columns'].items(), key=lambda kv: -kv[1])[:12])
    if header_map:
        stats['header_map'] = header_map
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
