from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cpa.db import Database
from cpa.memo import build_memo
from cpa.pricing import analyze_case
from cpa.seed import seed_demo_data
from cpa.sources import search_sam_opportunities, search_usaspending_awards


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
DB_PATH = ROOT / "data" / "commodity_price_analysis.sqlite3"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict | list) -> None:
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, payload: str, content_type: str = "text/plain") -> None:
    body = payload.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc


class AppHandler(BaseHTTPRequestHandler):
    server_version = "CommodityPriceAnalysis/0.1"

    @property
    def db(self) -> Database:
        return self.server.db  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == "/":
                self._serve_file(STATIC_ROOT / "index.html")
                return
            if path.startswith("/static/"):
                self._serve_file(STATIC_ROOT / path.removeprefix("/static/"))
                return
            if path == "/api/health":
                _json_response(self, 200, {"ok": True, "database": str(DB_PATH)})
                return
            if path == "/api/cases":
                _json_response(self, 200, self.db.list_cases())
                return
            if path.startswith("/api/cases/"):
                self._handle_case_get(path)
                return
            if path == "/api/search/usaspending":
                keywords = query.get("keywords", [""])[0]
                agency = query.get("agency", ["Agricultural Marketing Service"])[0]
                limit = int(query.get("limit", ["20"])[0])
                _json_response(self, 200, search_usaspending_awards(keywords=keywords, agency=agency, limit=limit))
                return
            if path == "/api/search/sam":
                title = query.get("title", [""])[0]
                ptype = query.get("ptype", ["a"])[0]
                posted_from = query.get("postedFrom", ["01/01/2025"])[0]
                posted_to = query.get("postedTo", ["06/06/2026"])[0]
                limit = int(query.get("limit", ["10"])[0])
                _json_response(
                    self,
                    200,
                    search_sam_opportunities(title=title, ptype=ptype, posted_from=posted_from, posted_to=posted_to, limit=limit),
                )
                return
            _json_response(self, 404, {"error": "not_found", "path": path})
        except Exception as exc:
            _json_response(self, 500, {"error": "server_error", "message": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = _read_json(self)
            if path == "/api/cases":
                case = self.db.create_case(payload)
                _json_response(self, 201, case)
                return
            if path.startswith("/api/cases/"):
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[3] == "evidence":
                    evidence = self.db.add_evidence(parts[2], payload)
                    _json_response(self, 201, evidence)
                    return
                if len(parts) == 4 and parts[3] == "adjustments":
                    adjustment = self.db.add_adjustment(parts[2], payload)
                    _json_response(self, 201, adjustment)
                    return
            _json_response(self, 404, {"error": "not_found", "path": path})
        except ValueError as exc:
            _json_response(self, 400, {"error": "bad_request", "message": str(exc)})
        except Exception as exc:
            _json_response(self, 500, {"error": "server_error", "message": str(exc)})

    def _handle_case_get(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) < 3:
            _json_response(self, 404, {"error": "not_found", "path": path})
            return

        case_id = parts[2]
        bundle = self.db.get_case_bundle(case_id)
        if not bundle:
            _json_response(self, 404, {"error": "case_not_found", "case_id": case_id})
            return

        if len(parts) == 3:
            _json_response(self, 200, bundle)
            return
        if len(parts) == 4 and parts[3] == "analysis":
            _json_response(self, 200, analyze_case(bundle["case"], bundle["evidence"], bundle["adjustments"]))
            return
        if len(parts) == 4 and parts[3] == "memo.txt":
            analysis = analyze_case(bundle["case"], bundle["evidence"], bundle["adjustments"])
            _text_response(self, 200, build_memo(bundle["case"], analysis))
            return
        _json_response(self, 404, {"error": "not_found", "path": path})

    def _serve_file(self, path: Path) -> None:
        resolved = path.resolve()
        if not str(resolved).startswith(str(STATIC_ROOT.resolve())) and resolved != (STATIC_ROOT / "index.html").resolve():
            _json_response(self, 403, {"error": "forbidden"})
            return
        if not resolved.exists() or not resolved.is_file():
            _json_response(self, 404, {"error": "static_file_not_found"})
            return

        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = Database(DB_PATH)
    db.initialize()
    seed_demo_data(db)

    port = int(os.environ.get("CPA_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    server.db = db  # type: ignore[attr-defined]
    print(f"Commodity Price Analysis running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

