"""Turn the NIST ground truth (the DISSOLVE crawl's per-row measurements) into NOMAD entries of the
hackathon schema, one EquilibriumSolution per NIST table row, deterministically.

Usage: uv run python scripts/nist_to_nomad.py 60 out_dir [--measurements nist_measurements.jsonl.gz]
                                                       [--sheets nist_gt.jsonl] [--compilation-only] [--zip]

Default inputs are the library copies (~/Documents/hu-box/sds-extraction/nist/). Each record of
nist_measurements.jsonl already names the solute, the solvents, the conditions and every value
with its quantity and unit, so no model is needed: the quantities map onto the named Amount
fields in storage units (mole and mass fraction, molality, molar and mass concentration, mass
ratio, Bunsen, Ostwald, Kuenen, Henry in its three conventions), a gas-phase mole fraction adds
a gas Phase, and whatever has no field (activity coefficients, salt-effect parameters, generic
"solubility" columns, inverse Henry constants) stays verbatim in the description. Components are
numbered in the order of the system name, as the SDS does, for the SOURCE AND PURITY split.

Identifiers: lab_id "NIST/<measurement_id>" (e.g. NIST/38_230/t0/r1) and a name starting with
"NIST", so ground truth and extraction are told apart in NOMAD; our extraction writes the same
measurement id into its entries' description where the aligner and the row match find it.
Output layout: out_dir/schema.archive.yaml, out_dir/NIST-SDS-60/60_232/t0_r01.archive.json.
"""
import argparse, gzip, json, pathlib, re, shutil, sys, zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schema.pydantic_schema import Amount, EquilibriumSolution, Phase, PhaseComponent, PubChemPureSubstanceSection, StateOfMatter  # noqa: E402
sys.path.insert(0, str(ROOT / 'scripts'))
from to_nomad import M_DEF, parse_citation, split_by_component, split_errors  # noqa: E402

LIB = pathlib.Path.home() / 'Documents' / 'hu-box' / 'sds-extraction' / 'nist'
P_UNIT = {'atm': 101325.0, 'kpa': 1000.0, 'mpa': 1e6, 'pa': 1.0, 'bar': 1e5, 'mmhg': 133.322, 'torr': 133.322, 'psia': 6894.757, 'kbar': 1e8}


def norm_unit(u) -> str:
    return re.sub(r'[\s^*]+', '', (u or '').lower().replace('–', '-').replace('−', '-'))


