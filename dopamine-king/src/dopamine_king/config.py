"""Runtime configuration: paths and identity, all overridable by environment."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_USER_AGENT = (
    "DopamineKing/0.1 (+https://github.com/kukudrap/home; research crawler; "
    "honours robots.txt and TDM reservations)"
)


def home_dir() -> Path:
    """Working directory for the database, caches and ledgers (KING_HOME)."""
    path = Path(os.environ.get("KING_HOME", ".king")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return Path(os.environ.get("KING_DB", str(home_dir() / "king.sqlite")))


def cache_dir() -> Path:
    path = Path(os.environ.get("KING_CACHE", str(home_dir() / "http-cache")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_agent() -> str:
    """Crawler identity. Set KING_CONTACT to an email or URL so site owners can reach you."""
    contact = os.environ.get("KING_CONTACT")
    base = os.environ.get("KING_USER_AGENT", DEFAULT_USER_AGENT)
    return f"{base} contact:{contact}" if contact else base


def anthropic_model(tier: str = "balanced") -> str:
    """Model ids per quality tier. KING_MODEL overrides the default (balanced) tier."""
    tiers = {
        "premium": "claude-fable-5-1",
        "balanced": "claude-opus-5-5",
        "economy": "claude-sonnet-5-5",
        "fast": "claude-haiku-4-5",
    }
    if tier == "balanced" and os.environ.get("KING_MODEL"):
        return os.environ["KING_MODEL"]
    return tiers.get(tier, tiers["balanced"])
