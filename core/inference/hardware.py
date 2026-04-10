"""Hardware detection and AI model recommendation for IntentOS.

Auto-detects GPU, RAM, CPU and recommends the optimal local AI model
for running via Ollama. Inspired by Project NOMAD's hardware auto-detection.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import asdict, dataclass
from typing import Dict, Optional


@dataclass
class GPUInfo:
    """Detected GPU information."""

    vendor: str   # "nvidia", "amd", "apple", "none"
    model: str
    vram_gb: float


@dataclass
class HardwareProfile:
    """Full hardware profile of the host machine."""

    gpu: Optional[GPUInfo]
    ram_gb: float
    cpu_cores: int
    cpu_model: str
    platform: str   # "darwin", "linux", "windows"
    arch: str       # "x86_64", "arm64", etc.

    def to_dict(self) -> Dict:
        d = {
            "gpu": asdict(self.gpu) if self.gpu else None,
            "ram_gb": self.ram_gb,
            "cpu_cores": self.cpu_cores,
            "cpu_model": self.cpu_model,
            "platform": self.platform,
            "arch": self.arch,
        }
        return d


@dataclass
class ModelRecommendation:
    """Recommended local AI model based on hardware."""

    model_name: str
    model_size: str
    estimated_ram_gb: float
    reason: str


class HardwareDetector:
    """Detects host hardware and recommends optimal local AI models."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self) -> HardwareProfile:
        """Run platform-specific detection and return a HardwareProfile."""
        plat = self._detect_platform()
        arch = self._detect_arch()
        gpu = self._detect_gpu(plat, arch)
        ram_gb = self._detect_ram(plat)
        cpu_cores, cpu_model = self._detect_cpu(plat)

        return HardwareProfile(
            gpu=gpu,
            ram_gb=ram_gb,
            cpu_cores=cpu_cores,
            cpu_model=cpu_model,
            platform=plat,
            arch=arch,
        )

    @staticmethod
    def recommend_model(profile: HardwareProfile) -> ModelRecommendation:
        """Return the optimal model recommendation for the given profile."""
        ram = profile.ram_gb
        gpu = profile.gpu

        # Less than 4 GB -- smallest viable model
        if ram < 4:
            return ModelRecommendation(
                model_name="gemma4:e2b",
                model_size="2.3B effective",
                estimated_ram_gb=2.0,
                reason="Low RAM; Gemma 4 E2B gives native function calling in under 2 GB.",
            )

        # 32 GB+ with NVIDIA GPU -- MoE model (only 3.8B active params)
        if ram >= 32 and gpu and gpu.vendor == "nvidia":
            return ModelRecommendation(
                model_name="gemma4:26b-a4b",
                model_size="26B MoE (3.8B active)",
                estimated_ram_gb=16.0,
                reason="High RAM with NVIDIA GPU enables Gemma 4 MoE — GPT-4o class locally.",
            )

        # 16 GB+ with any GPU (including Apple Silicon)
        if ram >= 16 and gpu:
            return ModelRecommendation(
                model_name="gemma4:26b-a4b",
                model_size="26B MoE (3.8B active)",
                estimated_ram_gb=16.0,
                reason="16 GB+ with GPU supports Gemma 4 MoE — GPT-4o class with native tool use.",
            )

        # 8 GB+, no GPU (or <16 GB with GPU)
        if ram >= 8:
            return ModelRecommendation(
                model_name="gemma4:e4b",
                model_size="4.5B effective",
                estimated_ram_gb=4.0,
                reason="8 GB RAM runs Gemma 4 E4B comfortably with native function calling.",
            )

        # 4-8 GB, no GPU
        return ModelRecommendation(
            model_name="gemma4:e2b",
            model_size="2.3B effective",
            estimated_ram_gb=2.0,
            reason="Limited RAM; Gemma 4 E2B gives best quality-per-byte with tool use support.",
        )

    @staticmethod
    def get_ollama_config(profile: HardwareProfile) -> Dict:
        """Return Ollama runtime configuration based on hardware."""
        gpu = profile.gpu

        if gpu and gpu.vendor in ("nvidia", "apple", "amd"):
            num_gpu_layers = -1  # offload all layers
        else:
            num_gpu_layers = 0

        # Scale context window and batch size with available RAM
        ram = profile.ram_gb
        if ram >= 32:
            context_window = 8192
            batch_size = 512
        elif ram >= 16:
            context_window = 4096
            batch_size = 256
        elif ram >= 8:
            context_window = 2048
            batch_size = 128
        else:
            context_window = 1024
            batch_size = 64

        return {
            "num_gpu_layers": num_gpu_layers,
            "context_window": context_window,
            "batch_size": batch_size,
        }

    # ------------------------------------------------------------------
    # Internal detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_sysctl(output: str) -> str:
        """Parse sysctl output, handling both 'key: value' and bare value."""
        text = output.strip()
        if ": " in text:
            return text.split(": ", 1)[1]
        return text

    @staticmethod
    def _detect_platform() -> str:
        return platform.system().lower()  # "darwin", "linux", "windows"

    @staticmethod
    def _detect_arch() -> str:
        return platform.machine()  # "x86_64", "arm64", etc.

    def _detect_gpu(self, plat: str, arch: str) -> Optional[GPUInfo]:
        """Try nvidia-smi, then AMD rocm-smi, then Apple Silicon sysctl."""
        # 1. NVIDIA
        gpu = self._try_nvidia()
        if gpu:
            return gpu

        # 2. Apple Silicon (macOS + arm64)
        if plat == "darwin" and arch == "arm64":
            gpu = self._try_apple_silicon()
            if gpu:
                return gpu

        return None

    def _try_nvidia(self) -> Optional[GPUInfo]:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                line = result.stdout.strip().split("\n")[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    name = parts[0]
                    vram_mib = float(parts[1])
                    return GPUInfo(
                        vendor="nvidia",
                        model=name,
                        vram_gb=round(vram_mib / 1024, 1),
                    )
        except Exception:
            pass
        return None

    def _try_apple_silicon(self) -> Optional[GPUInfo]:
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                cpu_brand = self._parse_sysctl(result.stdout)
                # Only Apple-branded chips have unified GPU memory
                if "Apple" in cpu_brand:
                    # Extract chip name (e.g. "Apple M2 Pro")
                    chip_name = cpu_brand.strip()
                    # Unified memory = system RAM
                    ram_gb = self._detect_ram("darwin")
                    return GPUInfo(
                        vendor="apple",
                        model=chip_name,
                        vram_gb=ram_gb,
                    )
        except Exception:
            pass
        return None

    def _detect_ram(self, plat: str) -> float:
        """Detect total system RAM in GB."""
        try:
            if plat == "darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    return int(self._parse_sysctl(result.stdout)) / (1024 ** 3)
            elif plat == "linux":
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal"):
                            kb = int(line.split()[1])
                            return kb / (1024 ** 2)
        except Exception:
            pass

        # Fallback: use os.sysconf if available
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return (pages * page_size) / (1024 ** 3)
        except (ValueError, OSError, AttributeError):
            pass

        # Last resort default
        return 4.0

    def _detect_cpu(self, plat: str) -> tuple:
        """Return (cpu_cores: int, cpu_model: str)."""
        cores = self._detect_cpu_cores(plat)
        model = self._detect_cpu_model(plat)
        return cores, model

    def _detect_cpu_cores(self, plat: str) -> int:
        try:
            if plat == "darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "hw.logicalcpu"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    return int(self._parse_sysctl(result.stdout))
        except Exception:
            pass

        # Fallback
        try:
            count = os.cpu_count()
            if count:
                return count
        except Exception:
            pass

        return 1  # safe default

    def _detect_cpu_model(self, plat: str) -> str:
        try:
            if plat == "darwin":
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    return self._parse_sysctl(result.stdout)
        except Exception:
            pass

        return platform.processor() or "unknown"
