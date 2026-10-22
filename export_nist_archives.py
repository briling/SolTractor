"""Export NIST measurements as NOMAD EquilibriumSolution archives.

    python export_nist_archives.py
"""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
from urllib import error, request

from tqdm import tqdm


ROOT = Path(__file__).parent
DEFAULT_INPUT = ROOT / "data" / "nist_measurements.jsonl"
DEFAULT_SHEETS = ROOT / "data" / "nist_gt.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "nist_archives"
DEFAULT_KEY_FILE = ROOT / ".key"
DEFAULT_BASE_URL = "https://containers.datacrunch.io/sds-qwen38/v1"
DEFAULT_MODEL = "qwen3.8-27b"


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
    values = {
        "name": component["name"],
        "molecular_formula": component["formula"],
        "cas_number": component["cas"],
    }
    return {key: value for key, value in values.items() if value is not None}


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
                candidate = normalized_amount_candidate(component_name, value)
                if candidate:
                    candidates.append(candidate)
    return candidates


def normalized_amount_candidate(component_name, value):
    """Map a normalized NIST value to one named Amount field and its storage unit."""
    quantity = value["quantity"]
    unit = (value["unit"] or "").lower().replace("–", "-").replace("−", "-")
    field, factor = {
        "mole_fraction": ("mole_fraction", 1),
        "gas_mole_fraction": ("mole_fraction", 1),
        "mass_fraction": ("mass_fraction", 1),
        "molality": ("molality", 1),
        "mass_per_100g_solution": ("mass_fraction", 0.01),
        "mass_per_kg": ("mass_fraction", 0.001),
        "mass_ratio": ("solute_solvent_mass_ratio", 1),
        "bunsen_coefficient": ("bunsen_coefficient", 1),
        "ostwald_coefficient": ("ostwald_coefficient", 1),
    }.get(quantity, (None, None))
    if quantity == "amount_concentration":
        if "mol/l" in unit or "mol l" in unit or unit == "":
            field, factor = "molar_concentration", 1_000
    elif quantity == "mass_concentration":
        if "g dm" in unit or unit == "g/l":
            field, factor = "mass_concentration", 1
        elif unit == "mg/l":
            field, factor = "mass_concentration", 0.001
        elif "g m" in unit:
            field, factor = "mass_concentration", 0.001
    if field is None:
        return None
    return {
        "component_name": component_name,
        "field": field,
        "value": value["value"] * factor,
        "source_header": value["header"],
    }


def load_sheet_context(sheets_path):
    context = {}
    with sheets_path.open(encoding="utf-8") as source:
        for line in source:
            sheet = json.loads(line)
            context[sheet["id"]] = {
                field: sheet[field]
                for field in (
                    "method",
                    "source_and_purity",
                    "experimental_remarks",
                    "experimental_data_text",
                )
                if sheet[field]
            }
    return context


def read_api_key(key_file):
    token = key_file.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"API key file is empty: {key_file}")
    return token


def prompt_for(record, sheet_context):
    components = record_components(record)
    return {
        "task": (
            "Populate one EquilibriumSolution from the NIST measurement. Return only a JSON "
            "object that is valid for the requested output shape. Do not infer, calculate, "
            "convert, or invent chemical identities, phases, methods, or numeric values."
        ),
        "rules": [
            "Create exactly one liquid phase named 'liquid solution'.",
            "The liquid phase must contain exactly the listed source components.",
            "Each phase component may have at most one amount.",
            "An amount may only set one named field from a candidate for that same component; "
            "preserve the candidate field, value, and source_header exactly.",
            "Omit an amount when the record does not directly report one for that component.",
            "Add solid or gas phases only when the source phase fields explicitly identify them.",
            "Use temperature_K as temperature and pressure_kPa multiplied by 1000 as pressure.",
            "Fill measurement_methods only from explicit measurement or analysis procedures in "
            "sheet_context. Fill mixing_methods only from explicit preparation, mixing, agitation, "
            "or equilibration steps in sheet_context. Preserve source wording; omit either list "
            "when no relevant source text exists.",
        ],
        "output_shape": {
            "name": "string",
            "temperature": "number or omitted",
            "pressure": "number or omitted",
            "measurement_methods": ["string"],
            "mixing_methods": ["string"],
            "phases": [{
                "name": "string",
                "state_of_matter": "solid | liquid | gas",
                "components": [{
                    "name": "string",
                    "substance": {
                        "name": "string",
                        "molecular_formula": "string or omitted",
                        "cas_number": "string or omitted",
                    },
                    "amount": {
                        "one named Amount field from amount_candidates": "number",
                        "source_header": "string",
                    },
                }],
            }],
        },
        "source": {
            "measurement": record,
            "sheet_context": sheet_context,
            "components": [
                {"name": component["name"], **substance(component)}
                for component in components
            ],
            "amount_candidates": measurement_candidates(record),
        },
    }


