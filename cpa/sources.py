from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date
from typing import Any


USA_SPENDING_ENDPOINT = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
SAM_OPPORTUNITIES_ENDPOINT = "https://api.sam.gov/opportunities/v2/search"


def search_usaspending_awards(keywords: str, agency: str = "Agricultural Marketing Service", limit: int = 20) -> dict[str, Any]:
    terms = [term.strip() for term in keywords.replace(",", " ").split() if term.strip()]
    if not terms:
        terms = ["beans", "vegetables", "potato", "tomato"]
    payload = {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{"start_date": "2025-01-01", "end_date": str(date.today())}],
            "agencies": [{"type": "awarding", "tier": "subtier", "name": agency}],
            "keywords": terms,
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Start Date",
            "End Date",
            "Award Amount",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Description",
            "NAICS",
            "PSC",
            "Primary Place of Performance",
        ],
        "limit": max(1, min(limit, 100)),
        "page": 1,
        "sort": "Start Date",
        "order": "desc",
    }
    data = _post_json(USA_SPENDING_ENDPOINT, payload)
    return {
        "source": "USAspending",
        "unit_price_warning": "Award amount is not treated as CLIN-level unit price. Use for discovery/context unless unit-price evidence is separately supplied.",
        "results": data.get("results", []),
        "page_metadata": data.get("page_metadata", {}),
        "messages": data.get("messages", []),
    }


def search_sam_opportunities(title: str, ptype: str, posted_from: str, posted_to: str, limit: int = 10) -> dict[str, Any]:
    api_key = os.environ.get("SAM_API_KEY")
    if not api_key:
        return {
            "source": "SAM.gov Opportunities",
            "error": "missing_api_key",
            "message": "Set SAM_API_KEY to enable SAM.gov opportunity searches. App functionality is not blocked.",
            "results": [],
        }
    params = {
        "api_key": api_key,
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "ptype": ptype,
        "limit": str(max(1, min(limit, 100))),
    }
    if title:
        params["title"] = title
    url = f"{SAM_OPPORTUNITIES_ENDPOINT}?{urllib.parse.urlencode(params)}"
    data = _get_json(url)
    return {
        "source": "SAM.gov Opportunities",
        "unit_price_warning": "SAM.gov notices and awards are discovery/context unless attachments or award data contain line-level unit prices.",
        "results": data.get("opportunitiesData", []),
        "totalRecords": data.get("totalRecords"),
    }


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

