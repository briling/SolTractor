"""Quality checks on the table rows of a volume's data sheets, from the identities between
the IUPAC solubility quantities and from the redundant columns the compilers printed.

Usage: python -I check_rows.py SDS-N [--boxes X.jsonl] [--out DIR] [--text] [--tolerance 0.003]
       python -I check_rows.py --all [--text]          (the ground-truth volumes, summary table)

Hard checks run per row and only where their inputs are present (the selection is
reported, not hidden): a printed value is recomputed from the other printed values
of the row and must agree within the precision of the printed digits (plus 0.3 %
for molar-mass drift; 0.3 K for temperatures).

    T_C=T_K          Celsius against kelvin column                 T=VARIABLES   table T against a single-valued VARIABLES box
    T_fin<=T_in      solidus not above liquidus (dynamic method)   w<->x         mass against mole fraction (binary, molar masses)
    r<->w, r<->x     mass ratio against fractions                 m<->x, m<->w  molality against fractions
    c<->w (rho)      concentration against fraction via density   gamma<->c     mass concentration against concentration
    L=aT/273.15      Ostwald against Bunsen                       a->x (water)  Bunsen to mole fraction via water density
    S=a/rho          Kuenen against Bunsen (water)                H_px->x       Henry (p/x) to mole fraction at the partial pressure
    H_pc<->H_px      the two Henry conventions via water density  H_pc=p1/c     Henry (p/c) against concentration
    P=p1+p_sat       total against partial pressure plus water vapour pressure
    sum_x=1          mole fractions of one phase close            range         fractions in [0, 1], molality and concentration positive
    row_width        the row has as many cells as the header; blank leading conditions ("as above") are filled from the
                     row above first (ditto rows), the remaining shifted rows get no value checks
    verbatim         every numeric token of the row occurs in the text layer of its page (--text)

Soft checks run per sheet: monotonic (the solubility against temperature changes
direction at most once; the row whose removal restores the trend is the outlier),
compiler pairing (a "(compiler)" column has the printed column it was computed
from), header coverage (columns mapped to a known quantity), glued cells (two
numbers in one cell, as "432.55570.68").

Writes DIR/checks-rows.csv (one line per applied hard check) and DIR/checks-sheets.csv;
DIR defaults to the folder of the boxes file.
"""
import argparse, collections, csv, json, math, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from paths import MINED, volume_root  # noqa: E402
from sdstable import load_header_map, BOX_NAME, column, conditions_from_variables, molar_mass, normalise_rows, parse_components, sigfigs, split_blocks, tex, to_canonical, value  # noqa: E402
from textnorm import numbers, strict  # noqa: E402

WATER = '7732-18-5'
V_STP = 22413.96                                   # cm^3/mol, ideal gas at 273.15 K and 101.325 kPa
R = 8.314462
SOURCES = {'molar_fraction': {'mass_fraction', 'mass_ratio', 'molality', 'concentration', 'mass_concentration', 'bunsen', 'ostwald', 'henry_px', 'kuenen'},
           'mass_fraction': {'mass_ratio', 'molar_fraction', 'mass_concentration', 'molality', 'concentration'},
           'temperature_K': {'temperature_C', 'temperature_F'}, 'temperature_C': {'temperature_K', 'temperature_F'},
           'pressure': {'pressure', 'partial_pressure'}, 'partial_pressure': {'pressure', 'partial_pressure'},
           'henry_pc': {'henry_px', 'concentration', 'mass_fraction', 'molar_fraction'}, 'henry_px': {'henry_pc', 'molar_fraction', 'bunsen'},
           'molality': {'mass_fraction', 'molar_fraction', 'concentration', 'mass_ratio'}, 'concentration': {'mass_fraction', 'molar_fraction', 'molality', 'mass_concentration'}}
SOLUBILITY = ('molar_fraction', 'mass_fraction', 'mass_ratio', 'molality', 'concentration', 'mass_concentration', 'bunsen', 'ostwald', 'kuenen', 'henry_px', 'henry_pc', 'henry_cc')


def water_density(T: float) -> float:
    """kg/m^3, Kell (1975), 0 to 150 °C."""
    t = T - 273.15
    return (999.83952 + 16.945176 * t - 7.9870401e-3 * t ** 2 - 46.170461e-6 * t ** 3 + 105.56302e-9 * t ** 4 - 280.54253e-12 * t ** 5) / (1 + 16.879850e-3 * t)


