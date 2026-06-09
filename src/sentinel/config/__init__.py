"""Sentinel runtime configuration (SENTINEL-001).

Single source of truth for backends, per-agent model, prompts, and generation parameters.
The agent builders read this instead of hardcoding values.
"""

from sentinel.config.schema import (
    AgentConfig,
    BackendConfig,
    BackendOption,
    GenerationConfig,
    GovernanceConfig,
    MemoryConfig,
    PriorityConfig,
    PromptTemplate,
    ResearchConfig,
    SearchConfig,
    SentinelConfig,
)
from sentinel.config.store import (
    config_path,
    get_config,
    load_config,
    reset_config,
    save_config,
    set_config,
)

__all__ = [
    "SentinelConfig", "AgentConfig", "BackendConfig", "BackendOption", "GenerationConfig",
    "PromptTemplate", "MemoryConfig", "GovernanceConfig", "SearchConfig", "PriorityConfig",
    "ResearchConfig",
    "get_config", "set_config", "reset_config", "load_config", "save_config", "config_path",
]
