"""Keep only the mappings of an external header map that the data supports.

Usage: python3 -I scripts/filter_header_map.py header-map.jsonl out/ [--pairs eval/SDS-N/pairs.csv ...] [--keep-untested]

Two witnesses judge every mapping of a header the rules leave as `other` (e.g. a language model's
answer, see `sdstable.load_header_map`):

1. The identities between the printed columns (`check_rows.hard_checks`). Each sheet that prints the
   header is checked twice, with the mapping and with that one header reverted to `other`; the checks
   that exist only because of the mapping are attributed to it, as passes or failures.
2. The ground truth. With `--pairs`, the `pairs.csv` files of `scripts/eval/compare_entries.py` on an
   export made with the full map: a mismatched or hallucinated field of the mapped quantity on a sheet
   that prints the header counts against it, a paired row of that sheet without such a defect for it.

A mapping is kept when it has evidence and no more than one failure per five successes, rejected when
it has more failures than that, and untested when nothing touches it (kept only with --keep-untested).
Writes header-map-kept.jsonl, header-map-rejected.jsonl, header-map-untested.jsonl and report.csv.
"""
import argparse, collections, csv, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sdstable                                                                          # noqa: E402
from sdstable import BOX_NAME, column, conditions_from_variables, molar_mass, normalise_rows, parse_components, split_blocks, tex  # noqa: E402
from check_rows import Row, hard_checks                                                   # noqa: E402

ROOT = HERE.parent / 'data' / 'ground_truth'
VOLUMES = ('SDS-20', 'SDS-37', 'SDS-38', 'SDS-57', 'SDS-58', 'SDS-59', 'SDS-60', 'SDS-62')
FIELD_KIND = {'mole_fraction': 'molar_fraction', 'mass_fraction': 'mass_fraction', 'molality': 'molality', 'molar_concentration': 'concentration',
              'mass_concentration': 'mass_concentration', 'solute_solvent_mass_ratio': 'mass_ratio', 'bunsen_coefficient': 'bunsen',
              'ostwald_coefficient': 'ostwald', 'kuenen_coefficient': 'kuenen', 'henry_constant_p_over_x': 'henry_px',
              'henry_constant_p_over_c': 'henry_pc', 'henry_constant_c_gas_over_c_liquid': 'henry_cc', 'partial_pressure': 'partial_pressure',
              'pressure': 'pressure', 'temperature': 'temperature', 'density': 'density', 'salinity': 'salinity'}
MAX_FAIL_RATIO = 0.2


def boxes_file(vol: str) -> pathlib.Path:
    d = ROOT / 'mineru' / vol
    return d / 'boxes-crops-v2.jsonl' if (d / 'boxes-crops-v2.jsonl').exists() else d / 'boxes-crops.jsonl'


def sheet_tables(vol: str):
    """(page, index, comps, masses, var_t, var_p, blocks) of every compilation sheet with a table."""
    for r in map(json.loads, boxes_file(vol).open()):
        if r['kind'] != 'compilation':
            continue
        comps = parse_components(r['boxes'].get('components', ''))
        if not any(c['cas'] for c in comps):
            continue
        blocks = [b for b in split_blocks(r['boxes'].get('experimental_values', '').split('\n')) if b[0]]
        if not blocks or any(BOX_NAME.search(h) for head, _ in blocks for h in head):
            continue
        masses = {c['i']: molar_mass(c['formula']) if c['formula'] else None for c in comps}
        var_t, var_p = conditions_from_variables(r['boxes'].get('variables', ''))
        yield r['page'], r['index_on_page'], comps, masses, var_t, var_p, blocks


