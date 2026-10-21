# PDF section extractor

Extracts text from scanned, ruled PDF forms such as `1.pdf`. It renders every
page, detects the horizontal and vertical rules, treats each enclosed leaf cell
as a section, OCRs it, and writes section headers as JSON keys.

Common form headers (for example `ORIGINAL MEASUREMENTS` and
`METHOD/APPARATUS/PROCEDURE`) are fuzzy-matched and normalized to their
canonical spelling before being used as JSON keys.

Each page also has a `header` value OCRed from the area above its first boxed
section; standalone page numbers are excluded.

For `EXPERIMENTAL VALUES`, a detected multi-column numeric table is included
as `table` with a title, column labels, and rows. Its complete OCR text is
retained in `raw_content`, while `content` contains the non-table text such as
notes and chemical equations. Formula parts split around parentheses are kept
together in table column labels.

## Requirements

Install the Python packages and the native [Tesseract OCR](https://tesseract-ocr.github.io/)
executable (including the language data you select):

```bash
python -m pip install -r requirements.txt
# Debian/Ubuntu:
sudo apt install tesseract-ocr
```

## Usage

```bash
python extract_pdf_sections.py 1.pdf sections.json --debug-dir debug
```

`--debug-dir` saves the detected rule mask for inspection. Bounds in the JSON
are PDF points (1/72 inch), with the origin at the page's upper-left corner.