def water_vapour_pressure(T: float) -> float | None:
    """Pa, Antoine constants of the NIST WebBook; 255 to 573 K."""
    if 255 <= T < 379:
        return 1e5 * 10 ** (4.6543 - 1435.264 / (T - 64.848))
    if 379 <= T <= 573:
        return 1e5 * 10 ** (3.55959 - 643.748 / (T - 198.043))
    return None


class Row:
    def __init__(self, cols, cells, comps, masses):
        self.q = {}                                   # (kind, i) -> (canonical value, printed cell, significant digits)
        self.glued = 0
        self.unparsed = 0
        for col, cell in zip(cols, cells):
            v = value(cell)
            if v is None:
                if len(numbers(cell)) >= 2 or re.search(r'\d\.\d+\d\.\d', cell):
                    self.glued += 1
                elif cell.strip() and cell.strip() not in '-–—':
                    self.unparsed += 1
                continue
            if col['kind'] == 'other':
                continue
            key = (col['kind'], col['i'] if col['kind'].endswith(('fraction', 'ratio', 'molality', 'concentration', 'pressure')) and col['kind'] != 'pressure' else None)
            if col['kind'] == 'mass_ratio':
                key = ('mass_ratio', (col['i'], col['j']))
            if key not in self.q:                     # first printed column wins; a compiler duplicate is checked against it
                self.q[key] = (to_canonical(col, v), cell.strip(), sigfigs(cell))
            else:
                self.q.setdefault(('dup',) + key, (to_canonical(col, v), cell.strip(), sigfigs(cell)))
        self.comps, self.masses = comps, masses

    def get(self, kind, i=None):
        return self.q.get((kind, i))

    def temperature(self):
        for k in ('temperature_K', 'temperature_C', 'temperature_F'):
            if (k, None) in self.q:
                return self.q[(k, None)]
        return None

    def M(self, i):
        return self.masses.get(i)

    def other(self, i):
        """The second component of a binary system."""
        js = [c['i'] for c in self.comps if c['i'] != i]
        return js[0] if len(js) == 1 else None

    def is_water(self, j):
        return any(c['i'] == j and c['cas'] == WATER for c in self.comps)


REL_EXTRA = 0.003


def compare(name, printed, predicted, sig, abs_tol=None, note='', rel_extra=None):
    """One check result. Tolerance: one unit of the least significant printed digit plus
    0.3 % (molar-mass drift), or an absolute tolerance. A failing ratio close to a power
    of ten is noted: a prefactor or an exponent was misread."""
    if printed is None or predicted is None or not math.isfinite(predicted):
        return None
    pv, cell, nsig = printed
    if abs_tol is not None:
        dev, tol = abs(pv - predicted), abs_tol
    else:
        if pv == 0 or predicted == 0:
            return None
        dev, tol = abs(pv - predicted) / abs(pv), 10 ** (1 - max(1, min(sig))) + (REL_EXTRA if rel_extra is None else max(rel_extra, REL_EXTRA))
    status = 'pass' if dev <= tol else 'fail'
    if status == 'fail' and abs_tol is None and predicted / pv > 0:
        k = math.log10(predicted / pv)
        if abs(k - round(k)) < 0.02 and round(k) != 0:
            note = (note + '; ' if note else '') + f'off by 10^{round(k)}: prefactor or exponent misread'
    return {'check': name, 'printed': cell, 'predicted': f'{predicted:.6g}', 'deviation': f'{dev:.4g}', 'tolerance': f'{tol:.3g}', 'status': status, 'note': note}


