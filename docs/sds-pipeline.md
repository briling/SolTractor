# Data layout and pipeline

Everything below lives under `data/`; the scripts are in `scripts/` and resolve the
folders themselves.

- `pdfs/`  volumes 1-65 from https://iupac.github.io/SolubilityDataSeries/volumes/SDS-N.pdf
           (5/6, 16/17, 27/28, 45/46, 53 are not on the mirror); scanned, OCR text layer.
           Volumes 66+ are JPCRD articles (DOI only), not included.
- `text/`  cached `pdftotext -layout` output per volume, one page per form feed.
- `scripts/fetch_volumes.sh`  download + text cache.
- `scripts/scan_columns.py`   tally EXPERIMENTAL VALUES table headers per volume.
- `extracted/`  LLM extraction output.
- `ground_truth/`  the 8 volumes keyed in the NIST database, kept apart from the extraction
           targets: their `pdfs/`, `text/`, `boxes/` and `extracted/`, plus `nist/` (the
           scraped database sheets and their alignment with the OCR sheets).

Each volume is a sequence of fixed-form data sheets: COMPONENTS / ORIGINAL
MEASUREMENTS / VARIABLES / PREPARED BY / EXPERIMENTAL VALUES / AUXILIARY
INFORMATION (METHOD, SOURCE AND PURITY, ESTIMATED ERROR, REFERENCES), plus
CRITICAL EVALUATION sheets per system.

The PDFs are not committed (687 MB); run `scripts/fetch_volumes.sh`
to download them into `pdfs/` (`ground_truth/pdfs/` for the mined volumes) and regenerate
`text/`. Scripts take a volume name and resolve its folder themselves (`scripts/paths.py`,
from the status in `volumes.csv`), e.g.

```bash
python3 -I scripts/scan_columns.py SDS-30 --tokens --lines 4
python3 -I scripts/backsearch.py SDS-1 "298.15" "10361-37-2" --page 45
```

## Mined vs unmined volumes

The IUPAC-NIST Solubility Database (NIST SRD 106, https://srdata.nist.gov/solubility/,
data last updated 2012) holds 18 volumes keyed by hand: 20, 37, 38, 57, 58, 59, 60, 62,
66-73, 77, 78. Each compilation sheet is one page
(`sol_detail.aspx?sysID=<vol>_<n>`) with the components, original measurement, variables,
an HTML table of the experimental values with explicit column headers and units, and the
method, purity and error boxes; critical evaluations are separate pages. Volumes are
listed at `dataSeries.aspx`, systems per volume at `sol_sys.aspx?nm_dataSeries=DS<k>`,
and sheets per system at `sol_sys_lst.aspx?sysID=<id>&SerialID=DS<k>` (paged, 30 per page).

`volumes.csv` classifies the 65 monograph volumes:

| status  | volumes | pages | meaning |
|---------|--------:|------:|---------|
| mined   | 8       | 3168  | PDF on the mirror and sheets in the NIST database: ground truth for calibrating extraction and QC, under `ground_truth/` |
| unmined | 46      | 17921 | PDF on the mirror, not in the database: the extraction target |
| index   | 3       |       | cumulative indexes (19, 39, 53), no data sheets |
| missing | 8       |       | not on the mirror (5/6, 16/17, 27/28, 45/46) |

The NIST transcription is not error-free either (e.g. a purity keyed as "00.78 %"), so
disagreements between the extraction and the database need the page image as arbiter.

## Pipeline scripts

- `scripts/paths.py`: where a volume's files live (`data/ground_truth/` for mined volumes,
  `data/` otherwise).
- `scripts/textnorm.py`: normalization shared by the QC scripts (strict: OCR-spaced
  digits and punctuation; loose: alphanumerics only; numeric tokens of a cell; CAS numbers).
- `scripts/segment_boxes.py SDS-N`: cuts the OCR text into sheets and their printed boxes
  (`boxes/SDS-N.jsonl`, one record per sheet). Box headers are matched fuzzily and the
  two-column regions are split at the column of the right-hand header. Committed for the
  mined volumes only (`ground_truth/boxes/`); the others regenerate in seconds.
- `scripts/nist_scrape.py 60 [...]`: scrapes the NIST database sheets of a volume into
  `ground_truth/nist/SDS-N.json` (same box names, plus the experimental table as headers
  and rows). Raw HTML is cached in the ignored `ground_truth/nist/raw/`. Volumes 66-78 are
  JPCRD articles without a PDF here, so only their NIST sheets are kept.
