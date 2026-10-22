"""Crop the EXPERIMENTAL VALUES band of every SDS data sheet to PNG, from the word
coordinates of the embedded text layer (pdftotext -bbox) and pdftoppm.

Usage: python -I crop_tables.py SDS-60.pdf out_dir [--dpi 300] [--rows] [--pages 41,42] [--manifest-only]

Band mode (default): one PNG per table band, from the EXPERIMENTAL VALUES header
down to the next closing banner (AUXILIARY INFORMATION, or its second word when the
first is unreadable, METHOD, COMMENTS, the next COMPONENTS header) or the last word
on the page. A page whose first banner precedes any header continues the previous
sheet's table, so its top part is cropped too. Files p<page>_<n>.png.

Only data-sheet pages are cut: a header counts when it is printed in capitals on a
page that carries the sheet frame (two or more printed field names such as COMPONENTS,
ORIGINAL MEASUREMENTS, VARIABLES; or the page continues an open band). This keeps front matter and evaluation chapters, where
"experimental" occurs in prose, out of the crops. Bands with the same vertical
range are emitted once.

Row mode (--rows): the same bands, but one PNG per printed text line inside the
band (words clustered by their y coordinate), files p<page>_<n>_r<line>.png. Use
it when the band pass does not return one table row per printed row.

Both modes write manifest.csv: file, page, band, line, y0, y1 (points), n_lines
(text lines inside the band, header lines included) and n_num_lines (lines with at
least two numeric tokens: the table rows, roughly, for the node's row-count check).
--manifest-only writes the manifest without rendering, to inspect the bands.
"""
import argparse, csv, pathlib, re, subprocess, sys
from xml.etree import ElementTree as ET

ap = argparse.ArgumentParser()
ap.add_argument('pdf', type=pathlib.Path)
ap.add_argument('out', type=pathlib.Path)
ap.add_argument('--dpi', type=int, default=300)
ap.add_argument('--rows', action='store_true')
ap.add_argument('--pages', help='comma-separated page numbers to process (default all)')
ap.add_argument('--manifest-only', action='store_true', help='write manifest.csv only, render nothing')
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
only = {int(p) for p in a.pages.split(',')} if a.pages else None

xml = subprocess.run(['pdftotext', '-bbox', str(a.pdf), '-'], check=True, capture_output=True, text=True).stdout
xml = re.sub(r'<!DOCTYPE[^>]*>', '', xml)
ns = {'h': 'http://www.w3.org/1999/xhtml'}
pages = ET.fromstring(xml).findall('.//h:page', ns)

# printed headers are set in capitals; the patterns allow the usual OCR confusions but no lowercase
HEAD = re.compile(r'^EXPER[Il1]MENTAL$')
AUX = re.compile(r'^AUX[Il1]L[Il1]ARY$|^[Il1]NF[O0]RMAT[Il1][O0]N:?$')
COMP = re.compile(r'^C[O0]MP[O0]NENTS')
FRAME = re.compile(r'^(C[O0]MP[O0]NENTS|[O0]R[Il1]G[Il1]NAL|MEASUREMENTS|VAR[Il1]ABLES|PREPARED|AUX[Il1]L[Il1]ARY|EST[Il1]MATED|REFERENCES|S[O0]URCE)')
STOP = re.compile(r'^METH[O0]D|^C[O0]MMENTS$')          # closing words used when the banner is missing
INDEX = re.compile(r'^[Il1]NDEX$')
NUM = re.compile(r'\d')


