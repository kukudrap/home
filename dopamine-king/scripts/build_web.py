"""Build the playable web game into ONE self-contained HTML file.

    python3 scripts/build_web.py [--bundle web/dev/bundle.json] [--out web/dist/dopamine-king.html]
                                 [--forge web/dev/mock-forge.json --guru web/dev/mock-guru.json]
                                 [--vertical pbm|general]

The script reads ``web/src/index.template.html``, inlines ``styles.css`` and the JavaScript files in
dependency order, and embeds the data bundle as ``<script id="dk-bundle" type="application/json">``.
Without ``--bundle`` the bundle is computed by ``dopamine_king.webdata.build_bundle()`` together with the
shipped seed evidence ledger (so the Vault shows studies and tactics). ``--forge`` and
``--guru`` inject a sample Pack and Plan when the bundle has none; when they are not given, the development
samples ``web/dev/mock-forge.json`` and ``web/dev/mock-guru.json`` are used (``--no-samples`` turns that off),
so the Forge and Guru views are never empty in the offline file. The edition is chosen with ``--vertical``: ``pbm``
(the default) is the MITO LIGHT edition with the claims map, the claims checker rules and the claims profile samples;
``general`` is the generic edition without them. Standard library only.

The result must work from file:// with no network, so the build verifies that the output has no external
URLs in markup or CSS, no em or en dash, and stays below 2 MB.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "src"
DEFAULT_OUT = ROOT / "web" / "dist" / "dopamine-king.html"
DEV_FORGE = ROOT / "web" / "dev" / "mock-forge.json"
DEV_GURU = ROOT / "web" / "dev" / "mock-guru.json"

# Dependency order: logic modules first, then the UI toolkit, then views, then the bootstrap.
JS_ORDER = [
    "scoring.js", "labstats.js", "claims.js", "game.js", "i18n.js", "store.js",
    "ui/dom.js", "ui/icons.js", "ui/charts.js", "ui/widgets.js", "ui/claimsui.js", "ui/fx.js", "ui/shell.js",
    "ui/home.js", "ui/arena.js", "ui/boss.js", "ui/lab.js", "ui/vault.js", "ui/forge.js", "ui/guru.js", "ui/about.js",
    "app.js",
]
TEMPLATE = "index.template.html"
STYLES = "styles.css"
PLACEHOLDERS = {"styles": "/*@@STYLES@@*/", "bundle": "/*@@BUNDLE@@*/", "scripts": "/*@@SCRIPTS@@*/"}
REQUIRED_BUNDLE_KEYS = ("spec", "benchmarks", "arena", "bosses", "myths", "lab", "loot")
MAX_BYTES = 2_000_000

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


class BuildError(RuntimeError):
    """A problem the person running the build can fix; printed without a traceback."""


# -- input ---------------------------------------------------------------------------------------
def read_source(rel: str) -> str:
    path = SRC / rel
    if not path.is_file():
        raise BuildError(f"missing source file: {path.relative_to(ROOT)}")
    return path.read_text("utf-8").lstrip("\ufeff")


def check_sources() -> None:
    missing = [rel for rel in [TEMPLATE, STYLES, *JS_ORDER] if not (SRC / rel).is_file()]
    if missing:
        raise BuildError("missing source file(s): " + ", ".join(f"web/src/{m}" for m in missing))
    known = set(JS_ORDER)
    stray = sorted(str(p.relative_to(SRC)).replace("\\", "/") for p in SRC.rglob("*.js")
                   if str(p.relative_to(SRC)).replace("\\", "/") not in known)
    if stray:
        raise BuildError("JavaScript file(s) not listed in JS_ORDER (they would be left out of the build): " + ", ".join(stray))


def load_json(path: Path, what: str) -> Any:
    if not path.is_file():
        raise BuildError(f"{what} file not found: {path}")
    try:
        return json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildError(f"{what} file is not valid JSON ({path}): {exc}") from exc


def load_bundle(bundle_path: Path | None, vertical: str | None = None) -> dict[str, Any]:
    if bundle_path is not None:
        bundle = load_json(bundle_path, "bundle")
    else:
        sys.path.insert(0, str(ROOT / "src"))
        try:
            from dopamine_king.webdata import build_bundle  # type: ignore
        except ImportError as exc:
            raise BuildError(f"cannot import dopamine_king.webdata.build_bundle: {exc}") from exc
        ledger = None
        try:  # the shipped seed ledger gives the Vault real studies and tactics instead of an empty state (a vertical brings its own)
            from dopamine_king.research.ledger import Ledger  # type: ignore
            ledger = Ledger.load()
        except Exception as exc:  # the game still builds without the evidence vault
            print(f"note: building without the evidence ledger ({exc})", file=sys.stderr)
        bundle = build_bundle(ledger=ledger, vertical=vertical)
    if not isinstance(bundle, dict):
        raise BuildError("the bundle must be a JSON object")
    missing = [k for k in REQUIRED_BUNDLE_KEYS if k not in bundle]
    if missing:
        raise BuildError("the bundle is missing required key(s): " + ", ".join(missing))
    return bundle


def inject_samples(bundle: dict[str, Any], forge: Path | None, guru: Path | None) -> None:
    """Add sample Pack and Plan JSON when the bundle has none (the real ones win)."""
    if forge is not None:
        pack = load_json(forge, "forge")
        if not bundle.get("forge_samples"):
            bundle["forge_samples"] = pack if isinstance(pack, list) else [pack]
    if guru is not None:
        plan = load_json(guru, "guru")
        if not bundle.get("guru_sample") and not bundle.get("guru_samples"):
            bundle["guru_sample"] = plan


# -- text hygiene --------------------------------------------------------------------------------
def replace_dashes(text: str) -> str:
    """Project rule: no em dash or en dash. A spaced dash becomes ' - ', a bare one a hyphen."""
    text = re.sub(r"\s*" + EM_DASH + r"\s*", " - ", text)
    text = re.sub(r"\s+" + EN_DASH + r"\s+", " - ", text)
    return text.replace(EN_DASH, "-")


def sanitize(value: Any, counter: list[int]) -> Any:
    if isinstance(value, str):
        if EM_DASH in value or EN_DASH in value:
            counter[0] += 1
            return replace_dashes(value)
        return value
    if isinstance(value, list):
        return [sanitize(v, counter) for v in value]
    if isinstance(value, dict):
        return {k: sanitize(v, counter) for k, v in value.items()}
    return value


def bundle_script_text(bundle: dict[str, Any]) -> str:
    """JSON that is safe inside <script type="application/json">."""
    text = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    return (text.replace("</", "<\\/").replace("<!--", "\\u003c!--")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


# -- assembly ------------------------------------------------------------------------------------
def assemble(bundle: dict[str, Any]) -> str:
    template = read_source(TEMPLATE)
    css = read_source(STYLES)
    scripts = []
    for rel in JS_ORDER:
        code = read_source(rel)
        if "</script" in code.lower() or "<!--" in code:
            raise BuildError(f"web/src/{rel} contains '</script' or '<!--', which would break the inline script")
        scripts.append(f"/* ---- {rel} ---- */\n{code.rstrip()}\n")
    if "</style" in css.lower():
        raise BuildError("styles.css contains '</style'")
    for key, token in PLACEHOLDERS.items():
        if template.count(token) != 1:
            raise BuildError(f"{TEMPLATE} must contain the placeholder {token} exactly once (found {template.count(token)})")
    html = template.replace(PLACEHOLDERS["styles"], css.rstrip())
    html = html.replace(PLACEHOLDERS["bundle"], bundle_script_text(bundle))
    html = html.replace(PLACEHOLDERS["scripts"], "\n".join(scripts))
    return html


_BLOCKS = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<([a-zA-Z][\w:-]*)\b([^>]*)>", re.S)
_URL_ATTR = re.compile(r"""\b(src|href|action|poster|srcset|data|xlink:href|formaction)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_CSS_URL = re.compile(r"""url\(\s*["']?\s*([^"')\s]+)""", re.I)
_CSS_IMPORT = re.compile(r"@import\b", re.I)


