"""Tests for IntentOS Offline Knowledge Packages (Phase 4.11)."""

import json
import os
import pytest
from pathlib import Path

from core.hub.offline import (
    ContentItem,
    OfflineKit,
    OfflinePackageManager,
)


# ---------------------------------------------------------------------------
# ContentItem model
# ---------------------------------------------------------------------------

class TestContentItem:
    def test_create_basic(self):
        item = ContentItem(
            name="phi3_mini",
            description="Phi-3 Mini quantized model",
            url="https://models.example.com/phi3_mini.bin",
            size_bytes=2_469_606_195,
            format="bin",
            category="ai_model",
        )
        assert item.name == "phi3_mini"
        assert item.description == "Phi-3 Mini quantized model"
        assert item.url == "https://models.example.com/phi3_mini.bin"
        assert item.size_bytes == 2_469_606_195
        assert item.format == "bin"
        assert item.category == "ai_model"

    def test_optional_checksum(self):
        item = ContentItem(
            name="wiki",
            description="Wikipedia",
            url="https://example.com/wiki.zim",
            size_bytes=100,
            format="zim",
            category="reference",
            checksum_sha256="abc123",
        )
        assert item.checksum_sha256 == "abc123"

    def test_checksum_default_none(self):
        item = ContentItem(
            name="wiki",
            description="Wikipedia",
            url="https://example.com/wiki.zim",
            size_bytes=100,
            format="zim",
            category="reference",
        )
        assert item.checksum_sha256 is None

    def test_installed_default_false(self):
        item = ContentItem(
            name="wiki",
            description="Wikipedia",
            url="https://example.com/wiki.zim",
            size_bytes=100,
            format="zim",
            category="reference",
        )
        assert item.installed is False

    def test_valid_formats(self):
        for fmt in ("zim", "json", "pdf", "bin"):
            item = ContentItem(
                name="x", description="x", url="http://x",
                size_bytes=1, format=fmt, category="reference",
            )
            assert item.format == fmt

    def test_valid_categories(self):
        for cat in ("reference", "education", "survival", "maps", "medical", "ai_model"):
            item = ContentItem(
                name="x", description="x", url="http://x",
                size_bytes=1, format="json", category=cat,
            )
            assert item.category == cat


# ---------------------------------------------------------------------------
# OfflineKit model
# ---------------------------------------------------------------------------

class TestOfflineKit:
    def test_create_kit(self):
        kit = OfflineKit(
            name="test_kit",
            description="A test kit",
            items=[],
            total_size_bytes=0,
            target_platform="linux-arm64",
        )
        assert kit.name == "test_kit"
        assert kit.description == "A test kit"
        assert kit.items == []
        assert kit.total_size_bytes == 0
        assert kit.target_platform == "linux-arm64"
        assert kit.created_at is not None

    def test_total_size_gb_property(self):
        kit = OfflineKit(
            name="test",
            description="test",
            items=[],
            total_size_bytes=5_368_709_120,  # 5 GB
            target_platform="linux-x86_64",
        )
        assert abs(kit.total_size_gb - 5.0) < 0.01

    def test_total_size_gb_fractional(self):
        kit = OfflineKit(
            name="test",
            description="test",
            items=[],
            total_size_bytes=1_610_612_736,  # 1.5 GB
            target_platform="linux-x86_64",
        )
        assert abs(kit.total_size_gb - 1.5) < 0.01


# ---------------------------------------------------------------------------
# OfflinePackageManager – catalog operations
# ---------------------------------------------------------------------------

class TestCatalog:
    def setup_method(self):
        self.mgr = OfflinePackageManager()

    def _make_item(self, name="test_item", category="reference"):
        return ContentItem(
            name=name, description=f"Desc for {name}",
            url=f"http://example.com/{name}",
            size_bytes=1000, format="json", category=category,
        )

    def test_register_content(self):
        item = self._make_item()
        self.mgr.register_content(item)
        catalog = self.mgr.get_catalog()
        assert len(catalog) == 1
        assert catalog[0].name == "test_item"

    def test_get_catalog_filter_by_category(self):
        self.mgr.register_content(self._make_item("a", "reference"))
        self.mgr.register_content(self._make_item("b", "medical"))
        self.mgr.register_content(self._make_item("c", "reference"))
        result = self.mgr.get_catalog(category="reference")
        assert len(result) == 2

    def test_search_catalog_by_name(self):
        self.mgr.register_content(self._make_item("wikipedia_quick"))
        self.mgr.register_content(self._make_item("medical_essential"))
        results = self.mgr.search_catalog("wiki")
        assert len(results) == 1
        assert results[0].name == "wikipedia_quick"

    def test_search_catalog_by_description(self):
        item = ContentItem(
            name="phi3", description="Small language model for offline",
            url="http://x", size_bytes=100, format="bin", category="ai_model",
        )
        self.mgr.register_content(item)
        results = self.mgr.search_catalog("language model")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Kit building