def hard_checks(row: Row, var_t, var_p) -> list[dict]:
    out = []
    q = row.q
    T = row.temperature()
    TK = T[0] if T else None
    tC, tK = row.get('temperature_C'), row.get('temperature_K')
    if tC and tK:
        out.append(compare('T_C=T_K', tK, tC[0], (9,), abs_tol=0.3))
    if T and var_t is not None:
        out.append(compare('T=VARIABLES', T, var_t, (9,), abs_tol=1.0, note=f'VARIABLES T={var_t:.2f} K'))
    tin, tfin = row.get('temperature_in_K'), row.get('temperature_fin_K')
    if tin and tfin:                                                   # crystallisation begins at T_in (liquidus), concludes at T_fin (solidus)
        ok = tfin[0] <= tin[0] + 0.3
        out.append({'check': 'T_fin<=T_in', 'printed': f'{tin[1]}, {tfin[1]}', 'predicted': 'solidus <= liquidus', 'deviation': f'{tfin[0] - tin[0]:+.1f}', 'tolerance': '0.3', 'status': 'pass' if ok else 'fail', 'note': ''})
    comps = [c['i'] for c in row.comps]
    for i in comps:
        j = row.other(i)
        Mi, Mj = row.M(i), row.M(j) if j else None
        w, x, m, c, g = row.get('mass_fraction', i), row.get('molar_fraction', i), row.get('molality', i), row.get('concentration', i), row.get('mass_concentration', i)
        r = row.get('mass_ratio', (i, j)) if j else None
        dup_w, dup_x = q.get(('dup', 'mass_fraction', i)), q.get(('dup', 'molar_fraction', i))
        if dup_w and w:
            out.append(compare('w=w (duplicate column)', dup_w, w[0], (w[2], dup_w[2])))
        if dup_x and x:
            out.append(compare('x=x (duplicate column)', dup_x, x[0], (x[2], dup_x[2])))
        if Mi and Mj:
            if w and x:
                a = w[0] / Mi
                out.append(compare('w<->x', x, a / (a + (1 - w[0]) / Mj), (w[2], x[2])))
            if r and w:
                out.append(compare('r<->w', w, r[0] / (1 + r[0]), (r[2], w[2])))
            if r and x and not w:
                a = r[0] / Mi
                out.append(compare('r<->x', x, a / (a + 1 / Mj), (r[2], x[2])))
            if m and x:
                a = m[0] * Mj / 1000
                out.append(compare('m<->x', x, a / (1 + a), (m[2], x[2])))
            if m and w and not x:
                a = m[0] * Mi / 1000
                out.append(compare('m<->w', w, a / (1 + a), (m[2], w[2])))
        if Mi:
            rho = row.get('density')
            if c and rho and (w or x):
                if not w:
                    a = x[0] * Mi
                    wf = a / (a + (1 - x[0]) * Mj) if Mj else None
                else:
                    wf = w[0]
                if wf is not None:
                    out.append(compare('c<->w (rho)', c, wf * rho[0] / Mi, (c[2], (w or x)[2], rho[2])))
            if g and c:
                out.append(compare('gamma<->c', c, g[0] / Mi, (g[2], c[2])))
    alpha, L, S = row.get('bunsen'), row.get('ostwald'), row.get('kuenen')
    if alpha and L and TK:
        out.append(compare('L=aT/273.15', L, alpha[0] * TK / 273.15, (alpha[2], L[2])))
    gas = comps[0] if comps else None                                  # gas volumes list the gas as component 1
    solvent = row.other(gas) if gas else None
    aqueous = solvent is not None and row.is_water(solvent) and TK is not None and 273 < TK < 423
    if aqueous:
        rho_w = water_density(TK) / 1000                               # g/cm^3
        xg = row.get('molar_fraction', gas)
        if alpha and xg:
            n_gas, n_solv = alpha[0] / V_STP, rho_w / row.M(solvent)
            out.append(compare('a->x (water)', xg, n_gas / (n_gas + n_solv), (alpha[2], xg[2]), rel_extra=0.012, note='ideal-gas molar volume; compilers used the real one (CO2: 0.7 % lower)'))
        if alpha and S:
            out.append(compare('S=a/rho', S, alpha[0] / rho_w, (alpha[2], S[2]), rel_extra=0.012))
    p1 = row.get('partial_pressure', gas) if gas else None
    p1v = p1[0] if p1 else var_p
    H, Hc = row.get('henry_px'), row.get('henry_pc')
    xg = row.get('molar_fraction', gas) if gas else None
    if H and xg and p1v:
        out.append(compare('H_px->x', xg, p1v / H[0], (H[2], xg[2]), note='' if p1 else f'partial pressure from VARIABLES {p1v:.0f} Pa'))
    if H and Hc and aqueous:
        out.append(compare('H_pc<->H_px', Hc, H[0] * row.M(solvent) / 1000 / water_density(TK), (H[2], Hc[2])))
    cg = row.get('concentration', gas) if gas else None
    if Hc and cg and p1v:
        out.append(compare('H_pc=p1/c', Hc, p1v / (cg[0] * 1000), (Hc[2], cg[2]), note='' if p1 else 'partial pressure from VARIABLES'))
    P = row.get('pressure')
    if P and p1 and aqueous:
        psat = water_vapour_pressure(TK)
        if psat:
            out.append(compare('P=p1+p_sat', P, p1[0] + psat, (P[2], p1[2])))
    xs = {i: row.get('molar_fraction', i) for i in comps if row.get('molar_fraction', i)}
    if len(xs) >= 2 and len(xs) == len(comps) and max(v[0] for v in xs.values()) >= 1 / len(comps):   # else fractions of different phases (mutual solubility)
        s = sum(v[0] for v in xs.values())
        out.append({'check': 'sum_x=1', 'printed': ' + '.join(v[1] for v in xs.values()), 'predicted': '1', 'deviation': f'{abs(s - 1):.4g}', 'tolerance': '0.003', 'status': 'pass' if abs(s - 1) <= 0.003 else 'fail', 'note': ''})
    qq = {k: v for k, v in q.items() if len(k) == 2}
    bad = [cell for (k, i), (v, cell, _) in qq.items() if k in ('molar_fraction', 'mass_fraction', 'solid_fraction', 'gas_fraction', 'mass_ratio') and not (0 <= v <= 1)]
    bad += [cell for (k, i), (v, cell, _) in qq.items() if k in ('molality', 'concentration', 'mass_concentration', 'bunsen', 'ostwald', 'kuenen', 'henry_px', 'henry_pc', 'henry_cc') and v < 0]
    if any(k in ('molar_fraction', 'mass_fraction', 'solid_fraction', 'gas_fraction', 'mass_ratio', 'molality', 'concentration') for k, _ in qq):
        out.append({'check': 'range', 'printed': '; '.join(bad), 'predicted': '[0, 1]', 'deviation': '', 'tolerance': '', 'status': 'fail' if bad else 'pass', 'note': ''})
    return [o for o in out if o]


