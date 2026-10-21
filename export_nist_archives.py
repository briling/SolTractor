"""Export NIST measurements as NOMAD EquilibriumSolution archives.

The initial export is intentionally limited to the first 10 measurement records:

    python export_nist_archives.py
"""
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).parent
DEFAULT_INPUT = ROOT / "data" / "nist_measurements.jsonl"
DEFAULT_SHEETS = ROOT / "data" / "nist_gt.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "nist_archives"
SCHEMA_REFERENCE = "schema.archive.yaml#/definitions/section/EquilibriumSolution"
INITIAL_RECORD_LIMIT = 10


def archive_component(component):
    """Return the PureSubstanceComponent fields available in the source data."""
    return {"name": component["name"]}


def record_components(record):
    components = [record["solute"], *(record["solvent"] or [])]
    return [archive_component(component) for component in components if component]


def measurement_values(record):
    values = []
    for source in ("solubility", "solvent_composition", "composition", "properties"):
        for value in record[source] or []:
            values.append({
                key: value[key]
                for key in (
                    "quantity",
                    "value",
                    "unit",
                    "species",
                    "value_qualifier",
                    "note",
                    "compiler_calculated",
                )
                if value.get(key) is not None
            } | {"source_header": value["header"]})
    return values


def load_measurement_methods(sheets_path):
    methods = {}
    with sheets_path.open(encoding="utf-8") as source:
        for line in source:
            sheet = json.loads(line)
            if sheet["method"]:
                methods[sheet["id"]] = sheet["method"]
    return methods


def archive_for(record, methods):
    """Map a normalized measurement to the fields defined by EquilibriumSolution."""
    components = record_components(record)
    data = {
        "m_def": SCHEMA_REFERENCE,
        "components": components,
        "phases": [{"name": record["system_name"], "components": components}],
        "measurement_values": measurement_values(record),
    }
    if method := methods.get(record["sheet_id"]):
        data["measurement_methods"] = [method]
    if record["temperature_K"] is not None:
        data["temperature"] = record["temperature_K"]
    if record["pressure_kPa"] is not None:
        data["pressure"] = record["pressure_kPa"] * 1_000
    return {"data": data}


def output_path(output_directory, measurement_id):
    return output_directory / f"{measurement_id.replace('/', '_')}.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Normalized NIST JSONL input.")
    parser.add_argument("--sheets", type=Path, default=DEFAULT_SHEETS, help="NIST compilation-sheet JSONL input.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="Archive JSON output directory.")
    parser.add_argument(
        "--limit",
        type=int,
        default=INITIAL_RECORD_LIMIT,
        help=f"Number of input records to export (default: {INITIAL_RECORD_LIMIT}).",
    )
    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be non-negative")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    methods = load_measurement_methods(args.sheets)
    count = 0
    with args.input.open(encoding="utf-8") as source:
        for line in source:
            if count == args.limit:
                break
            record = json.loads(line)
            destination = output_path(args.output_dir, record["measurement_id"])
            destination.write_text(
                json.dumps(archive_for(record, methods), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            count += 1
    print(f"Wrote {count} archive files to {args.output_dir}")


if __name__ == "__main__":
    main()
