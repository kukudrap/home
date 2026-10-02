"""Write web/dev/bundle.json, the data bundle the game UI loads during development.

Run from the project root:  PYTHONPATH=src python3 scripts/gen_bundle.py [--vertical pbm|general]
The default is the MITO LIGHT (photobiomodulation) edition; ``--vertical general`` writes the generic edition.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dopamine_king.webdata import build_bundle, bundle_json

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write the development data bundle of the web game.")
    parser.add_argument("--vertical", default="pbm", help="edition to compute: pbm (MITO LIGHT, default) or general")
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "dev" / "bundle.json", help="output file (default: web/dev/bundle.json)")
    args = parser.parse_args(argv)
    vertical = None if args.vertical in ("general", "none", "") else args.vertical
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(bundle_json(build_bundle(vertical=vertical), indent=1), "utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, edition {vertical or 'general'})")


if __name__ == "__main__":
    main()
