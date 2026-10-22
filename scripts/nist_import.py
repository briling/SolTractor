"""Import the complete NIST ground truth of the DISSOLVE repository into the per-volume files the aligner reads.

Usage: python3 -I scripts/nist_import.py /path/to/nist_gt.jsonl [--volumes 20,37,...]

The yardstick of this repository was first scraped by nist_scrape.py, which pages the sheet
lists but not the systems list, so every volume stopped after its first 30 systems (18 to 55
sheets where hundreds exist; volumes 60 and 20 nearly complete). A colleague's crawler
(github.com/yaruwangway/dissolve-solubility-data, data/nist_gt.jsonl, one record per sheet,
2 784 sheets over the eight volumes with a free PDF) replaces it. This script writes
ground_truth/nist/SDS-N.json in the shape align_nist.py expects: sheet_id, system, components
text and components_parsed, original_measurements, variables, critical_evaluation, tables as
headers plus rows of strings. Numeric cells, floats in the source, are printed with repr, so
"0.10" has become "0.1"; the aligner's measures are substring based and unaffected. Evaluation
sheets keep their flag through an empty original_measurements and critical_evaluation_refs.
"""
import argparse, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from paths import MINED, NIST  # noqa: E402


def cell(v) -> str:
    if v is None:
        return ''
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)
    return str(v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('gt', type=pathlib.Path, help='nist_gt.jsonl of the DISSOLVE repository')
    ap.add_argument('--volumes', help='comma-separated volume numbers (default: the mined volumes of volumes.csv)')
    a = ap.parse_args()
    vols = {int(v) for v in a.volumes.split(',')} if a.volumes else set(MINED)
    out = {v: [] for v in vols}
    for line in a.gt.open():
        r = json.loads(line)
        v = r.get('iupac_volume')
        if v not in vols:
            continue
        comps = r.get('components') or []
        out[v].append({
            'sheet_id': r['id'], 'system_id': r.get('system_id', ''), 'url': r.get('url', ''),
            'system': r.get('system_name', ''), 'system_name': r.get('system_name', ''),
            'components': '\n'.join(f"({c.get('index', i + 1)}) {c.get('name', '')}; {c.get('formula', '')}; [{c.get('cas', '')}]" for i, c in enumerate(comps)),
            'components_parsed': [{'index': c.get('index', i + 1), 'name': c.get('name', ''), 'formula': c.get('formula', ''), 'cas': c.get('cas', '')} for i, c in enumerate(comps)],
            'original_measurements': r.get('original_measurements') or '',
            'variables': r.get('variables') or '', 'prepared_by': r.get('prepared_by') or '',
            'critical_evaluation': r.get('critical_evaluation_refs') or ('evaluated' if r.get('evaluated') else ''),
            'experimental_values': '\n'.join(x for x in (r.get('experimental_remarks'), r.get('experimental_data_text')) if x),
            'notes': r.get('notes') or '', 'method': r.get('method') or '',
            'source_purity': r.get('source_and_purity') or '', 'estimated_error': r.get('estimated_errors') or '',
            'evaluated': bool(r.get('evaluated')),
            'tables': [{'caption': t.get('caption') or '', 'headers': [str(h) for h in t.get('columns', [])], 'rows': [[cell(c) for c in row] for row in t.get('rows', [])]} for t in r.get('tables', [])],
        })
    NIST.mkdir(parents=True, exist_ok=True)
    for v in sorted(out):
        (NIST / f'SDS-{v}.json').write_text(json.dumps(out[v], ensure_ascii=False, indent=0))
        n_tab = sum(1 for s in out[v] if s['tables'])
        print(f'SDS-{v}: {len(out[v])} sheets ({n_tab} with tables, {sum(s["evaluated"] for s in out[v])} evaluations) -> {NIST / f"SDS-{v}.json"}')


if __name__ == '__main__':
    main()
