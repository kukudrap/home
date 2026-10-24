"""Write web/dev/bundle.json, the data bundle the game UI loads during development.

Run from the project root:  PYTHONPATH=src python3 scripts/gen_bundle.py [--synthetic] [--vertical pbm|general]
The default is the REAL edition: the newest stored radar snapshot, the verified evidence ledger and the brand file, nothing simulated.
``--synthetic`` writes the old demo edition on the simulated corpus (``--vertical general`` for its generic variant).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dopamine_king.webdata import build_bundle, bundle_json

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write the development data bundle of the web game.")
    parser.add_argument("--synthetic", action="store_true", help="write the demo edition on the simulated corpus instead of the real one")
    parser.add_argument("--vertical", default="pbm", help="edition to compute: pbm (MITO LIGHT, default) or general (with --synthetic)")
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "dev" / "bundle.json", help="output file (default: web/dev/bundle.json)")
    args = parser.parse_args(argv)
    vertical = None if args.vertical in ("general", "none", "") else args.vertical
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.synthetic:
        out.write_text(bundle_json(build_bundle(vertical=vertical), indent=1), "utf-8")
        print(f"wrote {out} ({out.stat().st_size // 1024} KB, simulated edition {vertical or 'general'})")
        return
    from dopamine_king.radar.realbundle import build_real_bundle
    folders = sorted(p for p in (ROOT / "radar" / "snapshots").glob("*") if (p / "snapshot.json").is_file())
    if not folders:
        raise SystemExit("no radar snapshot in radar/snapshots: run kingctl radar collect, or use --synthetic")
    snap = folders[-1]
    bundle = build_real_bundle(snap, ROOT / "radar" / "drafts" / snap.name, ROOT / "radar" / "plan.json", vertical=vertical or "pbm")
    out.write_text(bundle_json(bundle, indent=1), "utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, real edition from {snap.name})")


if __name__ == "__main__":
    main()
