"""Parsing shared by the consumers of a boxes jsonl: table cells, column headers,
components and molar masses of an SDS data sheet.

`column(head, comps)` maps a printed header to one of the IUPAC solubility
quantities (the closed set defined in the "Quantities and units" chapter of
every volume) with the component index, the printed prefactor (10^3 x_1, 100
w_1, 103x1 with the caret lost) and a factor from the printed unit to the
canonical unit of the kind:

    temperature_C/F/K, temperature_in_K, temperature_fin_K   kelvin after conversion
    pressure, partial_pressure(i)                              pascal
    molar_fraction(i), mass_fraction(i), mass_ratio(i over j), solid_fraction(i),
    gas_fraction(i), molar_fraction_mixed(i)                   dimensionless
    molality(i)  mol/kg solvent      concentration(i)  mol/dm^3      mass_concentration(i)  g/dm^3
    density  kg/m^3                  bunsen, ostwald, kuenen  dimensionless (gas volumes at STP, 1 atm)
    henry_px  Pa  (p_1/x_1)          henry_pc  Pa m^3/mol  (p_1/c_1)     henry_cc  dimensionless (c_gas/c_liquid)
    ph, salinity (g/kg), solid_phase (text), other

`split_blocks(lines)` returns the (header, rows) blocks of a crop table and
`normalise_rows(cols, rows)` fills ditto rows (blank conditions meaning "as above");
`conditions_from_variables(text)` the single T and P of a VARIABLES box.
`to_canonical(col, v)` applies prefactor and factor. `molar_mass(formula)` reads the
printed formula; substance identity is left to NOMAD's PubChem normaliser.
"""
import re

PRESSURE_UNITS = {'atm': 101325.0, 'kpa': 1000.0, 'pa': 1.0, 'bar': 1e5, 'mmhg': 133.322, 'torr': 133.322, 'mpa': 1e6,
                  'psia': 6894.757, 'psi': 6894.757, 'kgcm-2': 98066.5, '105pa': 1e5}
VAL = re.compile(r'^\s*[<>~≈]?\s*(?P<v>[+-]?\d+(?:[.,]\d+)?)(?:\s*(?:±|\\pm)\s*(?P<e>\d+(?:\.\d+)?))?'
                 r'(?:\s*(?:×|\\times|x)\s*10\^?\{?(?P<x>-?\d+)\}?)?\s*(?:\(\d+\))?\s*[a-z]?\s*$')
BOX_NAME = re.compile(r'COMPONENTS|ORIGINAL MEASUREMENTS|VARIABLES|PREPARED BY|SOURCE AND PURITY|METHOD|REFERENCES|AUXILIARY|ESTIMATED ERROR|CRITICAL EVALUATION', re.I)
NUMBERED = re.compile(r'\((\d)\)|(?<![\d.,])(\d)\.(?=\s*[A-Za-z])')      # "(1) Water" or "1. Ethene"


def tex(s: str) -> str:
    """Strip the LaTeX MinerU puts around symbols: braces, backslash-space, \\circ, \\rho, \\alpha."""
    s = s.replace('\\ ', ' ').replace('^{\\circ}', '°').replace('^\\circ', '°').replace('\\circ', '°')
    s = s.replace('\\rho', 'ρ').replace('\\alpha', 'α').replace('\\gamma', 'γ').replace('℃', '°C')
    return re.sub(r'[{}$]', '', s).strip()


def value(cell: str):
    m = VAL.match(cell.strip())
    if not m:
        return None
    v = float(m.group('v').replace(',', '.'))
    if m.group('x'):
        v *= 10 ** int(m.group('x'))
    return v


def sigfigs(cell: str) -> int:
    """Significant digits of the printed mantissa (8.32 -> 3, 0.0047 -> 2, 5280 -> 4)."""
    m = VAL.match(cell.strip())
    if not m:
        return 0
    digits = m.group('v').replace(',', '.').lstrip('+-').lstrip('0.').replace('.', '')
    return max(1, len(digits))


IDX = r'[_ ]?\{?\(?(?P<i>[1-4Il])\)?\}?'
TAIL = r'\s*(?:\^?\s*[a-f](?:\s*,\s*[a-f])*)?\s*$'            # footnote letters: "T/K^a", "αa", "P/bara", "x_1^a,c"
U_P = r'(?P<u>10\^?5\s*Pa|kPa|MPa|Pa|atm|bar|mmHg|Torr|psia|psi|kg\s*cm\^?-?2)'
FRACT_WORDS = re.compile(r'^(?:Mole?|Mol)\s+Fractions?\s*(?:of\s+)?(?P<name>.*?)(?:,?\s*(?:\(10(?P<p>\d)\)|10\^?(?P<p2>\d))?\s*x_?(?P<i>\d))?' + TAIL, re.I | re.S)


