# NIST ground-truth data

Ground truth for the DISSOLVE challenge, scraped from the
[IUPAC-NIST Solubility Database](https://srdata.nist.gov/solubility/) (NIST SRD 106, v1.1,
data content last updated 2012, DOI [10.18434/T4QC79](http://dx.doi.org/10.18434/T4QC79)).


**At a glance:** 18 IUPAC volumes, 2,528 systems, 5,162 compilation sheets, 5,117 data
tables, 67,169 table rows. Crawled 2026-10-21.

## Files

| Path | What |
|---|---|
| `data/nist_gt.jsonl` | One JSON record per compilation sheet (5,162 lines, ~13 MB). **The starting point for all further processing** |
| `data/nist_measurements.jsonl` | Normalised: one JSON record per measurement, i.e. per table row (62,142 lines, ~96 MB), built from `nist_gt.jsonl` — see [Measurements](#measurements-nist_measurementsjsonl) |
| `data/index.json` | Crawl index: volume → systems → sheet ids, with the `evaluated` flag |
| `data/raw_html/<id>.html` | Cached detail pages; re-parsing never needs the network |
| `scrape_nist.py` | Crawler (resumable: re-running only fetches what is missing) |
| `parse_nist.py` | HTML → `nist_gt.jsonl` |
| `normalize_nist.py` | `nist_gt.jsonl` → `nist_measurements.jsonl` |

Reproduce:

```bash
source .venv/bin/activate
python scrape_nist.py     # ~30 min, polite: 4 parallel requests, 0.2 s delay each
python parse_nist.py      # seconds, offline
python normalize_nist.py  # ~1 min, offline; prints coverage and flag counts
```

## How the website maps to the data

There is no API or bulk download. On the website you click
**Search Menu → Data Series (IUPAC volume) → a volume → a system → a sheet**. Each of
those pages corresponds to a part of the data, and every record carries the links back
to its pages.

| Level on the website | URL pattern | In the data |
|---|---|---|
| Start page | [`index.aspx`](https://srdata.nist.gov/solubility/index.aspx) | — |
| Volume list ("Data Series (IUPAC volume)") | [`dataSeries.aspx`](https://srdata.nist.gov/solubility/dataSeries.aspx) | the 18 keys of `data/index.json`; filter records by `series_id` / `iupac_volume` |
| Volume → list of systems | `sol_sys.aspx?nm_dataSeries=<series_id>` | `series_id` (`DS9`), `iupac_volume` (38), `volume_title`, `volume_url` |
| System → list of sheets | `sol_sys_lst.aspx?goBack=Y&sysID=<system_id>&SerialID=<series_id>` | `system_id` (`38001`), `system_url`; `system_name` is the link text |
| Sheet (the data page) | `sol_detail.aspx?goBack=Y&sysID=<id>` | **one record** in `nist_gt.jsonl`, `id` (`38_230`), `url`; cached as `data/raw_html/<id>.html` |

Things that trip people up:

- **The series number is not the volume number.** `DS9` is volume 38, `DS1` is volume 20 —
  see the table below. Use `iupac_volume` for the SDS volume.
- **`id` is `<volume>_<n>`, `system_id` is a separate number.** Sheet `38_230` belongs to
  system `38001`. Several sheets can share one system (one per original paper).
- **The volume page has several pages of systems** (e.g. volume 38 has 7). `volume_url`
  opens page 1; if your system is not there, click through the page numbers or open
  `system_url` directly. Those later pages have no URL of their own — the site loads them
  with a form submit, which is why the crawler replays it.
- **The "Evaluated?" checkbox** on the system page is the `evaluated` field.

### Sheet page labels → JSON fields

What you see on a sheet page (`url`), top to bottom:

| Label on the page | JSON field |
|---|---|
| Title line (e.g. "Benzene with Water") | `system_name` |
| Components: | `components` — `(1) Water; H2O; [7732-18-5]` → `{"index": 1, "name": "Water", "formula": "H2O", "cas": "7732-18-5"}` |
| Original Measurements: | `original_measurements` |
| Variables: | `variables` |
| Prepared By: | `prepared_by` |
| Experimental Remarks: | `experimental_remarks` |
| Experimental Data: (text above the table) | `experimental_data_text` |
| The data table | `tables[]` — table caption → `caption`, header row → `columns`, other rows → `rows` |
| Notes: | `notes` |
| Method/Apparatus/Procedure: | `method` |
| Source and Purity of Materials: | `source_and_purity` |
| Estimated Errors: | `estimated_errors` |
| Reference list at the bottom (evaluation sheets) | `critical_evaluation_refs` |

To check a record by hand, open its `url` and compare it label by label.

## Volumes covered

The NIST database covers only **18 of the 104 SDS volumes**, and the free SDS PDFs are
volumes 1–65. **Only 8 volumes have both a free PDF and NIST ground truth** (marked ✓) —
2,784 sheets. Use these for extraction accuracy.

| Series | Vol | Title | Systems | Sheets | Evaluated | Free PDF |
|---|---|---|---|---|---|---|
| DS1 | 20 | Halogenated Benzenes, Toluenes and Phenols with Water | 67 | 220 | 63 | ✓ |
| DS8 | 37 | Hydrocarbons in Water and Seawater, Part I | 67 | 403 | 29 | ✓ |
| DS9 | 38 | Hydrocarbons in Water and Seawater, Part II | 183 | 473 | 60 | ✓ |
| DS18 | 57 | Ethene | 173 | 260 | 19 | ✓ |
| DS6 | 58 | Polycyclic Aromatic Hydrocarbons: Binary Non-aqueous Systems, Part I | 330 | 434 | 6 | ✓ |
| DS7 | 59 | Polycyclic Aromatic Hydrocarbons: Binary Non-aqueous Systems, Part II | 330 | 427 | 12 | ✓ |
| DS2 | 60 | Halogenated Methanes with Water | 34 | 298 | 11 | ✓ |
| DS16 | 62 | Carbon Dioxide in Water and Aqueous Electrolyte Solutions | 111 | 269 | 5 | ✓ |
| DS15 | 66 | Ammonium Phosphates | 83 | 179 | 21 | |
| DS3 | 67 | Halogenated Ethanes and Ethenes with Water | 85 | 405 | 22 | |
| DS4 | 68 | Halogenated Aliphatic Compounds C3-C14 with Water | 76 | 215 | 36 | |
| DS5 | 69 | Ternary Alcohol-Hydrocarbon-Water Systems | 117 | 272 | 46 | |
| DS17 | 70 | Solubility of Gases in Glassy Polymers | 179 | 230 | 24 | |
| DS10 | 71 | Nitromethane with Water or Organic Solvents | 148 | 273 | 39 | |
| DS12 | 72 | Nitromethane: Ternary and Quaternary Systems | 112 | 163 | 22 | |
| DS14 | 73 | Metal and Ammonium Formate Systems | 195 | 267 | 17 | |
| DS11 | 77 | Nitroalkanes with Water or Organic Solvents | 103 | 159 | 14 | |
| DS13 | 78 | Acetonitrile Binary Systems | 135 | 215 | 25 | |

Note for the salt–solvent theme: the overlap volumes are mostly organics and gases in
water. Volume 62 (CO₂ in aqueous electrolytes) is the closest to salt systems; the pure
salt volumes (66 ammonium phosphates, 73 formates) have ground truth but no free PDF.

## Record schema

One record per sheet. Example (abridged):

```json
{
  "id": "38_230",
  "series_id": "DS9",
  "iupac_volume": 38,
  "volume_title": "Hydrocarbons in Water and Seawater, Part II",
  "system_id": "38001",
  "evaluated": false,
  "url": "https://srdata.nist.gov/solubility/sol_detail.aspx?goBack=Y&sysID=38_230",
  "system_url": "https://srdata.nist.gov/solubility/sol_sys_lst.aspx?goBack=Y&sysID=38001&SerialID=DS9",
  "volume_url": "https://srdata.nist.gov/solubility/sol_sys.aspx?nm_dataSeries=DS9",
  "system_name": "(+)-(R)-P-Mentha-1,8-diene (d-Limonene) with Water",
  "components": [
    {"index": 1, "name": "Water", "formula": "H2O", "cas": "7732-18-5"},
    {"index": 2, "name": "(+)-(R)-P-Mentha-1,8-diene (d-Limonene)", "formula": "C10H16", "cas": "5989-27-5"}
  ],
  "original_measurements": "Massaldi, H.A.; King, C.J., J. Chem. Eng. Data 1973, 18, 393-7.",
  "variables": "Temperature = 0 °C - 25 °C",
  "prepared_by": "A. Maczynski and Z. Maczynska",
  "experimental_remarks": null,
  "experimental_data_text": null,
  "notes": null,
  "method": "A technique based on head-space analysis by gas-liquid chromatography ...",
  "source_and_purity": "(1) Matheson Coleman and bell Co., highest purity; ...\n(2) not specified.",
  "estimated_errors": "Temperature: ± 0.05°C",
  "critical_evaluation_refs": null,
  "tables": [{
    "caption": "Solubility of d-limonene in water",
    "columns": ["t/°C", "10^3 * g_1/100 g solution (compiler)", "V_2/V_1 [mL2/mL1]",
                "10^6 * Mole Fraction x_1", "10^4 * n_1/V_2 [mol/L]"],
    "rows": [[0.0, 0.97, 9.7, 1.3, 0.708], [5.0, 1.04, 10.4, 1.4, 0.767], [25.0, 1.38, 13.8, 1.8, 1.013]]
  }]
}
```

| Field | Meaning |
|---|---|
| `id` | NIST sheet id, `<volume>_<n>`. Unique; use it to join back to `raw_html/` |
| `series_id` | NIST series key (`DS1`…`DS18`); not the volume number |
| `system_id` | NIST system id; several sheets can share one system |
| `url`, `system_url`, `volume_url` | Links to the sheet, its system page and its volume page on the NIST site |
| `evaluated` | `true` for an IUPAC critical evaluation sheet, `false` for a compiled measurement |
| `components` | As listed by NIST. **`index` does not always match the `_1`/`_2` numbers in column headers** — see [Component numbering](#component-numbering-nist-vs-the-table-headers) |
| `original_measurements` | Citation of the primary paper |
| `variables` | Free text, e.g. temperature/pressure range |
| `experimental_remarks` | Free text. Sheets without a table often give their values here |
| `experimental_data_text` | Free text in the data section |
| `tables` | `caption`, `columns`, `rows` |
| `method`, `source_and_purity`, `estimated_errors`, `prepared_by`, `notes`, `critical_evaluation_refs` | Free text |

All text fields are `null` when the sheet leaves them empty.

## Things to know before using it

### Gaps and quirks

- **33 sheets have no data at all.** Those pages are empty on the NIST site itself, so it's
  not a parsing problem. Mostly volumes 38 and 70:
  `37_136 37_153 38_196 38_203 38_303 38_321 38_322 38_337 38_350 38_363 38_366 38_372
  38_384 38_407 38_413 38_471 67_312 70_11 70_46 70_61 70_98 70_110 70_121 70_147 70_175
  70_177 70_178 70_180 70_182 70_190 70_217 70_220 70_221`.
- **471 sheets are IUPAC critical evaluations** (`evaluated: true`). Their sources are in
  `critical_evaluation_refs` rather than `original_measurements` (which is empty for them).
  Their values are recommended/tentative values, not raw measurements — keep them apart
  from measured data, or flag them, when building a training set.
- **66 sheets have tables whose rows don't all have the same number of cells.** This is
  mostly merged cells in the original HTML. Do not assume `len(row) == len(columns)` —
  check before zipping rows to headers.
- **724 sheets have no table but do have free-text values** in `experimental_remarks` /
  `experimental_data_text` (e.g. "0.103 mol L⁻¹ at room temperature"). A table-only
  pipeline silently drops these.
- **546 sheets have more than one table** (e.g. one per phase or per temperature series).
- **Component count varies:** 3,898 binary sheets, 1,087 ternary, 173 with 4–15
  components, 7 with one and 2 with none listed. Don't assume solute + solvent.

### Reading the tables

- **Cells** are converted to `float` when they are a plain number (303k cells), otherwise
  kept as a string (105k), or `null` when empty (639). Common strings: `-` (no value),
  phase labels (`water-rich phase`, `Liquid`), solid-phase formulas (`NH4H2PO4`),
  footnote letters (`a`, `b`, `c`), and chemical names in multicomponent tables.
- **Column headers carry the unit and a scale factor.** `<sup>`/`<sub>` are rendered as
  `^` / `_`: `10^3 * Mass Fraction w_1` means the cell value is 10³·w₁, so divide by 1000
  to get w₁. Always parse the factor before comparing values.
- **Units are mixed across sheets:** `t/°C` (3,561 headers) vs `T/K` (2,537); mole
  fraction, mass fraction, `g_1/100 g solution`, molality `m_1 [mol/kg]`, concentration
  `c_1 [mol dm**-3]`, volume ratios. Normalise before pooling data.
- **`(compiler)`** in a header means the IUPAC compiler calculated that column from the
  author's data; the other columns are as reported in the paper.
- **The subscript number is the original SDS component number**: `x_1` is the mole
  fraction of component (1) *as numbered in the SDS volume*, which is often not the order
  NIST lists in `components` — see the next section.
- **In salt tables (volumes 66 and 73) the subscript is not a component number at
  all.** Columns come in groups `Chemical_N`, `Mass Fraction w_N`, `m_N`, …, and the
  species is the text in the `Chemical_N` cell of the same row (`N`, `P2O5`, `NH3 (a)`,
  `Ca2+`, …) — ions or oxides, not the listed components. (Volume 70 uses a `Chemical Name`
  column the same way, for the polymer.)
- **Ditto marks:** a cell `"` means "same as the row above" (common in solid-phase columns).
- **Note columns** (`x_1 Note`, `Concent. c_1 Note`, …) hold footnote letters for the value
  column directly to their left.

### Component numbering: NIST vs the table headers

The `_1`, `_2`, `_3` in column headers follow the original SDS numbering, which is **the
order of the names in `system_name`**: in "Carbon dioxide with Sodium sulfate and Water",
1 = carbon dioxide, 2 = sodium sulfate, 3 = water. NIST's `components` list is often in a
different order, so `components[].index` must not be used to resolve headers.

Example `38_230`: NIST lists (1) Water, (2) d-limonene, but the system is "d-Limonene with
Water", the caption is "Solubility of d-limonene in water" and the columns are
`g_1/100 g solution` and `x_1` — so 1 = d-limonene.

Evidence:

- The system-name order agrees with the caption ("Solubility of A in B") in **413 of 415**
  tables that can be checked, across all volumes.
- It agrees with the "Source and Purity of Materials" text, which also uses SDS numbering
  ("(2) distilled water"), in about 90% of sheets — that text signal is itself noisy.
- NIST's own order is wrong for most binary aqueous sheets in volumes 20, 37, 38, 60, 67
  and 68, and about half the time in volumes 77 and 78.

`nist_measurements.jsonl` resolves every header this way and records how in
`species_mapping`.

## Measurements (`nist_measurements.jsonl`)

`normalize_nist.py` reads `nist_gt.jsonl` and turns **every table row into one record**: one
measurement, with its conditions, what was dissolved in what, and the result in every unit
the table gives. No regrouping needed.

**At a glance:** 62,142 measurements from 4,227 sheets. 30,804 are `solubility` records
(536 distinct solutes, 1,968 distinct solute–solvent systems), 31,338 are
`phase_composition` records. 96% have a temperature, 23% a pressure; 88% carry no flag.
17,924 measurements are in the 8 volumes that also have a free PDF.

### Example: from table to records

Sheet `62_197`, "Carbon dioxide with Sodium sulfate and Water", 1 atm
([page](https://srdata.nist.gov/solubility/sol_detail.aspx?goBack=Y&sysID=62_197)):

| T/K | Concentration C_2 [mol/L] | α | α Note |
|---|---|---|---|
| 298.15 | 0.0 | 0.7595 | a |
| 298.15 | 0.54 | 0.5242 | a |
| 298.15 | 0.678 | 0.4742 | a |
| 298.15 | 1.436 | 0.2867 | a |

Each row says: at 298.15 K and 1 atm, in water containing this much Na₂SO₄, this much CO₂
dissolves (α = Bunsen coefficient, note a). Row 2 becomes:

```json
{
  "measurement_id": "62_197/t0/r1",
  "sheet_id": "62_197", "table_index": 0, "row_index": 1,
  "iupac_volume": 62, "evaluated": false,
  "system_name": "Carbon dioxide with Sodium sulfate and Water",
  "citation": "...", "url": "https://srdata.nist.gov/solubility/sol_detail.aspx?goBack=Y&sysID=62_197",
  "type": "solubility",
  "solute": {"name": "Carbon dioxide", "formula": "CO2", "cas": "124-38-9"},
  "solvent": [{"name": "Sodium sulfate", "formula": "Na2SO4", "cas": "7757-82-6"},
              {"name": "Water", "formula": "H2O", "cas": "7732-18-5"}],
  "temperature_K": 298.15, "temperature_source": "column",
  "pressure_kPa": 101.325, "pressure": {"value": 101.325, "unit": "kpa"},
  "solubility": [
    {"quantity": "bunsen_coefficient", "value": 0.5242, "unit": null, "value_qualifier": null,
     "raw_value": 0.5242, "header": "α", "compiler_calculated": false, "note": "a"}
  ],
  "solvent_composition": [
    {"quantity": "amount_concentration", "value": 0.54, "unit": "mol/L", "species": "Sodium sulfate",
     "value_qualifier": null, "raw_value": 0.54, "header": "Concentration C_2 [mol/L]", "compiler_calculated": false}
  ],
  "composition": null,
  "properties": [],
  "phase": null, "solid_phase": null, "conditions": {}, "labels": {},
  "species_mapping": "system_name",
  "flags": []
}
```

The general case — solvents a, b and solute x — has the same shape: `solute` = x,
`solvent` = [a, b], `solvent_composition` says how much b is in the solvent, `solubility`
says how much x dissolves (often the same amount in several units, e.g. g/100 g, mole
fraction and mol/L, all in one list). A sheet that measures two solutes has separate tables
or rows for each, so each record has one solute.

### Two record types

| `type` | Records | When | Filled fields |
|---|---|---|---|
| `solubility` | 30,804 | One compound is the solute | `solute`, `solvent`, `solubility`, `solvent_composition` |
| `phase_composition` | 31,338 | Multicomponent equilibria with no single solute: salt systems with `Chemical_N` columns (volumes 66, 73), ternary liquid–liquid tie lines (volumes 69, 72, 77), … | `composition` (each entry has its `species`), `solid_phase`, `phase` |

How the solute is chosen, per table, first rule that applies:

1. Table has `Chemical_N` columns (salt systems) → `phase_composition`.
2. Caption "Solubility of A in B" → A.
3. Table has a gas-solubility coefficient (Ostwald, Bunsen, Henry, Kuenen, sorption, …) →
   the first-named compound (the gas); other amount columns describe the solvent.
4. All amount columns refer to one compound → that compound. This is how "Solubility of
   water in benzene" tables (`x_2`) get water as the solute.
5. Binary system with amounts of both → compound 1 (e.g. `x_1` and `x_2 = 1 − x_1`).
6. Three or more compounds with fractions of several → `phase_composition`.

### Fields that need explaining

Most fields say what they are (`sheet_id`, `url`, `citation`, `iupac_volume`,
`temperature_K`, `pressure_kPa`, `phase`, …). These are the ones that don't:

**`measurement_id`** — `<sheet_id>/t<table>/r<row>`: the table and row (0-based) in that
sheet's `tables[].rows[]` in `nist_gt.jsonl`. `62_197/t0/r1` = sheet `62_197`, first table,
second row.

**`solubility` vs `solvent_composition` vs `composition`** — the numbers of the row, split
by what they describe:

| Field | Holds | Example (`62_197`, CO₂ in Na₂SO₄ solution) |
|---|---|---|
| `solubility` | How much **solute** dissolved. One entry per column, so the same amount can appear in several units (g/100 g, mole fraction, mol/L) | α = 0.5242 |
| `solvent_composition` | What the **solvent** is made of: salt concentration, cosolvent fraction, or `x_2` in a binary | Na₂SO₄ 0.54 mol/L |
| `composition` | Only in `phase_composition` records: amount of every species in the phase | — |
| `properties` | Anything else in the row (density, unclassified columns) | — |

**`solvent`** — every compound of the system except the solute, so for a salt solution it
lists both the salt and water. How much of each is in `solvent_composition`.

**`solute.group`** — present only when NIST lists a group as one component ("Alkali metal
iodides", "Argon with Krypton, Xenon, …") and the row names the specific compound. Then
`solute.name` is the row's compound (`Potassium iodide`, `CO2`) and `group` keeps the list.

**`temperature_source`** — where `temperature_K` came from:

| Value | Meaning |
|---|---|
| `column` | The table has a `t/°C` or `T/K` column; this row's own value. Most reliable |
| `caption` | No column; the table caption states one temperature for all rows ("… at 273 K") |
| `variables` | No column or caption temperature; the sheet's "Variables:" states one temperature |
| `null` | None found: a range ("0 °C - 25 °C"), "Room temperature", or nothing |

`pressure` / `pressure_kPa` work the same way (column, else a single "Pressure = …" in the
caption or Variables); `pressure` is as written, `pressure_kPa` converted when the unit is known.

**`species_mapping`** — how the header numbers (`x_1`, `w_2`) were matched to compounds:

| Value | Records | Meaning |
|---|---|---|
| `system_name` | 51,288 | Order of names in the system name (see Component numbering). Reliable |
| `table` | 9,127 | From `Chemical_N` cells in the row (salt systems). Reliable |
| `nist_order` | 1,683 | Fallback to NIST's component order. **Unverified** — may be swapped |
| `caption` | 29 | From "Solubility of A in B" |
| `source_text` | 15 | From the "(n) distilled water" line of Source and Purity |

**`evaluated`** (per record) and **`compiler_calculated`** (per value) — who the number is from.
`evaluated: true`: an IUPAC critical evaluation (recommended/tentative values), not one
paper's measurement. `compiler_calculated: true`: the header says `(compiler)` — the IUPAC
compiler converted the authors' data to this unit; the authors did not report it.

**`solid_phase`** — the solid in equilibrium with the solution. Often a letter (`A`, `B`,
`A + B`) defined in the sheet's `notes` or caption in `nist_gt.jsonl`.

**`labels`** — free-text row labels (comments, solution numbers). `labels.compound` is the
`Chemical Name` cell: which salt or polymer the row is about.

Inside each value entry:

| Field | Meaning |
|---|---|
| `value` | The number **after** applying the header's scale factor: `10^6 * Mole Fraction x_1` with cell `1.3` → `1.3e-6` |
| `raw_value`, `header` | The cell and column header exactly as on the website — use them to check `value` |
| `unit` | `"1"` = dimensionless fraction. Otherwise as written, with common aliases unified (`mol dm**-3` → `mol/L`) |
| `quantity` | One of 27 kinds. For the generic `solubility`, `composition` and `other`, read `header` and `unit` to know what the number is |
| `value_qualifier` | `<`, `>`, `~`, `ca.` if the cell had one, so `value` is a bound or estimate |
| `note` | Footnote letters from the `... Note` column next to it; defined in the sheet's `notes` |
| `flag` | `fraction_column_exceeds_1`, see Flags |

### How headers are read

Each header is split as `[10^k *] <quantity>_<n> [(compiler)] [[unit]] [^footnote]`:

| Header | quantity | n | scale | compiler | unit |
|---|---|---|---|---|---|
| `10^6 * Mole Fraction x_1` | `mole_fraction` | 1 | 1e-6 | no | `1` |
| `10^2 * Mass Fraction w_1 (compiler)` | `mass_fraction` | 1 | 0.01 | yes | `1` |
| `m_1 [mol kg-1]^a` | `molality` | 1 | 1 | no | `mol/kg` |
| `10^5 * Concentration c_1 [mol dm**-3]` | `amount_concentration` | 1 | 1e-5 | no | `mol/L` |

Other columns: `t/°C`, `T/K`, `Pressure`, `pH`, `Ionic Strength` → conditions;
`Phase`, `Solid Phase(s)` → `phase`, `solid_phase`; `... Note` → `note` of the value to its
left; `Chemical_N` → species of the values to its right; comments, solution numbers,
methods → `labels`. Ditto marks (`"`) are replaced by the value above.

### Flags

| Flag | Records | Meaning |
|---|---|---|
| `fraction_column_exceeds_1` | 7,279 | A mole/mass-fraction column with some value > 1. Mostly volumes 66/73, where `Mass Fraction w_1` columns hold percentages; in a few (volumes 57, 62) NIST dropped the `10^k` factor. Values are left untouched because the two cases can't be told apart reliably; the affected entries carry `"flag"` too |
| `temperature_implausible` | 133 | Temperature outside 200–800 K. Almost all are typos on NIST itself (`038.2 K` for 308.2 K, `29 K` for 298 K, `101.3 K` that is a pressure). 723–773 K in volume 62 is real |

### What is not in `nist_measurements.jsonl`

- **Values given only as text** (724 sheets, `experimental_remarks`). Not parsed.
- **488 rows of ragged tables** (cell count differs from header count) — skipped, because
  cells can't be assigned to columns safely.
- **3,939 rows with no amount at all** (only conditions, densities or text).
- **2,081 value cells that are not numbers**, e.g. `- (UCST)`, `760 g/1000g H2O`, `1:0.13`.
- The 33 empty sheets.

### Known limits of the solute/solvent assignment

The rules above are heuristics checked on examples, not on every sheet. Watch for:

- **Binary solid–liquid tables** (volumes 58, 59) cover the whole composition range; near
  the other end the "solute" is really the other compound. `solid_phase`, where given, tells.
- **`nist_order` records** (1,683) could not be resolved from the system name; their
  header-to-compound mapping is unverified.
- **Gas tables** (rule 3) assume the gas is named first in the system name, as the SDS
  does.
- **Group solutes:** some sheets list a group as one component ("Alkali metal iodides",
  "Argon with Krypton, Xenon, …") and name the specific compound per row in a
  `Chemical Name` column. For those 1,528 records `solute` is the row's compound (`CO2`,
  `Potassium iodide`) and `solute.group` keeps the listed group; the row's compound is
  often only a formula-like label (`CO2`, `N20`), without CAS.

### Using it

- **Solubility of X in Y at T:** `type == "solubility"`, `solute.name == X`, pick one
  `quantity` from `solubility` (e.g. `mole_fraction`) so you don't count the same
  measurement in several units, and filter `flags == []`.
- **Salt effects / mixed solvents:** `solvent_composition` gives the salt concentration or
  cosolvent fraction for each solubility value.
- **Measured vs derived:** `compiler_calculated` (per value) and `evaluated` (per record)
  separate author data from compiler conversions and IUPAC recommended values.

## Using it as gold for json-extract-eval

- The records are scraped from the database, not from the PDFs. A PDF sheet and its NIST
  record should hold the same content, but formatting differs (header spelling, `^`/`_`
  markers, footnotes). Evaluate on a normalised target schema, not on raw headers.
- Match extracted sheets to gold by citation + system (or by `id` if your extractor
  records the PDF sheet position), not by order.
- Restrict extraction-accuracy runs to the 8 overlap volumes above.