# ---------------------------------------------------------------------------

class TestKitBuilding:
    def setup_method(self):
        self.mgr = OfflinePackageManager()
        self.mgr.load_default_catalog()

    def test_create_kit(self):
        kit = self.mgr.create_kit("my_kit", ["phi3_mini", "wikipedia_quick"])
        assert kit.name == "my_kit"
        assert len(kit.items) == 2
        assert kit.total_size_bytes > 0

    def test_estimate_kit_size(self):
        size = self.mgr.estimate_kit_size(["phi3_mini", "wikipedia_quick"])
        expected = 2_469_606_195 + 328_204_288  # ~2.3GB + 313MB
        assert size == expected

    def test_unknown_content_item_raises(self):
        with pytest.raises(KeyError):
            self.mgr.create_kit("bad", ["nonexistent_item"])

    def test_empty_kit_valid_with_warning(self):
        kit = self.mgr.create_kit("empty_kit", [])
        assert kit is not None
        assert len(kit.items) == 0
        assert kit.total_size_bytes == 0


# ---------------------------------------------------------------------------
# Pre-built kits
# ---------------------------------------------------------------------------

class TestPrebuiltKits:
    def setup_method(self):
        self.mgr = OfflinePackageManager()
        self.mgr.load_default_catalog()

    def test_survival_basic(self):
        kit = self.mgr.get_prebuilt_kit("survival_basic")
        names = [i.name for i in kit.items]
        assert "phi3_mini" in names
        assert "wikipedia_quick" in names
        assert "medical_essential" in names

    def test_education_kit(self):
        kit = self.mgr.get_prebuilt_kit("education_kit")
        names = [i.name for i in kit.items]
        assert "phi3_mini" in names
        assert "khan_academy" in names
        assert "wikipedia_standard" in names

    def test_medical_kit(self):
        kit = self.mgr.get_prebuilt_kit("medical_kit")
        names = [i.name for i in kit.items]
        assert "phi3_mini" in names
        assert "medical_comprehensive" in names
        assert "drug_database" in names

    def test_developer_kit(self):
        kit = self.mgr.get_prebuilt_kit("developer_kit")
        names = [i.name for i in kit.items]
        assert "mistral_7b" in names
        assert "stackoverflow_excerpts" in names
        assert "documentation_pack" in names


# ---------------------------------------------------------------------------
# USB deployment
# ---------------------------------------------------------------------------

class TestUSBDeployment:
    def setup_method(self):
        self.mgr = OfflinePackageManager()
        self.mgr.load_default_catalog()

    def test_prepare_for_usb(self, tmp_path):
        kit = self.mgr.create_kit("usb_test", ["phi3_mini", "wikipedia_quick"])
        self.mgr.prepare_for_usb(kit, str(tmp_path))
        base = tmp_path / "intentos-offline"
        assert base.is_dir()
        assert (base / "MANIFEST.json").is_file()
        assert (base / "models").is_dir()
        assert (base / "content").is_dir()
        assert (base / "README.txt").is_file()
        assert (base / "install.sh").is_file()

    def test_manifest_contains_kit_info(self, tmp_path):
        kit = self.mgr.create_kit("usb_test", ["phi3_mini"])
        self.mgr.prepare_for_usb(kit, str(tmp_path))
        manifest_path = tmp_path / "intentos-offline" / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["name"] == "usb_test"
        assert len(manifest["items"]) == 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def setup_method(self):
        self.mgr = OfflinePackageManager()
        self.mgr.load_default_catalog()

    def test_validate_valid_kit(self):
        kit = self.mgr.create_kit("v", ["phi3_mini"])
        result = self.mgr.validate_kit(kit)
        assert result["valid"] is True

    def test_validate_kit_too_large(self):
        """Kit over 128 GB should produce a warning."""
        kit = OfflineKit(
            name="huge",
            description="Huge kit",
            items=[],
            total_size_bytes=140 * 1024**3,
            target_platform="linux-x86_64",
        )
        result = self.mgr.validate_kit(kit)
        assert any("large" in w.lower() or "128" in w for w in result.get("warnings", []))


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def setup_method(self):
        self.mgr = OfflinePackageManager()
        self.mgr.load_default_catalog()

    def test_save_and_load_catalog(self, tmp_path):
        path = str(tmp_path / "catalog.json")
        self.mgr.save_catalog(path)
        mgr2 = OfflinePackageManager()
        mgr2.load_catalog(path)
        assert len(mgr2.get_catalog()) == len(self.mgr.get_catalog())

    def test_save_and_load_kit(self, tmp_path):
        kit = self.mgr.create_kit("persist_test", ["phi3_mini", "wikipedia_quick"])
        path = str(tmp_path / "kit.json")
        self.mgr.save_kit(kit, path)
        loaded = self.mgr.load_kit(path)
        assert loaded.name == "persist_test"
        assert len(loaded.items) == 2
        assert loaded.total_size_bytes == kit.total_size_bytes
