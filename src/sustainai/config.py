"""SustainAI configuration loader.

Boundary: loads configuration from configs/default.yaml and environment
variables. All tunables live here and are accessed through the typed
SustainAIConfig dataclass. No other module reads config files or env
vars directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


@dataclass
class DataConfig:
    rul_cap: int = 125
    sensor_drop_variance_threshold: float = 1.0e-6
    rolling_window: int = 20


@dataclass
class SplitConfig:
    val_fraction: float = 0.2
    seed: int = 42


@dataclass
class SeverityConfig:
    critical_max: int = 25
    warning_max: int = 60
    watch_max: int = 100


@dataclass
class AgentConfig:
    timeout_seconds: int = 30
    max_output_tokens: int = 1024
    temperature: float = 0.2
    max_retries_on_malformed: int = 1
    max_tool_calls_per_exception: int = 6


@dataclass
class HarnessConfig:
    latency_percentiles: list[int] = field(default_factory=lambda: [50, 95])


@dataclass
class SustainAIConfig:
    """Top-level configuration for the entire SustainAI system."""
    data: DataConfig = field(default_factory=DataConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    severity: SeverityConfig = field(default_factory=SeverityConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    harness: HarnessConfig = field(default_factory=HarnessConfig)

    # Environment variable overrides
    gcp_project: str = ""
    vertex_location: str = "us-central1"
    gemini_model: str = "gemini-2.5-flash"
    agent_mode: str = "stub"
    seed: int = 42


def load_config(config_path: Path | None = None) -> SustainAIConfig:
    """Load configuration from YAML file and environment variables.

    Environment variables override YAML values per TRD Section 3.
    """
    if config_path is None:
        config_path = CONFIG_DIR / "default.yaml"

    cfg = SustainAIConfig()

    if config_path.exists():
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}

        # Data section
        if "data" in raw:
            d = raw["data"]
            cfg.data.rul_cap = d.get("rul_cap", cfg.data.rul_cap)
            cfg.data.sensor_drop_variance_threshold = d.get(
                "sensor_drop_variance_threshold", cfg.data.sensor_drop_variance_threshold
            )
            cfg.data.rolling_window = d.get("rolling_window", cfg.data.rolling_window)

        # Split section
        if "split" in raw:
            s = raw["split"]
            cfg.split.val_fraction = s.get("val_fraction", cfg.split.val_fraction)
            cfg.split.seed = s.get("seed", cfg.split.seed)

        # Severity section
        if "severity" in raw:
            sev = raw["severity"]
            cfg.severity.critical_max = sev.get("critical_max", cfg.severity.critical_max)
            cfg.severity.warning_max = sev.get("warning_max", cfg.severity.warning_max)
            cfg.severity.watch_max = sev.get("watch_max", cfg.severity.watch_max)

        # Agent section
        if "agent" in raw:
            a = raw["agent"]
            cfg.agent.timeout_seconds = a.get("timeout_seconds", cfg.agent.timeout_seconds)
            cfg.agent.max_output_tokens = a.get("max_output_tokens", cfg.agent.max_output_tokens)
            cfg.agent.temperature = a.get("temperature", cfg.agent.temperature)
            cfg.agent.max_retries_on_malformed = a.get("max_retries_on_malformed", cfg.agent.max_retries_on_malformed)
            cfg.agent.max_tool_calls_per_exception = a.get(
                "max_tool_calls_per_exception", cfg.agent.max_tool_calls_per_exception
            )

        # Harness section
        if "harness" in raw:
            h = raw["harness"]
            cfg.harness.latency_percentiles = h.get("latency_percentiles", cfg.harness.latency_percentiles)

    # Environment variable overrides
    cfg.gcp_project = os.environ.get("GCP_PROJECT", cfg.gcp_project)
    cfg.vertex_location = os.environ.get("VERTEX_LOCATION", cfg.vertex_location)
    cfg.gemini_model = os.environ.get("GEMINI_MODEL", cfg.gemini_model)
    cfg.agent_mode = os.environ.get("AGENT_MODE", cfg.agent_mode).lower()
    cfg.seed = int(os.environ.get("SUSTAINAI_SEED", cfg.seed))

    # Seed override from env should also set split seed for consistency
    if "SUSTAINAI_SEED" in os.environ:
        cfg.split.seed = cfg.seed

    return cfg


# Module-level singleton (lazy loaded)
_config: SustainAIConfig | None = None


def get_config() -> SustainAIConfig:
    """Get the global configuration singleton."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset the config singleton (for testing)."""
    global _config
    _config = None
