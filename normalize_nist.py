"""Normalise NIST compilation-sheet tables into one record per measurement (table row).

Input:  data/nist_gt.jsonl            (one record per sheet, from parse_nist.py)
Output: data/nist_measurements.jsonl  (one record per table row)

Each column header is decomposed as  [10^k *] <quantity>_<n> [(compiler)] [[unit]] [^footnote].
Header numbers _n follow the order of names in the sheet's system name ("CO2 with Na2SO4 and
Water": 1 = CO2, 2 = Na2SO4, 3 = Water), which often differs from NIST's component list.
Each row then becomes either
  solubility         one solute: how much of it dissolves, and the solvent's composition
  phase_composition  multicomponent equilibrium: the composition of the phase (+ solid phase)

    source .venv/bin/activate && python normalize_nist.py
"""
import collections
import json
import re
from pathlib import Path

DATA = Path(__file__).parent / "data"

# (quantity, regex on the lowercased header body) — first match wins, order matters
QUANTITIES = [
    ("gas_mole_fraction", r"mole fraction of gas|^y_\d"),
    ("mole_fraction", r"mole fractio|^x_\d|^\(?x_\d"),
    ("amount_per_mass", r"^w_\d/m_\d|^n_\d/g_\d"),
    ("mass_fraction", r"mass fraction|^w_\d"),
    ("mass_per_100g_solution", r"^g_\d/100 ?g"),
    ("mass_per_kg", r"^g_\d/kg"),
    ("mass_ratio", r"^g_\d/g_\d|^mass ratio"),
    ("mass_concentration", r"^g_\d/v_\d"),
    ("molality", r"molality|^m_\d|^mol_\d/kg"),
    ("amount_concentration", r"concent|^c_\d|^n_\d/v_\d|^c$"),
    ("volume_ratio", r"^v_\d/v_\d|^v_\d/g_\d"),
    ("ostwald_coefficient", r"ostwald"),
    ("bunsen_coefficient", r"bunsen|^α"),
    ("henry_constant", r"henry"),
    ("kuenen_coefficient", r"keunen|kuenen"),
    ("langmuir_capacity", r"langmuir"),
    ("affinity_coefficient", r"affinity"),
    ("sorption", r"sorption"),
    ("distribution_coefficient", r"distribution|partition"),
    ("activity_coefficient", r"^γ"),
    ("salt_effect", r"salt effect"),
    ("density", r"density|^ρ"),
    ("composition", r"^composition"),
    ("solubility", r"^solubility"),
    ("enthalpy", r"enthalpy|^δh"),
    ("entropy", r"entropy|^δs"),
]
# quantities that say how much of one species is in the solution
AMOUNT = {"mole_fraction", "mass_fraction", "gas_mole_fraction", "amount_per_mass", "mass_per_100g_solution",
          "mass_per_kg", "mass_ratio", "mass_concentration", "molality", "amount_concentration",
          "volume_ratio", "composition", "solubility"}
# gas-solubility coefficients and the like: no component number, always about the solute
SOLUTE_ONLY = {"ostwald_coefficient", "bunsen_coefficient", "henry_constant", "kuenen_coefficient",
               "langmuir_capacity", "affinity_coefficient", "sorption", "salt_effect",
               "distribution_coefficient", "activity_coefficient", "enthalpy", "entropy"}
