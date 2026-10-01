"""Write web/dev/bundle.json, the data bundle the game UI loads during development.

Run from the project root:  PYTHONPATH=src python3 scripts/gen_bundle.py
"""
from __future__ import annotations

from pathlib import Path

from dopamine_king.webdata import build_bundle, bundle_json

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    out = ROOT / "web" / "dev" / "bundle.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(bundle_json(build_bundle(), indent=1), "utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