def lines_of(words, y0, y1):
    """Cluster the words inside [y0, y1) into text lines by their vertical centre.

    Line pitch in the sheets (about 8 pt) is smaller than the word height (about
    10 pt, more with super/subscripts), so boxes of neighbouring rows overlap and
    centres are used. Returns (top, bottom, n_numeric) per line, half a pitch
    around the centre.
    """
    ws = sorted(((w0 + w1) / 2, w1 - w0, t) for w0, w1, t in words if y0 <= w0 < y1)
    if not ws:
        return []
    h = sorted(d for _, d, _ in ws)[len(ws) // 2]
    groups = [[ws[0]]]
    for w in ws[1:]:
        ref = sum(c for c, _, _ in groups[-1]) / len(groups[-1])
        (groups[-1].append(w) if abs(w[0] - ref) <= 0.45 * h else groups.append([w]))
    half = max(5.0, 0.55 * h)
    out = []
    for g in groups:
        c = sum(x for x, _, _ in g) / len(g)
        out.append((c - half, c + half, sum(1 for _, _, t in g if NUM.search(t))))
    return out


def render(pno, y0, y1, W, out):
    s = a.dpi / 72
    subprocess.run(['pdftoppm', '-png', '-r', str(a.dpi), '-f', str(pno), '-l', str(pno), '-singlefile',
                    '-x', '0', '-y', str(int(y0 * s)), '-W', str(int(W * s)), '-H', str(int((y1 - y0) * s)),
                    str(a.pdf), str(out)], check=True)


manifest = []
open_band = False                    # the last band of the previous page ran to the page bottom
for pno, page in enumerate(pages, 1):
    W, H = float(page.get('width')), float(page.get('height'))
    words = sorted((float(w.get('yMin')), float(w.get('yMax')), w.text or '') for w in page.findall('h:word', ns))
    comps = [y0 for y0, y1, t in words if COMP.match(t)]
    sheet_page = len({FRAME.match(t).group(1) for y0, y1, t in words if FRAME.match(t)}) >= 2
    # a header is EXPERIMENTAL in capitals on a page that carries the sheet frame (two or more of its
    # printed field names; COMPONENTS alone is often unreadable); VALUES is often lost by the OCR
    # the volume's indexes (SYSTEM INDEX, REGISTRY NUMBER INDEX, AUTHOR INDEX) follow the last sheet and would
    # continue its open band page after page; a page naming an index without any frame word closes the band
    index_page = not sheet_page and any(INDEX.match(t) for y0, y1, t in words)
    heads = [y0 for y0, y1, t in words if HEAD.match(t)] if sheet_page or (open_band and not index_page) else []
    stops = sorted([y0 for y0, y1, t in words if AUX.match(t) or STOP.match(t)] + comps)
    bands = []
    if open_band and words and not index_page:
        first_head = heads[0] if heads else H
        first_stop = next((s for s in stops if s < first_head), None)
        bands.append((max(0.0, words[0][0] - 4), first_stop - 4 if first_stop else H))
    for y in heads:
        stop = next((s for s in stops if s > y + 5), None)
        bands.append((y - 4, stop - 4 if stop else H))
    # the same band twice (a continuation band that also carries a header on the same line)
    uniq = []
    for b in bands:
        if not any(abs(b[0] - u[0]) < 6 and abs(b[1] - u[1]) < 6 for u in uniq):
            uniq.append(b)
    bands = uniq
    open_band = bool(bands) and bands[-1][1] >= H
    if only and pno not in only:
        continue
    for i, (y0, y1) in enumerate(bands):
        lines = lines_of(words, y0, y1)
        if lines:
            y1 = min(y1, lines[-1][1] + 12)                    # trim blank space under short tables
        if y1 - y0 < 20:
            continue
        n_num = sum(1 for _, _, n in lines if n >= 2)
        if i == 0 and y0 < 20 and n_num == 0:                 # a continuation band holding only the page number
            continue
        if a.rows:
            for j, (l0, l1, _) in enumerate(lines):
                name = f'p{pno:03d}_{i}_r{j:02d}'
                if not a.manifest_only:
                    render(pno, l0, l1, W, a.out / name)
                manifest.append((name + '.png', pno, i, j, round(l0, 1), round(l1, 1), len(lines), n_num))
        else:
            name = f'p{pno:03d}_{i}'
            if not a.manifest_only:
                render(pno, y0, y1, W, a.out / name)
            manifest.append((name + '.png', pno, i, '', round(y0, 1), round(y1, 1), len(lines), n_num))
with (a.out / 'manifest.csv').open('w', newline='') as f:
    w = csv.writer(f); w.writerow(['file', 'page', 'band', 'line', 'y0', 'y1', 'n_lines', 'n_num_lines']); w.writerows(manifest)
print(f'{len(manifest)} crops -> {a.out}', file=sys.stderr)
