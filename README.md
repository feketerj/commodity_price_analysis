# Commodity Price Analysis Prototype

Local-first prototype for USDA/AMS commodity price analysis, IGCE support, and fair-and-reasonable pricing documentation.

The app is built to keep the pricing record auditable:

- USAspending and SAM.gov are discovery/context sources unless line-level unit data is available.
- Unit-price evidence must pass a comparability gate before it enters the price range.
- Adjustments are explicit, source-cited, and included in the exported memo.
- Generated language is decision support only. The contracting officer remains responsible for the final determination.

## Run

Optional preflight:

```powershell
python scripts/doctor.py
```

```powershell
python app.py
```

Then open:

```text
http://127.0.0.1:8765
```

If the default port is already in use and `CPA_PORT` is not explicitly set, the server uses the next available port and prints the actual URL.

## Optional Environment

```powershell
$env:SAM_API_KEY = "your-sam-public-api-key"
$env:CPA_PORT = "8765"
$env:CPA_DB_PATH = "C:\CAOC\commodity_price_analysis\data\commodity_price_analysis.sqlite3"
$env:CPA_BACKUP_DIR = "C:\CAOC\commodity_price_analysis\data\backups"
```

Without `SAM_API_KEY`, the app still runs and USAspending discovery still works.

## Operator Controls

- `GET /api/operator/status` returns schema, database, WAL, row counts, host/port, and backup path.
- `POST /api/operator/backup` creates a local SQLite backup.
- `GET /api/cases/<case_id>/memo.txt` exports the memo draft.
- `GET /api/cases/<case_id>/igce.csv` exports the IGCE/evidence table.
- `GET /api/cases/<case_id>/export.json` exports the full case, analysis, and audit log.
- `GET /api/cases/<case_id>/audit` returns the audit events for the case.

Runtime state is intentionally ignored by git under `data/` and `logs/`.

## Operator-Level Guardrails

- Request bodies are size-limited.
- Case, evidence, adjustment, URL, unit, date, and numeric inputs are validated before write.
- SQLite uses WAL mode, busy timeouts, foreign keys, and local backup support.
- External API failures return source-specific error payloads instead of crashing the server.
- USAspending and SAM.gov remain context-only unless unit-price evidence is supplied separately.
- Evidence that fails comparability checks is blocked from the unit-price calculation and shown as context-only.
- Case exports include audit events so the operator can preserve the calculation path.

## Test

```powershell
python -m unittest discover -s tests
```

## Data Sources Used Conceptually

- FAR 13.106-3, 12.209, 15.404-1, 16.203
- USDA AMS Selling Food to USDA and product specifications
- USDA AMS Specialty Crops Market News / MyMarketNews
- USAspending API
- SAM.gov Opportunities API
- USDA AgTransport, BLS, EIA, and FRED as future adjustment data sources