def verify(html: str) -> None:
    """Fail loudly when the output could touch the network or breaks a project rule."""
    for ch, name in ((EM_DASH, "em dash"), (EN_DASH, "en dash")):
        if ch in html:
            idx = html.index(ch)
            raise BuildError(f"the output contains an {name} near: {html[max(0, idx - 40):idx + 40]!r}")
    markup = _BLOCKS.sub("", html)
    for tag in _TAG.finditer(markup):
        for attr in _URL_ATTR.finditer(tag.group(2)):
            value = (attr.group(2) or attr.group(3) or attr.group(4) or "").strip()
            if value and not value.startswith(("data:", "#")):
                raise BuildError(f"<{tag.group(1)} {attr.group(1)}=...> points to {value!r}: the page must be self-contained")
    for block in re.finditer(r"<style\b[^>]*>(.*?)</style>", html, re.S | re.I):
        css = block.group(1)
        if _CSS_IMPORT.search(css):
            raise BuildError("the CSS uses @import")
        for m in _CSS_URL.finditer(css):
            if not m.group(1).startswith(("data:", "#")):
                raise BuildError(f"the CSS references an external resource: {m.group(1)!r}")
    size = len(html.encode("utf-8"))
    if size >= MAX_BYTES:
        raise BuildError(f"the output is {size} bytes, the limit is {MAX_BYTES}")