def amount_field(v: dict):
    """(Amount field, value in storage units) for a DISSOLVE value, or None when the schema has no field for it."""
    q, u, x = v['quantity'], norm_unit(v.get('unit')), v['value']
    if not isinstance(x, (int, float)):
        return None
    if q in ('mole_fraction', 'gas_mole_fraction'):
        return 'mole_fraction', x
    if q == 'mass_fraction':
        return 'mass_fraction', x
    if q == 'mass_per_100g_solution':
        return 'mass_fraction', x / 100
    if q == 'mass_per_kg':
        return 'mass_fraction', x / 1000
    if q == 'mass_ratio':
        return 'solute_solvent_mass_ratio', x
    if q == 'molality':
        return 'molality', x
    if q == 'amount_concentration':
        if u in ('', 'mol/l', 'moll-1', 'moldm-3', 'mol/dm3', 'moldm**-3'):
            return 'molar_concentration', x * 1000
        if u in ('molm-3', 'mol/m3'):
            return 'molar_concentration', x
        return None
    if q == 'mass_concentration':
        if u in ('', 'gdm-3', 'g/l', 'g/dm3', 'kg/m3', 'gl-1'):
            return 'mass_concentration', x
        if u in ('mg/l', 'gm-3', 'g/m3'):
            return 'mass_concentration', x / 1000
        return None
    if q == 'bunsen_coefficient':
        return 'bunsen_coefficient', x
    if q == 'ostwald_coefficient':
        return 'ostwald_coefficient', x
    if q == 'kuenen_coefficient':
        return 'kuenen_coefficient', x / 1000           # cm^3(STP)/g -> m^3/kg
    if q == 'henry_constant':
        if 'mol' in u and ('atm' in u or 'pa' in u or 'bar' in u) and not u.startswith('mol'):
            f = next((P_UNIT[k] for k in P_UNIT if k in u), None)   # p/c: m^3 atm mol^-1
            return ('henry_constant_p_over_c', x * f) if f else None
        if u.startswith('mol'):                           # c/p, the inverse convention: no field
            return None
        if 'dimensionless' in u or u in ('', '1'):
            return 'henry_constant_c_gas_over_c_liquid', x
        f = next((P_UNIT[k] for k in P_UNIT if u.startswith(k)), None)
        return ('henry_constant_p_over_x', x * f) if f else None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume'); ap.add_argument('out', type=pathlib.Path)
    ap.add_argument('--measurements', type=pathlib.Path, default=LIB / 'nist_measurements.jsonl.gz')
    ap.add_argument('--sheets', type=pathlib.Path, default=LIB / 'nist_gt.jsonl')
    ap.add_argument('--compilation-only', action='store_true', help='skip the critical-evaluation sheets')
    ap.add_argument('--zip', action='store_true')
    a = ap.parse_args()
    n = int(str(a.volume).removeprefix('SDS-'))
    sheets = {s['id']: s for s in map(json.loads, a.sheets.open()) if s.get('iupac_volume') == n}
    opener = gzip.open if a.measurements.suffix == '.gz' else open
    records = [json.loads(l) for l in opener(a.measurements, 'rt') if f'"iupac_volume": {n},' in l]
    a.out.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / 'schema' / 'schema.archive.yaml', a.out / 'schema.archive.yaml')
    stats = {'measurements': len(records), 'entries': 0, 'evaluations': 0, 'with_amount': 0, 'gas_phases': 0, 'no_components': 0, 'unmapped_values': {}}
    for r in records:
        if r.get('evaluated') and a.compilation_only:
            continue
        sheet = sheets.get(r['sheet_id'], {})
        comps = [c for c in [r.get('solute'), *(r.get('solvent') or [])] if c] or [
            {'name': c.get('name'), 'formula': c.get('formula'), 'cas': c.get('cas')} for c in sheet.get('components') or []]
        if not comps:
            stats['no_components'] += 1
            continue
        system = r.get('system_name') or sheet.get('system_name') or ''
        order = sorted(range(len(comps)), key=lambda k: (system.lower().find((comps[k]['name'] or '').lower()[:12]) + 10 ** 6) % 10 ** 6)
        numbered = [{'i': k + 1, **comps[j]} for k, j in enumerate(order)]
        by_name = {c['name']: c for c in numbered}
        purity = split_by_component(sheet.get('source_and_purity') or '', numbered)
        err_t, err_s = split_errors(sheet.get('estimated_errors') or '')
        parts = {c['i']: PhaseComponent(name=c['name'], source_purity=purity.get(c['i']),
                                        substance=PubChemPureSubstanceSection(name=c['name'], molecular_formula=c.get('formula'), cas_number=c.get('cas'))) for c in numbered}
        amounts = {i: {} for i in parts}
        gas = {}
        extra = []
        solute = by_name.get((r.get('solute') or {}).get('name'))
        for src in ('solubility', 'solvent_composition', 'composition'):
            for v in r.get(src) or []:
                target = solute if src == 'solubility' else by_name.get(v.get('species'))
                if target is None and src == 'composition' and len(numbered) == 1:
                    target = numbered[0]
                mapped = amount_field(v)
                label = f"{v.get('header')} = {v.get('raw_value')}" + (f" {v['value_qualifier']}" if v.get('value_qualifier') else '') + (f" (note {v['note']})" if v.get('note') else '')
                if mapped and target is not None and v.get('value_qualifier') in (None, ''):
                    field, x = mapped
                    if v['quantity'] == 'gas_mole_fraction':
                        gas.setdefault(target['i'], x)
                    elif field not in amounts[target['i']]:
                        amounts[target['i']][field] = x
                    else:
                        extra.append(label)
                else:
                    extra.append(label)
                    if not mapped:
                        key = f"{v['quantity']} [{v.get('unit')}]"
                        stats['unmapped_values'][key] = stats['unmapped_values'].get(key, 0) + 1
        for v in r.get('properties') or []:
            extra.append(f"{v.get('header')} = {v.get('raw_value')}")
        for i, fields in amounts.items():
            if fields:
                parts[i].amount = Amount(**fields, estimated_error_solubility=err_s)
        phase = Phase(name='liquid solution' if not r.get('phase') else str(r['phase']), state_of_matter=StateOfMatter.liquid, components=[parts[k] for k in sorted(parts)])
        cond = r.get('conditions') or {}
        if isinstance(cond.get('pH'), (int, float)):
            phase.ph = cond['pH']
        phases = [phase]
        if gas:
            phases.append(Phase(name='gas phase', state_of_matter=StateOfMatter.gas,
                                components=[PhaseComponent(name=parts[i].name, substance=parts[i].substance, amount=Amount(mole_fraction=y)) for i, y in sorted(gas.items())]))
            stats['gas_phases'] += 1
        if r.get('solid_phase'):
            phases.append(Phase(name=f"solid phase: {r['solid_phase']}", state_of_matter=StateOfMatter.solid))
        method = re.sub(r'\s+', ' ', sheet.get('method') or '').strip()
        cite = r.get('citation') or sheet.get('original_measurements') or ''
        e = EquilibriumSolution(m_def=M_DEF, lab_id=f"NIST/{r['measurement_id']}",
                                name=f"NIST {r['sheet_id']} t{r['table_index']} r{r['row_index']}: {system}",
                                temperature=r.get('temperature_K'), pressure=(r['pressure_kPa'] * 1000 if isinstance(r.get('pressure_kPa'), (int, float)) else None),
                                estimated_error_temperature=err_t, measurement_methods=[method] if method else [],
                                phases=phases, publication_references=[parse_citation(cite, [])] if cite.strip() else [])
        desc = [f"source: IUPAC-NIST Solubility Database, sheet {r['sheet_id']}, table {r['table_index']}, row {r['row_index']} ({r.get('url') or sheet.get('url', '')})",
                f"measurement_id: {r['measurement_id']}", f"type: {r.get('type')}; species mapping: {r.get('species_mapping')}; temperature from {r.get('temperature_source')}",
                'row: ' + ' | '.join(f"{v.get('header')} = {v.get('raw_value')}" for src in ('solubility', 'solvent_composition', 'composition') for v in (r.get(src) or []))]
        if sheet.get('variables'):
            desc.append(f"variables: {sheet['variables']}")
        if r.get('evaluated'):
            desc.append('critical evaluation sheet: recommended or tentative values, not one paper\'s measurement')
            stats['evaluations'] += 1
        if r.get('flags'):
            desc.append(f"flags: {', '.join(r['flags'])}")
        if extra:
            desc.append(f"unmapped: {'; '.join(extra)}")
        e.description = '\n'.join(desc)
        d = a.out / f'NIST-SDS-{n}' / r['sheet_id']; d.mkdir(parents=True, exist_ok=True)
        (d / f"t{r['table_index']}_r{r['row_index']:02d}.archive.json").write_text(json.dumps({'data': e.model_dump(mode='json', exclude_none=True)}, ensure_ascii=False, indent=1))
        stats['entries'] += 1
        stats['with_amount'] += any(p.amount for p in parts.values())
    stats['unmapped_values'] = dict(sorted(stats['unmapped_values'].items(), key=lambda kv: -kv[1])[:12])
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    if a.zip:
        z = a.out.with_suffix('.zip')
        with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(a.out.rglob('*')):
                if f.is_file():
                    zf.write(f, f.relative_to(a.out))
        print(f'-> {z} ({z.stat().st_size // 1024} kB)')


if __name__ == '__main__':
    main()
