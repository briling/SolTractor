"""Pydantic v2 models for the OSI Hackathon NOMAD schema.

Numbers use NOMAD storage units. Serialize with
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


class Phase(ArchiveSection):
    """A phase and its substance within an equilibrium solution."""

    name: str | None = Field(
        default=None,
        description="Short descriptive name identifying this phase within the equilibrium solution.",
    )
    state_of_matter: StateOfMatter | None = Field(
        default=None,
        description="Physical state of the phase, such as solid, liquid, or gas.",
    )
    mass_fraction: float | None = Field(
        default=None,
        description="Mass of this phase divided by the total mass of the equilibrium solution.",
    )
    partial_pressure: float | None = Field(
        default=None,
        description="Partial pressure of this phase in the equilibrium system.",
    )
    molar_fraction: float | None = Field(
        default=None,
        description="Amount of substance in this phase divided by the total amount of substance in the equilibrium solution.",
    )
    substance: PubChemPureSubstanceSection | None = Field(
        default=None,
        description="Chemical identity and PubChem details of the substance forming this phase.",
    )


class EquilibriumSolution(EntryData, BaseSection):
    """Equilibrium solution with phases and publication references."""

    temperature: float | None = Field(
        default=None,
        description="Isothermal temperature of the solution.",
    )
    pressure: float | None = Field(
        default=None,
        description="Gas pressure over the solution (assumed to be isobar).",
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
