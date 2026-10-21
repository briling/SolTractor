"""Export NIST measurements as NOMAD EquilibriumSolution archives.

The initial export is intentionally limited to the first 10 measurement records:

    python export_nist_archives.py
"""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).parent
DEFAULT_INPUT = ROOT / "data" / "nist_measurements.jsonl"
DEFAULT_SHEETS = ROOT / "data" / "nist_gt.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "nist_archives"
INITIAL_RECORD_LIMIT = 10
MEASUREMENT_PRIORITY = {
    "amount_concentration": 0,
    "mass_concentration": 1,
    "molality": 2,
    "mass_per_kg": 3,
    "mass_per_100g_solution": 4,
    "mass_fraction": 5,
    "mole_fraction": 6,
    "gas_mole_fraction": 7,
    "amount_per_mass": 8,
    "mass_ratio": 9,
    "volume_ratio": 10,
    "composition": 11,
    "solubility": 12,
}


def load_schema_models():
    """Load pydantic_schema.py without pydantic.py shadowing the package."""
    package_paths = [path for path in sys.path if Path(path or ".").resolve() != ROOT]
    package_spec = importlib.machinery.PathFinder.find_spec("pydantic", package_paths)
    if package_spec is None or package_spec.loader is None:
        raise RuntimeError("The Pydantic package is required to load pydantic_schema.py.")
    package = importlib.util.module_from_spec(package_spec)
    sys.modules["pydantic"] = package
    package_spec.loader.exec_module(package)

    schema_spec = importlib.util.spec_from_file_location(
        "archive_schema_models", ROOT / "pydantic_schema.py"
    )
    if schema_spec is None or schema_spec.loader is None:
        raise RuntimeError("Could not load pydantic_schema.py.")
    schema = importlib.util.module_from_spec(schema_spec)
    schema_spec.loader.exec_module(schema)
    return schema


def substance(component):
    return {
        "name": component["name"],
        "molecular_formula": component["formula"],
        "cas_number": component["cas"],
    }


def record_components(record):
    return [component for component in [record["solute"], *(record["solvent"] or [])] if component]


def measurement_candidates(record):
    candidates = []
    for source in ("solubility", "solvent_composition", "composition"):
        for value in record[source] or []:
            component_name = (
                record["solute"]["name"] if source == "solubility" else value.get("species")
            )
            if component_name:
                candidates.append({
                    "component_name": component_name,
                    "quantity": value["quantity"],
                    "value": value["value"],
                    "unit": value["unit"],
                    "source_header": value["header"],
                })
    return candidates


def preferred_measurements(record):
    """Choose one directly reported value per component, without inference or conversion."""
    selected = {}
    for candidate in measurement_candidates(record):
        name = candidate["component_name"]
        key = (MEASUREMENT_PRIORITY.get(candidate["quantity"], len(MEASUREMENT_PRIORITY)),)
        if name not in selected or key < selected[name][0]:
            selected[name] = (key, candidate)
    return [candidate for _, candidate in selected.values()]


def phase_components(components, measurements, schema):
    result = []
    for component in components:
        measurement = measurements.get(component["name"])
        amount = None
        if measurement:
            amount = schema.Amount(
                type=measurement["quantity"],
                value=measurement["value"],
                units=measurement["unit"],
                source_header=measurement["source_header"],
            )
        result.append(schema.PhaseComponent(
            name=component["name"],
            substance=schema.PubChemPureSubstanceSection(**substance(component)),
            amount=amount,
        ))
    return result


def additional_phases(record, components, schema):
    phases = []
    phase_comment = record["phase"] or ""
    if record["solid_phase"] or "solid" in phase_comment.lower():
        phases.append(schema.Phase(
            name=record["solid_phase"] or phase_comment,
            state_of_matter=schema.StateOfMatter.solid,
            components=phase_components(components, {}, schema),
        ))
    if "gas" in phase_comment.lower() or "vapor" in phase_comment.lower():
        phases.append(schema.Phase(
            name=phase_comment,
            state_of_matter=schema.StateOfMatter.gas,
            components=phase_components(components, {}, schema),
        ))
    return phases


def load_measurement_methods(sheets_path):
    methods = {}
    with sheets_path.open(encoding="utf-8") as source:
        for line in source:
            sheet = json.loads(line)
            if sheet["method"]:
                methods[sheet["id"]] = sheet["method"]
    return methods


def archive_for(record, methods, schema):
    """Map a normalized measurement to the fields defined by EquilibriumSolution."""
    components = record_components(record)
    measurements = {value["component_name"]: value for value in preferred_measurements(record)}
    solution = schema.EquilibriumSolution(
        name=record["system_name"],
        phases=[
            schema.Phase(
                name="liquid solution",
                state_of_matter=schema.StateOfMatter.liquid,
                components=phase_components(components, measurements, schema),
            ),
            *additional_phases(record, components, schema),
        ],
    )
    if method := methods.get(record["sheet_id"]):
        solution.measurement_methods = [method]
    if record["temperature_K"] is not None:
        solution.temperature = record["temperature_K"]
    if record["pressure_kPa"] is not None:
        solution.pressure = record["pressure_kPa"] * 1_000
    return {"data": solution.model_dump(mode="json", exclude_none=True)}


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
    schema = load_schema_models()
    count = 0
    with args.input.open(encoding="utf-8") as source:
        for line in source:
            if count == args.limit:
                break
            record = json.loads(line)
            destination = output_path(args.output_dir, record["measurement_id"])
            destination.write_text(
                json.dumps(archive_for(record, methods, schema), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            count += 1
    print(f"Wrote {count} archive files to {args.output_dir}")


if __name__ == "__main__":
    main()
