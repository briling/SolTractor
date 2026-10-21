# IUPAC Solubility Data Series (SDS)

Text extraction with quality control from the IUPAC Solubility Data Series
(https://iupac.org/what-we-do/databases/solubility-data-series/).

- `pdfs/`  volumes 1-65 from https://iupac.github.io/SolubilityDataSeries/volumes/SDS-N.pdf
           (5/6, 16/17, 27/28, 45/46, 53 are not on the mirror); scanned, OCR text layer.
           Volumes 66+ are JPCRD articles (DOI only), not included.
- `text/`  cached `pdftotext -layout` output per volume, one page per form feed.
- `scripts/fetch_volumes.sh`  download + text cache.
- `scripts/scan_columns.py`   tally EXPERIMENTAL VALUES table headers per volume.
- `extracted/`  LLM extraction output.

Each volume is a sequence of fixed-form data sheets: COMPONENTS / ORIGINAL
MEASUREMENTS / VARIABLES / PREPARED BY / EXPERIMENTAL VALUES / AUXILIARY
INFORMATION (METHOD, SOURCE AND PURITY, ESTIMATED ERROR, REFERENCES), plus
CRITICAL EVALUATION sheets per system.

The PDFs are not committed (687 MB); run `scripts/fetch_volumes.sh` from this folder
to download them into `pdfs/` and regenerate `text/`. Scripts resolve paths relative to
this folder, e.g.

```bash
python3 -I data/sds/scripts/scan_columns.py SDS-30 --tokens --lines 4
python3 -I data/sds/scripts/backsearch.py SDS-1 "298.15" "10361-37-2" --page 45
```
