"""
IntentOS Industry Vertical Bundles (Phase 4.10)
Curated agent + knowledge packages per industry vertical.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BundleTier(IntEnum):
    """Bundle tier — each tier includes all lower tiers."""

    ESSENTIAL = 1
    STANDARD = 2
    COMPREHENSIVE = 3

    def includes(self, other: BundleTier) -> bool:
        """Return True if *self* includes *other* (i.e. other is a lower or equal tier)."""
        return self.value > other.value


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TierSpec:
    """Specification for a single tier within a vertical."""

    agents: List[str]
    knowledge_sources: List[str]
    estimated_size_gb: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agents": self.agents,
            "knowledge_sources": self.knowledge_sources,
            "estimated_size_gb": self.estimated_size_gb,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TierSpec:
        return cls(
            agents=data["agents"],
            knowledge_sources=data["knowledge_sources"],
            estimated_size_gb=data["estimated_size_gb"],
            description=data["description"],
        )


@dataclass
class KnowledgeSource:
    """A knowledge source included in a bundle."""

    name: str
    url: str
    size_gb: float
    description: str
    format: str  # "zim", "json", "csv", "pdf"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "size_gb": self.size_gb,
            "description": self.description,
            "format": self.format,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> KnowledgeSource:
        return cls(
            name=data["name"],
            url=data["url"],
            size_gb=data["size_gb"],
            description=data["description"],
            format=data["format"],
        )


@dataclass
class VerticalDefinition:
    """Definition of an industry vertical with tiered bundles."""

    name: str
    display_name: str
    description: str
    tiers: Dict[BundleTier, TierSpec]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "tiers": {tier.name: spec.to_dict() for tier, spec in self.tiers.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VerticalDefinition:
        tiers = {}
        for tier_name, spec_data in data["tiers"].items():
            tiers[BundleTier[tier_name]] = TierSpec.from_dict(spec_data)
        return cls(
            name=data["name"],
            display_name=data["display_name"],
            description=data["description"],
            tiers=tiers,
        )


@dataclass
class ValidationResult:
    """Result of validating a bundle manifest."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class BundleManifest:
    """Manifest describing a concrete bundle for a vertical + tier."""

    vertical: str
    tier: BundleTier
    version: str
    agents: List[str]
    knowledge: List[KnowledgeSource]
    total_size_gb: float
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vertical": self.vertical,
            "tier": self.tier.name,
            "version": self.version,
            "agents": self.agents,
            "knowledge": [k.to_dict() for k in self.knowledge],
            "total_size_gb": self.total_size_gb,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BundleManifest:
        return cls(
            vertical=data["vertical"],
            tier=BundleTier[data["tier"]],
            version=data["version"],
            agents=data["agents"],
            knowledge=[KnowledgeSource.from_dict(k) for k in data["knowledge"]],
            total_size_gb=data["total_size_gb"],
            created_at=data.get("created_at"),
        )


# ---------------------------------------------------------------------------
# Pre-built vertical definitions
# ---------------------------------------------------------------------------

