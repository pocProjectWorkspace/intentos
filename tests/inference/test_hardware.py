"""Tests for core.inference.hardware — Hardware detection and model recommendation."""

import platform
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from core.inference.hardware import (
    GPUInfo,
    HardwareDetector,
    HardwareProfile,
    ModelRecommendation,
)


# ---------------------------------------------------------------------------
# GPUInfo model
# ---------------------------------------------------------------------------

class TestGPUInfo:
    """Tests 1-2: GPUInfo dataclass fields and vendor validation."""

    def test_gpu_info_has_required_fields(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX 4090", vram_gb=24.0)
        assert gpu.vendor == "nvidia"
        assert gpu.model == "RTX 4090"
        assert gpu.vram_gb == 24.0

    @pytest.mark.parametrize("vendor", ["nvidia", "amd", "apple", "none"])
    def test_gpu_vendor_valid_values(self, vendor):
        gpu = GPUInfo(vendor=vendor, model="test", vram_gb=0.0)
        assert gpu.vendor == vendor


# ---------------------------------------------------------------------------
# HardwareProfile model
# ---------------------------------------------------------------------------

class TestHardwareProfile:
    """Tests 3-4: HardwareProfile dataclass and serialization."""

    def test_hardware_profile_has_required_fields(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX 4090", vram_gb=24.0)
        profile = HardwareProfile(
            gpu=gpu,
            ram_gb=32.0,
            cpu_cores=16,
            cpu_model="Intel i9-13900K",
            platform="linux",
            arch="x86_64",
        )
        assert profile.gpu is gpu
        assert profile.ram_gb == 32.0
        assert profile.cpu_cores == 16
        assert profile.cpu_model == "Intel i9-13900K"
        assert profile.platform == "linux"
        assert profile.arch == "x86_64"

    def test_hardware_profile_gpu_can_be_none(self):
        profile = HardwareProfile(
            gpu=None, ram_gb=8.0, cpu_cores=4,
            cpu_model="Intel i5", platform="linux", arch="x86_64",
        )
        assert profile.gpu is None

    def test_hardware_profile_to_dict(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX 3080", vram_gb=10.0)
        profile = HardwareProfile(
            gpu=gpu, ram_gb=16.0, cpu_cores=8,
            cpu_model="AMD Ryzen 7", platform="linux", arch="x86_64",
        )
        d = profile.to_dict()
        assert isinstance(d, dict)
        assert d["ram_gb"] == 16.0
        assert d["cpu_cores"] == 8
        assert d["cpu_model"] == "AMD Ryzen 7"
        assert d["platform"] == "linux"
        assert d["arch"] == "x86_64"
        assert d["gpu"]["vendor"] == "nvidia"
        assert d["gpu"]["model"] == "RTX 3080"
        assert d["gpu"]["vram_gb"] == 10.0

    def test_hardware_profile_to_dict_gpu_none(self):
        profile = HardwareProfile(
            gpu=None, ram_gb=8.0, cpu_cores=4,
            cpu_model="i5", platform="darwin", arch="arm64",
        )
        d = profile.to_dict()
        assert d["gpu"] is None


# ---------------------------------------------------------------------------
# HardwareDetector — detect()
# ---------------------------------------------------------------------------

class TestHardwareDetectorDetect:
    """Tests 5-11: detect() returns HardwareProfile with correct values."""

    def _make_detector(self):
        return HardwareDetector()

    @patch("core.inference.hardware.subprocess.run")
    @patch("core.inference.hardware.platform")
    def test_detect_returns_hardware_profile(self, mock_platform, mock_run):
        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "x86_64"
        mock_platform.processor.return_value = "x86_64"
        mock_run.side_effect = FileNotFoundError  # no GPU tools
        detector = self._make_detector()
        profile = detector.detect()
        assert isinstance(profile, HardwareProfile)

    @patch("core.inference.hardware.subprocess.run")
    @patch("core.inference.hardware.platform")
    def test_detect_macos_apple_silicon(self, mock_platform, mock_run):
        """On macOS ARM64 (Apple Silicon), detect apple GPU via sysctl."""
        mock_platform.system.return_value = "Darwin"
        mock_platform.machine.return_value = "arm64"
        mock_platform.processor.return_value = "arm"

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if cmd[0] == "nvidia-smi":
                raise FileNotFoundError
            elif cmd[0] == "sysctl":
                if "machdep.cpu.brand_string" in cmd:
                    result.stdout = "machdep.cpu.brand_string: Apple M2 Pro"
                elif "hw.memsize" in cmd:
                    result.stdout = f"hw.memsize: {16 * 1024**3}"
                elif "hw.perflevel0.logicalcpu" in cmd:
                    result.stdout = "hw.perflevel0.logicalcpu: 10"
                elif "hw.logicalcpu" in cmd:
                    result.stdout = "hw.logicalcpu: 10"
                else:
                    result.stdout = ""
                return result
            raise FileNotFoundError

        mock_run.side_effect = run_side_effect
        detector = self._make_detector()
        profile = detector.detect()
        assert profile.gpu is not None
        assert profile.gpu.vendor == "apple"
        assert "M2" in profile.gpu.model or "Apple" in profile.gpu.model

    @patch("core.inference.hardware.subprocess.run")
    @patch("core.inference.hardware.platform")
    def test_detect_macos_intel_no_gpu(self, mock_platform, mock_run):
        """On macOS x86_64 (Intel Mac), gpu should be None."""
        mock_platform.system.return_value = "Darwin"
        mock_platform.machine.return_value = "x86_64"
        mock_platform.processor.return_value = "i386"

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if cmd[0] == "nvidia-smi":
                raise FileNotFoundError
            elif cmd[0] == "sysctl":
                if "machdep.cpu.brand_string" in cmd:
                    result.stdout = "machdep.cpu.brand_string: Intel(R) Core(TM) i7-9750H"
                elif "hw.memsize" in cmd:
                    result.stdout = f"hw.memsize: {16 * 1024**3}"
                elif "hw.logicalcpu" in cmd:
                    result.stdout = "hw.logicalcpu: 12"
                else:
                    result.stdout = ""
                return result
            raise FileNotFoundError

        mock_run.side_effect = run_side_effect
        detector = self._make_detector()
        profile = detector.detect()
        assert profile.gpu is None

    @patch("core.inference.hardware.subprocess.run")
    @patch("core.inference.hardware.platform")
    def test_ram_detection_macos(self, mock_platform, mock_run):
        """RAM detection via sysctl hw.memsize returns correct value."""
        mock_platform.system.return_value = "Darwin"
        mock_platform.machine.return_value = "x86_64"
        mock_platform.processor.return_value = "i386"
        ram_bytes = 32 * 1024**3  # 32 GB

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if cmd[0] == "nvidia-smi":
                raise FileNotFoundError
            elif cmd[0] == "sysctl":
                if "hw.memsize" in cmd:
                    result.stdout = f"hw.memsize: {ram_bytes}"
                elif "machdep.cpu.brand_string" in cmd:
                    result.stdout = "machdep.cpu.brand_string: Intel Core i5"
                elif "hw.logicalcpu" in cmd:
                    result.stdout = "hw.logicalcpu: 8"
                else:
                    result.stdout = ""
                return result
            raise FileNotFoundError

        mock_run.side_effect = run_side_effect
        detector = self._make_detector()
        profile = detector.detect()
        assert profile.ram_gb == pytest.approx(32.0, abs=0.5)

    @patch("core.inference.hardware.subprocess.run")
    @patch("core.inference.hardware.platform")
    def test_cpu_cores_detected(self, mock_platform, mock_run):
        mock_platform.system.return_value = "Darwin"
        mock_platform.machine.return_value = "x86_64"
        mock_platform.processor.return_value = "i386"

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if cmd[0] == "nvidia-smi":
                raise FileNotFoundError
            elif cmd[0] == "sysctl":
                if "hw.logicalcpu" in cmd:
                    result.stdout = "hw.logicalcpu: 12"
                elif "hw.memsize" in cmd:
                    result.stdout = f"hw.memsize: {8 * 1024**3}"
                elif "machdep.cpu.brand_string" in cmd:
                    result.stdout = "machdep.cpu.brand_string: Intel i7"
                else:
                    result.stdout = ""
                return result
            raise FileNotFoundError

        mock_run.side_effect = run_side_effect
        detector = self._make_detector()
        profile = detector.detect()
        assert profile.cpu_cores == 12

    @patch("core.inference.hardware.subprocess.run")
    @patch("core.inference.hardware.platform")
    def test_platform_detected(self, mock_platform, mock_run):
        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "x86_64"
        mock_platform.processor.return_value = "x86_64"
        mock_run.side_effect = FileNotFoundError
        detector = self._make_detector()
        profile = detector.detect()
        assert profile.platform == "linux"

    @patch("core.inference.hardware.subprocess.run")
    @patch("core.inference.hardware.platform")
    def test_arch_detected(self, mock_platform, mock_run):
        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "arm64"
        mock_platform.processor.return_value = "aarch64"
        mock_run.side_effect = FileNotFoundError
        detector = self._make_detector()
        profile = detector.detect()
        assert profile.arch == "arm64"


# ---------------------------------------------------------------------------
# NVIDIA GPU detection
# ---------------------------------------------------------------------------

class TestNvidiaDetection:
    """Tests 12-13: nvidia-smi parsing."""

    @patch("core.inference.hardware.platform")
    @patch("core.inference.hardware.subprocess.run")
    def test_nvidia_smi_success(self, mock_run, mock_platform):
        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "x86_64"
        mock_platform.processor.return_value = "x86_64"

        nvidia_output = "NVIDIA GeForce RTX 4090, 24564"

        def run_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd[0] == "nvidia-smi":
                result.returncode = 0
                result.stdout = nvidia_output
                return result
            raise FileNotFoundError

        mock_run.side_effect = run_side_effect
        detector = HardwareDetector()
        profile = detector.detect()
        assert profile.gpu is not None
        assert profile.gpu.vendor == "nvidia"
        assert "RTX 4090" in profile.gpu.model or "4090" in profile.gpu.model
        assert profile.gpu.vram_gb == pytest.approx(24.0, abs=1.0)

    @patch("core.inference.hardware.platform")
    @patch("core.inference.hardware.subprocess.run")
    def test_nvidia_smi_not_installed(self, mock_run, mock_platform):
        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "x86_64"
        mock_platform.processor.return_value = "x86_64"
        mock_run.side_effect = FileNotFoundError
        detector = HardwareDetector()
        profile = detector.detect()
        assert profile.gpu is None


# ---------------------------------------------------------------------------
# Model recommendation
# ---------------------------------------------------------------------------

class TestModelRecommendation:
    """Tests 14-21: recommend_model returns correct model for hardware."""

    def _make_profile(self, ram_gb, gpu=None, arch="x86_64"):
        return HardwareProfile(
            gpu=gpu, ram_gb=ram_gb, cpu_cores=8,
            cpu_model="test", platform="linux", arch=arch,
        )

    def test_recommend_returns_model_recommendation(self):
        profile = self._make_profile(8.0)
        rec = HardwareDetector.recommend_model(profile)
        assert isinstance(rec, ModelRecommendation)
        assert hasattr(rec, "model_name")
        assert hasattr(rec, "model_size")
        assert hasattr(rec, "estimated_ram_gb")
        assert hasattr(rec, "reason")

    def test_4gb_no_gpu_gemma4_e2b(self):
        profile = self._make_profile(4.0)
        rec = HardwareDetector.recommend_model(profile)
        assert rec.model_name == "gemma4:e2b"

    def test_8gb_no_gpu_gemma4_e4b(self):
        profile = self._make_profile(8.0)
        rec = HardwareDetector.recommend_model(profile)
        assert rec.model_name == "gemma4:e4b"

    def test_16gb_any_gpu_gemma4_moe(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX 3060", vram_gb=12.0)
        profile = self._make_profile(16.0, gpu=gpu)
        rec = HardwareDetector.recommend_model(profile)
        assert rec.model_name == "gemma4:26b-a4b"

    def test_32gb_nvidia_gpu_gemma4_moe(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX 4090", vram_gb=24.0)
        profile = self._make_profile(32.0, gpu=gpu)
        rec = HardwareDetector.recommend_model(profile)
        assert rec.model_name == "gemma4:26b-a4b"

    def test_apple_silicon_16gb_gemma4_moe(self):
        gpu = GPUInfo(vendor="apple", model="Apple M2 Pro", vram_gb=16.0)
        profile = HardwareProfile(
            gpu=gpu, ram_gb=16.0, cpu_cores=10,
            cpu_model="Apple M2 Pro", platform="darwin", arch="arm64",
        )
        rec = HardwareDetector.recommend_model(profile)
        assert rec.model_name == "gemma4:26b-a4b"

    def test_less_than_4gb_smallest_model(self):
        profile = self._make_profile(2.0)
        rec = HardwareDetector.recommend_model(profile)
        assert rec.model_name == "gemma4:e2b"


# ---------------------------------------------------------------------------
# Ollama configuration
# ---------------------------------------------------------------------------

class TestOllamaConfig:
    """Tests 22-25: get_ollama_config returns correct settings."""

    def _make_profile(self, gpu=None):
        return HardwareProfile(
            gpu=gpu, ram_gb=16.0, cpu_cores=8,
            cpu_model="test", platform="linux", arch="x86_64",
        )

    def test_ollama_config_returns_dict(self):
        profile = self._make_profile()
        cfg = HardwareDetector.get_ollama_config(profile)
        assert isinstance(cfg, dict)
        assert "num_gpu_layers" in cfg
        assert "context_window" in cfg
        assert "batch_size" in cfg

    def test_no_gpu_zero_layers(self):
        profile = self._make_profile(gpu=None)
        cfg = HardwareDetector.get_ollama_config(profile)
        assert cfg["num_gpu_layers"] == 0

    def test_nvidia_gpu_all_layers(self):
        gpu = GPUInfo(vendor="nvidia", model="RTX 4090", vram_gb=24.0)
        profile = self._make_profile(gpu=gpu)
        cfg = HardwareDetector.get_ollama_config(profile)
        assert cfg["num_gpu_layers"] == -1

    def test_apple_silicon_all_layers(self):
        gpu = GPUInfo(vendor="apple", model="Apple M2", vram_gb=16.0)
        profile = self._make_profile(gpu=gpu)
        cfg = HardwareDetector.get_ollama_config(profile)
        assert cfg["num_gpu_layers"] == -1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests 26-27: graceful degradation on failures."""

    @patch("core.inference.hardware.platform")
    @patch("core.inference.hardware.subprocess.run")
    def test_all_subprocess_calls_fail(self, mock_run, mock_platform):
        """All subprocess calls fail — returns sensible defaults."""
        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "x86_64"
        mock_platform.processor.return_value = "x86_64"
        mock_run.side_effect = Exception("everything is broken")
        detector = HardwareDetector()
        profile = detector.detect()
        assert isinstance(profile, HardwareProfile)
        assert profile.gpu is None
        assert profile.ram_gb > 0
        assert profile.cpu_cores > 0

    @patch("core.inference.hardware.platform")
    @patch("core.inference.hardware.subprocess.run")
    def test_partial_failure_gpu_fails_ram_succeeds(self, mock_run, mock_platform):
        """GPU detection fails but RAM/CPU succeed."""
        mock_platform.system.return_value = "Darwin"
        mock_platform.machine.return_value = "arm64"
        mock_platform.processor.return_value = "arm"

        call_count = 0

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "nvidia-smi":
                raise FileNotFoundError
            result = MagicMock()
            result.returncode = 0
            if cmd[0] == "sysctl":
                if "machdep.cpu.brand_string" in cmd:
                    # Make it fail for GPU detection by raising for chip info
                    raise subprocess.SubprocessError("GPU sysctl failed")
                elif "hw.memsize" in cmd:
                    result.stdout = f"hw.memsize: {16 * 1024**3}"
                    return result
                elif "hw.logicalcpu" in cmd:
                    result.stdout = "hw.logicalcpu: 8"
                    return result
                else:
                    result.stdout = ""
                    return result
            raise FileNotFoundError

        mock_run.side_effect = run_side_effect
        detector = HardwareDetector()
        profile = detector.detect()
        assert isinstance(profile, HardwareProfile)
        # RAM should still be detected
        assert profile.ram_gb == pytest.approx(16.0, abs=0.5)