- `scripts/align_nist.py 60`: matches NIST sheets to OCR sheets (solute CAS numbers,
  citation tokens, and recall of the keyed table values in the OCR box; one-to-one) and
  writes `ground_truth/nist/align-SDS-N.csv`. For volume 60: 263 of 288 sheets aligned, 97% of the
  keyed table values occur verbatim in the matching OCR box.
- `scripts/backsearch.py SDS-N value ... --page P`: confirms extracted values against the
  OCR layer.

## Second witness: MinerU on the page images

The text layer is one reading of every page; the second is
the document vision model MinerU 2.5-Pro run on a GPU node over the page images. Its
results for the ground-truth volumes live in `ground_truth/mineru/SDS-N/` (page JSON,
run logs, the converted boxes, the NIST alignments, `CHECKS.md` with the numbers and
`example/` with one crop and its returned table). The bulky raw output (the model output
with region images, the crop PNGs, the per-crop results) and the PDFs live in the HU Box
library `sds-extraction`, which keeps the layout of the staging folder; sync it next to
the clone and link it as `ground_truth/mineru/SDS-N/raw` (ignored) and `pdfs`;
`scripts/unpack_node.py SDS-N` unpacks a hand-back into the committed layout. All eight
ground-truth volumes have been through both passes. Two passes per
volume:

- whole pages: every sheet comes back as one table whose cells are the printed boxes,
  nearly free of the text layer's defects (`scripts/mineru_to_boxes.py` converts it to the
  boxes format), but with the EXPERIMENTAL VALUES table flattened to one cell;
- crops: `scripts/crop_tables.py` cuts the EXPERIMENTAL VALUES band of every sheet from
  the PDF (located through the text layer's word coordinates; `--rows` cuts one strip per
  printed line instead), the node parses the crops, and `scripts/crops_to_boxes.py` puts
  the resulting row-structured tables back into the sheets.

`scripts/align_nist.py 60 --boxes ... --out ...` scores any boxes file the same way as the
text layer. On volume 60 the text layer, the page pass and the crop pass reproduce 97 %,
95 % and 96 % of the keyed values verbatim; only the crop pass reproduces the rows (207 of
264 sheets with every NIST row intact). `scripts/mineru_viewer.py` renders a page output
next to its region images for inspection.

## The eight ground-truth volumes through both passes

The node ran the page pass and the crop pass over all eight NIST-keyed volumes
(hand-backs in the library, unpacked with `scripts/unpack_node.py`, converted and
aligned as above; files under `ground_truth/mineru/SDS-N/`). Value recall is the
aligner's substring measure on the aligned sheets; "rows" counts NIST table rows whose
numeric tokens all occur in one line of the matched EXPERIMENTAL VALUES box, which only
the crop pass delivers. Note that the scraped NIST sheets cover volume 60 and 20 well
but only 18 to 55 sheets of the other volumes.

| volume | NIST sheets | text layer: aligned, recall | page pass: aligned, recall | crop pass: aligned, recall | rows in one line (crops) | entries |
|-------:|------------:|----------------------------:|---------------------------:|---------------------------:|-------------------------:|--------:|
| 20 | 94 | 90, 96.7 % | 83, 99.7 % | 83, 99.7 % | 183 / 185 | 237 |
| 37 | 23 | 18, 94.1 % | 19, 100 % | 19, 94.2 % | 81 / 94 | 1148 |
| 38 | 18 | 10, 98.3 % | 9, 100 % | 9, 100 % | 36 / 36 | 889 |
| 57 | 42 | 19, 81.2 % | 18, 83.4 % | 17, 83.0 % | 160 / 253 | 1595 |
| 58 | 32 | 10, 98.0 % | 30, 98.7 % | 29, 99.9 % | 198 / 235 | 1023 |
| 59 | 33 | 19, 87.2 % | 32, 99.5 % | 31, 99.6 % | 258 / 283 | 2423 |
| 60 | 288 | 263, 97.2 % | 263, 95.1 % | 264, 95.7 % | 614 / 733 | 722 |
| 62 | 55 | 21, 89.3 % | 21, 87.6 % | 21, 88.6 % | 422 / 688 | 4749 |