FRACTIONS = {"mole_fraction", "mass_fraction", "gas_mole_fraction"}
# columns that describe the row rather than hold a value
CONDITIONS = [
    ("temperature_C", r"^t/°c$|^t/ºc$"),
    ("temperature_K", r"^t/k$"),
    ("pressure", r"^pressure"),
    ("pH", r"^ph$"),
    ("initial_pH", r"^initial ph$"),
    ("ionic_strength", r"^ionic strength"),
]
LABELS = r"comment|remark|method|reference|^no\.$|solution number|polymer|equation|^note$|dilution"
MISSING = {"", "-", "--", "---", "----", "—", "–", "−", "- x 10^0", "n.d.", "nd"}
DITTO = {'"', "〃", "''", "”", "“"}
PRESSURE_TO_KPA = {
    "mpa": 1000, "kpa": 1, "pa": 1e-3, "bar": 100, "kbar": 1e5, "atm": 101.325, "1 atm": 101.325,
    "mmhg": 0.133322, "mm hg": 0.133322, "mm mercury": 0.133322, "mm": 0.133322,
    "cmhg": 1.33322, "cm hg": 1.33322, "psia": 6.894757, "kg/cm**-2": 98.0665, "kg cm**-2": 98.0665,
    "kg/cm^2": 98.0665,
}
UNIT_ALIASES = {
    "mol dm**-3": "mol/L", "mol/dm^3": "mol/L", "mol/l": "mol/L", "mol l^–1": "mol/L",
    "mol dm^–3": "mol/L", "mol/dm3": "mol/L", "mol/L": "mol/L",
    "mol kg-1": "mol/kg", "mol/kg": "mol/kg", "mol kg^–1": "mol/kg",
}
HEADER = re.compile(
    r"^(?:10\^(?P<exp>-?\d+)\s*\*\s*)?(?P<body>.*?)\s*(?P<compiler>\(compiler\))?\s*"
    r"(?:\[(?P<unit>[^\]]*)\])?\s*(?P<foot>\^.*)?$"
)
NUMBER = re.compile(
    r"^(?P<q>[<>≤≥~≈]|ca\.)?\s*(?P<num>[-+−–]?(?:\d+\.?\d*|\.\d+))"
    r"(?:\s*(?:x|×|\*)\s*10\^?\s*(?P<exp>[-+−–]?\d+))?(?:[eE](?P<e>[-+]?\d+))?"
    r"\s*(?:±\s*[\d.]+)?\s*(?:\^?\(?[a-z]\)?)?$"
)
TEMP_TEXT = re.compile(r"((?<![\d.])-?\d+(?:\.\d+)?)\s*(?:°|º|o)?\s*(C|K)\b")
TEMP_RANGE = re.compile(r"\d\s*(?:°|º)?\s*[CK]?\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*(?:°|º|o)?\s*[CK]\b")
T_PLAUSIBLE_K = (200, 800)  # outside: flagged, usually a typo in the source (e.g. '038.2 K')
WATER_SOURCE = re.compile(r"distill|deioni[sz]|water|millipore|conductivity", re.I)
CAPTION = re.compile(r"solubility of (.+?) in (.+)")
PRESSURE_LINE = re.compile(r"pressure\s*=\s*[^\n]*", re.I)
PRESSURE_TEXT = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(MPa|kPa|bar|atm|mmHg|mm Hg)\b", re.I)


def parse_header(h):
    m = HEADER.match((h or "").strip())
    body = m["body"].strip()
    low = body.lower()
    idx = re.search(r"_(\d+)", body)
    info = {
        "header": h,
        "scale_factor": 10 ** -int(m["exp"]) if m["exp"] else 1.0,
        "compiler": bool(m["compiler"]) or "(compiler)" in (h or ""),
        "unit": m["unit"].strip() if m["unit"] else None,
        "index": int(idx[1]) if idx else None,
        "kind": "value",
        "quantity": None,
    }
    if "note" in low:
        info["kind"] = "note"
    elif low.startswith("chemical name"):
        info["kind"] = "row_compound"  # one name per row: which salt / polymer this row is about
    elif low.startswith("chemical"):
        info["kind"] = "species"
    elif "solid phase" in low:
        info["kind"] = "solid_phase"
    elif low.startswith("phase"):
        info["kind"] = "phase"
    elif re.search(LABELS, low):
        info["kind"] = "label"
    else:
        for name, pat in CONDITIONS:
            if re.search(pat, low):
                info["kind"], info["quantity"] = "condition", name
                break
        else:
            info["quantity"] = next((q for q, pat in QUANTITIES if re.search(pat, low)), "other")
    if info["unit"]:
        info["unit"] = UNIT_ALIASES.get(info["unit"], info["unit"])
    elif info["quantity"] in FRACTIONS:
        info["unit"] = "1"
    elif info["quantity"] == "mass_per_100g_solution":
        info["unit"] = "g/100 g solution"
    elif info["quantity"] == "mass_per_kg":
        info["unit"] = "g/kg"
    return info