def verbatim(cells: list[str], page_text: str) -> tuple[int, int]:
    """(numeric tokens found, tokens) of a row in the strict-normalised text layer of its page."""
    toks = [t for c in cells for t in numbers(c)]
    return sum(1 for t in toks if t in page_text), len(toks)


def monotonic(rows: list[Row]) -> tuple[str, int | None]:
    """Direction changes of the first solubility quantity against temperature within a sheet."""
    key = next((k for k in rows[0].q if len(k) == 2 and k[0] in SOLUBILITY), None) if rows else None
    if not key:
        return 'n.a.', None
    pts = [(r.temperature()[0], r.q[key][0], n) for n, r in enumerate(rows) if r.temperature() and key in r.q]
    if any(('pressure', None) in r.q or any(k[0] == 'partial_pressure' for k in r.q) for r in rows):
        ps = {r.q.get(('pressure', None), r.q.get(('partial_pressure', 1), (None,)))[0] for r in rows}
        if len(ps) > 1:
            return 'n.a. (pressure varies)', None
    if len({p[0] for p in pts}) < 4:
        return 'n.a. (fewer than 4 temperatures)', None

    def changes(seq):
        d = [b - a for a, b in zip(seq, seq[1:]) if b != a]
        return sum(1 for a, b in zip(d, d[1:]) if (a > 0) != (b > 0))
    pts.sort()
    ys = [p[1] for p in pts]
    n = changes(ys)
    if n == 0:
        return 'monotonic', None
    for k in range(len(pts)):
        if changes(ys[:k] + ys[k + 1:]) == 0:
            return 'outlier', pts[k][2]
    return f'{n} direction changes', None


