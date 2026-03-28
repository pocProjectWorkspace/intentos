"""IntentOS Offline Knowledge Packages (Phase 4.11).

NOMAD-style survival kits for air-gapped environments.
Provides content catalog management, kit building, USB deployment,
and persistence for offline knowledge packages.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

VALID_FORMATS = {"zim", "json", "pdf", "bin"}
VALID_CATEGORIES = {"reference", "education", "survival", "maps", "medical", "ai_model"}


@dataclass
class ContentItem:
    """A single piece of downloadable offline content."""

    name: str
    description: str
    url: str
    size_bytes: int
    format: str          # zim / json / pdf / bin
    category: str        # reference / education / survival / maps / medical / ai_model
    checksum_sha256: Optional[str] = None
    installed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ContentItem":
        return cls(**d)


@dataclass
class OfflineKit:
    """A bundled collection of ContentItems ready for deployment."""

    name: str
    description: str
    items: List[ContentItem]
    total_size_bytes: int
    target_platform: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def total_size_gb(self) -> float:
        return self.total_size_bytes / (1024 ** 3)

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
            "items": [i.to_dict() for i in self.items],
            "total_size_bytes": self.total_size_bytes,
            "target_platform": self.target_platform,
            "created_at": self.created_at,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "OfflineKit":
        items = [ContentItem.from_dict(i) for i in d.get("items", [])]
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            items=items,
            total_size_bytes=d["total_size_bytes"],
            target_platform=d.get("target_platform", "linux-x86_64"),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


# ---------------------------------------------------------------------------
# Default catalog entries
# ---------------------------------------------------------------------------

_DEFAULT_CATALOG: List[ContentItem] = [
    ContentItem(
        name="phi3_mini",
        description="Phi-3 Mini quantized model for offline inference",
        url="https://models.intentos.dev/phi3_mini_q4.bin",
        size_bytes=2_469_606_195,  # ~2.3 GB
        format="bin",
        category="ai_model",
    ),
    ContentItem(
        name="mistral_7b",
        description="Mistral 7B quantized model for offline inference",
        url="https://models.intentos.dev/mistral_7b_q4.bin",
        size_bytes=4_294_967_296,  # 4.0 GB
        format="bin",
        category="ai_model",
    ),
    ContentItem(
        name="wikipedia_quick",
        description="Wikipedia Quick Reference – condensed top articles",
        url="https://content.intentos.dev/wikipedia_quick.zim",
        size_bytes=328_204_288,  # 313 MB
        format="zim",
        category="reference",
    ),
    ContentItem(
        name="wikipedia_standard",
        description="Wikipedia Standard – full text of English Wikipedia",
        url="https://content.intentos.dev/wikipedia_standard.zim",
        size_bytes=12_884_901_888,  # 12 GB
        format="zim",
        category="reference",
    ),
    ContentItem(
        name="medical_essential",
        description="Essential medical reference for field use",
        url="https://content.intentos.dev/medical_essential.zim",
        size_bytes=1_073_741_824,  # 1 GB
        format="zim",
        category="medical",
    ),
    ContentItem(
        name="medical_comprehensive",
        description="Comprehensive medical encyclopedia and treatment guides",
        url="https://content.intentos.dev/medical_comprehensive.zim",
        size_bytes=3_221_225_472,  # 3 GB
        format="zim",
        category="medical",
    ),
    ContentItem(
        name="drug_database",
        description="Offline drug interaction and dosage database",
        url="https://content.intentos.dev/drug_database.json",
        size_bytes=536_870_912,  # 512 MB
        format="json",
        category="medical",
    ),
    ContentItem(
        name="khan_academy",
        description="Khan Academy offline course materials",
        url="https://content.intentos.dev/khan_academy.zim",
        size_bytes=2_147_483_648,  # 2 GB
        format="zim",
        category="education",
    ),
    ContentItem(
        name="stackoverflow_excerpts",
        description="Stack Overflow top Q&A excerpts for developers",
        url="https://content.intentos.dev/stackoverflow.zim",
        size_bytes=2_684_354_560,  # 2.5 GB
        format="zim",
        category="reference",
    ),
    ContentItem(
        name="documentation_pack",
        description="Developer documentation pack – Python, JS, Linux",
        url="https://content.intentos.dev/docs_pack.zim",
        size_bytes=1_073_741_824,  # 1 GB
        format="zim",
        category="reference",
    ),
]

# Pre-built kit definitions: name -> (description, item_names)
_PREBUILT_KITS: Dict[str, tuple] = {
    "survival_basic": (
        "Basic survival kit with small AI model and essential references",
        ["phi3_mini", "wikipedia_quick", "medical_essential"],
    ),
    "education_kit": (
        "Education-focused kit with learning materials",
        ["phi3_mini", "khan_academy", "wikipedia_standard"],
    ),
    "medical_kit": (
        "Medical-focused kit with comprehensive health references",
        ["phi3_mini", "medical_comprehensive", "drug_database"],
    ),
    "developer_kit": (
        "Developer kit with coding references and larger model",
        ["mistral_7b", "stackoverflow_excerpts", "documentation_pack"],
    ),
}

MAX_KIT_SIZE_BYTES = 128 * 1024 ** 3  # 128 GB


# ---------------------------------------------------------------------------
# OfflinePackageManager
# ---------------------------------------------------------------------------

class OfflinePackageManager:
    """Manages offline content catalog, kit creation, and USB deployment."""

    def __init__(self) -> None:
        self._catalog: Dict[str, ContentItem] = {}

    # -- Catalog operations --------------------------------------------------

    def register_content(self, item: ContentItem) -> None:
        """Add a content item to the catalog."""
        self._catalog[item.name] = item

    def get_catalog(self, category: Optional[str] = None) -> List[ContentItem]:
        """Return catalog items, optionally filtered by category."""
        items = list(self._catalog.values())
        if category is not None:
            items = [i for i in items if i.category == category]
        return items

    def search_catalog(self, query: str) -> List[ContentItem]:
        """Search catalog by name and description (case-insensitive)."""
        q = query.lower()
        return [
            item for item in self._catalog.values()
            if q in item.name.lower() or q in item.description.lower()
        ]

    def load_default_catalog(self) -> None:
        """Populate the catalog with the built-in default items."""
        for item in _DEFAULT_CATALOG:
            self.register_content(item)

    # -- Kit building --------------------------------------------------------

    def create_kit(
        self,
        name: str,
        item_names: List[str],
        description: str = "",
        target_platform: str = "linux-x86_64",
    ) -> OfflineKit:
        """Create an OfflineKit from catalog items by name."""
        if not item_names:
            warnings.warn(f"Kit '{name}' has no items.", UserWarning)

        items: List[ContentItem] = []
        for item_name in item_names:
            if item_name not in self._catalog:
                raise KeyError(f"Unknown content item: '{item_name}'")
            items.append(self._catalog[item_name])

        total = sum(i.size_bytes for i in items)
        return OfflineKit(
            name=name,
            description=description,
            items=items,
            total_size_bytes=total,
            target_platform=target_platform,
        )

    def estimate_kit_size(self, item_names: List[str]) -> int:
        """Return total bytes for the given item names without creating a kit."""
        total = 0
        for item_name in item_names:
            if item_name not in self._catalog:
                raise KeyError(f"Unknown content item: '{item_name}'")
            total += self._catalog[item_name].size_bytes
        return total

    def get_prebuilt_kit(self, kit_name: str) -> OfflineKit:
        """Return a pre-built kit by name."""
        if kit_name not in _PREBUILT_KITS:
            raise KeyError(f"Unknown pre-built kit: '{kit_name}'")
        description, item_names = _PREBUILT_KITS[kit_name]
        return self.create_kit(kit_name, item_names, description=description)

    # -- Validation ----------------------------------------------------------

    def validate_kit(self, kit: OfflineKit) -> dict:
        """Validate a kit. Returns dict with 'valid' bool and 'warnings' list."""
        result: dict = {"valid": True, "warnings": []}

        # Check items exist in catalog
        for item in kit.items:
            if item.name not in self._catalog:
                result["valid"] = False
                result["warnings"].append(f"Item '{item.name}' not in catalog.")

        # Check size
        if kit.total_size_bytes > MAX_KIT_SIZE_BYTES:
            result["warnings"].append(
                f"Kit size ({kit.total_size_gb:.1f} GB) exceeds 128 GB limit."
            )

        if not kit.items:
            result["warnings"].append("Kit has no items.")

        return result

    # -- USB deployment ------------------------------------------------------

    def prepare_for_usb(self, kit: OfflineKit, target_dir: str) -> Path:
        """Create directory structure for USB deployment."""
        base = Path(target_dir) / "intentos-offline"
        models_dir = base / "models"
        content_dir = base / "content"

        models_dir.mkdir(parents=True, exist_ok=True)
        content_dir.mkdir(parents=True, exist_ok=True)

        # MANIFEST.json
        manifest = kit.to_dict()
        (base / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))

        # README.txt
        readme_text = (
            "IntentOS Offline Knowledge Package\n"
            "===================================\n\n"
            f"Kit: {kit.name}\n"
            f"Created: {kit.created_at}\n"
            f"Total Size: {kit.total_size_gb:.2f} GB\n\n"
            "Setup:\n"
            "  1. Copy this folder to your target machine.\n"
            "  2. Run: bash install.sh\n"
            "  3. Follow on-screen instructions.\n"
        )
        (base / "README.txt").write_text(readme_text)

        # install.sh stub
        install_script = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'echo "IntentOS Offline Installer"\n'
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
            'echo "Installing from $SCRIPT_DIR ..."\n'
            '# TODO: implement full installation logic\n'
            'echo "Installation complete."\n'
        )
        install_path = base / "install.sh"
        install_path.write_text(install_script)
        install_path.chmod(0o755)

        return base

    # -- Persistence ---------------------------------------------------------

    def save_catalog(self, path: str) -> None:
        """Save the current catalog to a JSON file."""
        data = [item.to_dict() for item in self._catalog.values()]
        Path(path).write_text(json.dumps(data, indent=2))

    def load_catalog(self, path: str) -> None:
        """Load a catalog from a JSON file, replacing the current catalog."""
        data = json.loads(Path(path).read_text())
        self._catalog.clear()
        for entry in data:
            item = ContentItem.from_dict(entry)
            self._catalog[item.name] = item

    def save_kit(self, kit: OfflineKit, path: str) -> None:
        """Save an OfflineKit to a JSON file."""
        Path(path).write_text(json.dumps(kit.to_dict(), indent=2))

    def load_kit(self, path: str) -> OfflineKit:
        """Load an OfflineKit from a JSON file."""
        data = json.loads(Path(path).read_text())
        return OfflineKit.from_dict(data)
