"""Locate a volume's files: ground-truth volumes under ground_truth/, all others at the top level.

A volume is ground truth when its sheets are keyed in the IUPAC-NIST Solubility
Database (status "mined" in volumes.csv). Its PDF, text layer, boxes and
extractions live under ground_truth/ together with the scraped NIST sheets, so
calibration data never mixes with the extraction targets.
"""
import csv, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
GROUND_TRUTH = ROOT / 'ground_truth'
NIST = GROUND_TRUTH / 'nist'
MINED = {int(r['volume']) for r in csv.DictReader((ROOT / 'volumes.csv').open()) if r['status'] == 'mined'}


def volume_number(volume: int | str) -> int:
    return int(str(volume).removeprefix('SDS-'))


def volume_root(volume: int | str) -> pathlib.Path:
    """ground_truth/ for a mined volume, the data folder otherwise."""
    return GROUND_TRUTH if volume_number(volume) in MINED else ROOT


def all_boxes() -> list[pathlib.Path]:
    """Segmented box files of every volume, ground truth and targets, in volume order."""
    files = [*(ROOT / 'boxes').glob('SDS-*.jsonl'), *(GROUND_TRUTH / 'boxes').glob('SDS-*.jsonl')]
    return sorted(files, key=lambda p: volume_number(p.stem))
