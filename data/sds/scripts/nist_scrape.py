"""Scrape the IUPAC-NIST Solubility Database (SRD 106) for one or more SDS volumes.

Usage: python -I nist_scrape.py 60 [62 ...] [--delay 0.5]

Writes nist/SDS-<vol>.json with one record per compilation/evaluation sheet
(the boxes of the printed form as keyed by NIST, plus the experimental table as
headers and rows). Raw HTML is cached in nist/raw/ so reruns do not hit the
server. Only the standard library is used.
"""
import argparse, html, json, pathlib, re, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = 'https://srdata.nist.gov/solubility/'
SERIES = {20: 'DS1', 37: 'DS8', 38: 'DS9', 57: 'DS18', 58: 'DS6', 59: 'DS7', 60: 'DS2',
          62: 'DS16', 66: 'DS15', 67: 'DS3', 68: 'DS4', 69: 'DS5', 70: 'DS17', 71: 'DS10',
          72: 'DS12', 73: 'DS14', 77: 'DS11', 78: 'DS13'}
HEADERS = {'User-Agent': 'Mozilla/5.0 (sds-extraction research scraper)'}
BOXES = {'SysName': 'system', 'compValue': 'components', 'MeasValue': 'original_measurements',
         'VariValue': 'variables', 'prepValue': 'prepared_by', 'ExpRValue': 'critical_evaluation',
         'ExpDValue': 'experimental_values', 'NoteValue': 'notes', 'MethValue': 'method',
         'SrcValue': 'source_purity', 'ErrValue': 'estimated_error', 'RefValue': 'references'}


def fetch(url: str, cache: pathlib.Path, delay: float, data: dict | None = None) -> str:
    if cache.exists():
        return cache.read_text()
    req = urllib.request.Request(url, headers=HEADERS,
                                 data=urllib.parse.urlencode(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode('utf-8', errors='replace')
    cache.write_text(text)
    time.sleep(delay)
    return text


def form_fields(page: str) -> dict:
    return {m.group(1): html.unescape(m.group(2)) for m in
            re.finditer(r'<input type="hidden" name="(__\w+)" id="__\w+" value="([^"]*)"', page)}


def span(page: str, label: str) -> str | None:
    m = re.search(rf'<span id="MainContentPlaceHolder_lbl_{label}"[^>]*>(.*?)</span>\s*(?:<br\s*/?>\s*)*(?=<|$)',
                  page, re.S)
    return m.group(1) if m else None


def to_text(fragment: str) -> str:
    """HTML fragment -> plain text; sub/sup become _x / ^x, <br> become newlines."""
    f = re.sub(r'<a [^>]*>NIST Chemistry WebBook</a> for detail', '', fragment)
    f = re.sub(r'<sub>(.*?)</sub>', r'_\1', f, flags=re.S)
    f = re.sub(r'<sup>(.*?)</sup>', r'^\1', f, flags=re.S)
    f = re.sub(r'<br\s*/?>', '\n', f, flags=re.I)
    f = re.sub(r'<[^>]+>', '', f)
    f = html.unescape(f).replace('\xa0', ' ')
    return '\n'.join(line.strip() for line in f.split('\n')).strip()


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell, self.headers = [], None, None, []
        self.sub = self.sup = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row = []
        elif tag in ('td', 'th'): self.cell = [tag, '']
        elif tag == 'sub' and self.cell is not None: self.cell[1] += '_'
        elif tag == 'sup' and self.cell is not None: self.cell[1] += '^'

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None and self.row is not None:
            self.row.append((self.cell[0], re.sub(r'\s+', ' ', self.cell[1]).strip(' ^_')))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.row and all(k == 'th' for k, _ in self.row) and not self.headers:
                self.headers = [v for _, v in self.row]
            elif self.row:
                self.rows.append([v for _, v in self.row])
            self.row = None

    def handle_data(self, data):
        if self.cell is not None: self.cell[1] += data


def parse_tables(fragment: str) -> list[dict]:
    out = []
    for t in re.findall(r'<table.*?</table>', fragment, re.S):
        p = TableParser(); p.feed(t)
        out.append({'headers': p.headers, 'rows': p.rows})
    return out


def parse_components(text: str) -> list[dict]:
    comps = []
    for line in text.split('\n'):
        m = re.match(r'\((\d+)\)\s*(.*?);\s*([^;]*?);\s*\[([\d\-]+)\]', line)
        if m:
            comps.append({'index': int(m.group(1)), 'name': m.group(2).strip(),
                          'formula': m.group(3).strip(), 'cas': m.group(4)})
    return comps


def parse_detail(page: str, sheet_id: str, system_id: str, url: str) -> dict:
    rec = {'sheet_id': sheet_id, 'system_id': system_id, 'url': url}
    for label, key in BOXES.items():
        frag = span(page, label)
        rec[key] = to_text(frag) if frag else ''
    rec['components_parsed'] = parse_components(rec['components'])
    tbl = span(page, 'Table') or ''
    rec['tables'] = parse_tables(tbl)
    rec['kind'] = 'evaluation' if rec['critical_evaluation'] else 'compilation'
    return rec


def sheet_ids(list_page: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'sol_detail\.aspx\?goBack=Y&amp;sysID=([\d_]+)', list_page)))


def scrape_volume(vol: int, delay: float) -> None:
    ds = SERIES[vol]
    raw = ROOT / 'nist' / 'raw' / f'SDS-{vol}'
    raw.mkdir(parents=True, exist_ok=True)
    vol_page = fetch(f'{BASE}sol_sys.aspx?nm_dataSeries={ds}', raw / 'systems.html', delay)
    systems = re.findall(r'sysID=(\d+)&amp;SerialID=' + ds + r'[^>]*>([^<]*)', vol_page)
    print(f'SDS-{vol} ({ds}): {len(systems)} systems', flush=True)
    records = []
    for sys_id, sys_name in systems:
        list_url = f'{BASE}sol_sys_lst.aspx?goBack=Y&sysID={sys_id}&SerialID={ds}'
        page = fetch(list_url, raw / f'sys_{sys_id}_p1.html', delay)
        ids = sheet_ids(page)
        npage = 2
        while f'Page${npage}' in page:
            fields = form_fields(page)
            fields.update({'__EVENTTARGET': 'ctl00$MainContentPlaceHolder$GridView1',
                           '__EVENTARGUMENT': f'Page${npage}'})
            page = fetch(list_url, raw / f'sys_{sys_id}_p{npage}.html', delay, data=fields)
            ids += sheet_ids(page)
            npage += 1
        ids = list(dict.fromkeys(ids))
        for sid in ids:
            url = f'{BASE}sol_detail.aspx?goBack=Y&sysID={sid}'
            detail = fetch(url, raw / f'detail_{sid}.html', delay)
            rec = parse_detail(detail, sid, sys_id, url)
            rec['system_name'] = html.unescape(sys_name)
            records.append(rec)
        print(f'  {sys_id} {html.unescape(sys_name)}: {len(ids)} sheets ({npage - 1} pages)', flush=True)
    out = ROOT / 'nist' / f'SDS-{vol}.json'
    out.write_text(json.dumps(records, indent=1, ensure_ascii=False))
    kinds = {k: sum(r['kind'] == k for r in records) for k in ('compilation', 'evaluation')}
    print(f'SDS-{vol}: {len(records)} sheets {kinds} -> {out.relative_to(ROOT)}', flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volumes', nargs='+', type=int, choices=sorted(SERIES))
    ap.add_argument('--delay', type=float, default=0.5)
    a = ap.parse_args()
    for v in a.volumes:
        scrape_volume(v, a.delay)


main()