def parse_number(v):
    """float cell -> (value, qualifier); strings like '1.2 x 10^-3', '<0.1', '3.4a' are parsed."""
    if isinstance(v, (int, float)):
        return float(v), None
    s = str(v).strip().replace("−", "-").replace("–", "-")
    s = re.sub(r"(?<=\d) (?=\d)", "", s)  # digit grouping: '0.000 02'
    s = re.sub(r"\s*%$", "", s)  # '34 %' in columns that are already percent
    m = NUMBER.match(s)
    if not m:
        return None, None
    x = float(m["num"])
    if m["exp"]:
        x *= 10 ** int(m["exp"])
    if m["e"]:
        x *= 10 ** int(m["e"])
    return x, m["q"]


def is_missing(v):
    return v is None or (isinstance(v, str) and v.strip().lower() in MISSING)


def table_temperature(sheet, table):
    """Single temperature stated in the caption or Variables, when the table has no T column."""
    for src, text in (("caption", table["caption"]), ("variables", sheet["variables"])):
        if TEMP_RANGE.search(text or ""):
            continue
        temps = {round(float(n) + (273.15 if u == "C" else 0), 2) for n, u in TEMP_TEXT.findall(text or "")}
        if len(temps) == 1:
            return temps.pop(), src
    return None, None


def table_pressure(sheet, table):
    """Single pressure stated in the caption or Variables ('Pressure = 101.325 kPa')."""
    for text in (table["caption"], sheet["variables"]):
        found = {(float(n), u.lower()) for n, u in PRESSURE_TEXT.findall(text or "")}
        if len(found) == 1 and not re.search(r"\d\s*(?:-|–|to)\s*\d", (PRESSURE_LINE.search(text or "") or [""])[0]):
            x, unit = found.pop()
            return {"value": x, "unit": unit}, round(x * PRESSURE_TO_KPA[unit], 6)
    return None, None


def _name_candidates(name):
    n = name.lower().strip()
    c = {n, re.split(r",\s*\(|\s+\(|,\s+or\s+|\s+or\s+", n)[0].strip(" ,")}
    c |= {x.strip() for x in re.findall(r"\(([^()]{3,})\)", n)}
    c |= {x.strip(" ,") for x in re.split(r"\s+or\s+", n)}
    return {x for x in c if len(x) >= 3}


def _matches(name, text):
    text = text.strip().lower()
    return any(x in text or text in x for x in _name_candidates(name))


def component_map(sheet, cols, table):
    """Map header numbers (x_1, w_2, ...) to components, strongest evidence first.

    system_name  order of the names in "A with B and C" (agrees with captions in 413/415 tables)
    caption      binary sheets: 'Solubility of A in B' + the single number used by the value columns
    source_text  water + X sheets: the '(n) ... distilled water' line of Source and Purity
    nist_order   NIST's listed order, unverified
    """
    comps = [c for c in sheet["components"] if c["index"]]
    s = sheet["system_name"].lower()
    pos = {}
    for c in comps:
        hits = [s.find(x) for x in _name_candidates(c["name"]) if s.find(x) >= 0]
        if not hits:
            break
        pos[id(c)] = min(hits)
    else:
        if comps and len(set(pos.values())) == len(comps):
            ordered = sorted(comps, key=lambda c: pos[id(c)])
            return {i + 1: c for i, c in enumerate(ordered)}, "system_name"
    if len(comps) == 2:
        a, b = comps
        m = CAPTION.match((table["caption"] or "").lower())
        idx = {c["index"] for c in cols if c["quantity"] in AMOUNT} - {None}
        if m and len(idx) == 1 and idx <= {1, 2}:
            hits = [c for c in comps if _matches(c["name"], m[1])]
            if len(hits) == 1:
                hi = idx.pop()
                return {hi: hits[0], 3 - hi: b if hits[0] is a else a}, "caption"
        water = [c for c in comps if c["name"].lower() == "water"]
        if water:
            items = dict((int(n), t) for n, t in re.findall(r"\((\d)\)\s*([^\n]*)", sheet["source_and_purity"] or ""))
            hits = [n for n, t in items.items() if WATER_SOURCE.search(t)]
            if len(hits) == 1 and hits[0] in (1, 2):
                return {hits[0]: water[0], 3 - hits[0]: b if water[0] is a else a}, "source_text"
    return {c["index"]: c for c in comps}, "nist_order"


