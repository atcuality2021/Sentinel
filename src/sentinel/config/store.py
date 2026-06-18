"""Config persistence — YAML on disk, cached process-level accessor.

`get_config()` is the runtime entry point: it reads the file once and caches it. `load_config`
self-seeds a default file when absent (spec AC-3). The file holds no secrets (keys stay in env).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from sentinel.config.schema import SentinelConfig

_DEFAULT_FILENAME = "sentinel.config.yaml"
_cache: SentinelConfig | None = None


def config_path() -> Path:
    return Path(os.getenv("SENTINEL_CONFIG_PATH", _DEFAULT_FILENAME))


def save_config(cfg: SentinelConfig, path: str | Path | None = None) -> Path:
    p = Path(path) if path else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(cfg.model_dump(), sort_keys=False, allow_unicode=True), "utf-8")
    return p


def _backfill_defaults(cfg: SentinelConfig) -> SentinelConfig:
    """Merge any default agent/prompt keys missing from a loaded config (SENTINEL-008.1).

    A config written before a feature shipped (e.g. a pre-008 file with no ``*.extractor`` agents
    or prompts) would ``KeyError`` the moment that feature is enabled. Back-filling the shipped
    defaults for *missing* keys only — never overwriting an admin's edits — keeps an old config
    forward-compatible without a manual migration. New keys inherit the default (dark) behaviour.

    ``role`` and ``pin_gemini`` are structural metadata (capability tier and cloud-pin — set by
    the canonical defaults, not by the admin). They are always synced from the shipped defaults so
    that a YAML written before role-tiering existed gets the correct tier without a manual migration.
    The user-editable fields (``enabled``, ``model``, ``generation``) are never touched here.
    """
    d = SentinelConfig.default()
    for key, ac in d.agents.items():
        if key not in cfg.agents:
            cfg.agents[key] = ac
        else:
            # Sync role (structural capability tier — never user-editable, set by defaults only).
            # pin_gemini and all other fields are user-editable and must not be overwritten.
            existing = cfg.agents[key]
            if existing.role != ac.role:
                cfg.agents[key] = existing.model_copy(update={"role": ac.role})
    for key, tmpl in d.prompts.items():
        cfg.prompts.setdefault(key, tmpl)
    # New shipped MCP servers appear without a manual migration; user edits
    # (enabled, domains, tool_filter) on existing entries are never touched.
    for key, server in d.mcp_servers.items():
        cfg.mcp_servers.setdefault(key, server)
    return cfg


def _apply_env_overrides(cfg: SentinelConfig) -> SentinelConfig:
    """Apply env-var overrides on top of whatever the YAML says (env is authoritative).

    Env vars win over YAML values — the YAML holds structure/shape; the env holds
    deployment-specific URLs and keys. This means operators never need to edit the
    YAML to point at a different vLLM host; they only set env vars.

    Supported overrides:
      GEMMA_12B_API_BASE  → backend.vllm.api_base
      GEMMA_26B_API_BASE  → backend.roles.*.api_base (all tiered roles)
    """
    api_12b = os.getenv("GEMMA_12B_API_BASE", "").strip()
    api_26b = os.getenv("GEMMA_26B_API_BASE", "").strip()

    if api_12b and cfg.backend.vllm is not None:
        cfg.backend.vllm = cfg.backend.vllm.model_copy(update={"api_base": api_12b})

    if api_26b and cfg.backend.roles:
        cfg.backend.roles = {
            role: rc.model_copy(update={"api_base": api_26b})
            for role, rc in cfg.backend.roles.items()
        }

    return cfg


def load_config(path: str | Path | None = None, *, write_if_absent: bool = True) -> SentinelConfig:
    """Load config from YAML. If absent, build defaults and (optionally) seed the file once."""
    p = Path(path) if path else config_path()
    if p.exists():
        data = yaml.safe_load(p.read_text("utf-8")) or {}
        return _apply_env_overrides(_backfill_defaults(SentinelConfig.model_validate(data)))
    cfg = _apply_env_overrides(SentinelConfig.default())
    if write_if_absent:
        save_config(cfg, p)
    return cfg


def get_config() -> SentinelConfig:
    """Cached config for the running process (read/seed once)."""
    global _cache
    if _cache is None:
        try:
            _cache = load_config()
        except Exception:  # never let a bad config file break agent construction
            _cache = SentinelConfig.default()
    return _cache


def set_config(cfg: SentinelConfig, *, persist: bool = False) -> None:
    """Replace the cached config (used by the Settings UI and tests)."""
    global _cache
    _cache = cfg
    if persist:
        save_config(cfg)


def reset_config() -> None:
    """Clear the cache so the next get_config() re-reads (tests)."""
    global _cache
    _cache = None
