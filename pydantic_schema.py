"""Pydantic v2 models for the OSI Hackathon NOMAD schema.

Numbers use the fixed NOMAD storage units declared in the JSON Schema and
field metadata; dimensionless fractions are stored as ratios. Header prefactors
and source units must be normalized before validation. No unit conversion or
derivation of missing measures is performed by these models. Serialize with
``model_dump(mode="json", exclude_none=True)`` to omit unset scalar quantities
and produce data compatible with ``json_schema.json``.
"""

from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class StateOfMatter(str, Enum):
    """Physical states allowed by the NOMAD Phase definition."""

    solid = "solid"
    liquid = "liquid"
    gas = "gas"


class ArchiveSection(BaseModel):
    """Common archive metadata; additional properties follow the JSON Schema."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    m_def: str | None = Field(
        default=None,
        description="Optional NOMAD section definition reference for selecting a concrete section type.",
    )


class EntryData(ArchiveSection):
    """Base for the data section of a NOMAD entry; adds no quantities."""


class BaseSection(ArchiveSection):
    """Shared descriptive metadata for NOMAD sections."""

    name: str | None = Field(
        default=None,
        description="Human-readable name of the section.",
    )
    datetime: AwareDatetime | None = Field(
        default=None,
        description="Date and time associated with the section.",
    )
    lab_id: str | None = Field(
        default=None,
        description="Identifier unique within the laboratory producing the data.",
    )
    description: str | None = Field(
        default=None,
        description="Additional information not captured by the other fields.",
    )


class ComponentBase(ArchiveSection):
    """NOMAD Component amounts and identifying information."""

    name: str | None = Field(
        default=None,
        description="Component label.",
    )
    mass: float | None = Field(
        default=None,
        description="Mass of this component.",
    )
    mass_fraction: float | None = Field(
        default=None,
        description="Component mass divided by the mixture mass.",
    )


class PureSubstanceSection(ArchiveSection):
    """Chemical identity and molecular properties of a pure substance."""

    name: str | None = Field(
        default=None,
        description="Name of the substance.",
    )
    iupac_name: str | None = Field(
        default=None,
        description="Systematic IUPAC name of the substance.",
    )
    molecular_formula: str | None = Field(
        default=None,
        description="Chemical formula.",
    )
    molecular_mass: float | None = Field(
        default=None,
        description="Mass of a molecule with the most likely isotopic composition.",
    )
    molar_mass: float | None = Field(
        default=None,
        description="Mass per mole using the substance's isotopic composition.",
    )
    monoisotopic_mass: float | None = Field(
        default=None,
        description="Molecular mass calculated from the most abundant isotope of each element.",
    )
    inchi: str | None = Field(
        default=None,
        description="InChI structure identifier.",
    )
    inchi_key: str | None = Field(
        default=None,
        description="Hashed InChI identifier.",
    )
    smile: str | None = Field(
        default=None,
        description="SMILES representation of the structure.",
    )
    canonical_smile: str | None = Field(
        default=None,
        description="Canonical SMILES representation of the structure.",
    )
    cas_number: str | None = Field(
        default=None,
        description="CAS Registry Number.",
    )


class PubChemPureSubstanceSection(PureSubstanceSection):
    """Pure substance with PubChem compound identifiers and chemical properties."""

    pub_chem_cid: int | None = Field(
        default=None,
        description="PubChem compound identifier (CID).",
    )
    pub_chem_link: str | None = Field(
        default=None,
        description="Link to the PubChem compound record.",
    )


class PureSubstanceComponent(ComponentBase):
    """Mixture component linked to its pure-substance details."""

    substance_name: str | None = Field(
        default=None,
        description="Substance name used within the containing mixture.",
    )
    pure_substance: PureSubstanceSection | None = Field(
        default=None,
        description="Chemical properties of the substance forming this component.",
    )


class Component(PureSubstanceComponent):
    """Pure-substance component with amounts and PubChem substance details."""

    pure_substance: PubChemPureSubstanceSection | None = Field(
        default=None,
        description="Chemical properties of the substance forming this component.",
    )


class PublicationReference(ArchiveSection):
    """Bibliographic details for a related publication or dataset."""

    citation: str | None = Field(
        default=None,
        description="Source citation preserved verbatim when structured bibliographic metadata is unavailable.",
    )
    DOI_number: str | None = Field(
        default=None,
        description="DOI identifying the publication or dataset.",
    )
    publication_authors: list[str] = Field(
        default_factory=list,
        description="Authors of the publication.",
    )
    publication_date: AwareDatetime | None = Field(
        default=None,
        description="Publication date and time.",
    )
    journal: str | None = Field(
        default=None,
        description="Journal containing the publication.",
    )
    publication_title: str | None = Field(
        default=None,
        description="Title of the publication.",
    )


class Amount(ArchiveSection):
    """Named solubility and composition quantities for one component, normalized to the declared storage units. For a header 10^n q, divide the tabulated value by 10^n before unit conversion. Several measures may coexist; omitted measures are not derived."""

    mole_fraction: float | None = Field(
        default=None,
        description="Component amount divided by total amount in its phase: x in liquids, y in gases, or x(s) in solids; dimensionless.",
    )
    mass_fraction: float | None = Field(
        default=None,
        description="Component mass divided by solution mass; dimensionless. Divide printed 100 w or g per 100 g solution by 100, g/kg solution by 1000, and mg/kg solution by 1000000.",
    )
    molality: float | None = Field(
        default=None,
        description="Solute amount per unit mass of solvent, in mol/kg solvent.",
        json_schema_extra={"unit": "mole / kilogram"},
    )
    molar_concentration: float | None = Field(
        default=None,
        description="Component amount per solution volume, in mol/m^3. Multiply mol/dm^3 or mol/L values by 1000 for storage.",
        json_schema_extra={"unit": "mole / meter ** 3"},
    )
    mass_concentration: float | None = Field(
        default=None,
        description="Component mass per solution volume, in kg/m^3; g/dm^3 and g/L have the same numerical value. Mass-per-mass forms use mass_fraction or solute_solvent_mass_ratio according to the stated denominator.",
        json_schema_extra={"unit": "kilogram / meter ** 3"},
    )
    solute_solvent_mass_ratio: float | None = Field(
        default=None,
        description="Solute mass divided by solvent mass; dimensionless. Divide g per 100 g solvent by 100, g/kg solvent by 1000, and mg/kg solvent by 1000000. The source must identify the solvent denominator.",
    )
    bunsen_coefficient: float | None = Field(
        default=None,
        description="Bunsen coefficient alpha: gas volume at the source's stated reference conditions (usually 273.15 K and 1 atm) divided by solvent volume at measurement conditions; dimensionless. Use bunsen_coefficient_per_pressure for a pressure-normalized result.",
    )
    bunsen_coefficient_per_pressure: float | None = Field(
        default=None,
        description="Bunsen reference-condition gas-volume/solvent-volume ratio divided by gas partial pressure, in Pa^-1. The source must specify the gas-volume reference conditions; convert inverse-atmosphere values to inverse pascals.",
        json_schema_extra={"unit": "1 / pascal"},
    )
    ostwald_coefficient: float | None = Field(
        default=None,
        description="Ostwald coefficient L: gas volume at measurement temperature and pressure divided by solvent volume at measurement conditions; dimensionless. No value is derived from the Bunsen coefficient.",
    )
    kuenen_coefficient: float | None = Field(
        default=None,
        description="Kuenen coefficient S: gas volume at the source's stated reference conditions (usually 273.15 K and 1 atm) per solvent mass, in m^3/kg. Use kuenen_coefficient_per_pressure for a pressure-normalized result.",
        json_schema_extra={"unit": "meter ** 3 / kilogram"},
    )
    kuenen_coefficient_per_pressure: float | None = Field(
        default=None,
        description="Kuenen reference-condition gas volume per solvent mass divided by gas partial pressure, in m^3/(kg Pa). The source must specify the gas-volume reference conditions; convert cm^3/(g atm) to the storage units.",
        json_schema_extra={"unit": "meter ** 3 / (kilogram * pascal)"},
    )
    henry_constant_p_over_x: float | None = Field(
        default=None,
        description="Henry constant defined as gas partial pressure divided by liquid-phase mole fraction, p/x, in pascals. Select this convention from the source definition, not the symbol H alone.",
        json_schema_extra={"unit": "pascal"},
    )
    henry_constant_p_over_c: float | None = Field(
        default=None,
        description="Henry constant defined as gas partial pressure divided by liquid-phase molar concentration, p/c, in Pa m^3/mol. Convert reported atm m^3/mol or dm^3 mmHg/mol to these storage units.",
        json_schema_extra={"unit": "pascal * meter ** 3 / mole"},
    )
    henry_constant_c_gas_over_c_liquid: float | None = Field(
        default=None,
        description="Henry constant defined as gas-phase molar concentration divided by liquid-phase molar concentration using matching concentration units; dimensionless. Select this convention from the source definition, not the symbol H alone.",
    )
    partial_pressure: float | None = Field(
        default=None,
        description="Component partial pressure associated with the reported gas-solubility measurements, in pascals. No pressure is assumed when omitted.",
        json_schema_extra={"unit": "pascal"},
    )
    estimated_error_solubility: str | None = Field(
        default=None,
        description="Reported estimated error in solubility, preserved as source text with its expression, units, symbols, and line breaks.",
    )
    units: str | None = Field(
        default=None,
        description="Storage unit for the single populated numeric amount field, or 1 for dimensionless amounts.",
    )


class PhaseComponent(ArchiveSection):
    """A component within a phase, with its substance and extracted amount."""

    name: str | None = Field(
        default=None,
        description="Short descriptive name identifying this component within the phase.",
    )
    density: float | None = Field(
        default=None,
        description="Mass density of this component at the stated measurement conditions, in kg/m^3.",
        json_schema_extra={"unit": "kilogram / meter ** 3"},
    )
    source_purity: str | None = Field(
        default=None,
        description="Reported source, preparation, and purity of this material, preserved as text including units, symbols, percentages, and line breaks.",
    )
    substance: PubChemPureSubstanceSection | None = Field(
        default=None,
        description="Chemical identity and PubChem details of the substance forming this component.",
    )
    amount: Amount | None = Field(
        default=None,
        description="Reported solubility and composition quantities for this component, normalized to the declared storage units.",
    )


class Phase(ArchiveSection):
    """A phase, its physical properties, substance, and components within a solution."""

    name: str | None = Field(
        default=None,
        description="Short descriptive name identifying this phase within the equilibrium solution.",
    )
    state_of_matter: StateOfMatter | None = Field(
        default=None,
        description="Physical state of the phase, such as solid, liquid, or gas.",
    )
    density: float | None = Field(
        default=None,
        description="Bulk mass density of this phase at the stated measurement conditions, in kg/m^3.",
        json_schema_extra={"unit": "kilogram / meter ** 3"},
    )
    salinity: float | None = Field(
        default=None,
        description="Mass of dissolved salts divided by solution mass in this phase; dimensionless. Divide reported g/kg solution by 1000 for storage.",
        json_schema_extra={"unit": "dimensionless"},
    )
    ph: float | None = Field(
        default=None,
        description="pH of this phase at the stated measurement conditions; dimensionless.",
    )
    substance: PubChemPureSubstanceSection | None = Field(
        default=None,
        description="Chemical identity and PubChem details of the substance forming this phase.",
    )
    components: list[PhaseComponent] = Field(
        default_factory=list,
        description="Components forming this phase, with their substance details and solubility quantities.",
    )


class EquilibriumSolution(EntryData, BaseSection):
    """Equilibrium solution with phases and publication references."""

    temperature: float | None = Field(
        default=None,
        description="Isothermal temperature of the solution.",
        json_schema_extra={"unit": "kelvin"},
    )
    temperature_initial: float | None = Field(
        default=None,
        description="Initial temperature T_in of a dynamic measurement interval, in kelvin.",
        json_schema_extra={"unit": "kelvin"},
    )
    temperature_final: float | None = Field(
        default=None,
        description="Final temperature T_fin of a dynamic measurement interval, in kelvin.",
        json_schema_extra={"unit": "kelvin"},
    )
    estimated_error_temperature: str | None = Field(
        default=None,
        description="Reported estimated error in temperature, preserved as source text with its expression, units, symbols, and line breaks.",
    )
    pressure: float | None = Field(
        default=None,
        description="Total gas pressure over the solution, in pascals; component partial pressures are stored in PhaseComponent.amount.",
        json_schema_extra={"unit": "pascal"},
    )
    measurement_methods: list[str] = Field(
        default_factory=list,
        description="Methods used to measure the equilibrium properties of the solution.",
    )
    mixing_methods: list[str] = Field(
        default_factory=list,
        description="Methods used to mix the components when preparing the solution.",
    )
    phases: list[Phase] = Field(default_factory=list)
    publication_references: list[PublicationReference] = Field(default_factory=list)
