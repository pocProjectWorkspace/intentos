"""
Tests for IntentHub Registry (Phase 4.7).
Covers CapabilityManifest, RegistryEntry, Registry operations,
statistics, persistence, and edge cases.
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

import pytest

from core.platform.registry import (
    CapabilityManifest,
    Registry,
    RegistryEntry,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(**overrides) -> CapabilityManifest:
    """Return a valid manifest with optional field overrides."""
    defaults = dict(
        name="sample_agent",
        version="1.0.0",
        description="A sample capability.",
        author="alice",
        license="MIT",
        category="utility",
        status="stable",
        permissions=["read"],
        actions=["run"],
        platforms=["linux", "macos"],
        min_intentos_version="0.1.0",
    )
    defaults.update(overrides)
    return CapabilityManifest(**defaults)


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def bundle_path(tmp_dir):
    """Create a minimal capability bundle directory."""
    bp = os.path.join(tmp_dir, "bundle", "sample_agent")
    os.makedirs(bp)
    with open(os.path.join(bp, "main.py"), "w") as f:
        f.write("# capability entry\n")
    return bp


@pytest.fixture
def registry(tmp_dir):
    return Registry(storage_dir=os.path.join(tmp_dir, "registry_store"))


# ---------------------------------------------------------------------------
# 1. CapabilityManifest model tests
# ---------------------------------------------------------------------------

class TestCapabilityManifest:

    def test_create_manifest_all_fields(self):
        m = _make_manifest()
        assert m.name == "sample_agent"
        assert m.version == "1.0.0"
        assert m.description == "A sample capability."
        assert m.author == "alice"
        assert m.license == "MIT"
        assert m.category == "utility"
        assert m.status == "stable"
        assert m.permissions == ["read"]
        assert m.actions == ["run"]
        assert m.platforms == ["linux", "macos"]
        assert m.min_intentos_version == "0.1.0"
        assert m.checksum is not None  # sha256 auto-computed
        assert m.published_at is not None

    def test_manifest_default_status_is_draft(self):
        m = _make_manifest(status=None)
        assert m.status == "draft"

    def test_manifest_signature_optional(self):
        m = _make_manifest()
        assert m.signature is None
        m2 = _make_manifest(signature="abc123")
        assert m2.signature == "abc123"

    def test_manifest_serialization_round_trip(self):
        m = _make_manifest(signature="sig1")
        data = m.to_dict()
        assert isinstance(data, dict)
        m2 = CapabilityManifest.from_dict(data)
        assert m2.name == m.name
        assert m2.version == m.version
        assert m2.checksum == m.checksum
        assert m2.signature == m.signature
        assert m2.published_at == m.published_at

    def test_manifest_to_json_string(self):
        m = _make_manifest()
        j = json.loads(m.to_json())
        assert j["name"] == "sample_agent"

    def test_validation_name_must_be_snake_case_ending_agent(self):
        with pytest.raises(ValidationError, match="name"):
            _make_manifest(name="BadName")

    def test_validation_name_must_end_with_agent(self):
        with pytest.raises(ValidationError, match="name"):
            _make_manifest(name="sample_tool")

    def test_validation_version_must_be_semver(self):
        with pytest.raises(ValidationError, match="version"):
            _make_manifest(version="abc")

    def test_validation_version_semver_variants(self):
        # valid semver forms
        _make_manifest(version="0.0.1")
        _make_manifest(version="10.20.30")
        with pytest.raises(ValidationError):
            _make_manifest(version="1.0")

    def test_validation_required_fields(self):
        with pytest.raises(ValidationError):
            _make_manifest(description="")
        with pytest.raises(ValidationError):
            _make_manifest(author="")


# ---------------------------------------------------------------------------
# 2. RegistryEntry tests
# ---------------------------------------------------------------------------

class TestRegistryEntry:

    def test_registry_entry_defaults(self):
        m = _make_manifest()
        entry = RegistryEntry(manifest=m, download_url="file:///tmp/x")
        assert entry.install_count == 0
        assert entry.rating == 0.0
        assert entry.download_url == "file:///tmp/x"

    def test_registry_entry_serialization(self):
        m = _make_manifest()
        entry = RegistryEntry(manifest=m, download_url="/tmp/x", install_count=5, rating=4.2)
        d = entry.to_dict()
        entry2 = RegistryEntry.from_dict(d)
        assert entry2.install_count == 5
        assert entry2.rating == pytest.approx(4.2)
        assert entry2.manifest.name == "sample_agent"


# ---------------------------------------------------------------------------
# 3. Registry — publish / get / search / list
# ---------------------------------------------------------------------------

class TestRegistryPublishAndGet:

    def test_publish_and_get(self, registry, bundle_path):
        m = _make_manifest()
        registry.publish(m, bundle_path)
        entry = registry.get("sample_agent")
        assert entry is not None
        assert entry.manifest.version == "1.0.0"

    def test_publish_invalid_manifest_raises(self, registry, bundle_path):
        with pytest.raises(ValidationError):
            bad = {"name": "bad"}  # not a proper manifest
            registry.publish(CapabilityManifest._raw_construct(**{
                "name": "bad", "version": "1.0.0"
            }), bundle_path)

    def test_duplicate_name_version_rejected(self, registry, bundle_path):
        m = _make_manifest()
        registry.publish(m, bundle_path)
        with pytest.raises(ValidationError, match="already exists"):
            registry.publish(m, bundle_path)

    def test_different_version_ok(self, registry, bundle_path):
        registry.publish(_make_manifest(version="1.0.0"), bundle_path)
        registry.publish(_make_manifest(version="2.0.0"), bundle_path)
        assert registry.get("sample_agent").manifest.version == "2.0.0"

    def test_get_nonexistent_returns_none(self, registry):
        assert registry.get("no_such_agent") is None

    def test_get_version(self, registry, bundle_path):
        registry.publish(_make_manifest(version="1.0.0"), bundle_path)
        registry.publish(_make_manifest(version="1.1.0"), bundle_path)
        entry = registry.get_version("sample_agent", "1.0.0")
        assert entry is not None
        assert entry.manifest.version == "1.0.0"

    def test_get_version_missing(self, registry, bundle_path):
        registry.publish(_make_manifest(version="1.0.0"), bundle_path)
        assert registry.get_version("sample_agent", "9.9.9") is None

    def test_list_versions(self, registry, bundle_path):
        registry.publish(_make_manifest(version="1.0.0"), bundle_path)
        registry.publish(_make_manifest(version="1.1.0"), bundle_path)
        registry.publish(_make_manifest(version="2.0.0"), bundle_path)
        versions = registry.list_versions("sample_agent")
        assert len(versions) == 3


class TestRegistrySearch:

    def test_search_by_name(self, registry, bundle_path):
        registry.publish(_make_manifest(name="weather_agent", description="Weather info"), bundle_path)
        registry.publish(_make_manifest(name="finance_agent", description="Finance info"), bundle_path)
        results = registry.search("weather")
        assert len(results) == 1
        assert results[0].manifest.name == "weather_agent"

    def test_search_by_description(self, registry, bundle_path):
        registry.publish(_make_manifest(name="helper_agent", description="Manages todo lists"), bundle_path)
        results = registry.search("todo")
        assert len(results) == 1

    def test_search_by_category(self, registry, bundle_path):
        registry.publish(_make_manifest(name="net_agent", category="networking"), bundle_path)
        results = registry.search("networking")
        assert len(results) == 1

    def test_search_empty_query_returns_all(self, registry, bundle_path):
        registry.publish(_make_manifest(name="one_agent"), bundle_path)
        registry.publish(_make_manifest(name="two_agent"), bundle_path)
        results = registry.search("")
        assert len(results) == 2


class TestRegistryList:

    def test_list_all(self, registry, bundle_path):
        registry.publish(_make_manifest(name="a_agent"), bundle_path)
        registry.publish(_make_manifest(name="b_agent"), bundle_path)
        assert len(registry.list_all()) == 2

    def test_list_all_filter_category(self, registry, bundle_path):
        registry.publish(_make_manifest(name="a_agent", category="util"), bundle_path)
        registry.publish(_make_manifest(name="b_agent", category="net"), bundle_path)
        assert len(registry.list_all(category="net")) == 1

    def test_list_all_filter_status(self, registry, bundle_path):
        registry.publish(_make_manifest(name="a_agent", status="stable"), bundle_path)
        registry.publish(_make_manifest(name="b_agent", status="deprecated"), bundle_path)
        assert len(registry.list_all(status="deprecated")) == 1


# ---------------------------------------------------------------------------
# 4. Install / Uninstall / is_installed / check_updates
# ---------------------------------------------------------------------------

class TestRegistryInstall:

    def test_install(self, registry, bundle_path, tmp_dir):
        registry.publish(_make_manifest(), bundle_path)
        target = os.path.join(tmp_dir, "installed")
        os.makedirs(target)
        path = registry.install("sample_agent", target)
        assert os.path.isdir(path)
        assert registry.is_installed("sample_agent", target)

    def test_install_nonexistent_raises(self, registry, tmp_dir):
        target = os.path.join(tmp_dir, "installed")
        os.makedirs(target)
        with pytest.raises(ValueError, match="not found"):
            registry.install("ghost_agent", target)

    def test_uninstall(self, registry, bundle_path, tmp_dir):
        registry.publish(_make_manifest(), bundle_path)
        target = os.path.join(tmp_dir, "installed")
        os.makedirs(target)
        registry.install("sample_agent", target)
        registry.uninstall("sample_agent", target)
        assert not registry.is_installed("sample_agent", target)

    def test_is_installed_false_when_not(self, registry, tmp_dir):
        target = os.path.join(tmp_dir, "installed")
        os.makedirs(target)
        assert not registry.is_installed("sample_agent", target)

    def test_install_increments_count(self, registry, bundle_path, tmp_dir):
        registry.publish(_make_manifest(), bundle_path)
        target = os.path.join(tmp_dir, "installed")
        os.makedirs(target)
        registry.install("sample_agent", target)
        entry = registry.get("sample_agent")
        assert entry.install_count == 1

    def test_check_updates(self, registry, bundle_path):
        registry.publish(_make_manifest(version="1.0.0"), bundle_path)
        registry.publish(_make_manifest(version="2.0.0"), bundle_path)
        updates = registry.check_updates({"sample_agent": "1.0.0"})
        assert len(updates) == 1
        assert updates[0]["latest_version"] == "2.0.0"

    def test_check_updates_none_needed(self, registry, bundle_path):
        registry.publish(_make_manifest(version="1.0.0"), bundle_path)
        updates = registry.check_updates({"sample_agent": "1.0.0"})
        assert len(updates) == 0


# ---------------------------------------------------------------------------
# 5. Statistics
# ---------------------------------------------------------------------------

class TestRegistryStats:

    def test_get_stats_empty(self, registry):
        stats = registry.get_stats()
        assert stats["total_capabilities"] == 0
        assert stats["total_installs"] == 0

    def test_get_stats(self, registry, bundle_path, tmp_dir):
        registry.publish(_make_manifest(name="a_agent", category="util"), bundle_path)
        registry.publish(_make_manifest(name="b_agent", category="net"), bundle_path)
        target = os.path.join(tmp_dir, "installed")
        os.makedirs(target)
        registry.install("a_agent", target)
        stats = registry.get_stats()
        assert stats["total_capabilities"] == 2
        assert stats["by_category"]["util"] == 1
        assert stats["by_category"]["net"] == 1
        assert stats["by_status"]["stable"] == 2
        assert stats["total_installs"] == 1


# ---------------------------------------------------------------------------
# 6. Persistence
# ---------------------------------------------------------------------------

class TestRegistryPersistence:

    def test_save_and_load(self, registry, bundle_path, tmp_dir):
        registry.publish(_make_manifest(name="persist_agent"), bundle_path)
        save_path = os.path.join(tmp_dir, "registry.json")
        registry.save(save_path)
        assert os.path.isfile(save_path)

        registry2 = Registry(storage_dir=os.path.join(tmp_dir, "store2"))
        registry2.load(save_path)
        entry = registry2.get("persist_agent")
        assert entry is not None
        assert entry.manifest.name == "persist_agent"

    def test_load_nonexistent_file(self, registry, tmp_dir):
        with pytest.raises(FileNotFoundError):
            registry.load(os.path.join(tmp_dir, "nope.json"))


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_registry_list(self, registry):
        assert registry.list_all() == []

    def test_empty_registry_search(self, registry):
        assert registry.search("anything") == []

    def test_empty_registry_stats(self, registry):
        s = registry.get_stats()
        assert s["total_capabilities"] == 0