The text layer aligns a third of the NIST sheets of volumes 58 and 59 where the page
pass aligns nearly all of them: the segmenter loses the sheets, not the values. Volume 57
(gas solubilities, two-block tables with pressure columns) and 62 (long multi-column
tables, Bunsen and Ostwald coefficients) are the hard cases for the row structure.
The rows column is `align_nist.py`'s second number, NIST table rows whose numeric tokens all occur in one
line of the matched box; it moved from 54 to 160 (volume 57), 569 to 614 (60) and 90 to 422 (62) when
`crops_to_boxes.py` started to honour rowspan cells (see the quality checks below).
`scripts/to_nomad.py` turns the crop-pass boxes of each volume into one NOMAD upload
(`nomad-SDS-N.zip` in the library's `nomad/` folder, 12 786 entries in all, every one
validated against the schema with NOMAD's metainfo). Since the schema of 2026-10-22 names
each solubility quantity as its own field of `Amount`, the exporter fills every quantity a row
prints for a component (mole and mass fraction, molality, molar and mass concentration, mass
ratio, Bunsen, Ostwald and Kuenen coefficients, Henry's constant in its three conventions,
partial pressure) in the schema's storage units, adds a solid or gas phase for x(s) and y
columns, and carries density, salinity, pH, the SOURCE AND PURITY text per component and the
ESTIMATED ERROR box split into temperature and solubility. 11 311 entries (88 %) carry at
least one solubility quantity; the rest are rows whose columns the mapper does not know.
Crops in which the model returned the whole sheet as a table (header cells carrying box
names) are skipped; when the table has no temperature column, a single-valued VARIABLES
box supplies it.

## Quality checks on the rows

`scripts/check_rows.py` checks every exported row against the physics the sheets print
twice. The compilers added a "(compiler)" column to nearly every table, converting the
original quantity to the IUPAC one, and the IUPAC quantities are related by closed
formulas: mass and mole fraction through the molar masses (from the printed formulas),
mass ratio and mass fraction, molality and mole fraction, Celsius and kelvin, Ostwald and
Bunsen coefficient (L = αT/273.15), Bunsen coefficient and mole fraction through the
water density, Henry's constant and mole fraction at the stated partial pressure, total
pressure against partial pressure plus the water vapour pressure, closure of the mole
fractions of one phase, ranges. Each check applies only where its inputs are printed in
the row; the recomputed value must agree with the printed one within one unit of the
last printed digit plus 0.3 % (`--tolerance`). A failing ratio close to a power of ten is
noted as a misread prefactor or exponent, which is what a vision model gets wrong in a
header. Per sheet, the solubility against temperature must change direction at most once
(the row whose removal restores the trend is the outlier), a compiler column must have
the printed column it was computed from, and the header coverage is reported. With
`--text` every numeric token of a row is searched in the text layer of its page.

The row width check found the largest single defect of the pipeline. When a sheet
leaves the temperature blank to mean "as above", MinerU returns the cell with a rowspan,
and `crops_to_boxes.py` flattened the HTML row by row and dropped the span, so 2 678 of
the 4 631 rows of volume 62 and 1 041 of 1 847 in volume 57 came back shorter than their
header and were exported with values in the wrong columns. The converter now repeats a
rowspan cell in every row it spans. The rows still short (252 in volume 57, two-block
tables with an extra leading cell; 21 in 59; 11 in 62) are skipped by the exporter and
listed for the arbiter; `sdstable.normalise_rows` keeps a ditto fallback for converters
without spans. Two other layout defects are handled in `split_blocks`: two sub-tables in
one crop (solubility of (1) in (2) above (2) in (1)), and a header whose first line holds
`t/°C` and a title. Results over the crop pass of the eight volumes
(`check_rows.py --all --text`):

| volume | rows | ditto rows (fallback) | shifted rows | headers mapped | hard checks | pass | fail | rows with a number missing from the text layer | sheets monotonic / outlier / changing |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 20 | 237 | 0 | 0 | 233/283 | 504 | 443 | 61 | 4 | 12 / 0 / 4 |
| 37 | 1 148 | 0 | 0 | 575/645 | 2 000 | 1 892 | 108 | 70 | 60 / 13 / 8 |
| 38 | 889 | 0 | 0 | 405/522 | 1 413 | 1 368 | 45 | 43 | 41 / 6 / 5 |
| 57 | 1 847 | 2 | 252 | 717/1 067 | 1 834 | 1 753 | 81 | 145 | 26 / 2 / 2 |
| 58 | 1 023 | 0 | 0 | 333/341 | 1 765 | 1 760 | 5 | 37 | 54 / 2 / 28 |
| 59 | 2 444 | 0 | 21 | 695/711 | 4 404 | 4 384 | 20 | 242 | 83 / 7 / 84 |
| 60 | 722 | 0 | 0 | 1 099/1 241 | 1 582 | 1 540 | 42 | 36 | 35 / 6 / 10 |
| 62 | 4 760 | 11 | 11 | 1 033/1 234 | 6 875 | 6 870 | 5 | 134 | 2 / 1 / 45 |

The failures are what the check is for. Volume 60, page 43: the header `10^5 x_1` against
a mass fraction that predicts `10^3 x_1`, all three rows off by exactly 10^2. Volume 37,
page 39: `10^3 x_1` disagrees with the printed `g(1)/100 g sln` by a factor ten while the
next column, `10^4 x_1 (corrected by compiler)`, agrees, so the sheet itself carries a
compiler's correction the check reproduces. Volume 20 shows a steady 3.5 % between
`mol(1)/kg` and `10^6 x(1)` on one sheet, which is the compilers' arithmetic rather than a
reading error. Sheets where many checks fail at once have a shifted or misaligned header.
Volume 62's trend column (2 monotonic sheets, 45 changing) reflects tables in which the
pressure varies along with temperature, not bad values; the check declares itself not
applicable when a pressure column varies, and the remaining changes are sheets with
several series.

The same header mapper feeds the exporter: 11 311 of the 12 786 entries (88 %, from 35 %
with the first mapper) carry at least one solubility quantity; volumes 20 and 62 go from none
to 98 % and 91 %.

## Second crop pass on volumes 38, 62 and 59

The node re-ran the crop pass with the band finder of `nd/crop-bands` (caps-only header on a
page carrying the sheet frame, bands emitted once, closed at INFORMATION / METHOD / COMMENTS,
index pages excluded) on the best, the worst and the second-best volume of the row measure.
Hand-backs under `mineru/crops-v2/SDS-N/` in the library, unpacked with
`unpack_node.py SDS-N --crops crops-v2 --raw ...` into `mineru/SDS-N/crops-v2/`, converted
against the same page-pass boxes into `boxes-crops-v2.jsonl`, and run through
`check_rows.py`, `align_nist.py` and `to_nomad.py`. First run against second run:

| volume | crops | crops with a table | crops matching no sheet | sheets with a crop table | rows exported | checker failures | NIST aligned, rows in one line |
|---:|---:|---:|---:|---:|---:|---:|---|
| 38 | 575 → 407 | 242 → 165 | 47 → 2 | 183 → 163 | 889 → 843 | 45 → 45 | 9, 36 / 36 → 9, 36 / 36 |
| 62 | 474 → 307 | 277 → 253 | 42 → 7 | 251 → 240 | 4 760 → 4 680 | 5 → 5 | 21, 422 / 688 → 21, 422 / 688 |
| 59 | 611 → 336 | 301 → 214 | 113 → 5 | 251 → 209 | 2 444 → 2 447 | 20 → 16 | 31, 258 / 283 → 32, 248 / 295 |

The band fix did what it was built for: the crops that matched no sheet (front matter,
evaluation prose, duplicate bands) are gone, the whole-sheet crops fell from 16 to 5 on volume
38, and the yardstick did not move. The sheets that lost their crop table are mostly crops that
held no numeric rows in the first run; the exceptions are sheets whose printed field names never
reached the text layer (volume 38 pages 174, 327, 494; volume 62 pages 326, 328; volume 59 page
59, whose NIST sheet 59_34 drops from 12 to 0 rows in one line), which the frame test rejected.
The finder now also recognises a sheet by its component line "name; formula; [CAS]" or by one
surviving field name next to an EXPERIMENTAL header, and cuts a fallback band below the component
and VARIABLES lines when the header word itself was lost; over the eight volumes that adds 170
bands, mostly sheets of volumes 58 and 59 whose EXPERIMENTAL word the text layer garbles. Those
crops are the third, small batch for the node.

The 400 dpi test on the pages with glued cells (two printed values in one cell, "432.55570.68")
returned byte-identical tables to 300 dpi for volume 38 and the same glued cells for volume 62:
the gluing is MinerU's reading of those tables, not a resolution effect, and the arbiter is the
place to resolve it from the text layer's lines.