def _prebuilt_verticals() -> List[VerticalDefinition]:
    """Return the five pre-built industry verticals."""
    return [
        VerticalDefinition(
            name="legal",
            display_name="Legal",
            description="Legal document analysis, case research, and contract management",
            tiers={
                BundleTier.ESSENTIAL: TierSpec(
                    agents=["contract_agent"],
                    knowledge_sources=["legal_codes"],
                    estimated_size_gb=2.0,
                    description="Core contract review and legal code lookup",
                ),
                BundleTier.STANDARD: TierSpec(
                    agents=["case_agent"],
                    knowledge_sources=["case_law_db"],
                    estimated_size_gb=5.0,
                    description="Case law research and analysis",
                ),
                BundleTier.COMPREHENSIVE: TierSpec(
                    agents=["compliance_agent"],
                    knowledge_sources=["regulatory_db", "legal_journals"],
                    estimated_size_gb=8.0,
                    description="Full regulatory compliance and journal access",
                ),
            },
        ),
        VerticalDefinition(
            name="medical",
            display_name="Medical",
            description="Patient management, clinical references, and medical research",
            tiers={
                BundleTier.ESSENTIAL: TierSpec(
                    agents=["patient_agent"],
                    knowledge_sources=["drug_reference"],
                    estimated_size_gb=1.5,
                    description="Patient intake and drug reference",
                ),
                BundleTier.STANDARD: TierSpec(
                    agents=["reference_agent"],
                    knowledge_sources=["clinical_guidelines"],
                    estimated_size_gb=4.0,
                    description="Clinical guidelines and medical references",
                ),
                BundleTier.COMPREHENSIVE: TierSpec(
                    agents=["research_agent"],
                    knowledge_sources=["pubmed_archive", "icd_codes"],
                    estimated_size_gb=10.0,
                    description="Full medical research and coding databases",
                ),
            },
        ),
        VerticalDefinition(
            name="financial",
            display_name="Financial",
            description="Invoice processing, financial reporting, and regulatory compliance",
            tiers={
                BundleTier.ESSENTIAL: TierSpec(
                    agents=["invoice_agent"],
                    knowledge_sources=["tax_codes"],
                    estimated_size_gb=1.0,
                    description="Invoice processing and tax code lookup",
                ),
                BundleTier.STANDARD: TierSpec(
                    agents=["report_agent"],
                    knowledge_sources=["financial_regulations"],
                    estimated_size_gb=3.0,
                    description="Financial reporting and regulations",
                ),
                BundleTier.COMPREHENSIVE: TierSpec(
                    agents=["audit_agent"],
                    knowledge_sources=["sec_filings", "gaap_standards"],
                    estimated_size_gb=6.0,
                    description="Audit support with SEC filings and GAAP standards",
                ),
            },
        ),
        VerticalDefinition(
            name="manufacturing",
            display_name="Manufacturing",
            description="Inventory tracking, quality assurance, and safety compliance",
            tiers={
                BundleTier.ESSENTIAL: TierSpec(
                    agents=["inventory_agent"],
                    knowledge_sources=["safety_standards"],
                    estimated_size_gb=1.0,
                    description="Inventory management and safety standards",
                ),
                BundleTier.STANDARD: TierSpec(
                    agents=["quality_agent"],
                    knowledge_sources=["iso_standards"],
                    estimated_size_gb=2.5,
                    description="Quality control and ISO standards",
                ),
                BundleTier.COMPREHENSIVE: TierSpec(
                    agents=["maintenance_agent"],
                    knowledge_sources=["osha_regulations", "equipment_manuals"],
                    estimated_size_gb=5.0,
                    description="Predictive maintenance and full regulatory library",
                ),
            },
        ),
        VerticalDefinition(
            name="education",
            display_name="Education",
            description="Course management, assessments, and educational content",
            tiers={
                BundleTier.ESSENTIAL: TierSpec(
                    agents=["course_agent"],
                    knowledge_sources=["khan_academy"],
                    estimated_size_gb=3.0,
                    description="Course management with Khan Academy content",
                ),
                BundleTier.STANDARD: TierSpec(
                    agents=["assessment_agent"],
                    knowledge_sources=["curriculum_standards"],
                    estimated_size_gb=2.0,
                    description="Assessment creation and curriculum standards",
                ),
                BundleTier.COMPREHENSIVE: TierSpec(
                    agents=["analytics_agent"],
                    knowledge_sources=["open_textbooks", "research_papers"],
                    estimated_size_gb=8.0,
                    description="Learning analytics with open textbooks and research",
                ),
            },
        ),
    ]


# ---------------------------------------------------------------------------
# BundleManager
# ---------------------------------------------------------------------------

