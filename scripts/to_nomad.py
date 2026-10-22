"""Turn the data sheets of a volume into NOMAD entries of the hackathon schema (schema/schema.archive.yaml).

Usage: uv run python scripts/to_nomad.py SDS-60 boxes.jsonl out_dir [--zip]

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
with the provenance (volume, page, sheet, raw row, citation, witness). Rows whose
blank leading conditions mean "as above" are filled from the row above; rows
still shorter than the header are skipped (`shifted_rows`).
Entries are validated with schema/pydantic_schema.py (the model of schema.archive.yaml) before writing. Output layout:
out_dir/schema.archive.yaml, out_dir/SDS-60/p041-0/r03.archive.json.
"""
import argparse, json, pathlib, re, shutil, sys, zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schema.pydantic_schema import Amount, EquilibriumSolution, Phase, PhaseComponent, PubChemPureSubstanceSection, PublicationReference, StateOfMatter  # noqa: E402
sys.path.insert(0, str(ROOT / 'scripts'))
from paths import volume_root  # noqa: E402
from textnorm import loose, strict  # noqa: E402
from sdstable import BOX_NAME, PRESSURE_UNITS, VAL, column, conditions_from_variables, normalise_rows, parse_components, split_blocks, tex, to_canonical, value  # noqa: E402

M_DEF = '../upload/raw/schema.archive.yaml#/definitions/section_definitions/EquilibriumSolution'
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
             'no_temperature': 0, 'conditions_from_variables': 0, 'shifted_rows': 0, 'ditto_rows': 0, 'entries_with_amount': 0, 'unmapped_columns': {}}
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
        purity = split_by_component(r['boxes'].get('source_purity', ''), comps)
        err_t, err_s = split_errors(r['boxes'].get('estimated_error', ''))
        gas = comps[0]['i'] if comps else None
        for ri, (head, cols, row, layout) in enumerate(table):
            if layout == 'shifted':                                # fewer cells than columns: the values cannot be assigned
                stats['shifted_rows'] += 1
                continue
            stats['ditto_rows'] += layout == 'ditto'
            stats['rows'] += 1
            vals = [value(c) for c in row]
            e = EquilibriumSolution(m_def=M_DEF, lab_id=f"{vol}/p{r['page']:03d}/{r['index_on_page']}/r{ri:02d}",
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
