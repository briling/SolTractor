"""Compare the CAS numbers printed on SDS sheets with an external registry (PubChem).

Usage: python -I cas_resolve.py [--limit N] [--delay 0.25]

Collects every CAS-shaped string in the COMPONENTS boxes of boxes/SDS-*.jsonl
together with the printed name and formula next to it, resolves the string in
PubChem (PUG REST: title and molecular formula; responses cached in
cas/pubchem-cache.json), and compares the printed formula with the resolved
one, element by element, allowing the OCR confusions 0/O and I/l, and the
printed name with the PubChem title (loose, alphanumerics only). The formula
test is weak evidence because the OCR drops subscripts ("C H" for C2H4), so a
CAS counts as `ok` when the check digit holds, PubChem knows it, and either the
formula or the name agrees. For strings that fail the check digit, that PubChem
does not know, or whose name and formula both disagree, the printed name is
looked up the other way and the registry numbers PubChem lists for that
compound are recorded as `suggested_cas`; a round trip to the same CAS counts
as confirmation (`ok_via_name`).

Writes cas/cas_resolved.csv, one row per distinct CAS string.
"""
import argparse, collections, csv, json, pathlib, re, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from textnorm import cas_valid, loose, strict  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUG = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/'
CAS = re.compile(r'(?<!\d)\d{2,7}-\d{2}-\d(?!\d)')
COMPONENT = re.compile(r'(?:\(\s*\d\s*\)|^\s*\d\s*\.)?\s*([^;\[\]]{3,80}?)\s*;\s*([A-Za-z0-9().·\s]{1,30}?)\s*;?\s*[\[(]?\s*(\d{2,7}-\d{2}-\d)', re.M)
ELEMENT = re.compile(r'([A-Z][a-z]?)(\d*)')


def pug(path: str, cache: dict, delay: float) -> dict | None:
    if path in cache:
        return cache[path]
    try:
        with urllib.request.urlopen(PUG + path, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        data = None if e.code == 404 else {'error': e.code}
    except (urllib.error.URLError, TimeoutError):
        data = {'error': 'network'}
    if not (isinstance(data, dict) and data.get('error')):
        cache[path] = data
    time.sleep(delay)
    return data


def counts(formula: str) -> collections.Counter:
    f = re.sub(r'[\s().·]', '', formula)
    return collections.Counter({el: int(n or 1) for el, n in ELEMENT.findall(f)}) if f else collections.Counter()


def formula_match(printed: str, resolved: str) -> bool:
    if not printed or not resolved:
        return False
    target = counts(resolved)
    variants = {printed, printed.replace('0', 'O'), printed.replace('I', 'l'),
                printed.replace('0', 'O').replace('I', 'l'), printed.replace('l', 'I').replace('0', 'O')}
    return any(counts(v) == target for v in variants)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--delay', type=float, default=0.25)
    a = ap.parse_args()
    cache_file = ROOT / 'cas' / 'pubchem-cache.json'
    cache = json.load(cache_file.open()) if cache_file.exists() else {}
    seen: dict[str, dict] = {}
    for f in sorted((ROOT / 'boxes').glob('SDS-*.jsonl'), key=lambda p: int(p.stem.split('-')[1])):
        for line in f.open():
            r = json.loads(line)
            comp = strict(r['boxes'].get('components', ''))
            for m in COMPONENT.finditer(comp):
                name = re.sub(r'^[^A-Za-z]*', '', m.group(1)).strip(' .;,')
                formula, cas = m.group(2).strip(), m.group(3)
                e = seen.setdefault(cas, {'cas': cas, 'n_sheets': 0, 'volumes': set(), 'printed_name': name,
                                          'printed_formula': formula, 'example': f'{f.stem} p{r["page"]}'})
                e['n_sheets'] += 1; e['volumes'].add(f.stem)
            for cas in set(CAS.findall(comp)) - {m.group(3) for m in COMPONENT.finditer(comp)}:
                e = seen.setdefault(cas, {'cas': cas, 'n_sheets': 0, 'volumes': set(), 'printed_name': '',
                                          'printed_formula': '', 'example': f'{f.stem} p{r["page"]}'})
                e['n_sheets'] += 1; e['volumes'].add(f.stem)
    items = sorted(seen.values(), key=lambda e: -e['n_sheets'])[: a.limit]
    print(f'{len(seen)} distinct CAS strings, resolving {len(items)}', flush=True)
    rows = []
    for k, e in enumerate(items, 1):
        row = {'cas': e['cas'], 'check_digit': cas_valid(e['cas']), 'n_sheets': e['n_sheets'],
               'n_volumes': len(e['volumes']), 'example': e['example'], 'printed_name': e['printed_name'],
               'printed_formula': e['printed_formula'], 'pubchem_cid': '', 'pubchem_title': '',
               'pubchem_formula': '', 'formula_match': '', 'name_match': '', 'suggested_cas': '', 'status': ''}
        q = urllib.parse.quote(e['cas'])
        d = pug(f'name/{q}/property/MolecularFormula,Title/JSON', cache, a.delay)
        if d and 'PropertyTable' in d:
            p = d['PropertyTable']['Properties'][0]
            row.update(pubchem_cid=p.get('CID', ''), pubchem_title=p.get('Title', ''),
                       pubchem_formula=p.get('MolecularFormula', ''))
            row['formula_match'] = formula_match(e['printed_formula'], row['pubchem_formula'])
            ln, lt = loose(e['printed_name']), loose(row['pubchem_title'])
            row['name_match'] = bool(ln and lt and (ln in lt or lt in ln))
        if row['check_digit'] and row['pubchem_cid'] and (row['formula_match'] or row['name_match']):
            row['status'] = 'ok'
        elif row['check_digit'] and row['pubchem_cid'] and not e['printed_formula'] and not e['printed_name']:
            row['status'] = 'ok_unverified'            # nothing printed to compare with
        else:
            row['status'] = ('bad_check_digit' if not row['check_digit'] else
                             'unknown_to_pubchem' if not row['pubchem_cid'] else 'name_formula_mismatch')
            if e['printed_name']:                      # look the printed name up the other way
                n = pug(f'name/{urllib.parse.quote(e["printed_name"])}/xrefs/RN/JSON', cache, a.delay)
                if n and 'InformationList' in n:
                    rns = [x for x in n['InformationList']['Information'][0].get('RN', []) if cas_valid(x)]
                    row['suggested_cas'] = ' '.join(rns[:3])
                    if e['cas'] in rns and row['check_digit']:
                        row['status'] = 'ok_via_name'
        rows.append(row)
        if k % 100 == 0:
            print(f'  {k}/{len(items)}', flush=True)
            json.dump(cache, cache_file.open('w'))
    json.dump(cache, cache_file.open('w'))
    out = ROOT / 'cas' / 'cas_resolved.csv'
    with out.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(collections.Counter(r['status'] for r in rows))
    print(f'-> {out.relative_to(ROOT)}')


main()
