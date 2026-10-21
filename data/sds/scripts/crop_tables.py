"""Crop the EXPERIMENTAL VALUES band of every SDS data sheet to PNG, from the word
coordinates of the embedded text layer (pdftotext -bbox) and pdftoppm.

Usage: python -I crop_tables.py SDS-60.pdf out_dir [--dpi 300] [--rows] [--pages 41,42]

Band mode (default): one PNG per table band, from the EXPERIMENTAL VALUES header
down to the next AUXILIARY INFORMATION banner (or next COMPONENTS header, or the
last word on the page). A page whose first banner precedes any header continues
the previous sheet's table, so its top part is cropped too. Files p<page>_<n>.png.

Row mode (--rows): the same bands, but one PNG per printed text line inside the
band (words clustered by their y coordinate), files p<page>_<n>_r<line>.png. Use
it when the band pass does not return one table row per printed row.

Both modes write manifest.csv: file, page, band, line, y0, y1 (points), n_lines
(text lines inside the band, header lines included).
"""
import argparse, csv, pathlib, re, subprocess, sys
from xml.etree import ElementTree as ET

ap = argparse.ArgumentParser()
ap.add_argument('pdf', type=pathlib.Path)
ap.add_argument('out', type=pathlib.Path)
ap.add_argument('--dpi', type=int, default=300)
ap.add_argument('--rows', action='store_true')
ap.add_argument('--pages', help='comma-separated page numbers to process (default all)')
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
only = {int(p) for p in a.pages.split(',')} if a.pages else None

xml = subprocess.run(['pdftotext', '-bbox', str(a.pdf), '-'], check=True, capture_output=True, text=True).stdout
xml = re.sub(r'<!DOCTYPE[^>]*>', '', xml)
ns = {'h': 'http://www.w3.org/1999/xhtml'}
pages = ET.fromstring(xml).findall('.//h:page', ns)

HEAD = re.compile(r'^EXPER[Il1]MENTAL$', re.I)
AUX = re.compile(r'^AUX[Il1]L[Il1]ARY$', re.I)
COMP = re.compile(r'^C[O0]MP[O0]NENTS', re.I)


def lines_of(words, y0, y1):
    """Cluster the words inside [y0, y1) into text lines by their vertical centre.

    Line pitch in the sheets (about 8 pt) is smaller than the word height (about
    10 pt, more with super/subscripts), so boxes of neighbouring rows overlap and
    centres are used. Returns (top, bottom) per line, half a pitch around the centre.
    """
    ws = sorted(((w0 + w1) / 2, w1 - w0) for w0, w1, _ in words if y0 <= w0 < y1)
    if not ws:
        return []
    h = sorted(d for _, d in ws)[len(ws) // 2]
    groups = [[ws[0][0]]]
    for c, _ in ws[1:]:
        ref = sum(groups[-1]) / len(groups[-1])
        (groups[-1].append(c) if abs(c - ref) <= 0.45 * h else groups.append([c]))
    half = max(5.0, 0.55 * h)
    return [(sum(g) / len(g) - half, sum(g) / len(g) + half) for g in groups]


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
    heads = [y0 for y0, y1, t in words if HEAD.match(t)]
    stops = sorted([y0 for y0, y1, t in words if AUX.match(t)] + [y0 for y0, y1, t in words if COMP.match(t)])
    bands = []
    if open_band and words:
        first_head = heads[0] if heads else H
        first_stop = next((s for s in stops if s < first_head), None)
        bands.append((max(0.0, words[0][0] - 4), first_stop - 4 if first_stop else H))
    for y in heads:
        stop = next((s for s in stops if s > y + 5), None)
        bands.append((y - 4, stop - 4 if stop else H))
    open_band = bool(bands) and bands[-1][1] >= H
    if only and pno not in only:
        continue
    for i, (y0, y1) in enumerate(bands):
        lines = lines_of(words, y0, y1)
        if lines:
            y1 = min(y1, lines[-1][1] + 12)                    # trim blank space under short tables
        if y1 - y0 < 20:
            continue
        if a.rows:
            for j, (l0, l1) in enumerate(lines):
                name = f'p{pno:03d}_{i}_r{j:02d}'
                render(pno, l0, l1, W, a.out / name)
                manifest.append((name + '.png', pno, i, j, round(l0, 1), round(l1, 1), len(lines)))
        else:
            name = f'p{pno:03d}_{i}'
            render(pno, y0, y1, W, a.out / name)
            manifest.append((name + '.png', pno, i, '', round(y0, 1), round(y1, 1), len(lines)))
with (a.out / 'manifest.csv').open('w', newline='') as f:
    w = csv.writer(f); w.writerow(['file', 'page', 'band', 'line', 'y0', 'y1', 'n_lines']); w.writerows(manifest)
print(f'{len(manifest)} crops -> {a.out}', file=sys.stderr)
