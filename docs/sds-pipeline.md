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
the clone and link it as `ground_truth/mineru/SDS-N/raw` (ignored) and `pdfs`. Two passes per
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
