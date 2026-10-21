"""Align NIST database sheets with OCR sheets of the same volume and score the OCR layer.

Usage: python -I align_nist.py 60 [--min-score 0.6]

Reads nist/SDS-<vol>.json (scraped, hand-keyed sheets) and boxes/SDS-<vol>.jsonl
(segmented OCR sheets). Each NIST compilation sheet is matched to the OCR sheet
whose COMPONENTS box holds its CAS numbers and whose ORIGINAL MEASUREMENTS box
shares the most tokens with its citation. For every aligned pair the numeric
tokens of the NIST table are searched in the OCR EXPERIMENTAL VALUES box
(strict normalization), which gives the fraction of ground-truth values the OCR
layer reproduces verbatim. Writes nist/align-SDS-<vol>.csv.
"""
import argparse, csv, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from textnorm import cas_numbers, loose, numbers, strict  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def tokens(s: str) -> set[str]:
    return {t for t in re.findall(r'[a-z]{3,}|\d{4}', s.lower()) if t not in {'and', 'the', 'vol', 'pp'}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume', type=int)
    ap.add_argument('--min-score', type=float, default=0.6)
    a = ap.parse_args()
    nist = json.load((ROOT / 'nist' / f'SDS-{a.volume}.json').open())
    for n in nist:                                   # NIST keys evaluator tables as sheets without a citation
        n['kind'] = ('evaluation' if n['critical_evaluation'] or not n['original_measurements'].strip()
                     else 'compilation')
        if not n['tables'] and n['kind'] == 'evaluation':
            n['kind'] = 'evaluation-text'
    nist = [n for n in nist if n['kind'] != 'evaluation-text']
    ocr = [json.loads(l) for l in (ROOT / 'boxes' / f'SDS-{a.volume}.jsonl').open()]
    # continuation sheets (flagged, or same components + citation as the sheet before) are merged
    anchors = []
    def key(r): return loose(r['boxes'].get('components', ''))[:60] + loose(r['boxes'].get('original_measurements', ''))[:60]
    for r in ocr:
        if r['kind'] == 'evaluation':
            r['boxes']['experimental_values'] = r['boxes'].get('critical_evaluation', '')
            r['boxes']['original_measurements'] = r['boxes'].get('evaluator', '')
        prev = anchors[-1] if anchors else None
        if prev and r['kind'] == prev['kind'] and (r['continued'] or (
                key(r) == key(prev) and not prev['boxes'].get('method') and not prev['boxes'].get('source_purity'))):
            anchors[-1]['boxes']['experimental_values'] += '\n' + r['boxes'].get('experimental_values', '')
            anchors[-1]['pages'].append(r['page'])
            for b in ('method', 'source_purity', 'estimated_error', 'references'):
                if r['boxes'].get(b) and not anchors[-1]['boxes'].get(b):
                    anchors[-1]['boxes'][b] = r['boxes'][b]
        else:
            r['pages'] = [r['page']]
            anchors.append(r)
    feats = []
    for r in anchors:
        b = r['boxes']
        feats.append((set(cas_numbers(b.get('components', ''))), tokens(b.get('original_measurements', '')),
                      strict(b.get('experimental_values', ''))))
    WATER = '7732-18-5'
    # score every (NIST sheet, OCR anchor) pair: solute CAS numbers must all be present,
    # then citation token overlap and recall of the table values in the OCR box
    cands = []
    for ni, n in enumerate(nist):
        cas = {c['cas'] for c in n['components_parsed']} - {WATER}
        cit = tokens(n['original_measurements'])
        vals = [v for t in n['tables'] for row in t['rows'] for cell in row for v in numbers(cell)]
        for i, (ocas, otok, text) in enumerate(feats):
            if anchors[i]['kind'] != n['kind']:
                continue
            s_cas = len(cas & ocas) / len(cas) if cas else 1.0
            if cas and s_cas == 0:
                continue
            s_cit = len(cit & otok) / len(cit) if cit else 1.0
            found = [v for v in vals if v in text]
            s_val = len(found) / len(vals) if vals else s_cit
            cands.append((0.2 * s_cas + 0.3 * s_cit + 0.5 * s_val, ni, i, found))
    cands.sort(reverse=True)
    taken_n, taken_o, pick = set(), set(), {}
    for s, ni, i, found in cands:                      # greedy one-to-one assignment
        if s < a.min_score or ni in taken_n or i in taken_o:
            continue
        taken_n.add(ni); taken_o.add(i); pick[ni] = (s, i, found)
    rows = []
    for ni, n in enumerate(nist):
        vals = [v for t in n['tables'] for row in t['rows'] for cell in row for v in numbers(cell)]
        rec = {'sheet_id': n['sheet_id'], 'system': n['system_name'], 'score': '', 'dup': '',
               'page': '', 'index_on_page': '', 'n_values': len(vals), 'n_found': 0, 'recall': '', 'missing': ''}
        if ni in pick:
            s, i, found = pick[ni]; o = anchors[i]
            rec.update(score=round(s, 2), page=o['page'], index_on_page=o['index_on_page'], n_found=len(found),
                       recall=round(len(found) / len(vals), 2) if vals else '',
                       missing=' '.join(v for v in vals if v not in found)[:120])
        rows.append(rec)
    out = ROOT / 'nist' / f'align-SDS-{a.volume}.csv'
    with out.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['sheet_id', 'system', 'score', 'page', 'index_on_page', 'dup',
                                          'n_values', 'n_found', 'recall', 'missing'])
        w.writeheader(); w.writerows(rows)
    aligned = [r for r in rows if r['page'] != '']
    dups = sum(1 for r in aligned if r.get('dup'))
    nv, nf = sum(r['n_values'] for r in aligned), sum(r['n_found'] for r in aligned)
    un = [r for r in rows if r['page'] == '']
    print(f'unaligned: {[r["sheet_id"] for r in un][:20]}')
    kinds = {k: sum(n['kind'] == k for n in nist) for k in ('compilation', 'evaluation')}
    print(f'SDS-{a.volume}: {len(nist)} NIST sheets with tables {kinds}, {len(anchors)} OCR sheets; '
          f'aligned {len(aligned)} (score >= {a.min_score}), {dups} OCR sheets matched twice')
    print(f'table numeric tokens: {nv}, found verbatim in OCR box: {nf} ({nf / nv:.1%})' if nv else 'no values')
    low = sorted((r for r in aligned if r['recall'] != '' and r['recall'] < 0.8), key=lambda r: r['recall'])
    print(f'{len(low)} aligned sheets with recall < 0.8; worst:')
    for r in low[:8]:
        print(f"  {r['sheet_id']:8s} p{r['page']:<4} recall {r['recall']}  missing: {r['missing'][:80]}")
    print(f'-> {out.relative_to(ROOT)}')


main()
