"""Tally the table-header lines found under EXPERIMENTAL VALUES in an SDS volume.

Usage: python -I scan_columns.py SDS-N [--top 25] [--lines 3]
"""
import argparse, collections, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from paths import volume_root  # noqa: E402

START = re.compile(r'EXPERIMENTAL\s+VALUES', re.I)
END = re.compile(r'AUXILIARY\s+INFORMATION|METHOD\s*[/:]|COMPONENTS\s*:|SOURCE\s+AND\s+PURITY', re.I)
NUMERIC_ROW = re.compile(r'^[\s\d.,±xX×+\-/()e]+$')


def normalize(line: str) -> str:
    line = re.sub(r'(?<=\d) (?=\d)', '', line)          # OCR-spaced digits "2 9 8 . 15"
    line = re.sub(r'(?<=\d) \. (?=\d)', '.', line)
    line = re.sub(r'\s{2,}', ' | ', line.strip())        # column gaps -> separator
    return line


def sheets(volume: str):
    """Yield EXPERIMENTAL VALUES blocks from the cached text layer text/<volume>.txt."""
    cache = volume_root(volume) / 'text' / f'{volume}.txt'
    text = cache.read_text(errors='replace')
    for page in text.split('\f'):
        m = START.search(page)
        while m:
            rest = page[m.end():]
            e = END.search(rest)
            block = rest[: e.start()] if e else rest
            yield block
            m = START.search(rest, e.end()) if e else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume', help='e.g. SDS-30 (reads text/SDS-30.txt)')
    ap.add_argument('--top', type=int, default=25)
    ap.add_argument('--lines', type=int, default=3, help='header lines to take per sheet')
    ap.add_argument('--tokens', action='store_true',
                    help='count individual column cells instead of whole header lines')
    a = ap.parse_args()
    headers, n = collections.Counter(), 0
    noise = re.compile(r'^(\(?compiler\)?|\(?authors?\)?|[:;.,|() ]*|\(continued\))$', re.I)
    for block in sheets(a.volume):
        n += 1
        lines = [normalize(l) for l in block.splitlines() if l.strip()]
        head = []
        for l in lines:
            if NUMERIC_ROW.match(l.replace('|', '')):
                break                                    # first data row ends the header
            head.append(l)
            if len(head) >= a.lines:
                break
        if head and a.tokens:
            for cell in re.split(r'\s*\|\s*|\s*//\s*', ' | '.join(head)):
                cell = cell.strip(' :;.,')
                if cell and not noise.match(cell) and len(cell) < 40:
                    headers[cell] += 1
        elif head:
            headers[' // '.join(head)] += 1
    print(f'{a.volume}: {n} EXPERIMENTAL VALUES blocks, {len(headers)} distinct headers')
    for h, c in headers.most_common(a.top):
        print(f'{c:5d}  {h[:150]}')


main()
