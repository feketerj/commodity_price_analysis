from __future__ import annotations

import json
import logging
import mimetypes
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cpa.db import Database
from cpa.exporting import build_case_export, build_igce_csv
from cpa.memo import build_memo
from cpa.pricing import analyze_case
from cpa.seed import seed_demo_data
from cpa.sources import search_sam_opportunities, search_usaspending_awards


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
DB_PATH = Path(os.environ.get("CPA_DB_PATH", ROOT / "data" / "commodity_price_analysis.sqlite3")).resolve()
BACKUP_DIR = Path(os.environ.get("CPA_BACKUP_DIR", ROOT / "data" / "backups")).resolve()
MAX_JSON_BYTES = int(os.environ.get("CPA_MAX_JSON_BYTES", str(256 * 1024)))
STARTED_AT = time.time()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("commodity_price_analysis")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict | list) -> None:
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")
    handler.send_response(status)
    _common_headers(handler)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, payload: str, content_type: str = "text/plain") -> None:
    body = payload.encode("utf-8")
    handler.send_response(status)
    _common_headers(handler)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _common_headers(handler: BaseHTTPRequestHandler) -> None:
    request_id = getattr(handler, "request_id", "")
    if request_id:
        handler.send_header("X-Request-Id", request_id)
    handler.send_header("Cache-Control", "no-store")


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length == 0:
        return {}
    if length > MAX_JSON_BYTES:
        raise ValueError(f"JSON body exceeds {MAX_JSON_BYTES} bytes")
    raw = handler.rfile.read(length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _parse_limit(query: dict[str, list[str]], default: int, maximum: int) -> int:
    raw = query.get("limit", [str(default)])[0]
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    return max(1, min(value, maximum))


def _download_response(handler: BaseHTTPRequestHandler, status: int, payload: str, filename: str, content_type: str) -> None:
    body = payload.encode("utf-8")
    handler.send_response(status)
    _common_headers(handler)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "CommodityPriceAnalysis/0.2"

    @property
    def db(self) -> Database:
        return self.server.db  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info("%s %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        self.request_id = str(uuid.uuid4())
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
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "database": str(DB_PATH),
                        "uptime_seconds": round(time.time() - STARTED_AT, 2),
                        "request_id": self.request_id,
                    },
                )
                return
            if path == "/api/operator/status":
                status = self.db.status()
                status["uptime_seconds"] = round(time.time() - STARTED_AT, 2)
                status["host"] = self.server.server_address[0]
                status["port"] = self.server.server_address[1]
                status["backup_dir"] = str(BACKUP_DIR)
                _json_response(self, 200, status)
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
                limit = _parse_limit(query, 20, 100)
                _json_response(self, 200, search_usaspending_awards(keywords=keywords, agency=agency, limit=limit))
                return
            if path == "/api/search/sam":
                title = query.get("title", [""])[0]
                ptype = query.get("ptype", ["a"])[0]
                posted_from = query.get("postedFrom", ["01/01/2025"])[0]
                posted_to = query.get("postedTo", ["06/06/2026"])[0]
                limit = _parse_limit(query, 10, 100)
                _json_response(
                    self,
                    200,
                    search_sam_opportunities(title=title, ptype=ptype, posted_from=posted_from, posted_to=posted_to, limit=limit),
                )
                return
            _json_response(self, 404, {"error": "not_found", "path": path})
        except ValueError as exc:
            _json_response(self, 400, {"error": "bad_request", "message": str(exc), "request_id": self.request_id})
        except Exception as exc:
            LOGGER.exception("request failed request_id=%s path=%s", self.request_id, path)
            _json_response(self, 500, {"error": "server_error", "message": str(exc), "request_id": self.request_id})

    def do_POST(self) -> None:
        self.request_id = str(uuid.uuid4())
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            payload = _read_json(self)
            if path == "/api/operator/backup":
                backup_path = self.db.backup(BACKUP_DIR)
                _json_response(self, 201, {"ok": True, "backup_path": str(backup_path), "request_id": self.request_id})
                return
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
            _json_response(self, 400, {"error": "bad_request", "message": str(exc), "request_id": self.request_id})
        except Exception as exc:
            LOGGER.exception("request failed request_id=%s path=%s", self.request_id, path)
            _json_response(self, 500, {"error": "server_error", "message": str(exc), "request_id": self.request_id})

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
        if len(parts) == 4 and parts[3] == "igce.csv":
            analysis = analyze_case(bundle["case"], bundle["evidence"], bundle["adjustments"])
            _download_response(self, 200, build_igce_csv(bundle["case"], analysis), f"{case_id}-igce.csv", "text/csv")
            return
        if len(parts) == 4 and parts[3] == "export.json":
            analysis = analyze_case(bundle["case"], bundle["evidence"], bundle["adjustments"])
            export = build_case_export(bundle, analysis, self.db.audit_events(case_id))
            _download_response(self, 200, json.dumps(export, indent=2, default=str), f"{case_id}-export.json", "application/json")
            return
        if len(parts) == 4 and parts[3] == "audit":
            _json_response(self, 200, self.db.audit_events(case_id))
            return
        _json_response(self, 404, {"error": "not_found", "path": path})

    def _serve_file(self, path: Path) -> None:
        resolved = path.resolve()
        try:
            resolved.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            _json_response(self, 403, {"error": "forbidden"})
            return
        if not resolved.exists() or not resolved.is_file():
            _json_response(self, 404, {"error": "static_file_not_found"})
            return

        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        body = resolved.read_bytes()
        self.send_response(200)
        _common_headers(self)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _build_server(host: str, preferred_port: int) -> ThreadingHTTPServer:
    explicit_port = "CPA_PORT" in os.environ
    candidates = [preferred_port] if explicit_port else list(range(preferred_port, preferred_port + 20))
    last_error: OSError | None = None
    for port in candidates:
        try:
            return ThreadingHTTPServer((host, port), AppHandler)
        except OSError as exc:
            last_error = exc
            if explicit_port:
                break
            continue
    raise OSError(f"could not bind {host}:{preferred_port}") from last_error


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = Database(DB_PATH)
    db.initialize()
    seed_demo_data(db)

    host = os.environ.get("CPA_HOST", "127.0.0.1")
    port = int(os.environ.get("CPA_PORT", "8765"))
    server = _build_server(host, port)
    server.db = db  # type: ignore[attr-defined]
    actual_host, actual_port = server.server_address
    LOGGER.info("Commodity Price Analysis running at http://%s:%s", actual_host, actual_port)
    print(f"Commodity Price Analysis running at http://{actual_host}:{actual_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
