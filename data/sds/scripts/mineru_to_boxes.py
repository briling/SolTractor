"""Convert MinerU structured_content.json of an SDS volume into the boxes jsonl format of segment_boxes.py.

Usage: python -I mineru_to_boxes.py SDS-60/extracted/structured_content.json SDS-60/boxes/SDS-60.jsonl

MinerU renders every data sheet as one HTML table whose cells are the printed boxes.
A sheet starts at a cell beginning with COMPONENTS; its other cells are assigned to
boxes by their printed header. Row text of the EXPERIMENTAL VALUES table is kept
as MinerU emits it (rows may be run together).
"""
import html, json, pathlib, re, sys

HEADERS = {
    'COMPONENTS': 'components', 'ORIGINAL MEASUREMENTS': 'original_measurements', 'EVALUATOR': 'evaluator',
    'VARIABLES': 'variables', 'PREPARED BY': 'prepared_by', 'EXPERIMENTAL VALUES': 'experimental_values',
    'CRITICAL EVALUATION': 'critical_evaluation', 'METHOD/APPARATUS/PROCEDURE': 'method', 'METHOD': 'method',
    'SOURCE AND PURITY OF MATERIALS': 'source_purity', 'ESTIMATED ERRORS': 'estimated_error',
    'ESTIMATED ERROR': 'estimated_error', 'REFERENCES': 'references', 'AUXILIARY INFORMATION': None,
}
HEAD_RE = re.compile(r'^\s*(' + '|'.join(re.escape(h) for h in sorted(HEADERS, key=len, reverse=True)) + r')\s*:?\s*', re.I)
TAG = re.compile(r'<[^>]+>')


def clean(cell: str) -> str:
    cell = re.sub(r'\$([^$]*)\$', r'\1', cell)             # inline LaTeX markers
    cell = cell.replace('<br>', '\n').replace('<br/>', '\n')
    return html.unescape(TAG.sub(' ', cell)).strip()


def sheets_of_table(table_html: str, page: int, start_index: int) -> list[dict]:
    cells = [clean(c) for r in re.findall(r'<tr>(.*?)</tr>', table_html, re.S)
             for c in re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)]
    out, cur, last = [], None, None
    for c in cells:
        m = HEAD_RE.match(c)
        head = HEADERS.get(m.group(1).upper()) if m else None
        if m and m.group(1).upper() == 'COMPONENTS':
            cur = {'kind': 'compilation', 'continued': False, 'col_header': None, 'boxes': {}, 'flags': [],
                   'volume': None, 'page': page, 'index_on_page': start_index + len(out), 'preamble': ''}
            out.append(cur)
        if cur is None:
            continue
        if m and head:
            cur['boxes'][head] = (cur['boxes'].get(head, '') + '\n' + c[m.end():]).strip()
            last = head
            if head == 'evaluator' or head == 'critical_evaluation':
                cur['kind'] = 'evaluation'
        elif m:                                              # AUXILIARY INFORMATION banner
            last = None
        elif last in ('experimental_values', 'critical_evaluation') or last is None:
            key = 'critical_evaluation' if cur['kind'] == 'evaluation' else 'experimental_values'
            cur['boxes'][key] = (cur['boxes'].get(key, '') + '\n' + c).strip()
        else:
            cur['boxes'][last] = (cur['boxes'].get(last, '') + '\n' + c).strip()
    return out


def main() -> None:
    src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    doc = json.load(src.open())
    vol = dst.stem
    records = []
    for p in doc['pages']:
        page = p['page_idx'] + 1
        n = 0
        for b in p['blocks']:
            if b['type'] != 'table':
                continue
            recs = sheets_of_table(b['content'], page, n)
            # a table without COMPONENTS continues the previous sheet (second page of a long table)
            if not recs and records and records[-1]['page'] == page - 1:
                cont = dict(records[-1]); cont = json.loads(json.dumps(records[-1]))
                cont.update(continued=True, page=page, index_on_page=n)
                cont['boxes'] = {'components': records[-1]['boxes'].get('components', ''),
                                 'original_measurements': records[-1]['boxes'].get('original_measurements', ''),
                                 'experimental_values': clean(b['content'])}
                recs = [cont]
            n += len(recs)
            records.extend(recs)
    for r in records:
        r['volume'] = vol
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open('w') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    kinds = {k: sum(r['kind'] == k for r in records) for k in ('compilation', 'evaluation')}
    print(f'{len(records)} sheets {kinds}, {sum(r["continued"] for r in records)} continuations -> {dst}')


main()