def _index(m) -> int | None:
    i = m.group('i') if m and 'i' in m.groupdict() else None
    return None if i is None else 1 if i in 'Il' else int(i)


def column(head: str, comps: list[dict] | None = None) -> dict:
    """Classify a header cell. Keys: raw, kind, i (component), j (second component of a ratio), pre
    (printed prefactor), factor (printed unit to canonical unit), compiler (bool), note."""
    comps = comps or []
    h = tex(head)
    col = {'raw': head.strip(), 'kind': 'other', 'i': None, 'j': None, 'pre': 1.0, 'factor': 1.0, 'compiler': False, 'note': ''}
    if re.search(r'\(compilers?\)', h, re.I):
        col['compiler'] = True
        h = re.sub(r'\(compilers?\)', '', h, flags=re.I).strip()
    h = re.sub(r'^\d\s*(?=[A-Za-z(])', '', h)                        # footnote digit glued in front: "1T/K", "1 Mole Fraction"
    h = re.sub(r'^(?:Temperature|Pressure|Molality|Concentration|Solubility),?\s*(?=(?:10\S*\s*)?[tTpPmc]_?\d?\s*/)', '', h)
    m = re.match(r'^(?:(?P<pre>10\^\{?-?\d+\}?|\(10(?P<d1>\d)\)|100(?=\s|$)|10(?P<d2>\d)(?=\s*[A-Za-zαρ(])|10(?=\s*[A-Za-zαρ(]))\s*)?(?P<body>.*)$', h, re.S)
    pre, body = m.group('pre'), m.group('body').strip()
    if pre:
        if m.group('d1') or m.group('d2'):
            col['pre'] = 10.0 ** int(m.group('d1') or m.group('d2'))
        elif '^' in pre:
            col['pre'] = 10.0 ** int(re.sub(r'[^\d-]', '', pre.split('^')[1]))
        else:
            col['pre'] = float(pre)
    b = body

    def kind(k, i=None, j=None, factor=1.0, note=''):
        col.update(kind=k, i=i, j=j, factor=factor, note=note)
        return col

    if re.match(r'^T' + IDX.replace('(?P<i>[1-4Il])', '(?:in|fin)') + r'\s*/\s*K' + TAIL, b):
        return kind('temperature_in_K' if 'in' in b.split('/')[0] and 'fin' not in b.split('/')[0] else 'temperature_fin_K')
    if re.match(r'^T\s*/\s*K' + TAIL, b):
        return kind('temperature_K')
    if re.match(r'^[tT]\s*/\s*[°º0o]?\s*C' + TAIL, b):
        return kind('temperature_C')
    if re.match(r'^[tT]\s*/\s*[°º]?\s*F' + TAIL, b):
        return kind('temperature_F')
    mp = re.match(r'^(?P<total>Total\s+)?(?:Pressure\s+)?(?P<partial>Partial\s+Pressure\s+)?\d?\s*[pP](?:' + IDX + r')?\s*/\s*' + U_P + TAIL, b)
    if mp:
        u = re.sub(r'[\s^]', '', mp.group('u')).lower().replace('105pa', '105pa')
        f = PRESSURE_UNITS[u]
        i = _index(mp)
        if i or mp.group('partial'):
            return kind('partial_pressure', i=i or 1, factor=f)
        return kind('pressure', factor=f)
    ms = re.match(r'^x' + IDX + r'(?P<solid>\s*\^?\s*\(?s\)?)?(?P<mixed>\s+in\s+mixed\s+salt)?' + TAIL, b)
    if ms:
        i = _index(ms)
        if ms.group('solid'):
            return kind('solid_fraction', i=i)
        if ms.group('mixed'):
            return kind('molar_fraction_mixed', i=i)
        return kind('molar_fraction', i=i)
    mw = FRACT_WORDS.match(b)
    if mw:
        i = _index(mw)
        if mw.group('p') or mw.group('p2'):
            col['pre'] = 10.0 ** int(mw.group('p') or mw.group('p2'))
        name = mw.group('name') or ''
        if i is None and name:
            key = re.sub(r'[^a-z]', '', re.sub(r'\bin\s+(?:the\s+)?(?:liquid|vapou?r|gas)\b.*$', '', name, flags=re.I).lower())
            for c in comps:
                ck = re.sub(r'[^a-z]', '', c['name'].split('(')[0].lower())
                if key and ck and (key in ck or ck in key):
                    i = c['i']
                    break
        if re.search(r'\b(?:gas|vapou?r)\b', b, re.I):
            return kind('gas_fraction', i=i or 1)
        return kind('molar_fraction', i=i if i else 1, note='' if i else 'index assumed 1')
    if re.match(r'^y' + IDX + TAIL, b):
        return kind('gas_fraction', i=_index(re.match(r'^y' + IDX, b)))
    if re.match(r'^w' + IDX + TAIL, b):
        return kind('mass_fraction', i=_index(re.match(r'^w' + IDX, b)))
    mg = re.match(r'^(?:Mass\s+Percent\s*)?(?P<m>m)?g\s*\(?(?P<i>\d)\)?\s*/\s*(?P<per>100\s*g|kg|g)\s*(?P<what>sln|soln\.?|solution|\(?(?P<j>\d)\)?)?' + TAIL, b, re.I)
    if mg and (mg.group('what') or mg.group('per') != 'g'):
        f = (1e-3 if mg.group('m') else 1.0) * {'100g': 0.01, 'kg': 1e-3, 'g': 1.0}[re.sub(r'\s', '', mg.group('per'))]
        j = mg.group('j')
        if j:
            return kind('mass_ratio', i=int(mg.group('i')), j=int(j), factor=f)
        return kind('mass_fraction', i=int(mg.group('i')), factor=f)
    mr = re.match(r'^g' + IDX + r'\s*/\s*g[_ ]?\{?(?P<j>\d)\}?' + TAIL, b)
    if mr:
        return kind('mass_ratio', i=_index(mr), j=int(mr.group('j')))
    mm = re.match(r'^(?:m' + IDX + r'|mol\s*\((?P<i2>\d)\))\s*/\s*\(?mol\s*kg\^?-?1\)?' + TAIL, b) or re.match(r'^mol\s*\((?P<i2>\d)\)\s*/\s*kg' + TAIL, b)
    if mm:
        i = mm.groupdict().get('i2') or mm.groupdict().get('i')
        return kind('molality', i=_index(re.match(r'(?P<i>.)', i)) if i else None)
    mc = re.match(r'^(?:c' + IDX + r'|mol\s*\((?P<i2>\d)\))\s*/\s*\(?mol\s*(?P<u>dm\^?-?3|L\^?-?1|m\^?-?3|dm3|L)\)?' + TAIL, b) or re.match(r'^mol\s*\((?P<i2>\d)\)\s*/\s*(?P<u>dm3|L)' + TAIL, b)
    if mc:
        i = mc.groupdict().get('i2') or mc.groupdict().get('i')
        f = 1e-3 if re.sub(r'[\s^-]', '', mc.group('u')).startswith('m') and 'dm' not in mc.group('u') else 1.0
        return kind('concentration', i=_index(re.match(r'(?P<i>.)', i)) if i else None, factor=f)
    mq = re.match(r'^g\s*\((?P<i>\d)\)\s*/\s*(?P<u>dm3|L|dm\^?-?3)' + TAIL, b)
    if mq:
        return kind('mass_concentration', i=int(mq.group('i')))
    md = re.match(r'^ρ(?:' + IDX + r')?\s*/\s*(?P<u>kg\s*m\^?-?3|g\s*cm\^?-?3)' + TAIL, b)
    if md:
        return kind('density', factor=1000.0 if md.group('u').startswith('g') else 1.0)
    if re.match(r'^(?:Bunsen\s+coefficient,?\s*)?α(?:\s*/\s*(?:cm\^?3\s*\(STP\)\s*cm\^?-?3\s*atm\^?-?1|dimensionless))?' + TAIL, b) or re.match(r'^Bunsen', b, re.I):
        return kind('bunsen')
    if re.match(r'^(?:Ostwald\s+coefficient,?\s*)?L(?:\s*/\s*cm\^?3\s*cm\^?-?3)?' + TAIL, b) or re.match(r'^Ostwald', b, re.I):
        return kind('ostwald')
    if re.match(r'^(?:Kuenen\s+coefficient,?\s*)?S(?:' + IDX + r')?' + TAIL, b) or re.match(r'^Kuenen', b, re.I):
        return kind('kuenen')
    if re.search(r"Henry", b, re.I) or re.match(r'^P_?[I1l]\s*/\s*c_?[I1l]', b):
        unit = b.split('/', 1)[1] if '/' in b else ''
        if re.search(r'dimensionless', unit, re.I):
            return kind('henry_cc')
        if re.search(r'mol', unit) and not re.search(r'mole\s+fraction', unit, re.I):
            if re.search(r'm\^?3\s*atm', unit):
                return kind('henry_pc', i=1, factor=101325.0)
            if re.search(r'dm3?\s*mmHg', unit):
                return kind('henry_pc', i=1, factor=133.322e-3)
            return kind('henry_unknown', i=1, note='unit not parsed')
        mu = re.search(U_P, unit)
        if mu:
            return kind('henry_px', i=1, factor=PRESSURE_UNITS[re.sub(r'[\s^]', '', mu.group('u')).lower()])
        return kind('henry_unknown', i=1, note='unit not parsed')
    if re.match(r'^pH' + TAIL, b):
        return kind('ph')
    if re.match(r'^Salinity', b, re.I):
        return kind('salinity')
    if re.match(r'^Solid\s+Phase', b, re.I):
        return kind('solid_phase')
    return col


