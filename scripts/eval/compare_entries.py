"""Score the extraction against the ground truth with FAIRmat's json-extract-eval, on the NIST row id.

Usage: scripts/eval/.venv/bin/python scripts/eval/compare_entries.py --gold nist-SDS-60[.zip] --extracted nomad-SDS-60[.zip]
                                                                    [--tol 0.005] [--out data/ground_truth/eval/SDS-60]

Both inputs are NOMAD upload folders or zips of EquilibriumSolution entries: the ground truth
from nist_to_nomad.py (lab_id NIST/<measurement id>) and the extraction from to_nomad.py (the
line "nist: <measurement id>" in the description where the row was matched). Pairs are formed
on that id; an extraction entry without one, or a ground-truth row no extraction entry claims,
is reported as unpaired and left out of the field scores (the row measure in align_nist.py
covers that coverage). Each pair is flattened to the quantities the two exporters share:
temperature, pressure, and per component of the liquid phase (keyed by CAS number) every
numeric Amount field; gas-phase mole fractions as a second list. json-extract-eval compares
field by field: numbers within a relative tolerance (--tol), components aligned by CAS, and
reports precision (of what we wrote, how much is right), recall (of what NIST has, how much we
got) and F1, overall and per field, with match / mismatch / omission / hallucination counts.

Writes <out>/summary.json, <out>/per_field.csv and <out>/pairs.csv (per pair: scores, and the mismatched fields with
both values, the omitted and the hallucinated fields, so every failure can be looked up by NIST id and lab_id).
"""
import argparse, csv, dataclasses, io, json, pathlib, re, zipfile

from json_extract_eval import annotate_xeval, evaluate, infer_schema, parse_eval_schema

NUMERIC_AMOUNT = ('mole_fraction', 'mass_fraction', 'molality', 'molar_concentration', 'mass_concentration', 'solute_solvent_mass_ratio',
                  'bunsen_coefficient', 'bunsen_coefficient_per_pressure', 'ostwald_coefficient', 'kuenen_coefficient', 'kuenen_coefficient_per_pressure',
                  'henry_constant_p_over_x', 'henry_constant_p_over_c', 'henry_constant_c_gas_over_c_liquid', 'partial_pressure')


def load_entries(src: pathlib.Path) -> list[dict]:
    out = []
    if src.suffix == '.zip':
        with zipfile.ZipFile(src) as z:
            for name in z.namelist():
                if name.endswith('.archive.json'):
                    out.append(json.loads(z.read(name))['data'])
    else:
        for f in src.rglob('*.archive.json'):
            out.append(json.load(f.open())['data'])
    return out


FRACTIONS = ('mole_fraction', 'mass_fraction', 'solute_solvent_mass_ratio')


def flatten(e: dict, gold: bool = False, invalid: list | None = None) -> dict:
    """The comparable part of an entry: conditions and, per liquid-phase component, the numeric Amount fields.

    On the gold side a fraction above 1 is dropped and counted: the crawl's documentation flags
    7 279 values where NIST dropped the 10^k header factor (`fraction_column_exceeds_1`), and such
    a value cannot be compared with anything."""
    rec = {}
    if isinstance(e.get('temperature'), (int, float)):
        rec['temperature'] = float(e['temperature'])
    if isinstance(e.get('pressure'), (int, float)):
        rec['pressure'] = float(e['pressure'])
    comps, gas = [], []
    for ph in e.get('phases', []):
        for c in ph.get('components', []):
            sub = c.get('substance') or {}
            key = sub.get('cas_number') or sub.get('name') or c.get('name') or '?'
            item = {'cas': key}
            for k, v in (c.get('amount') or {}).items():
                if k in NUMERIC_AMOUNT and isinstance(v, (int, float)):
                    if gold and k in FRACTIONS and v > 1:
                        if invalid is not None:
                            invalid.append((e.get('lab_id'), k, v))
                        continue
                    item[k] = float(v)
            (gas if ph.get('state_of_matter') == 'gas' else comps).append(item)
    rec['components'] = sorted(comps, key=lambda x: x['cas'])
    if gas:
        rec['gas'] = sorted(gas, key=lambda x: x['cas'])
    return rec


