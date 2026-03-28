"""
Tests for Industry Vertical Bundles (Phase 4.10).
Covers BundleTier, VerticalDefinition, BundleManifest, BundleManager,
pre-built verticals, tier inclusion, persistence, and edge cases.
"""

import json
import os
import tempfile
import shutil

import pytest

from core.platform.bundles import (
    BundleTier,
    TierSpec,
    KnowledgeSource,
    VerticalDefinition,
    BundleManifest,
    BundleManager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_knowledge(name="test_kb", **overrides):
    defaults = dict(
        name=name,
        url="https://example.com/test.zim",
        size_gb=0.5,
        description="Test knowledge source",
        format="zim",
    )
    defaults.update(overrides)
    return KnowledgeSource(**defaults)


def _make_tier_spec(**overrides):
    defaults = dict(
        agents=["test_agent"],
        knowledge_sources=["test_kb"],
        estimated_size_gb=1.0,
        description="Test tier",
    )
    defaults.update(overrides)
    return TierSpec(**defaults)


def _make_vertical(name="testing", **overrides):
    defaults = dict(
        name=name,
        display_name="Testing Vertical",
        description="A vertical for testing",
        tiers={
            BundleTier.ESSENTIAL: _make_tier_spec(
                agents=["basic_agent"],
                knowledge_sources=["basic_kb"],
                estimated_size_gb=0.5,
                description="Essential tier",
            ),
            BundleTier.STANDARD: _make_tier_spec(
                agents=["standard_agent"],
                knowledge_sources=["standard_kb"],
                estimated_size_gb=1.0,
                description="Standard tier",
            ),
            BundleTier.COMPREHENSIVE: _make_tier_spec(
                agents=["advanced_agent"],
                knowledge_sources=["advanced_kb"],
                estimated_size_gb=2.0,
                description="Comprehensive tier",
            ),
        },
    )
    defaults.update(overrides)
    return VerticalDefinition(**defaults)


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def manager():
    return BundleManager()


@pytest.fixture
def manager_with_verticals():
    mgr = BundleManager()
    mgr.register_vertical(_make_vertical("alpha"))
    mgr.register_vertical(_make_vertical("beta"))
    return mgr


# ---------------------------------------------------------------------------
# BundleTier enum
# ---------------------------------------------------------------------------

class TestBundleTier:
    def test_tier_values_exist(self):
        assert BundleTier.ESSENTIAL is not None
        assert BundleTier.STANDARD is not None
        assert BundleTier.COMPREHENSIVE is not None

    def test_tier_ordering(self):
        """Each tier has a higher numeric value than the previous."""
        assert BundleTier.ESSENTIAL.value < BundleTier.STANDARD.value
        assert BundleTier.STANDARD.value < BundleTier.COMPREHENSIVE.value

    def test_tier_includes_lower(self):
        """COMPREHENSIVE includes STANDARD which includes ESSENTIAL."""
        assert BundleTier.COMPREHENSIVE.includes(BundleTier.STANDARD)
        assert BundleTier.COMPREHENSIVE.includes(BundleTier.ESSENTIAL)
        assert BundleTier.STANDARD.includes(BundleTier.ESSENTIAL)
        assert not BundleTier.ESSENTIAL.includes(BundleTier.STANDARD)
        assert not BundleTier.STANDARD.includes(BundleTier.COMPREHENSIVE)


# ---------------------------------------------------------------------------
# VerticalDefinition model
# ---------------------------------------------------------------------------

class TestVerticalDefinition:
    def test_create_vertical(self):
        v = _make_vertical()
        assert v.name == "testing"
        assert v.display_name == "Testing Vertical"
        assert BundleTier.ESSENTIAL in v.tiers

    def test_vertical_has_all_tiers(self):
        v = _make_vertical()
        assert len(v.tiers) == 3


# ---------------------------------------------------------------------------
# BundleManifest model
# ---------------------------------------------------------------------------

class TestBundleManifest:
    def test_create_manifest(self):
        ks = _make_knowledge()
        m = BundleManifest(
            vertical="testing",
            tier=BundleTier.ESSENTIAL,
            version="1.0.0",
            agents=["basic_agent"],
            knowledge=[ks],
            total_size_gb=0.5,
        )
        assert m.vertical == "testing"
        assert m.tier == BundleTier.ESSENTIAL
        assert m.created_at is not None

    def test_manifest_serialization(self):
        ks = _make_knowledge()
        m = BundleManifest(
            vertical="testing",
            tier=BundleTier.STANDARD,
            version="1.0.0",
            agents=["a_agent"],
            knowledge=[ks],
            total_size_gb=1.5,
        )
        d = m.to_dict()
        assert d["vertical"] == "testing"
        assert d["tier"] == "STANDARD"
        m2 = BundleManifest.from_dict(d)
        assert m2.vertical == m.vertical
        assert m2.tier == m.tier
        assert len(m2.knowledge) == 1


# ---------------------------------------------------------------------------
# KnowledgeSource model
# ---------------------------------------------------------------------------

class TestKnowledgeSource:
    def test_valid_formats(self):
        for fmt in ("zim", "json", "csv", "pdf"):
            ks = _make_knowledge(format=fmt)
            assert ks.format == fmt

    def test_knowledge_serialization(self):
        ks = _make_knowledge()
        d = ks.to_dict()
        ks2 = KnowledgeSource.from_dict(d)
        assert ks2.name == ks.name
        assert ks2.url == ks.url


# ---------------------------------------------------------------------------
# BundleManager — registration
# ---------------------------------------------------------------------------

class TestBundleManagerRegistration:
    def test_register_vertical(self, manager):
        v = _make_vertical()
        manager.register_vertical(v)
        assert manager.get_vertical("testing") is not None

    def test_list_verticals(self, manager_with_verticals):
        names = manager_with_verticals.list_verticals()
        assert "alpha" in names
        assert "beta" in names

    def test_get_vertical_not_found(self, manager):
        assert manager.get_vertical("nonexistent") is None

    def test_register_duplicate_vertical_raises(self, manager):
        v = _make_vertical()
        manager.register_vertical(v)
        with pytest.raises(ValueError, match="already registered"):
            manager.register_vertical(v)


# ---------------------------------------------------------------------------
# BundleManager — tier spec resolution
# ---------------------------------------------------------------------------

class TestBundleManagerTierSpec:
    def test_get_tier_spec_essential(self, manager):
        manager.register_vertical(_make_vertical())
        spec = manager.get_tier_spec("testing", BundleTier.ESSENTIAL)
        assert "basic_agent" in spec.agents
        assert "standard_agent" not in spec.agents

    def test_get_tier_spec_standard_includes_essential(self, manager):
        manager.register_vertical(_make_vertical())
        spec = manager.get_tier_spec("testing", BundleTier.STANDARD)
        assert "basic_agent" in spec.agents
        assert "standard_agent" in spec.agents
        assert "basic_kb" in spec.knowledge_sources
        assert "standard_kb" in spec.knowledge_sources

    def test_get_tier_spec_comprehensive_includes_all(self, manager):
        manager.register_vertical(_make_vertical())
        spec = manager.get_tier_spec("testing", BundleTier.COMPREHENSIVE)
        assert "basic_agent" in spec.agents
        assert "standard_agent" in spec.agents
        assert "advanced_agent" in spec.agents

    def test_get_tier_spec_unknown_vertical_raises(self, manager):
        with pytest.raises(ValueError, match="Unknown vertical"):
            manager.get_tier_spec("nope", BundleTier.ESSENTIAL)


# ---------------------------------------------------------------------------
# BundleManager — manifest creation
# ---------------------------------------------------------------------------

class TestBundleManagerManifest:
    def test_create_manifest(self, manager):
        manager.register_vertical(_make_vertical())
        manifest = manager.create_manifest("testing", BundleTier.ESSENTIAL)
        assert manifest.vertical == "testing"
        assert manifest.tier == BundleTier.ESSENTIAL
        assert "basic_agent" in manifest.agents

    def test_create_manifest_comprehensive_has_all_knowledge(self, manager):
        manager.register_vertical(_make_vertical())
        manifest = manager.create_manifest("testing", BundleTier.COMPREHENSIVE)
        kb_names = [k.name for k in manifest.knowledge]
        assert "basic_kb" in kb_names
        assert "standard_kb" in kb_names
        assert "advanced_kb" in kb_names


# ---------------------------------------------------------------------------
# BundleManager — size estimation
# ---------------------------------------------------------------------------

class TestBundleManagerSize:
    def test_estimate_size_essential(self, manager):
        manager.register_vertical(_make_vertical())
        size = manager.estimate_size("testing", BundleTier.ESSENTIAL)
        assert size == pytest.approx(0.5)

    def test_estimate_size_comprehensive(self, manager):
        manager.register_vertical(_make_vertical())
        size = manager.estimate_size("testing", BundleTier.COMPREHENSIVE)
        # 0.5 + 1.0 + 2.0
        assert size == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# BundleManager — validation
# ---------------------------------------------------------------------------

class TestBundleManagerValidation:
    def test_validate_manifest_valid(self, manager):
        manager.register_vertical(_make_vertical())
        manifest = manager.create_manifest("testing", BundleTier.ESSENTIAL)
        result = manager.validate_manifest(manifest)
        assert result.is_valid

    def test_validate_manifest_unknown_agent(self, manager):
        """Manifest referencing agents not in the vertical should fail."""
        manager.register_vertical(_make_vertical())
        manifest = manager.create_manifest("testing", BundleTier.ESSENTIAL)
        manifest.agents.append("ghost_agent")
        result = manager.validate_manifest(manifest)
        assert not result.is_valid
        assert any("ghost_agent" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Pre-built verticals
# ---------------------------------------------------------------------------

class TestPrebuiltVerticals:
    def test_prebuilt_verticals_count(self):
        mgr = BundleManager(load_prebuilt=True)
        names = mgr.list_verticals()
        assert len(names) >= 5

    def test_legal_vertical_agents(self):
        mgr = BundleManager(load_prebuilt=True)
        v = mgr.get_vertical("legal")
        assert v is not None
        all_agents = []
        for spec in v.tiers.values():
            all_agents.extend(spec.agents)
        assert "contract_agent" in all_agents
        assert "case_agent" in all_agents

    def test_medical_vertical_exists(self):
        mgr = BundleManager(load_prebuilt=True)
        assert mgr.get_vertical("medical") is not None

    def test_financial_vertical_exists(self):
        mgr = BundleManager(load_prebuilt=True)
        assert mgr.get_vertical("financial") is not None

    def test_manufacturing_vertical_exists(self):
        mgr = BundleManager(load_prebuilt=True)
        assert mgr.get_vertical("manufacturing") is not None

    def test_education_vertical_exists(self):
        mgr = BundleManager(load_prebuilt=True)
        assert mgr.get_vertical("education") is not None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_and_load(self, manager, tmp_dir):
        manager.register_vertical(_make_vertical())
        path = os.path.join(tmp_dir, "bundles.json")
        manager.save(path)
        assert os.path.isfile(path)

        mgr2 = BundleManager()
        mgr2.load(path)
        assert mgr2.get_vertical("testing") is not None

    def test_load_nonexistent_raises(self, manager):
        with pytest.raises(FileNotFoundError):
            manager.load("/nonexistent/path/bundles.json")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_vertical_no_agents(self, manager):
        """A vertical with empty agent lists is valid but produces a warning."""
        v = VerticalDefinition(
            name="empty",
            display_name="Empty Vertical",
            description="No agents",
            tiers={
                BundleTier.ESSENTIAL: TierSpec(
                    agents=[],
                    knowledge_sources=[],
                    estimated_size_gb=0.0,
                    description="Empty",
                ),
            },
        )
        manager.register_vertical(v)
        manifest = manager.create_manifest("empty", BundleTier.ESSENTIAL)
        result = manager.validate_manifest(manifest)
        assert result.is_valid
        assert len(result.warnings) > 0
