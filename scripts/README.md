# Scripts: roles and how they connect

All scripts are standard-library Python 3, run as `python3 -I scripts/<name>.py` from the
repository root, and take a volume name (`SDS-60` or `60`). Two modules are imported by
the others and have no command line of their own:

- `paths.py`: where a volume's files live. `volume_root(vol)` is `data/ground_truth/` for
  the eight volumes keyed in the NIST database (status `mined` in `data/volumes.csv`) and
  `data/` otherwise; `NIST` is the folder of the scraped database sheets; `all_boxes()`
  lists every segmented volume. Every script that reads or writes per-volume files goes
  through it, so the ground-truth split is in one place.
- `textnorm.py`: the normalisations that make OCR text and keyed text comparable.
  `strict()` closes the spaces ClearScan puts inside numbers and folds a few glyph
  confusions, `loose()` keeps lowercase alphanumerics only, `numbers()` yields the numeric
  tokens of a table cell (mantissa only), `cas_numbers()` and `cas_valid()` find and
  check CAS Registry Numbers. Any matching between witnesses uses these, never ad hoc
  regexes, so that "found" means the same thing in every report.

## Data flow

```
IUPAC mirror ──fetch_volumes.sh──▶ pdfs/SDS-N.pdf ──pdftotext──▶ text/SDS-N.txt
                                        │                              │
                                        │                      segment_boxes.py
                                        │                              ▼
                                        │                       boxes/SDS-N.jsonl ◀── mineru_to_boxes.py ◀── MinerU page pass
                                        │                              │                     ▲
                                  crop_tables.py                       │              crops_to_boxes.py ◀── MinerU crop pass
                                        ▼                              │
                                 crops/p<page>_<band>.png ─────▶ (GPU node) ──▶ crops/tables.jsonl

NIST database ──nist_scrape.py──▶ ground_truth/nist/SDS-N.json
                                        │
                                  align_nist.py  ◀── any boxes/*.jsonl (text layer, MinerU page, MinerU crops)
                                        ▼
                            ground_truth/nist/align-SDS-N.csv   (per sheet: matched OCR sheet, value recall)

boxes/*.jsonl ──cas_survey.py──▶ check-digit report          extracted values ──backsearch.py──▶ OK / ELSEWHERE / MISSING
boxes/*.jsonl ──cas_resolve.py──▶ cas/cas_resolved.csv        text/SDS-N.txt ──scan_columns.py──▶ header vocabulary
```

The boxes jsonl is the hinge. One record per data sheet, with `page`, `index_on_page`,
`kind` (compilation or evaluation), `continued`, and `boxes` keyed by the printed field
(`components`, `original_measurements`, `variables`, `prepared_by`, `experimental_values`,
`method`, `source_purity`, `estimated_error`, `references`, or `evaluator` and
`critical_evaluation`). Whatever reads a page, text layer or vision model, is converted
to this shape, and everything downstream (alignment, CAS checks, extraction) consumes it
without knowing which witness produced it.

## The scripts

