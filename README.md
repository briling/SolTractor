# OSI hackathon: the IUPAC Solubility Data Series

Text extraction with quality control from the IUPAC Solubility Data Series
(https://iupac.org/what-we-do/databases/solubility-data-series/): 56 scanned volumes of
fixed-form data sheets, about 21000 pages, to be turned into structured records that can
be checked value by value against the page.

## Layout

- `data/`: the text layer of every volume, the volume classification, the segmented
  sheets, the CAS checks, and `data/ground_truth/` with the eight volumes keyed in the
  IUPAC-NIST Solubility Database (their boxes, the scraped NIST sheets, the alignments
  and the MinerU results). The PDFs and the bulky raw model output are not committed;
  they live in the HU Box library `sds-extraction` (see `docs/sds-pipeline.md`).
- `scripts/`: the pipeline, stdlib-only Python run as `python3 -I scripts/<name>.py`,
  plus `fetch_volumes.sh`. Documented in `docs/sds-pipeline.md`.
- `schema/`: the target record as a NOMAD YAML schema, a JSON schema and a pydantic model.
- `docs/`: `sds-pipeline.md` (data, scripts, QC numbers). The brief for running the
  document vision model on a GPU node is internal and lives in the HU Box library, not here.

## Setup

The scripts need only Python 3.13 and poppler (`pdftotext`, `pdftoppm`; Debian/Ubuntu:
`apt install poppler-utils`). The schema's pydantic model is the one Python dependency:

```bash
uv sync --locked          # creates .venv with pydantic
uv run python -c "import schema.pydantic"
```

The PDFs are downloaded by `scripts/fetch_volumes.sh` from the IUPAC GitHub mirror, or
synced from the HU Box library.

## Approach

Each page is read twice: by the OCR text layer embedded in the PDFs (Adobe ClearScan,
segmented into sheets and boxes by `scripts/segment_boxes.py`) and by the document vision
model MinerU on the page images. Every extracted value is searched back in the page, and
the eight volumes keyed in the NIST database are the ground truth: `scripts/align_nist.py`
reports, per sheet, the fraction of keyed values a witness reproduces verbatim. The
numbers so far are in `docs/sds-pipeline.md` and
`data/ground_truth/mineru/SDS-60/CHECKS.md`.
