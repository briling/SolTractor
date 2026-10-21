"""Survey CAS Registry Numbers in the segmented COMPONENTS boxes and in the NIST ground truth.

Usage: python -I cas_survey.py [--examples 10]

For every boxes/SDS-N.jsonl, CAS-shaped strings in the COMPONENTS box are
validated by their check digit (textnorm.cas_valid); the same is done for the
components keyed by NIST in nist/SDS-N.json. A failing check digit in the OCR
side points at an OCR error (or a list number glued to the CAS number); on the
NIST side it points at a keying error in the database.
"""
import argparse, collections, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from textnorm import cas_valid, strict  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOOSE_CAS = re.compile(r'(?<!\d)\d{2,7}\s?[-·‑]\s?\d{2}\s?[-·‑]\s?\d(?!\d)')


def norm(c: str) -> str:
    return re.sub(r'\s', '', c).replace('·', '-').replace('‑', '-')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--examples', type=int, default=10)
    a = ap.parse_args()
    print(f'{"volume":8s} {"sheets":>6s} {"noCAS":>6s} {"CAS":>6s} {"ok":>6s} {"bad":>5s} {"bad%":>5s}')
    tot, bad_ex = [0] * 5, collections.Counter()
    for f in sorted((ROOT / 'boxes').glob('SDS-*.jsonl'), key=lambda p: int(p.stem.split('-')[1])):
        n = [0] * 5                                   # sheets, no cas, cas, ok, bad
        for line in f.open():
            r = json.loads(line); n[0] += 1
            found = [norm(c) for c in LOOSE_CAS.findall(strict(r['boxes'].get('components', '')))]
            n[1] += not found
            for c in found:
                n[2] += 1
                if cas_valid(c): n[3] += 1
                else: n[4] += 1; bad_ex[c] += 1
        tot = [t + x for t, x in zip(tot, n)]
        print(f'{f.stem:8s} {n[0]:6d} {n[1]:6d} {n[2]:6d} {n[3]:6d} {n[4]:5d} {100 * n[4] / n[2] if n[2] else 0:5.1f}')
    print(f'{"TOTAL":8s} {tot[0]:6d} {tot[1]:6d} {tot[2]:6d} {tot[3]:6d} {tot[4]:5d} {100 * tot[4] / tot[2]:5.1f}')
    print('most frequent failing OCR CAS:', bad_ex.most_common(a.examples))
    print('\nNIST ground truth')
    for f in sorted((ROOT / 'nist').glob('SDS-*.json'), key=lambda p: int(p.stem.split('-')[1])):
        recs = json.load(f.open())
        cas = [c['cas'] for r in recs for c in r['components_parsed']]
        bad = sorted({c for c in cas if not cas_valid(c)})
        print(f'{f.stem:8s} sheets {len(recs):4d}  CAS {len(cas):5d}  bad {len(bad):3d} {bad[:6]}')


main()