def check_counts(blocks, comps, masses, var_t, var_p) -> collections.Counter:
    """(check name, status) -> count over the rows of a sheet, under the current HEADER_MAP."""
    out = collections.Counter()
    for head, data in blocks:
        cols = [column(h, comps) for h in head]
        for cells, _ in normalise_rows(cols, data):
            if len(cells) != len(cols):
                continue
            for res in hard_checks(Row(cols, cells, comps, masses), var_t, var_p):
                out[(res['check'], res['status'])] += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('map', type=pathlib.Path)
    ap.add_argument('out', type=pathlib.Path)
    ap.add_argument('--pairs', type=pathlib.Path, nargs='*', default=[], help='pairs.csv of compare_entries.py on an export made with the full map')
    ap.add_argument('--keep-untested', action='store_true')
    a = ap.parse_args()
    records = {}
    for line in a.map.open():
        if line.strip():
            r = json.loads(line); records.setdefault(tex(r['header']), r)
    print('loaded:', sdstable.load_header_map(a.map), file=sys.stderr)
    ext = {k for k, v in sdstable.HEADER_MAP.items() if v['note'].startswith('external map')}
    evidence = {k: collections.Counter() for k in ext}                       # header -> counts
    sheets_of = collections.defaultdict(set)                                 # header -> {(vol, page, index)}
    for vol in VOLUMES:
        for page, idx, comps, masses, var_t, var_p, blocks in sheet_tables(vol):
            heads = [h for head, _ in blocks for h in head]
            present = [k for k in {tex(h) for h in heads} if k in ext]
            if not present:
                continue
            for k in present:
                sheets_of[k].add((vol, page, idx))
            with_map = check_counts(blocks, comps, masses, var_t, var_p)
            for k in present:                                                # ablation: this header alone reverted to `other`
                saved = sdstable.HEADER_MAP.pop(k)
                without = check_counts(blocks, comps, masses, var_t, var_p)
                sdstable.HEADER_MAP[k] = saved
                for (name, status), n in (with_map - without).items():
                    evidence[k][f'identity_{status}'] += n
                    evidence[k][f'identity_{status}:{name}'] += n
    # ground truth, per pair, attributed through the sheet of the extraction entry
    sheet_headers = collections.defaultdict(set)
    for k, s in sheets_of.items():
        for key in s:
            sheet_headers[key].add(k)
    for pcsv in a.pairs:
        for row in csv.DictReader(pcsv.open()):
            vol, p, idx, _ = row['lab_id'].split('/')
            key = (vol, int(p[1:]), int(idx))
            bad = {f.split('.')[-1] for f in (row['mismatched'] + ' ' + row['hallucinated']).split()}
            bad_kinds = {FIELD_KIND.get(f) for f in bad}
            for k in sheet_headers.get(key, ()):
                kind = sdstable.HEADER_MAP[k]['kind']
                kind = 'temperature' if kind.startswith('temperature') else kind
                evidence[k]['gold_bad' if kind in bad_kinds else 'gold_good'] += 1
    a.out.mkdir(parents=True, exist_ok=True)
    verdicts = collections.Counter()
    files = {v: (a.out / f'header-map-{v}.jsonl').open('w') for v in ('kept', 'rejected', 'untested')}
    report = []
    for k in sorted(ext, key=lambda k: -len(sheets_of[k])):
        e = evidence[k]
        good = e['identity_pass'] + e['gold_good']
        bad = e['identity_fail'] + e['gold_bad']
        if good + bad == 0:
            verdict = 'untested'
        elif bad <= MAX_FAIL_RATIO * good:
            verdict = 'kept'
        else:
            verdict = 'rejected'
        verdicts[verdict] += 1
        rec = dict(records[k]); rec['verdict'] = verdict
        rec['evidence'] = {kk: n for kk, n in sorted(e.items())}
        rec['sheets'] = len(sheets_of[k])
        files[verdict].write(json.dumps(rec, ensure_ascii=False) + '\n')
        if verdict == 'untested' and a.keep_untested:
            files['kept'].write(json.dumps(rec, ensure_ascii=False) + '\n')
        checks = '; '.join(f'{kk.split(":")[1]} {n}' for kk, n in sorted(e.items()) if kk.startswith('identity_fail:'))
        report.append({'header': records[k]['header'], 'kind': rec['kind'], 'i': rec.get('i'), 'pre': rec.get('pre'), 'unit': rec.get('unit'), 'sheets': len(sheets_of[k]),
                       'identity_pass': e['identity_pass'], 'identity_fail': e['identity_fail'], 'gold_good': e['gold_good'], 'gold_bad': e['gold_bad'],
                       'verdict': verdict, 'failing_checks': checks, 'confidence': rec.get('confidence')})
    for f in files.values():
        f.close()
    with (a.out / 'report.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(report[0])); w.writeheader(); w.writerows(report)
    not_printed = len(ext) - len(sheets_of)
    print(f'{len(ext)} mappings loaded, {len(sheets_of)} printed in the eight volumes, verdicts: {dict(verdicts)}; '
          f'{not_printed} never seen in a table are untested', file=sys.stderr)


if __name__ == '__main__':
    main()