class BundleManager:
    """Manages industry vertical bundles — register, resolve, build manifests."""

    def __init__(self, load_prebuilt: bool = False) -> None:
        self._verticals: Dict[str, VerticalDefinition] = {}
        if load_prebuilt:
            for v in _prebuilt_verticals():
                self._verticals[v.name] = v

    # -- registration ------------------------------------------------------

    def register_vertical(self, definition: VerticalDefinition) -> None:
        if definition.name in self._verticals:
            raise ValueError(
                f"Vertical '{definition.name}' is already registered."
            )
        self._verticals[definition.name] = definition

    def list_verticals(self) -> List[str]:
        return list(self._verticals.keys())

    def get_vertical(self, name: str) -> Optional[VerticalDefinition]:
        return self._verticals.get(name)

    # -- tier resolution ---------------------------------------------------

    def get_tier_spec(self, vertical: str, tier: BundleTier) -> TierSpec:
        """Return a merged TierSpec that includes all lower tiers."""
        vdef = self._verticals.get(vertical)
        if vdef is None:
            raise ValueError(f"Unknown vertical: '{vertical}'")

        merged_agents: List[str] = []
        merged_knowledge: List[str] = []
        merged_size = 0.0
        merged_desc_parts: List[str] = []

        for t in BundleTier:
            if t.value > tier.value:
                continue
            spec = vdef.tiers.get(t)
            if spec is None:
                continue
            for a in spec.agents:
                if a not in merged_agents:
                    merged_agents.append(a)
            for k in spec.knowledge_sources:
                if k not in merged_knowledge:
                    merged_knowledge.append(k)
            merged_size += spec.estimated_size_gb
            merged_desc_parts.append(spec.description)

        return TierSpec(
            agents=merged_agents,
            knowledge_sources=merged_knowledge,
            estimated_size_gb=merged_size,
            description="; ".join(merged_desc_parts),
        )

    # -- manifest creation -------------------------------------------------

    def create_manifest(
        self,
        vertical: str,
        tier: BundleTier,
        version: str = "1.0.0",
    ) -> BundleManifest:
        """Build a BundleManifest with all agents + knowledge for the given tier."""
        spec = self.get_tier_spec(vertical, tier)

        # Build KnowledgeSource stubs for each knowledge_source name
        vdef = self._verticals[vertical]
        knowledge_list: List[KnowledgeSource] = []
        for ks_name in spec.knowledge_sources:
            knowledge_list.append(
                KnowledgeSource(
                    name=ks_name,
                    url=f"https://intentos.dev/knowledge/{vertical}/{ks_name}",
                    size_gb=0.0,
                    description=f"{ks_name} for {vertical}",
                    format="zim",
                )
            )

        return BundleManifest(
            vertical=vertical,
            tier=tier,
            version=version,
            agents=list(spec.agents),
            knowledge=knowledge_list,
            total_size_gb=spec.estimated_size_gb,
        )

    # -- size estimation ---------------------------------------------------

    def estimate_size(self, vertical: str, tier: BundleTier) -> float:
        spec = self.get_tier_spec(vertical, tier)
        return spec.estimated_size_gb

    # -- validation --------------------------------------------------------

    def validate_manifest(self, manifest: BundleManifest) -> ValidationResult:
        """Check that all agents in the manifest exist in the vertical registry."""
        errors: List[str] = []
        warnings: List[str] = []

        vdef = self._verticals.get(manifest.vertical)
        if vdef is None:
            errors.append(f"Unknown vertical: '{manifest.vertical}'")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

        # Collect all known agents across all tiers
        known_agents: set[str] = set()
        for spec in vdef.tiers.values():
            known_agents.update(spec.agents)

        for agent in manifest.agents:
            if agent not in known_agents:
                errors.append(
                    f"Agent '{agent}' is not registered in vertical '{manifest.vertical}'."
                )

        if not manifest.agents:
            warnings.append("Bundle has no agents — this may be unintentional.")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # -- persistence -------------------------------------------------------

    def save(self, path: str) -> None:
        data = {
            name: vdef.to_dict()
            for name, vdef in self._verticals.items()
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Bundle file not found: {path}")
        with open(path) as f:
            data = json.load(f)
        self._verticals.clear()
        for name, vdef_data in data.items():
            self._verticals[name] = VerticalDefinition.from_dict(vdef_data)
