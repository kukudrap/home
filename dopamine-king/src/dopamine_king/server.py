"""Local JSON API and static host for the game.

``handle_api`` is a pure function (easy to test); ``serve`` wraps it in a small threaded HTTP
server bound to localhost. The server uses YOUR credentials when the Anthropic writer is selected,
so it refuses to bind to a public interface unless explicitly allowed.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .analysis import compare_hooks
from .generate.providers import WriterError, WriterRefused, select_writer
from .generate.types import Brief
from .guru import build_plan
from .lab import bayes_ab, sample_size_per_arm, two_proportion_test
from .scoring import score_hook

MAX_BODY = 1_000_000
Json = dict[str, Any]


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _brief(data: Json) -> Brief:
    raw = data.get("brief")
    if not isinstance(raw, dict):
        raise ApiError(400, "field 'brief' (object) is required")
    for key in ("brand", "topic", "audience"):
        if not str(raw.get(key, "")).strip():
            raise ApiError(400, f"brief.{key} is required")
    return Brief.from_dict(raw)


def _formats_list() -> list[Json]:
    from .generate import formats as registry
    return [{"id": s.id, "name_en": s.name_en, "name_cs": s.name_cs, "family": s.family, "platform": s.platform, "limits": s.limits}
            for s in registry.list_formats()]


def _forge(data: Json, ctx: Json) -> Json:
    from .generate.packs import build_pack
    brief = _brief(data)
    ledger = ctx.get("ledger")
    if brief.vertical:                    # a vertical brings its own studies, so its citations resolve
        try:
            from .verticals import load_vertical
            ledger = load_vertical(brief.vertical).ledger()
        except Exception as err:
            raise ApiError(400, f"unknown vertical {brief.vertical!r}") from err
    try:
        writer = select_writer(data.get("writer") or ctx.get("writer", "auto"))
    except ValueError as err:
        raise ApiError(400, str(err)) from err
    formats = data.get("formats")
    if formats is not None and not (isinstance(formats, list) and all(isinstance(f, str) for f in formats)):
        raise ApiError(400, "'formats' must be a list of format ids")
    try:
        pack = build_pack(brief, formats, writer=writer, ledger=ledger, options=data.get("options"),
                          improve_rounds=int(data.get("improve_rounds", 1)))
    except WriterRefused as err:
        raise ApiError(422, str(err)) from err
    except WriterError as err:
        raise ApiError(502, str(err)) from err
    return pack.to_dict()


def _lab_ab(data: Json) -> Json:
    try:
        (ca, na), (cb, nb) = data["a"], data["b"]
        freq = two_proportion_test(int(ca), int(na), int(cb), int(nb))
        bayes = bayes_ab(int(ca), int(na), int(cb), int(nb))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as err:
        raise ApiError(400, "expected {'a': [conversions, n], 'b': [conversions, n]} with n > 0") from err
    return {"frequentist": freq.to_dict(), "bayesian": bayes.to_dict(),
            "sample_size_per_arm_for_20pct_lift": sample_size_per_arm(max(0.001, min(0.99, int(ca) / int(na))), 0.2)
            if 0 < int(ca) < int(na) else None}


def handle_api(method: str, path: str, body: Json | None, ctx: Json | None = None) -> tuple[int, Json | list]:
    """Route one API call. Returns (status, JSON-serialisable payload)."""
    ctx = ctx or {}
    try:
        if path == "/api/health" and method == "GET":
            return 200, {"ok": True, "version": __version__, "writer": ctx.get("writer", "auto")}
        if path == "/api/formats" and method == "GET":
            return 200, _formats_list()
        if method != "POST":
            raise ApiError(405 if path.startswith("/api/") else 404, "method not allowed" if path.startswith("/api/") else "not found")
        data = body or {}
        if path == "/api/score":
            text = data.get("text")
            if not isinstance(text, str):
                raise ApiError(400, "field 'text' (string) is required")
            return 200, score_hook(text, str(data.get("body", "")), lang=data.get("lang")).to_dict()
        if path == "/api/compare":
            if not (isinstance(data.get("a"), str) and isinstance(data.get("b"), str)):
                raise ApiError(400, "fields 'a' and 'b' (strings) are required")
            return 200, compare_hooks(data["a"], data["b"], lang=data.get("lang")).to_dict()
        if path == "/api/forge":
            return 200, _forge(data, ctx)
        if path == "/api/guru":
            opts = data.get("options") or {}
            return 200, build_plan(_brief(data), weeks=int(opts.get("weeks", 4)), posts_per_week=int(opts.get("posts_per_week", 5)),
                                   channels=opts.get("channels")).to_dict()
        if path == "/api/lab/ab":
            return 200, _lab_ab(data)
        raise ApiError(404, "not found")
    except ApiError as err:
        return err.status, {"ok": False, "error": str(err)}
    except (ValueError, TypeError) as err:
        return 400, {"ok": False, "error": f"bad request: {err}"}
    except ImportError as err:
        return 501, {"ok": False, "error": f"module not available: {err}"}


def make_handler(ctx: Json, page: Callable[[], bytes]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"DopamineKing/{__version__}"

        def _send(self, status: int, payload: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status: int, payload: Any) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, page(), "text/html; charset=utf-8")
            elif path.startswith("/api/"):
                status, payload = handle_api("GET", path, None, ctx)
                self._json(status, payload)
            else:
                self._json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._json(413, {"ok": False, "error": "request too large"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("JSON object expected")
            except ValueError:
                self._json(400, {"ok": False, "error": "invalid JSON body"})
                return
            status, payload = handle_api("POST", path, body, ctx)
            self._json(status, payload)

        def log_message(self, fmt: str, *args: Any) -> None:  # quiet by default
            if ctx.get("verbose"):
                super().log_message(fmt, *args)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, *, writer: str = "auto", page_path: str | Path | None = None,
          allow_remote: bool = False, ledger: Any = None, verbose: bool = False) -> None:
    if host not in ("127.0.0.1", "localhost", "::1") and not allow_remote:
        raise SystemExit("Refusing to bind to a non-local address: the server would spend your API credits for anyone. "
                         "Pass --allow-remote if you really mean it and put authentication in front of it.")
    ctx = {"writer": writer, "ledger": ledger, "verbose": verbose}

    def page() -> bytes:
        path = Path(page_path) if page_path else None
        if path and path.exists():
            return path.read_bytes()
        return b"<!doctype html><meta charset=utf-8><title>Dopamine King</title><p>Game page not built yet. Run: kingctl build-web</p>"

    httpd = ThreadingHTTPServer((host, port), make_handler(ctx, page))
    print(f"Dopamine King on http://{host}:{port}  (writer: {writer})  Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()
