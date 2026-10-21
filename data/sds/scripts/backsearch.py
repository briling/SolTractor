"""Check extracted values against a volume's cached text layer.

Usage: python -I backsearch.py SDS-N value [value ...] [--page N] [--context 30]

Two match tiers. STRICT: single spaces inside numbers/CAS numbers are removed
("2 9 8 . 15" -> "298.15") while multi-space column gaps are kept; spaces
before punctuation are dropped; a few OCR confusions are folded. LOOSE:
only lowercase alphanumerics are compared, which survives any spacing or
punctuation noise. Each value is reported as OK/ELSEWHERE/MISSING against
the expected page (or FOUND/MISSING without one), with the tier that hit.
Exit status 1 if any value is not OK/FOUND.
"""
import argparse, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from textnorm import loose, strict  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume', help='e.g. SDS-1')
    ap.add_argument('values', nargs='+')
    ap.add_argument('--page', type=int, help='expected PDF page (1-based)')
    ap.add_argument('--context', type=int, default=0, help='chars of context to print')
    a = ap.parse_args()
    pages = (ROOT / 'text' / f'{a.volume}.txt').read_text(errors='replace').split('\f')
    tiers = [('strict', [strict(p) for p in pages]), ('loose', [loose(p) for p in pages])]
    ok = True
    for v in a.values:
        hits, tier_used, nv = [], None, None
        for tier, npages in tiers:
            nv = strict(v) if tier == 'strict' else loose(v)
            hits = [i + 1 for i, p in enumerate(npages) if nv in p]
            if hits:
                tier_used = tier
                break
        if a.page:
            status = 'OK' if a.page in hits else ('ELSEWHERE' if hits else 'MISSING')
            ok &= status == 'OK'
        else:
            status = 'FOUND' if hits else 'MISSING'
            ok &= bool(hits)
        shown = hits[:8] + (['...'] if len(hits) > 8 else [])
        print(f'{status:9s} {tier_used or "-":6s} {v!r:34s} pages {shown}')
        if a.context and hits:
            pg = a.page if a.page in hits else hits[0]
            p = dict(tiers)[tier_used][pg - 1]
            i = p.index(nv)
            print(' ' * 10 + '...' + p[max(0, i - a.context): i + len(nv) + a.context] + '...')
    sys.exit(0 if ok else 1)


main()