def set_numeric_tolerance(schema: dict, tol: float) -> None:
    """Numbers within a relative tolerance; component lists aligned by CAS; the id skipped."""
    def walk(node: dict, path: str):
        t = node.get('type')
        if t in ('number', 'integer'):
            node['x-eval-compare'] = {'numeric': {'tolerance': {'rel': tol}}}
        if t == 'array' and isinstance(node.get('items'), dict):
            if 'properties' in node['items'] and 'cas' in node['items']['properties']:
                node['x-eval-align'] = {'match_by': 'key_field', 'key': 'cas'}
            walk(node['items'], path + '[]')
        for k, child in (node.get('properties') or {}).items():
            if k == 'nist_id':
                child['x-eval-skip'] = True
                child.pop('x-eval-compare', None)
            else:
                walk(child, f'{path}.{k}')
    walk(schema, '')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--gold', type=pathlib.Path, required=True, nargs='+')
    ap.add_argument('--extracted', type=pathlib.Path, required=True, nargs='+')
    ap.add_argument('--tol', type=float, default=0.005)
    ap.add_argument('--out', type=pathlib.Path, required=True)
    a = ap.parse_args()
    gold_by_id = {}
    for src in a.gold:
        for e in load_entries(src):
            if str(e.get('lab_id', '')).startswith('NIST/'):
                gold_by_id[e['lab_id'][5:]] = e
    ext_by_id, dup, unmatched = {}, 0, 0
    for src in a.extracted:
        for e in load_entries(src):
            m = re.search(r'^nist: (\S+)$', e.get('description', ''), re.M)
            if not m:
                unmatched += 1
                continue
            if m.group(1) in ext_by_id:
                dup += 1
                continue
            ext_by_id[m.group(1)] = e
    ids = sorted(set(gold_by_id) & set(ext_by_id))
    invalid = []
    gold = [{'nist_id': i, **flatten(gold_by_id[i], gold=True, invalid=invalid)} for i in ids]
    extracted = [{'nist_id': i, **flatten(ext_by_id[i])} for i in ids]
    schema = infer_schema(gold)
    annotate_xeval(schema)
    set_numeric_tolerance(schema, a.tol)
    parse_eval_schema(schema)
    result = evaluate(gold, extracted, schema=schema, id_field='nist_id')
    a.out.mkdir(parents=True, exist_ok=True)
    summary = {'pairs': len(ids), 'gold_rows': len(gold_by_id), 'gold_rows_unclaimed': len(gold_by_id) - len(ids), 'gold_fractions_above_1_dropped': len(invalid),
               'extraction_entries_without_id': unmatched, 'extraction_entries_duplicate_id': dup, 'tolerance_rel': a.tol,
               'precision': result.mean_precision, 'recall': result.mean_recall, 'f1': result.mean_f1,
               'per_field': {p: {k: getattr(agg, k) for k in ('matches', 'mismatches', 'omissions', 'hallucinations', 'precision', 'recall', 'f1') if hasattr(agg, k)} for p, agg in result.per_field.items()}}
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=1))
    with (a.out / 'per_field.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['field', 'matches', 'mismatches', 'omissions', 'hallucinations', 'precision', 'recall', 'f1'])
        for p, s in summary['per_field'].items():
            w.writerow([p, *(s.get(k, '') for k in ('matches', 'mismatches', 'omissions', 'hallucinations', 'precision', 'recall', 'f1'))])
    with (a.out / 'pairs.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['nist_id', 'lab_id', 'precision', 'recall', 'f1', 'mismatched', 'omitted', 'hallucinated'])
        for i, r in zip(ids, result.records):
            by = {}
            for fr in r.field_results:
                by.setdefault(fr.status, []).append(f'{fr.path}={fr.gold_value}|{fr.extracted_value}' if fr.status == 'mismatch' else fr.path)
            w.writerow([i, ext_by_id[i].get('lab_id', ''), round(r.precision, 4), round(r.recall, 4), round(r.f1, 4),
                        ' '.join(by.get('mismatch', [])), ' '.join(by.get('omission', [])), ' '.join(by.get('hallucination', []))])
    print(f"pairs {len(ids)} (gold rows {len(gold_by_id)}, unclaimed {len(gold_by_id) - len(ids)}; extraction entries without id {unmatched}, duplicate id {dup}; gold fractions above 1 dropped {len(invalid)})")
    print(f"precision {result.mean_precision:.3f}  recall {result.mean_recall:.3f}  F1 {result.mean_f1:.3f}  (relative tolerance {a.tol})")
    for p, s in sorted(summary['per_field'].items(), key=lambda kv: -(kv[1].get('matches', 0) + kv[1].get('mismatches', 0) + kv[1].get('omissions', 0))):
        print(f"  {p:48s} match {s.get('matches', 0):6d}  mismatch {s.get('mismatches', 0):5d}  omission {s.get('omissions', 0):5d}  hallucination {s.get('hallucinations', 0):5d}  P {s.get('precision', 0):.3f} R {s.get('recall', 0):.3f}")
    print(f'-> {a.out}')


if __name__ == '__main__':
    main()