| script | reads | writes | role |
|---|---|---|---|
| `fetch_volumes.sh` | IUPAC GitHub mirror | `pdfs/`, `text/` | download the 56 volume PDFs and cache their text layer, one page per form feed |
| `scan_columns.py SDS-N` | `text/` | report | tally the column-header lines under EXPERIMENTAL VALUES: the vocabulary of units and quantities per volume |
| `segment_boxes.py SDS-N` | `text/` | `boxes/SDS-N.jsonl` | cut the text layer into sheets at the COMPONENTS header and into boxes at the printed field headers (fuzzy, OCR-tolerant); split two-column regions; flag sheets with missing parts |
| `nist_import.py nist_gt.jsonl` | the DISSOLVE repository's complete NIST crawl (library `nist/nist_gt.jsonl`) | `ground_truth/nist/SDS-N.json` | write the per-volume ground truth the aligner reads from the colleague's one-record-per-sheet file: all 2 784 sheets of the eight volumes with a free PDF, evaluation sheets flagged; supersedes `nist_scrape.py`, which stopped after the first 30 systems of a volume |
| `nist_scrape.py 60` | srdata.nist.gov | `ground_truth/nist/SDS-N.json` | the original scraper of the hand-keyed sheets (boxes plus the table as headers and rows; raw HTML cached); pages the sheet lists but not the systems list, so it is kept for reference only |
| `align_nist.py 60 [--boxes X --out Y]` | NIST json, a boxes jsonl | `align-SDS-N.csv` | match each NIST sheet to one segmented sheet (solute CAS numbers, citation tokens, value recall; greedy one-to-one) and report the fraction of keyed values found verbatim and the NIST rows whose numeric tokens all occur in one line of the matched box: the acceptance numbers of every witness |
| `backsearch.py SDS-N values --page P` | `text/` | report | search extracted values back into the page in two tiers (strict, loose); CAS-shaped values also get a check digit verdict |
| `cas_survey.py` | all boxes, NIST json | report | check digit of every printed CAS number and of NIST's: OCR errors on one side, keying errors on the other |
| `cas_resolve.py` | all boxes, PubChem | `cas/cas_resolved.csv`, cache | resolve each printed CAS number in PubChem and compare the resolved name and formula with the printed ones; suggests the intended number for typos |
| `crop_tables.py SDS-N.pdf out/ [--rows] [--pages] [--manifest-only]` | PDF, its text layer | `out/p<page>_<band>.png`, `manifest.csv` | cut the EXPERIMENTAL VALUES band of every sheet (or, with `--rows`, every printed line) to an image for the vision model, located by the text layer's word coordinates; only capitalised headers on pages with the sheet frame count, duplicate bands are dropped, INFORMATION/METHOD/COMMENTS close a band when the AUXILIARY banner is unreadable; the manifest counts the numeric lines per band |
| `mineru_to_boxes.py page.json boxes.jsonl` | MinerU page output | boxes jsonl | turn MinerU's one-table-per-sheet HTML into boxes records: a sheet starts at a COMPONENTS cell, a table without one continues the sheet before |
| `crops_to_boxes.py boxes.jsonl tables.jsonl out.jsonl` | boxes jsonl, crop results | boxes jsonl | replace each sheet's flattened EXPERIMENTAL VALUES text by the row-structured table read from its crop, matched by shared numbers on the same page; rowspan cells (a temperature left blank to mean "as above") are repeated in every row they span |
| `mineru_viewer.py extracted/ out.html` | MinerU page output | HTML | show each sheet's region image next to the table MinerU returned, for eyeballing |
| `unpack_node.py SDS-N [--raw DIR]` | the node hand-back linked as `mineru/SDS-N/raw` (page zip, per-crop zips, logs, manifest) | `mineru/SDS-N/{structured_content.json, middle_json.json, run.log, handback.md, crops/manifest.csv, crops/run.log, crops/tables.jsonl}` | unpack one volume's node results into the layout the converters read; `tables.jsonl` holds the blocks of every crop, read from the per-crop zips without extracting their images; with `--crops NAME --raw DIR` a crop-pass-only hand-back (a second run on new bands) is unpacked into `mineru/SDS-N/NAME/` next to the first run, for `crops_to_boxes.py boxes-page.jsonl NAME/tables.jsonl boxes-NAME.jsonl` and the checks on that file |
| `sdstable.py` (module) | | | parsing shared by the consumers of a boxes jsonl: `column()` maps a printed header to one of the IUPAC solubility quantities (temperature, total and partial pressure, mole and mass fraction, mass ratio, molality, concentration, mass concentration, density, Bunsen, Ostwald, Kuenen, Henry in three conventions, pH, salinity, solid phase) with component index, prefactor (`10^4 x_1`, `103x1`) and unit factor; `split_blocks()` the header and rows of each sub-table of a crop; `normalise_rows()` fills blank leading conditions meaning "as above"; `conditions_from_variables()` the single T and P of a VARIABLES box; `molar_mass()` from the printed formula |
| `to_nomad.py SDS-N boxes.jsonl out/ --zip` | a boxes jsonl (crop pass), the text layer's citation lines, `schema/` | `out/schema.archive.yaml`, `out/SDS-N/p<page>-<sheet>/r<row>.archive.json`, zip | one `EquilibriumSolution` entry per table row: temperature, T_in/T_fin and pressure (from the table, else from a single-valued VARIABLES box); a liquid phase whose components carry CAS, name, formula, the SOURCE AND PURITY text and an `Amount` with every solubility quantity the row prints for them in the schema's storage units (mole and mass fraction, molality, molar and mass concentration, mass ratio, Bunsen, Ostwald, Kuenen, Henry in three conventions, partial pressure); a solid or gas phase for x(s) and y columns; density, salinity, pH; the ESTIMATED ERROR box split into its temperature and solubility sentences; unmapped columns and provenance in `description`; whole-sheet crops and rows shorter than the header skipped; validated with `schema/pydantic_schema.py`; run with `uv run python` |
| `check_rows.py SDS-N [--text] [--all]` | a boxes jsonl (crop pass), `text/` | `checks-rows.csv`, `checks-sheets.csv` next to the boxes | quality checks on every table row from the identities between the IUPAC quantities and the redundant columns the compilers printed (mass against mole fraction through the molar masses, molality, mass ratio, Celsius against kelvin, Ostwald against Bunsen, Henry against mole fraction, total against partial pressure, closure of mole fractions, ranges, row width against the header, every numeric token found in the text layer); per sheet the trend against temperature, compiler columns without their source column, header coverage, glued cells; a check applies only where its inputs are printed and the selection is reported; a failing ratio near a power of ten is noted as a misread prefactor or exponent |

## Typical sequences

Text-layer witness for a volume: `fetch_volumes.sh`, `segment_boxes.py SDS-N`, then for a
ground-truth volume `nist_import.py` once (the library holds `nist/nist_gt.jsonl`) and `align_nist.py N`.

Vision witness: `crop_tables.py` here, the page pass and the crop pass on the GPU node
(driven by the internal brief in the HU Box library), `unpack_node.py` on the hand-back, then `mineru_to_boxes.py`, `crops_to_boxes.py`, and
`align_nist.py N --boxes ... --out ...` to score the result with the same yardstick.

Quality control of an extraction: `check_rows.py SDS-N --text` for the rows (identities between
the printed columns, text-layer back-search of every number), `backsearch.py` for single values,
`cas_survey.py` and `cas_resolve.py` for the identifiers; `check_rows.py --all --text` prints the
summary table over the ground-truth volumes.

NOMAD upload: `uv run python scripts/to_nomad.py SDS-60 data/ground_truth/mineru/SDS-60/boxes-crops.jsonl out/nomad-SDS-60 --zip`
writes the entries next to a copy of the schema and zips them as an upload; the volume 60
zip is in the HU Box library under `nomad/`.
