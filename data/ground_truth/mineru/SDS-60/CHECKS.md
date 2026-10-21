# MinerU on SDS-60: checks against the text layer and NIST

Run: MinerU 4.0.12, tier `standard`, model MinerU2.5-Pro-2605-1.2B, vLLM 0.28.0,
NVIDIA compute capability 8.0 (A100 class), `parse_mode: ocr` (embedded text layer
ignored). 216 pages, 121 s model time (1.78 page/s), 3 min 4 s wall. Output here: `structured_content.json`, `middle_json.json`, `run.log`; the
126 MB `model_output.json`, the region images and the crop PNGs stay outside
the repo (symlink `raw/`, ignored).

"ClearScan" below is the text layer embedded in the PDFs (Acrobat 11 Paper Capture
with ClearScan, 2020), read with `pdftotext -layout`; no OCR was run on our side.

## 1. What MinerU emits per page (structured_content.json)

Block types over 216 pages: text 262, ref_text 253, table 199, page_number 179,
paragraph_title 49, equation 29, chart 12, aside_text 12, doc_title 6, header 5,
index 2, footer 1. Pages with 0 / 1 / 2 table blocks: 22 / 189 / 5.

Each data sheet is one HTML table whose cells are the printed boxes (COMPONENTS,
ORIGINAL MEASUREMENTS, VARIABLES, PREPARED BY, EXPERIMENTAL VALUES, AUXILIARY
INFORMATION, METHOD, SOURCE AND PURITY, ESTIMATED ERRORS, REFERENCES). 310 cells
start with COMPONENTS, 23 mention EVALUATOR. The EXPERIMENTAL VALUES table is a
single cell: rows are run together without separator (page 41, Rex 1906:
`0 9.7 × 10^{-2} 9.7 × 10^{-2} 1.1410 8.3 × 10^{-2} ... 0.97320 ...`, i.e. 1.141|10
and 0.973|20 fused). This is already so in `model_output.json`; no `<br>` occurs
anywhere in the three JSON files, and no line/span coordinates exist inside
table regions. MinerU has no option for line breaks inside cells.

## 2. NIST alignment (same aligner for both witnesses)

Converter `scripts/mineru_to_boxes.py` turns the page JSON into the boxes jsonl format
(`boxes-page.jsonl`: 327 sheets, 305 compilation, 22 evaluation, 19
continuations). Scored with `scripts/align_nist.py 60 --boxes boxes-page.jsonl --out align-page.csv`:

| witness        | sheets (segmenter / converter) | aligned to NIST (of 288) | NIST table values found verbatim |
|----------------|--------------------------------|--------------------------|----------------------------------|
| ClearScan      | 323                            | 259                      | 2997 / 3078 = 97.4 %             |
| MinerU         | 327                            | 263                      | 2766 / 2909 = 95.1 %             |

On the 249 sheets both witnesses aligned (2818 values): ClearScan 97.2 %, MinerU
94.2 %, found by either 98.4 %, found by both 93.0 %. Only-ClearScan sheets 10,
only-MinerU 14. Files: `align-page.csv` (MinerU), `../../nist/align-SDS-60.csv` (ClearScan).

Worst MinerU misses: fused numbers (`12.519.2`, `250.45160.4644.37`) and
continuation pages (p35, p86, p170) where the converter attached the table to the
wrong sheet.

## 3. Prose boxes (components, citations, method, ...)

Over all boxes of the volume, raw text:

| volume 60                                   | MinerU      | ClearScan   |
|---------------------------------------------|-------------|-------------|
| sheets                                      | 327         | 323         |
| CAS strings / check digit valid             | 643 / 642   | 617 / 613   |
| spaced-digit runs (`2 9 8 . 15`)            | 0           | 56          |
| `Chern` / `Hol ` / `Atrn` confusions        | 0           | 81          |
| citation boxes containing a 4-digit year    | 304 / 327   | 10 / 323    |
| evaluation sheets                           | 22          | 28          |

(The ClearScan year count is on raw text; after `strict()` the spaced years
collapse. The point stands: MinerU needs none of the normalisation tiers.)

## 4. Can the column count rebuild the rows? (259 aligned compilation sheets, single NIST table)

Column count taken from the NIST rows, start of the data block located from
NIST's first cell (best case for the idea); cell tokens = number with optional
`× 10^{n}`:

