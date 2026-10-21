"""Replace the EXPERIMENTAL VALUES box of MinerU whole-page sheets by the table read from the crop pass.

Usage: python -I crops_to_boxes.py boxes-page.jsonl crops/tables.jsonl boxes-crops.jsonl

The second argument is either a folder with one MinerU output folder per crop
(p<page>_<band>/structured_content.json, as the node returns them) or the
tables.jsonl condensed from it (one line per crop: {"crop": ..., "blocks": [...]}).
Bands on a page map in order onto the compilation sheets of that page (a leading
continuation record takes band 0). The table becomes one line per row, cells
separated by " | "; a crop with no table keeps the whole-page text.
"""
import html, json, pathlib, re, sys

src, crops, dst = map(pathlib.Path, sys.argv[1:4])


def table_text(doc) -> str | None:
    for p in doc['pages']:
        for b in p['blocks']:
            if b['type'] != 'table':
                continue
            c = b['content'] if isinstance(b['content'], str) else ' '.join(x.get('content', '') for x in b['content'])
            if '<table' in c:
                rows = [[html.unescape(re.sub(r'<[^>]+>', '', td)).strip() for td in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)]
                        for r in re.findall(r'<tr[^>]*>(.*?)</tr>', c, re.S)]
            else:                                        # markdown pipe table
                rows = [[x.strip() for x in l.strip().strip('|').split('|')] for l in c.splitlines()
                        if l.strip().startswith('|') and not re.match(r'^\|?\s*-', l.strip())]
            text = '\n'.join(' | '.join(r) for r in rows)
            return text.replace('$', '').replace('\\times', '×')
    return None


crop = {}
if crops.is_dir():
    for d in sorted(crops.iterdir()):
        f = next(d.rglob('structured_content.json'), None)
        if f:
            crop[d.name] = table_text(json.load(f.open()))
else:
    for line in crops.open():
        rec = json.loads(line)
        crop[rec['crop'].removesuffix('.png')] = table_text({'pages': [{'blocks': rec['blocks']}]})
records = [json.loads(l) for l in src.open()]
by_page = {}
for r in records:
    by_page.setdefault(r['page'], []).append(r)
NUM = re.compile(r'\d+(?:\.\d+)?')
used, no_table, unmatched = 0, 0, 0
for page, recs in by_page.items():
    bands = [k for k in sorted(crop) if k.startswith(f'p{page:03d}_') and crop[k]]
    targets = [r for r in recs if r['kind'] == 'compilation']
    no_table += sum(1 for k in crop if k.startswith(f'p{page:03d}_') and not crop[k])
    # each crop goes to the sheet on its page whose whole-page table text shares most numeric tokens
    taken = set()
    for name in bands:
        toks = [t for t in NUM.findall(crop[name]) if len(t) >= 3]
        best = max(((sum(1 for t in toks if t in r['boxes'].get('experimental_values', '')), i)
                    for i, r in enumerate(targets) if i not in taken), default=(0, None))
        if best[1] is None or (toks and best[0] == 0):
            unmatched += 1
            continue
        r = targets[best[1]]; taken.add(best[1])
        r['boxes']['experimental_values'] = crop[name]
        r['flags'] = r.get('flags', []) + ['crop_table']
        used += 1
with dst.open('w') as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'{used} sheets took the crop table, {no_table} crops without table, {unmatched} crops without a matching sheet -> {dst}')