def compound(c):
    return {"name": c["name"], "formula": c["formula"], "cas": c["cas"]} if c else None


def table_solute(sheet, cols, table, cmap):
    """Header number of the solute, or None when the table is a phase composition.

    In order: Chemical_N columns (salt systems) -> phase composition; caption 'Solubility
    of A in B' -> A; a gas coefficient (Ostwald, Bunsen, Henry, ...) -> the first-named
    compound, the gas (other amount columns then describe the solvent, e.g. salt
    concentration); amounts of one component only -> that one; binary with both x_1 and x_2
    -> 1; three or more components with fractions of several -> phase composition
    (e.g. ternary liquid-liquid tie lines).
    """
    if any(c["kind"] == "species" for c in cols):
        return None
    m = CAPTION.match((table["caption"] or "").lower())
    if m:
        hits = [n for n, c in cmap.items() if _matches(c["name"], m[1])]
        if len(hits) == 1:
            return hits[0]
    if any(c["quantity"] in SOLUTE_ONLY for c in cols):
        return 1
    amount_idx = {c["index"] for c in cols if c["quantity"] in AMOUNT and c["index"]}
    if len(amount_idx) == 1:
        return amount_idx.pop()
    if not amount_idx:
        return None
    if len(cmap) == 2:
        return 1
    fraction_idx = {c["index"] for c in cols if c["quantity"] in FRACTIONS | {"composition"} and c["index"]}
    if len(fraction_idx) >= 2:
        return None
    return 1 if 1 in amount_idx else None


def entry(col, x, qual, v, note):
    e = {"quantity": col["quantity"], "value": float(f"{x * col['scale_factor']:.12g}"),
         "unit": col["unit"], "value_qualifier": qual, "raw_value": v, "header": col["header"],
         "compiler_calculated": col["compiler"]}
    if note:
        e["note"] = note
    return e


