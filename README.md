# Commodity Price Analysis Prototype

Local-first prototype for USDA/AMS commodity price analysis, IGCE support, and fair-and-reasonable pricing documentation.

The app is built to keep the pricing record auditable:

- USAspending and SAM.gov are discovery/context sources unless line-level unit data is available.
- Unit-price evidence must pass a comparability gate before it enters the price range.
- Adjustments are explicit, source-cited, and included in the exported memo.
- Generated language is decision support only. The contracting officer remains responsible for the final determination.

## Run

```powershell
python app.py
```

Then open:

```text
http://127.0.0.1:8765
```

## Optional Environment

```powershell
$env:SAM_API_KEY = "your-sam-public-api-key"
```

Without `SAM_API_KEY`, the app still runs and USAspending discovery still works.

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