def check_volume(vol: str, boxes: pathlib.Path, out: pathlib.Path, with_text: bool) -> dict:
    pages = (volume_root(vol) / 'text' / f'{vol}.txt').read_text(errors='replace').split('\f') if with_text else []
    page_cache = {}
    rows_csv, sheets_csv = [], []
    tally = collections.defaultdict(lambda: [0, 0])                   # check -> [pass, fail]
    unmapped = collections.Counter()
    n_sheets = n_rows = n_cols = n_mapped = n_glued = n_short = n_ditto = 0
    vb_found = vb_total = vb_rows_fail = 0
    for r in map(json.loads, boxes.open()):
        if r['kind'] != 'compilation':
            continue
        comps = parse_components(r['boxes'].get('components', ''))
        if not any(c['cas'] for c in comps):
            continue
        blocks = [b for b in split_blocks(r['boxes'].get('experimental_values', '').split('\n')) if b[0]]
        if not blocks or any(BOX_NAME.search(h) for head, _ in blocks for h in head):
            continue
        n_sheets += 1
        masses = {c['i']: molar_mass(c['formula']) if c['formula'] else None for c in comps}   # printed formula; identity is NOMAD's PubChem normaliser's job
        table = []
        for head, data in blocks:
            cols = [column(h, comps) for h in head]
            n_cols += len(cols)
            n_mapped += sum(1 for c in cols if c['kind'] != 'other')
            for c in cols:
                if c['kind'] == 'other':
                    unmapped[tex(c['raw'])[:40]] += 1
            table += [(cols, row, note) for row, note in normalise_rows(cols, data)]
        cols = [c for head, _ in blocks for c in [column(h, comps) for h in head]]
        var_t, var_p = conditions_from_variables(r['boxes'].get('variables', ''))
        rows = []
        unpaired = [tex(c['raw']) for c in cols if c['compiler'] and c['kind'] in SOURCES and not any(o is not c and o['kind'] in SOURCES[c['kind']] for o in cols)]
        page_text = None
        if with_text and 0 < r['page'] <= len(pages):
            page_text = page_cache.setdefault(r['page'], strict(pages[r['page'] - 1]))
        sheet_vb = [0, 0]
        for n, (cols, cells, ditto) in enumerate(table):
            row = Row(cols, cells, comps, masses)
            rows.append(row)
            n_rows += 1
            n_glued += row.glued > 0
            if ditto == 'ditto':
                n_ditto += 1
            if len(cells) != len(cols):                               # MinerU drops empty leading cells: the row is shifted
                n_short += 1
                tally['row_width'][1] += 1
                rows_csv.append({'volume': vol, 'page': r['page'], 'sheet': r['index_on_page'], 'row': n, 'check': 'row_width', 'printed': ' | '.join(cells),
                                 'predicted': f'{len(cols)} cells', 'deviation': f'{len(cells) - len(cols):+d}', 'tolerance': '0', 'status': 'fail', 'note': 'value checks skipped'})
                continue
            tally['row_width'][0] += 1
            for res in hard_checks(row, var_t, var_p):
                tally[res['check']][res['status'] == 'fail'] += 1
                rows_csv.append({'volume': vol, 'page': r['page'], 'sheet': r['index_on_page'], 'row': n, **res, 'note': (res['note'] + '; ' if res['note'] else '') + 'ditto row' if ditto else res['note']})
            if page_text is not None:
                f, t = verbatim(cells, page_text)
                vb_found += f; vb_total += t; sheet_vb[0] += f; sheet_vb[1] += t
                if f < t:
                    vb_rows_fail += 1
                    rows_csv.append({'volume': vol, 'page': r['page'], 'sheet': r['index_on_page'], 'row': n, 'check': 'verbatim', 'printed': ' | '.join(cells),
                                     'predicted': 'text layer of the page', 'deviation': f'{t - f} of {t} tokens missing', 'tolerance': '0', 'status': 'fail', 'note': ''})
                    tally['verbatim'][1] += 1
                else:
                    tally['verbatim'][0] += 1
        trend, outlier = monotonic(rows)
        sheets_csv.append({'volume': vol, 'page': r['page'], 'sheet': r['index_on_page'], 'rows': len(table), 'columns': len(cols),
                           'mapped': sum(1 for c in cols if c['kind'] != 'other'), 'unmapped': '; '.join(tex(c['raw']) for c in cols if c['kind'] == 'other'),
                           'compiler_unpaired': '; '.join(unpaired), 'trend': trend, 'outlier_row': '' if outlier is None else outlier,
                           'glued_rows': sum(1 for x in rows if x.glued), 'short_rows': sum(1 for c, cells, _ in table if len(cells) != len(c)), 'ditto_rows': sum(1 for *_, d in table if d == 'ditto'), 'verbatim': f'{sheet_vb[0]}/{sheet_vb[1]}' if page_text is not None else ''})
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'checks-rows.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['volume', 'page', 'sheet', 'row', 'check', 'printed', 'predicted', 'deviation', 'tolerance', 'status', 'note']); w.writeheader(); w.writerows(rows_csv)
    with (out / 'checks-sheets.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(sheets_csv[0]) if sheets_csv else ['volume']); w.writeheader(); w.writerows(sheets_csv)
    trends = collections.Counter(s['trend'].split(' (')[0] for s in sheets_csv)
    return {'volume': vol, 'sheets': n_sheets, 'rows': n_rows, 'columns': n_cols, 'mapped': n_mapped, 'unmapped': unmapped.most_common(10),
            'checks': {k: {'pass': v[0], 'fail': v[1]} for k, v in sorted(tally.items())}, 'glued_rows': n_glued, 'short_rows': n_short, 'ditto_rows': n_ditto,
            'verbatim_tokens': f'{vb_found}/{vb_total}' if with_text else '', 'verbatim_rows_fail': vb_rows_fail,
            'trend': dict(trends), 'outliers': sum(1 for s in sheets_csv if s['trend'] == 'outlier'),
            'compiler_unpaired_sheets': sum(1 for s in sheets_csv if s['compiler_unpaired'])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('volume', nargs='?')
    ap.add_argument('--boxes', type=pathlib.Path)
    ap.add_argument('--out', type=pathlib.Path)
    ap.add_argument('--text', action='store_true', help='also check every numeric token against the text layer of the page')
    ap.add_argument('--header-map', type=pathlib.Path, help='jsonl of mappings for headers the rules leave unmapped (checked by hard constraints)')
    ap.add_argument('--tolerance', type=float, default=0.003, help='relative tolerance added to the printed precision (default 0.003)')
    ap.add_argument('--all', action='store_true', help='all ground-truth volumes with crop-pass boxes; prints a summary table')
    a = ap.parse_args()
    global REL_EXTRA
    REL_EXTRA = a.tolerance
    if a.header_map:
        print('header map:', load_header_map(a.header_map), file=sys.stderr)
    vols = [f'SDS-{n}' for n in sorted(MINED)] if a.all else [a.volume if a.volume.startswith('SDS-') else f'SDS-{a.volume}']
    summaries = []
    for vol in vols:
        boxes = a.boxes or volume_root(vol) / 'mineru' / vol / 'boxes-crops.jsonl'
        if not boxes.exists():
            continue
        s = check_volume(vol, boxes, a.out or boxes.parent, a.text)
        summaries.append(s)
        if not a.all:
            print(json.dumps(s, ensure_ascii=False, indent=1))
    if a.all:
        print('| volume | sheets | rows | ditto rows filled | shifted rows | headers mapped | hard checks applied | pass | fail | verbatim rows failing | glued rows | sheets monotonic / outlier / changing | compiler columns unpaired |')
        print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
        for s in summaries:
            hard = {k: v for k, v in s['checks'].items() if k not in ('verbatim', 'row_width')}
            p, f = sum(v['pass'] for v in hard.values()), sum(v['fail'] for v in hard.values())
            t = s['trend']
            print(f"| {s['volume'][4:]} | {s['sheets']} | {s['rows']} | {s['ditto_rows']} | {s['short_rows']} | {s['mapped']}/{s['columns']} | {p + f} | {p} | {f} | "
                  f"{s['verbatim_rows_fail']} | {s['glued_rows']} | {t.get('monotonic', 0)} / {t.get('outlier', 0)} / {sum(v for k, v in t.items() if 'change' in k)} | {s['compiler_unpaired_sheets']} |")
        print()
        for s in summaries:
            print(s['volume'], {k: (v['pass'], v['fail']) for k, v in s['checks'].items()})
            print('   unmapped:', s['unmapped'][:8])


if __name__ == '__main__':
    main()