def build_web(bundle_path: Path | None = None, out_path: Path | None = None,
              forge: Path | None = None, guru: Path | None = None, quiet: bool = False, vertical: str | None = None) -> Path:
    """Build the single-file game and return the output path."""
    out_path = Path(out_path) if out_path else DEFAULT_OUT
    check_sources()
    bundle = load_bundle(Path(bundle_path) if bundle_path else None, vertical)
    inject_samples(bundle, Path(forge) if forge else None, Path(guru) if guru else None)
    counter = [0]
    bundle = sanitize(bundle, counter)
    if counter[0] and not quiet:
        print(f"note: replaced long dash characters in {counter[0]} bundle string(s)", file=sys.stderr)
    html = assemble(bundle)
    verify(html)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, "utf-8")
    if not quiet:
        try:
            shown = out_path.resolve().relative_to(ROOT)
        except ValueError:
            shown = out_path
        print(f"wrote {shown} ({len(html.encode('utf-8')) // 1024} KB)")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Dopamine King web game into one HTML file.")
    parser.add_argument("--bundle", type=Path, help="data bundle JSON (default: computed by dopamine_king.webdata.build_bundle)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output file (default: web/dist/dopamine-king.html)")
    parser.add_argument("--forge", type=Path, help="sample Pack JSON, used when the bundle has no forge_samples")
    parser.add_argument("--guru", type=Path, help="sample Plan JSON, used when the bundle has no guru_sample")
    parser.add_argument("--no-samples", action="store_true", help="do not fall back to the development sample Pack and Plan in web/dev")
    parser.add_argument("--vertical", default="pbm", help="edition computed into the bundle: pbm (MITO LIGHT, default) or general")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    forge, guru = args.forge, args.guru
    if not args.no_samples:
        forge = forge or (DEV_FORGE if DEV_FORGE.is_file() else None)
        guru = guru or (DEV_GURU if DEV_GURU.is_file() else None)
    try:
        build_web(args.bundle, args.out, forge, guru, args.quiet, None if args.vertical in ("general", "none", "") else args.vertical)
    except BuildError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
