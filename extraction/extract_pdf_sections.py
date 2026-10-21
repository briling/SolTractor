#!/usr/bin/env python3
"""Extract OCR text from boxed sections in scanned PDF forms."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np
import pymupdf


@dataclass(frozen=True)
class Section:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class OcrWord:
    text: str
    left: int
    width: int


@dataclass(frozen=True)
class OcrLine:
    text: str
    words: tuple[OcrWord, ...]


@dataclass(frozen=True)
class ExtractedTable:
    data: dict[str, object]
    source_lines: tuple[str, ...]


CANONICAL_SECTION_TITLES = (
    "COMPONENTS",
    "ORIGINAL MEASUREMENTS",
    "PREPARED BY",
    "VARIABLES",
    "EXPERIMENTAL VALUES",
    "AUXILIARY INFORMATION",
    "METHOD/APPARATUS/PROCEDURE",
    "SOURCE AND PURITY OF MATERIALS",
    "REFERENCES",
)


def normalized_text(text: str) -> str:
    return "".join(character for character in text.upper() if character.isalnum())


def canonical_title(line: str) -> str | None:
    candidate = normalized_text(line.rstrip(":"))
    if not candidate:
        return None
    best_title = max(
        CANONICAL_SECTION_TITLES,
        key=lambda title: SequenceMatcher(None, candidate, normalized_text(title)).ratio(),
    )
    similarity = SequenceMatcher(None, candidate, normalized_text(best_title)).ratio()
    return best_title if similarity >= 0.78 else None


def render_page(page: pymupdf.Page, dpi: int) -> np.ndarray:
    scale = dpi / 72
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY)
    return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)


def find_grid(image: np.ndarray) -> np.ndarray:
    binary = cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 11
    )
    horizontal_width = max(30, image.shape[1] // 25)
    vertical_height = max(30, image.shape[0] // 25)
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_width, 1))
    )
    vertical = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_height))
    )
    return cv2.bitwise_or(horizontal, vertical)


def find_sections(grid: np.ndarray, page_shape: tuple[int, int]) -> list[Section]:
    """Return enclosed whitespace regions, which are the leaf cells of the ruled form."""
    # Joining small line gaps makes the inverted grid form closed barriers.  Text is
    # deliberately absent here, so it cannot fragment a section into false cells.
    barriers = cv2.dilate(grid, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    interiors = cv2.bitwise_not(barriers)
    count, _, stats, _ = cv2.connectedComponentsWithStats(interiors, connectivity=8)
    page_area = page_shape[0] * page_shape[1]
    sections: list[Section] = []
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if area < page_area * 0.002 or width < 100 or height < 35:
            continue
        # The background surrounding the form is the only component that reaches
        # the page edge.  All remaining sufficiently large components are cells.
        if x == 0 or y == 0 or x + width >= page_shape[1] or y + height >= page_shape[0]:
            continue
        sections.append(Section(int(x), int(y), int(width), int(height)))
    return sorted(sections, key=lambda box: (box.y, box.x))


def run_ocr(image: np.ndarray, language: str, page_segmentation_mode: int = 6) -> str:
    executable = shutil.which("tesseract")
    if not executable:
        raise RuntimeError(
            "Tesseract was not found on PATH. Install Tesseract OCR, then run this command again."
        )
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Could not encode section image for OCR.")
    result = subprocess.run(
        [executable, "stdin", "stdout", "-l", language, "--psm", str(page_segmentation_mode)],
        input=encoded.tobytes(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout.decode("utf-8", errors="replace").strip()


def run_ocr_tsv(image: np.ndarray, language: str) -> list[OcrLine]:
    executable = shutil.which("tesseract")
    if not executable:
        raise RuntimeError(
            "Tesseract was not found on PATH. Install Tesseract OCR, then run this command again."
        )
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Could not encode section image for OCR.")
    result = subprocess.run(
        [executable, "stdin", "stdout", "-l", language, "--psm", "6", "tsv"],
        input=encoded.tobytes(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())

    grouped: dict[tuple[str, str, str, str], list[OcrWord]] = {}
    for row in csv.DictReader(io.StringIO(result.stdout.decode("utf-8", errors="replace")), delimiter="\t"):
        text = row["text"].strip()
        if not text or row["level"] != "5":
            continue
        line_key = (row["block_num"], row["par_num"], row["line_num"], row["page_num"])
        grouped.setdefault(line_key, []).append(
            OcrWord(text=text, left=int(row["left"]), width=int(row["width"]))
        )
    return [
        OcrLine(" ".join(word.text for word in words), tuple(words))
        for words in grouped.values()
    ]


NUMERIC_TOKEN = re.compile(r"^[+-]?(?:\d+(?:[.,]\d*)?|\.\d+)(?:[Ee][+-]?\d+)?%?$")


def numeric_words(line: OcrLine) -> list[OcrWord]:
    return [word for word in line.words if NUMERIC_TOKEN.match(word.text)]


def join_column_words(words: list[str]) -> str:
    """Preserve formulas split around parentheses by OCR."""
    result = ""
    for word in words:
        if result and (word.startswith(("(", "[", "·")) or result.endswith((")", "]", "·"))):
            result += word
        else:
            result += (" " if result else "") + word
    return result


def structured_table(lines: list[OcrLine]) -> ExtractedTable | None:
    """Extract a numeric table with up to two header rows from positioned OCR words."""
    candidates = [
        (index, numeric_words(line))
        for index, line in enumerate(lines)
        if len(numeric_words(line)) >= 2
    ]
    if not candidates:
        return None
    data_index, first_row = max(candidates, key=lambda candidate: len(candidate[1]))
    if data_index < 2:
        return None

    centers = [word.left + word.width / 2 for word in first_row]
    header_lines = lines[data_index - 2 : data_index]
    headers = [[] for _ in centers]
    for header_line in header_lines:
        for word in header_line.words:
            column = min(
                range(len(centers)), key=lambda index: abs(word.left + word.width / 2 - centers[index])
            )
            headers[column].append(word.text)
    column_names = [
        join_column_words(parts) if parts else f"column_{index + 1}"
        for index, parts in enumerate(headers)
    ]

    rows: list[dict[str, str]] = []
    table_end = data_index
    for index, line in enumerate(lines[data_index:], start=data_index):
        values = numeric_words(line)
        if len(values) < max(2, len(centers) // 2):
            if rows:
                break
            continue
        row = {
            column_names[index]: values[index].text
            for index in range(min(len(column_names), len(values)))
        }
        rows.append(row)
        table_end = index
    if not rows:
        return None
    title = lines[data_index - 3].text if data_index >= 3 else ""
    table_start = data_index - 3 if title else data_index - 2
    return ExtractedTable(
        data={"title": title, "columns": column_names, "rows": rows},
        source_lines=tuple(line.text for line in lines[table_start : table_end + 1]),
    )


def content_without_table(raw_content: str, table_lines: tuple[str, ...]) -> str:
    normalized_table_lines = [normalized_text(line) for line in table_lines if normalized_text(line)]
    retained_lines = []
    for line in raw_content.splitlines():
        normalized_line = normalized_text(line)
        is_table_line = any(
            normalized_line == table_line
            or (
                min(len(normalized_line), len(table_line)) >= 6
                and SequenceMatcher(None, normalized_line, table_line).ratio() >= 0.9
            )
            for table_line in normalized_table_lines
        )
        if not is_table_line:
            retained_lines.append(line)
    return "\n".join(retained_lines).strip()


def extract_page_header(image: np.ndarray, sections: list[Section], language: str) -> str:
    if not sections:
        return ""
    header_bottom = min(section.y for section in sections) - 4
    if header_bottom <= 0:
        return ""
    text = run_ocr(image[:header_bottom, :], language, page_segmentation_mode=11)
    header_lines = [
        re.sub(r"^\s*\d+\s+", "", line).strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().isdigit()
    ]
    return "\n".join(line for line in header_lines if line)


def clean_section(image: np.ndarray, grid: np.ndarray, section: Section) -> np.ndarray:
    pad = 4
    y1, y2 = section.y + pad, section.y + section.height - pad
    x1, x2 = section.x + pad, section.x + section.width - pad
    crop = image[y1:y2, x1:x2].copy()
    crop_grid = grid[y1:y2, x1:x2]
    crop[cv2.dilate(crop_grid, np.ones((3, 3), np.uint8)) > 0] = 255
    return crop


def section_header(text: str, fallback_number: int) -> tuple[str, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return f"section_{fallback_number}", ""
    for index, line in enumerate(lines[:3]):
        title = canonical_title(line)
        if title:
            return title, "\n".join(lines[index + 1 :]).strip()
        if line.endswith(":"):
            return line[:-1].strip(), "\n".join(lines[index + 1 :]).strip()
    return f"section_{fallback_number}", "\n".join(lines).strip()


def unique_key(key: str, sections: dict[str, object]) -> str:
    if key not in sections:
        return key
    number = 2
    while f"{key} ({number})" in sections:
        number += 1
    return f"{key} ({number})"


def extract(pdf_path: Path, dpi: int, language: str, debug_dir: Path | None) -> dict[str, object]:
    document = pymupdf.open(pdf_path)
    pages: list[dict[str, object]] = []
    try:
        for page_number, page in enumerate(document, start=1):
            image = render_page(page, dpi)
            grid = find_grid(image)
            detected = find_sections(grid, image.shape)
            page_header = extract_page_header(image, detected, language)
            page_sections: dict[str, object] = {}
            for number, section in enumerate(detected, start=1):
                section_image = clean_section(image, grid, section)
                text = run_ocr(section_image, language)
                header, content = section_header(text, number)
                value: dict[str, object] = {
                    "content": content,
                    "bounds": {
                        "x": round(section.x * 72 / dpi, 2),
                        "y": round(section.y * 72 / dpi, 2),
                        "width": round(section.width * 72 / dpi, 2),
                        "height": round(section.height * 72 / dpi, 2),
                    },
                }
                if header == "EXPERIMENTAL VALUES":
                    table = structured_table(run_ocr_tsv(section_image, language))
                    if table:
                        value["raw_content"] = content
                        value["content"] = content_without_table(content, table.source_lines)
                        value["table"] = table.data
                page_sections[unique_key(header, page_sections)] = value
            pages.append(
                {"page_number": page_number, "header": page_header, "sections": page_sections}
            )
            if debug_dir:
                debug_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(debug_dir / f"page-{page_number}-grid.png"), grid)
    finally:
        document.close()
    return {"source": str(pdf_path), "pages": pages}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--language", default="eng")
    parser.add_argument("--debug-dir", type=Path)
    args = parser.parse_args()
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    try:
        output = extract(args.input_pdf, args.dpi, args.language, args.debug_dir)
    except (OSError, RuntimeError, pymupdf.FileDataError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.output_json.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