| outcome                                                        | sheets |
|----------------------------------------------------------------|--------|
| token count = rows × columns (chunking reconstructs the table) | 143    |
| divisible by the column count, count differs from NIST         | 16     |
| more tokens than cells (footnotes, header fragments in data)   | 46     |
| fewer tokens (fused numbers)                                   | 35     |
| NIST first value not present                                   | 19     |

Chunking recovers about 55 %. It cannot split fused tokens, and on two-block
headers the model's order is not row-major (page 91: header tokens `100 10 3`
emitted between the values). Row breaks exist only in the ClearScan layer.

## 5. The `continues_prev` flag

Set on 148 of 199 table blocks. Cross-checked with the first cell:

| `continues_prev` | table starts with COMPONENTS              | count |
|------------------|-------------------------------------------|-------|
| true             | yes, new sheet                            | 138   |
| true             | yes, and the sheet says "(continued)"     | 6     |
| true             | no, real continuation                     | 4     |
| false            | yes, new sheet                            | 28    |
| false            | no                                        | 23    |

It fires whenever a table touches the page top after a page ending in a table,
which is nearly every sheet page. Sheet boundaries stay our rule: a sheet starts
at a COMPONENTS cell; a table without one continues the sheet before it.

## 6. Crops for the second pass

`scripts/crop_tables.py` cuts the EXPERIMENTAL VALUES band (header to AUXILIARY banner,
continuation tables from the page top, blank space trimmed) at 300 dpi from the
word coordinates of `pdftotext -bbox`: 338 PNGs over 177 pages (`crops/manifest.csv`; the PNGs regenerate in a minute). Checked by eye: `p041_0.png` (4 rows x 4
columns), `p035_0.png` (continuation, two column pairs). A few false positives
on preface pages (`p009_*`) where the word EXPERIMENTAL occurs in prose.

Decision so far: MinerU supplants the layer for every box except the numbers
table; for the table, either the crop pass yields one `<tr>` per printed row, or
the extraction merges MinerU's digits with the layer's row breaks.

## 7. Crop pass result (node run on the 338 band crops)

One MinerU output per crop, condensed into `crops/tables.jsonl` (log: `crops/run.log`). 317 crops came back with a table,
21 without (preface pages where EXPERIMENTAL occurs in prose, a page-number
strip from a false continuation band, a chart). Page 41 verbatim: header row
`t/°C | 100 g1/g2 | 100 w1 (compiler) | 10^4 x1 (compiler)`, then rows
`0 | 9.7 × 10^-2 | 9.7 × 10^-2 | 1.14`, `10 | ... | 0.973`, `20 | ... | 0.938`,
`30 | ... | 0.996`. Row structure is explicit; no fused numbers in the checked
crops. Some crops come back as a Markdown pipe table instead of HTML (p041_1).

`n_lines` (text-layer lines in the band) minus `<tr>` count: 1 for 232 crops
(the "(compiler)" line merges into the header cell), 2 for 24, a tail of large
differences on preface prose and on long two-block evaluation tables.

`scripts/crops_to_boxes.py` puts each crop table into the whole-page sheet on the same
page sharing most numeric tokens (`boxes-crops.jsonl`, `align-crops.csv`; 290 sheets, 15 crops unmatched):

| measure (aligned compilation sheets)                          | whole-page   | crops         |
|---------------------------------------------------------------|--------------|---------------|
| NIST values found verbatim in the box (aligner)               | 95.1 %       | 95.7 %        |
| NIST rows reproduced as one row, same numbers, any column order | 0 / 718      | 483 / 733 (65.9 %) |
| ... or NIST row a subset of one output row                    | 0.4 %        | 70.3 %        |
| sheets with every NIST row matched                            | 3 / 263      | 207 / 264     |

The aligner's recall is substring-based and so blind to structure (it already
accepted "1.141" inside "1.1410"); the row measure is the one the crop pass
moves. Remaining row misses are mostly NIST-side recoding (NIST reorders columns
to its canonical order, keys `0.2972` as `2972`, `9.0 × 10^-2` as `9.0`, keeps
comment numbers such as "10 % HCl" as a column) and continuation pages whose
table spans two crops.

The crop pass took 9 min 46 s wall for 338 crops, about one second per crop. The
engine was started once for the folder; the "Using vllm-async-engine" line that
`crops/run.log` repeats 343 times is written per file, not per engine start (an
earlier version of this note read it as 343 reloads). MinerU treats every image as
its own document, so there is no batching across crops; one PDF per volume of
crops, parsed once and split by page in manifest order, is the untested speed-up.
