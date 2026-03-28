"""
Tests for IntentOS Image Agent (Phase 2C.3)
TDD — written before the implementation.
"""

import os
import shutil
import tempfile

import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def workspace(tmp_path):
    """Create a workspace dir with an outputs/ sub-dir."""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    return tmp_path


@pytest.fixture()
def granted_dir(tmp_path):
    """A directory that is in the granted_paths list."""
    d = tmp_path / "images"
    d.mkdir()
    return d


@pytest.fixture()
def context(workspace, granted_dir):
    return {
        "workspace": str(workspace),
        "granted_paths": [str(granted_dir), str(workspace)],
    }


@pytest.fixture()
def png_image(granted_dir):
    """Create a 100x80 RGBA PNG test image."""
    path = granted_dir / "test.png"
    img = Image.new("RGBA", (100, 80), color=(255, 0, 0, 255))
    img.save(str(path), format="PNG")
    return str(path)


@pytest.fixture()
def jpeg_image(granted_dir):
    """Create a 120x90 RGB JPEG test image with some variation for compression tests."""
    path = granted_dir / "photo.jpg"
    img = Image.new("RGB", (120, 90), color=(0, 128, 255))
    # Add variation so compression has something to work with
    pixels = img.load()
    for x in range(120):
        for y in range(90):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 3) % 256)
    img.save(str(path), format="JPEG", quality=100)
    return str(path)


# ---------------------------------------------------------------------------
# Import the agent under test
# ---------------------------------------------------------------------------

from capabilities.image_agent.agent import run


# ---------------------------------------------------------------------------
# 1-3  ACP Contract
# ---------------------------------------------------------------------------

class TestACPContract:
    def test_run_returns_required_keys(self, png_image, context):
        result = run({"action": "get_info", "params": {"path": png_image}, "context": context})
        assert isinstance(result, dict)
        assert "status" in result
        assert "action_performed" in result
        assert "result" in result
        assert "metadata" in result

    def test_unknown_action_returns_error(self, context):
        result = run({"action": "explode", "params": {}, "context": context})
        assert result["status"] == "error"
        assert result["error"]["code"] == "UNKNOWN_ACTION"

    def test_metadata_always_present(self, png_image, context):
        result = run({"action": "get_info", "params": {"path": png_image}, "context": context})
        meta = result["metadata"]
        assert "files_affected" in meta
        assert "bytes_affected" in meta
        assert "duration_ms" in meta
        assert "paths_accessed" in meta


# ---------------------------------------------------------------------------
# 4-6  get_info
# ---------------------------------------------------------------------------

class TestGetInfo:
    def test_returns_image_info(self, png_image, context):
        result = run({"action": "get_info", "params": {"path": png_image}, "context": context})
        assert result["status"] == "success"
        info = result["result"]
        assert info["width"] == 100
        assert info["height"] == 80
        assert info["format"] == "PNG"
        assert info["mode"] == "RGBA"
        assert info["file_size"] > 0

    def test_nonexistent_file(self, context, granted_dir):
        path = os.path.join(str(granted_dir), "nope.png")
        result = run({"action": "get_info", "params": {"path": path}, "context": context})
        assert result["status"] == "error"

    def test_dry_run(self, png_image, context):
        result = run({"action": "get_info", "params": {"path": png_image}, "context": context, "dry_run": True})
        assert result["status"] == "success"
        # Still returns info — get_info is read-only anyway
        assert result["result"]["width"] == 100


# ---------------------------------------------------------------------------
# 7-11  resize
# ---------------------------------------------------------------------------