def measurements_for_table(sheet, ti, table, stats):
    cols = [parse_header(h) for h in table["columns"]]
    if not any(c["kind"] == "value" for c in cols):
        return
    t_default, t_src = table_temperature(sheet, table)
    p_default, p_kpa = table_pressure(sheet, table)
    cmap, mapping = component_map(sheet, cols, table)
    solute_n = table_solute(sheet, cols, table, cmap)
    solute = cmap.get(solute_n) if solute_n else None
    if solute_n and not solute:
        solute_n = None
    kind = "solubility" if solute else "phase_composition"
    over_1 = {j for j, c in enumerate(cols) if c["quantity"] in FRACTIONS and any(
        (x := parse_number(r[j])[0]) is not None and x * c["scale_factor"] > 1
        for r in table["rows"] if len(r) == len(cols) and not is_missing(r[j]))}

    prev = {}
    for ri, raw_row in enumerate(table["rows"]):
        if len(raw_row) != len(cols):
            stats["ragged_rows_skipped"] += 1
            continue
        row = [prev.get(j) if isinstance(v, str) and v.strip() in DITTO else v for j, v in enumerate(raw_row)]
        prev = dict(enumerate(row))

        rec = {
            "measurement_id": f"{sheet['id']}/t{ti}/r{ri}",
            "sheet_id": sheet["id"], "table_index": ti, "row_index": ri,
            "iupac_volume": sheet["iupac_volume"], "evaluated": sheet["evaluated"],
            "system_name": sheet["system_name"], "citation": sheet["original_measurements"],
            "url": sheet["url"], "type": kind,
            "solute": compound(solute),
            "solvent": [compound(c) for n, c in sorted(cmap.items()) if n != solute_n] if solute else None,
            "temperature_K": t_default, "temperature_source": t_src,
            "pressure_kPa": p_kpa, "pressure": p_default,
            "solubility": [] if solute else None,
            "solvent_composition": [] if solute else None,
            "composition": None if solute else [],
            "properties": [],
            "phase": None, "solid_phase": None, "conditions": {}, "labels": {},
            "species_mapping": "table" if any(c["kind"] == "species" for c in cols) else mapping,
            "flags": [],
        }
        species = None
        for j, (col, v) in enumerate(zip(cols, row)):
            if col["kind"] == "species":
                species = None if is_missing(v) else str(v)
                continue
            if is_missing(v):
                continue
            if col["kind"] in ("phase", "solid_phase"):
                rec[col["kind"]] = str(v)
            elif col["kind"] == "row_compound":
                rec["labels"]["compound"] = str(v)
            elif col["kind"] == "label":
                rec["labels"][col["header"]] = v
            elif col["kind"] == "condition":
                x, _ = parse_number(v)
                q = col["quantity"]
                if q.startswith("temperature") and x is not None:
                    rec["temperature_K"] = round(x * col["scale_factor"] + (273.15 if q == "temperature_C" else 0), 4)
                    rec["temperature_source"] = "column"
                elif q == "pressure" and x is not None:
                    x *= col["scale_factor"]
                    rec["pressure"] = {"value": x, "unit": col["unit"]}
                    f = PRESSURE_TO_KPA.get((col["unit"] or "").lower())
                    rec["pressure_kPa"] = round(x * f, 6) if f else None
                else:
                    rec["conditions"][q] = x if x is not None else v
            elif col["kind"] == "value":
                x, qual = parse_number(v)
                if x is None:
                    stats["non_numeric_value_cells"] += 1
                    continue
                note = None
                if j + 1 < len(cols) and cols[j + 1]["kind"] == "note" and not is_missing(row[j + 1]):
                    note = str(row[j + 1])
                e = entry(col, x, qual, v, note)
                if j in over_1:
                    e["flag"] = "fraction_column_exceeds_1"
                    if "fraction_column_exceeds_1" not in rec["flags"]:
                        rec["flags"].append("fraction_column_exceeds_1")
                if col["quantity"] in ("density",) or col["quantity"] == "other":
                    rec["properties"].append(e)
                elif kind == "phase_composition":
                    c = cmap.get(col["index"])
                    e["species"] = species if species else (c["name"] if c else None)
                    rec["composition"].append(e)
                elif col["index"] in (None, solute_n) and (col["index"] or col["quantity"] in SOLUTE_ONLY | AMOUNT):
                    rec["solubility"].append(e)
                else:
                    c = cmap.get(col["index"])
                    e["species"] = c["name"] if c else None
                    rec["solvent_composition"].append(e)
        group = rec["solute"]
        if group and "compound" in rec["labels"] and (
                re.search(r" with |,", group["name"]) or re.search(r",| and ", group["formula"] or "")):
            # the listed component is a group ("Alkali metal iodides", "Argon with Krypton, Xenon");
            # the row names the specific one: 'Potassium iodide; IK; [7681-11-0]' or 'CO2'
            name, formula, cas = (rec["labels"]["compound"].split(";") + [None, None])[:3]
            rec["solute"] = {"name": name.strip(), "formula": formula.strip() if formula else None,
                             "cas": cas.strip(" []") if cas else None, "group": group["name"]}
        if not (rec["solubility"] or rec["composition"]):
            stats["rows_without_solubility_value"] += 1
            continue
        t = rec["temperature_K"]
        if t is not None and not T_PLAUSIBLE_K[0] <= t <= T_PLAUSIBLE_K[1]:
            rec["flags"].append("temperature_implausible")
        yield rec


def main():
    stats = collections.Counter()
    sheets = set()
    with open(DATA / "nist_gt.jsonl") as f, open(DATA / "nist_measurements.jsonl", "w") as out:
        for line in f:
            sheet = json.loads(line)
            for ti, table in enumerate(sheet["tables"]):
                for rec in measurements_for_table(sheet, ti, table, stats):
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    sheets.add(sheet["id"])
                    stats["measurements"] += 1
                    stats[f"type={rec['type']}"] += 1
                    stats[f"species_mapping={rec['species_mapping']}"] += 1
                    stats["with_temperature"] += rec["temperature_K"] is not None
                    for fl in rec["flags"]:
                        stats[f"flag={fl}"] += 1
    stats["sheets"] = len(sheets)
    print(json.dumps(dict(sorted(stats.items())), indent=1))


if __name__ == "__main__":
    main()