def call_llm(prompt, base_url, model, api_key, timeout, max_tokens):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Return only the requested JSON object. Do not include markdown or reasoning.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"LLM request to {base_url} timed out after {timeout} seconds.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach LLM endpoint {base_url}: {exc.reason}") from exc
    try:
        choice = result["choices"][0]
        content = choice["message"]["content"]
        if content is None:
            raise RuntimeError(
                "LLM returned no final content "
                f"(finish_reason={choice.get('finish_reason')!r}, "
                f"message_fields={sorted(choice['message'])!r})."
            )
        return content if isinstance(content, dict) else json.loads(content)
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("LLM response did not contain a JSON chat-completion message.") from exc


def validate_grounding(solution, record):
    components = {component["name"]: component for component in record_components(record)}
    if solution.name != record["system_name"]:
        raise RuntimeError("LLM output changed the source system name.")
    if solution.temperature != record["temperature_K"]:
        raise RuntimeError("LLM output changed or omitted the source temperature.")
    expected_pressure = record["pressure_kPa"] * 1_000 if record["pressure_kPa"] is not None else None
    if solution.pressure != expected_pressure:
        raise RuntimeError("LLM output changed or omitted the source pressure.")
    liquid_phases = [phase for phase in solution.phases if phase.state_of_matter == "liquid"]
    if len(liquid_phases) != 1:
        raise RuntimeError("LLM output must contain exactly one liquid phase.")
    liquid_components = {component.name: component for component in liquid_phases[0].components}
    if set(liquid_components) != set(components):
        raise RuntimeError("LLM output liquid-phase components do not match the source record.")

    candidates = measurement_candidates(record)
    for phase in solution.phases:
        for component in phase.components:
            if component.name not in components:
                raise RuntimeError(f"LLM output contains an unknown component: {component.name!r}.")
            source_component = components[component.name]
            if component.substance is None:
                raise RuntimeError(f"LLM output omitted the identity of {component.name!r}.")
            if component.substance.model_dump(exclude_none=True) != substance(source_component):
                raise RuntimeError(f"LLM output changed the identity of {component.name!r}.")
            if component.amount is None:
                if any(candidate["component_name"] == component.name for candidate in candidates):
                    raise RuntimeError(
                        f"LLM output omitted an eligible source amount for {component.name!r}."
                    )
                continue
            amount = component.amount
            source_header = getattr(amount, "source_header", None)
            amount_values = {
                field: value
                for field, value in amount.model_dump(exclude_none=True).items()
                if field not in {"m_def", "source_header"}
            }
            if len(amount_values) != 1:
                raise RuntimeError(
                    f"LLM output must set exactly one Amount field for {component.name!r}."
                )
            field, value = next(iter(amount_values.items()))
            if not any(
                candidate["component_name"] == component.name
                and candidate["field"] == field
                and candidate["value"] == value
                and candidate["source_header"] == source_header
                for candidate in candidates
            ):
                raise RuntimeError(f"LLM output selected a non-source amount for {component.name!r}.")


def archive_for(record, sheet_context, schema, base_url, model, api_key, timeout, max_tokens):
    """Use the LLM to create a grounded and Pydantic-validated archive."""
    response = call_llm(
        prompt_for(record, sheet_context.get(record["sheet_id"], {})),
        base_url,
        model,
        api_key,
        timeout,
        max_tokens,
    )
    solution = schema.EquilibriumSolution.model_validate(response)
    validate_grounding(solution, record)
    return {"data": solution.model_dump(mode="json", exclude_none=True)}


def output_path(output_directory, measurement_id):
    return output_directory / f"{measurement_id.replace('/', '_')}.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Normalized NIST JSONL input.")
    parser.add_argument("--sheets", type=Path, default=DEFAULT_SHEETS, help="NIST compilation-sheet JSONL input.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="Archive JSON output directory.")
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE, help="API key file.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible API base URL.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Chat-completions model name.")
    parser.add_argument("--timeout", type=float, default=300, help="LLM request timeout in seconds.")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Maximum LLM completion tokens.")
    parser.add_argument(
        "--max-records",
        type=int,
        help="Maximum number of input records to export (default: all records).",
    )
    args = parser.parse_args()

    if args.max_records is not None and args.max_records < 1:
        parser.error("--max-records must be positive")
    if args.max_tokens < 1:
        parser.error("--max-tokens must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sheet_context = load_sheet_context(args.sheets)
    schema = load_schema_models()
    api_key = read_api_key(args.key_file)
    count = 0
    total_records = args.max_records
    if total_records is None:
        with args.input.open(encoding="utf-8") as source:
            total_records = sum(1 for _ in source)
    with args.input.open(encoding="utf-8") as source, tqdm(
        total=total_records, desc="Exporting archives", unit="record"
    ) as progress:
        for line in source:
            if args.max_records is not None and count == args.max_records:
                break
            record = json.loads(line)
            destination = output_path(args.output_dir, record["measurement_id"])
            destination.write_text(
                json.dumps(
                    archive_for(
                        record,
                        sheet_context,
                        schema,
                        args.base_url,
                        args.model,
                        api_key,
                        args.timeout,
                        args.max_tokens,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            count += 1
            progress.update()
    print(f"Wrote {count} archive files to {args.output_dir}")


if __name__ == "__main__":
    main()