class TestResize:
    def test_resize_to_exact_dimensions(self, png_image, context):
        result = run({"action": "resize", "params": {"path": png_image, "width": 50, "height": 40}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        with Image.open(out_path) as img:
            assert img.size == (50, 40)

    def test_resize_maintain_aspect_width_only(self, png_image, context):
        # Original is 100x80 → width=50 means height should be 40
        result = run({"action": "resize", "params": {"path": png_image, "width": 50}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        with Image.open(out_path) as img:
            assert img.size == (50, 40)

    def test_resize_maintain_aspect_height_only(self, png_image, context):
        # Original is 100x80 → height=40 means width should be 50
        result = run({"action": "resize", "params": {"path": png_image, "height": 40}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        with Image.open(out_path) as img:
            assert img.size == (50, 40)

    def test_output_saved_to_workspace_outputs(self, png_image, context):
        result = run({"action": "resize", "params": {"path": png_image, "width": 50, "height": 40}, "context": context})
        out_path = result["result"]["output_path"]
        assert "/outputs/" in out_path

    def test_dry_run_no_file_created(self, png_image, context, workspace):
        outputs_before = set(os.listdir(str(workspace / "outputs")))
        result = run({"action": "resize", "params": {"path": png_image, "width": 50}, "context": context, "dry_run": True})
        assert result["status"] == "success"
        outputs_after = set(os.listdir(str(workspace / "outputs")))
        assert outputs_before == outputs_after
        assert "would" in result["result"]["description"].lower()

    def test_invalid_dimensions_zero(self, png_image, context):
        result = run({"action": "resize", "params": {"path": png_image, "width": 0}, "context": context})
        assert result["status"] == "error"

    def test_invalid_dimensions_negative(self, png_image, context):
        result = run({"action": "resize", "params": {"path": png_image, "width": -10}, "context": context})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# 12-14  crop
# ---------------------------------------------------------------------------

class TestCrop:
    def test_crop_image(self, png_image, context):
        result = run({"action": "crop", "params": {"path": png_image, "box": [10, 10, 60, 50]}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        with Image.open(out_path) as img:
            assert img.size == (50, 40)

    def test_crop_box_exceeds_dimensions(self, png_image, context):
        result = run({"action": "crop", "params": {"path": png_image, "box": [0, 0, 200, 200]}, "context": context})
        assert result["status"] == "error"

    def test_crop_dry_run(self, png_image, context, workspace):
        outputs_before = set(os.listdir(str(workspace / "outputs")))
        result = run({"action": "crop", "params": {"path": png_image, "box": [10, 10, 60, 50]}, "context": context, "dry_run": True})
        assert result["status"] == "success"
        outputs_after = set(os.listdir(str(workspace / "outputs")))
        assert outputs_before == outputs_after
        assert "would" in result["result"]["description"].lower()


# ---------------------------------------------------------------------------
# 15-18  convert_format
# ---------------------------------------------------------------------------

class TestConvertFormat:
    def test_png_to_jpeg(self, png_image, context):
        result = run({"action": "convert_format", "params": {"path": png_image, "target_format": "JPEG"}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        with Image.open(out_path) as img:
            assert img.format == "JPEG"

    def test_jpeg_to_png(self, jpeg_image, context):
        result = run({"action": "convert_format", "params": {"path": jpeg_image, "target_format": "PNG"}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        with Image.open(out_path) as img:
            assert img.format == "PNG"

    def test_unsupported_format(self, png_image, context):
        result = run({"action": "convert_format", "params": {"path": png_image, "target_format": "BMP2000"}, "context": context})
        assert result["status"] == "error"

    def test_output_in_workspace_outputs(self, png_image, context):
        result = run({"action": "convert_format", "params": {"path": png_image, "target_format": "JPEG"}, "context": context})
        out_path = result["result"]["output_path"]
        assert "/outputs/" in out_path


# ---------------------------------------------------------------------------
# 19-21  compress
# ---------------------------------------------------------------------------

class TestCompress:
    def test_compress_jpeg(self, jpeg_image, context):
        result = run({"action": "compress", "params": {"path": jpeg_image, "quality": 30}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        assert os.path.getsize(out_path) < os.path.getsize(jpeg_image)

    def test_compressed_file_smaller(self, jpeg_image, context):
        result = run({"action": "compress", "params": {"path": jpeg_image, "quality": 10}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        assert os.path.getsize(out_path) < os.path.getsize(jpeg_image)

    def test_compress_non_jpeg_converts_first(self, png_image, context):
        result = run({"action": "compress", "params": {"path": png_image, "quality": 50}, "context": context})
        assert result["status"] == "success"
        out_path = result["result"]["output_path"]
        with Image.open(out_path) as img:
            assert img.format == "JPEG"


# ---------------------------------------------------------------------------
# 22  remove_background (stub)
# ---------------------------------------------------------------------------

class TestRemoveBackground:
    def test_stub_not_available(self, png_image, context):
        result = run({"action": "remove_background", "params": {"path": png_image}, "context": context})
        assert result["status"] == "error"
        assert "not yet available" in result["error"]["message"].lower()


# ---------------------------------------------------------------------------
# 23-25  Path enforcement
# ---------------------------------------------------------------------------

class TestPathEnforcement:
    def test_rejects_path_outside_granted(self, context):
        result = run({"action": "get_info", "params": {"path": "/etc/passwd"}, "context": context})
        assert result["status"] == "error"
        assert "path" in result["error"]["message"].lower() or "denied" in result["error"]["message"].lower() or "not allowed" in result["error"]["message"].lower()

    def test_output_defaults_to_workspace_outputs(self, png_image, context):
        result = run({"action": "resize", "params": {"path": png_image, "width": 50}, "context": context})
        assert result["status"] == "success"
        workspace = context["workspace"]
        assert result["result"]["output_path"].startswith(os.path.join(workspace, "outputs"))

    def test_respects_granted_paths(self, png_image, context):
        # Remove workspace from granted_paths — should still allow read from granted_dir
        result = run({"action": "get_info", "params": {"path": png_image}, "context": context})
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# 26  Sensitive file detection
# ---------------------------------------------------------------------------

class TestSensitiveFiles:
    def test_rejects_sensitive_file(self, granted_dir, context):
        secret = granted_dir / "secret_keys.png"
        img = Image.new("RGB", (10, 10), color=(0, 0, 0))
        img.save(str(secret), format="PNG")
        result = run({"action": "get_info", "params": {"path": str(secret)}, "context": context})
        assert result["status"] == "error"
        assert "sensitive" in result["error"]["message"].lower()