def to_canonical(col: dict, v: float) -> float:
    """Printed number to the canonical unit of its kind."""
    v = v / col['pre'] * col['factor']
    if col['kind'] == 'temperature_C':
        return v + 273.15
    if col['kind'] == 'temperature_F':
        return (v - 32) / 1.8 + 273.15
    return v


def parse_components(text: str) -> list[dict]:
    marks = list(NUMBERED.finditer(text))
    out = []
    for k, m in enumerate(marks):
        body = text[m.end():marks[k + 1].start() if k + 1 < len(marks) else len(text)]
        parts = [p.strip() for p in body.split(';')]
        name = parts[0] if parts else ''
        formula = tex(parts[1]) if len(parts) > 1 else None
        cas = re.search(r'\[(\d{2,7}-\d{2}-\d)\]', body)
        formula = re.sub(r'[_\s]', '', formula) if formula else None
        out.append({'i': int(m.group(1) or m.group(2)), 'name': re.sub(r'\s+', ' ', name), 'formula': formula or None, 'cas': cas.group(1) if cas else None})
    return out


def split_blocks(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    """(header cells, data rows) per table block of a crop. A crop holds several
    blocks when the sheet prints sub-tables ("Solubility of (1) in (2)" above
    "Solubility of (2) in (1)"): a non-numeric line with a recognisable column
    header after data rows starts a new block. A header printed on two lines is
    joined cell by cell when both lines have the data width; a last header line
    shorter than the data takes its leading cells from the line above ("t/°C | title"
    over "mg(2)/kg(1) | ..."). Columns printed twice side by side are unfolded."""
    rows = [[re.sub(r'^\s*EXPERIMENTAL VALUES:?\s*(\(continued\))?\s*', '', c.strip()) for c in l.split(' | ')] for l in lines if l.strip()]
    blocks, heads, data = [], [], []
    for cs in rows:
        if sum(1 for c in cs if VAL.match(c)) >= max(1, (len(cs) + 1) // 2):
            data.append(cs)
        elif len(cs) > 1:
            if data:
                if not any(column(c)['kind'] != 'other' for c in cs):      # footnote split by separators, not a header
                    continue
                blocks.append((heads, data))
                heads, data = [], []
            heads.append(cs)
    blocks.append((heads, data))
    out = []
    for heads, data in blocks:
        if not heads:
            if out:
                out[-1] = (out[-1][0], out[-1][1] + data)
            elif data:
                out.append(([], data))
            continue
        width = max((len(r) for r in data), default=0)
        if len(heads) > 1 and len(heads[-1]) < width <= len(heads[-1]) + len(heads[-2]):
            heads.append(heads[-2][:width - len(heads[-1])] + heads[-1])
        head = next((h for h in reversed(heads) if len(h) == width), max(heads, key=len))
        if len(heads) > 1 and len(heads[-1]) == width and len(heads[-2]) == width:   # two-line header
            head = [(a + ' ' + b).strip() for a, b in zip(heads[-2], heads[-1])]
        n = len(head)
        if n and n % 2 == 0 and head[:n // 2] == head[n // 2:]:        # same columns printed twice side by side
            head = head[:n // 2]
            data = [r[:n // 2] for r in data] + [r[n // 2:] for r in data if len(r) > n // 2]
        out.append((head, data))
    return out


CONDITION_KINDS = ('temperature_C', 'temperature_F', 'temperature_K', 'temperature_in_K', 'temperature_fin_K', 'pressure', 'partial_pressure')


def normalise_rows(cols: list[dict], data: list[list[str]]) -> list[tuple[list[str], str]]:
    """Rows brought to the header width where the sheet's layout allows it, with a note.

    Trailing empty cells beyond the header are dropped. A row short by k cells
    where the first k header columns are conditions (temperature, pressure) and
    the row above was complete is a ditto row: the sheet left the condition
    blank to mean "as above" and MinerU dropped the empty cells; the cells are
    inherited (note "ditto"). Any other width mismatch is left as is (note "shifted").
    """
    lead = 0
    for c in cols:
        if c['kind'] in CONDITION_KINDS:
            lead += 1
        else:
            break
    out, prev = [], None
    for cells in data:
        cells = list(cells)
        while len(cells) > len(cols) and not cells[-1].strip():
            cells.pop()
        k = len(cols) - len(cells)
        if k == 0:
            out.append((cells, ''))
            prev = cells
        elif 0 < k <= lead and prev is not None:
            cells = prev[:k] + cells
            out.append((cells, 'ditto'))
            prev = cells
        else:
            out.append((cells, 'shifted'))
            prev = None
    return out


SINGLE_T = re.compile(r'(?:T/K\s*[=:]\s*(?P<K>\d{3}(?:\.\d+)?)|(?<!and )(?<!, )(?<!to )(?<![-–] )(?<![-–\d.])(?P<C>-?\d{1,3}(?:\.\d+)?)\s*°\s*C)'
                      r'(?![\d.]|\s*(?:[-–,]|to|and)\s*-?\d)')
SINGLE_P = re.compile(r'[pP](?:_?\{?\d\}?)?/(?P<u>kPa|MPa|atm|bar|mmHg|Torr|Pa)\s*[=:]\s*(?P<v>\d+(?:\.\d+)?)(?![\d.]|\s*(?:[-–,]|to|and)\s*-?\d)')
T_MENTIONS = re.compile(r'(?<![\d.])\d{1,3}(?:\.\d+)?(?=\s*(?:°\s*C|K\b))|T/K\s*[=:]\s*\d')


def conditions_from_variables(text: str) -> tuple[float | None, float | None]:
    """Temperature (K) and pressure (Pa) when the VARIABLES box states one value each
    ("T/K = 298.15", "at 27°C", "P/kPa = 101.325"); None for lists and ranges."""
    t = SINGLE_T.search(text) if len(T_MENTIONS.findall(text)) <= 1 else None
    p = SINGLE_P.search(text)
    temperature = (float(t.group('K')) if t and t.group('K') else float(t.group('C')) + 273.15 if t else None)
    pressure = float(p.group('v')) * PRESSURE_UNITS[p.group('u').lower()] if p else None
    return temperature, pressure


ATOMIC_WEIGHTS = {'H': 1.008, 'He': 4.0026, 'Li': 6.94, 'Be': 9.0122, 'B': 10.81, 'C': 12.011, 'N': 14.007, 'O': 15.999, 'F': 18.998,
                  'Ne': 20.180, 'Na': 22.990, 'Mg': 24.305, 'Al': 26.982, 'Si': 28.085, 'P': 30.974, 'S': 32.06, 'Cl': 35.45, 'Ar': 39.948,
                  'K': 39.098, 'Ca': 40.078, 'Ti': 47.867, 'Cr': 51.996, 'Mn': 54.938, 'Fe': 55.845, 'Co': 58.933, 'Ni': 58.693,
                  'Cu': 63.546, 'Zn': 65.38, 'Br': 79.904, 'Kr': 83.798, 'Rb': 85.468, 'Sr': 87.62, 'Ag': 107.87, 'Cd': 112.41, 'Sn': 118.71,
                  'I': 126.90, 'Xe': 131.29, 'Cs': 132.91, 'Ba': 137.33, 'Hg': 200.59, 'Pb': 207.2, 'D': 2.014}
_ELEM = re.compile(r'([A-Z][a-z]?)(\d*)|(\()|(\))(\d*)')


def molar_mass(formula: str) -> float | None:
    """g/mol from a Hill formula; hydrates with '·' or '.' and parentheses are handled."""
    total = 0.0
    for part in re.split(r'[·.]', formula.replace(' ', '')):
        m = re.match(r'^(\d+)(?=[A-Z(])', part)
        mult = int(m.group(1)) if m else 1
        part = part[m.end():] if m else part
        stack = [0.0]
        for sym, n, open_, close, cn in _ELEM.findall(part):
            if open_:
                stack.append(0.0)
            elif close:
                if len(stack) < 2:
                    return None
                inner = stack.pop()
                stack[-1] += inner * (int(cn) if cn else 1)
            else:
                if sym not in ATOMIC_WEIGHTS:
                    return None
                stack[-1] += ATOMIC_WEIGHTS[sym] * (int(n) if n else 1)
        if len(stack) != 1 or not re.fullmatch(r'(?:[A-Z][a-z]?\d*|[()]\d*)+', part):
            return None
        total += mult * stack[0]
    return total or None

