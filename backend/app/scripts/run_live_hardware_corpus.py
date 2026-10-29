from __future__ import annotations

import argparse
import inspect
import json
from statistics import median
from time import perf_counter

import httpx

if "app" not in inspect.signature(httpx.Client.__init__).parameters:
    _original_httpx_client_init = httpx.Client.__init__

    def _compat_httpx_client_init(self, *args, app=None, **kwargs):
        return _original_httpx_client_init(self, *args, **kwargs)

    httpx.Client.__init__ = _compat_httpx_client_init

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


DEFAULT_LOCATION = "Bengaluru"
HARDWARE_LIVE_CORPUS = [
    "esp32 development board",
    "esp32 s3 development board",
    "arduino uno",
    "arduino nano",
    "nodemcu esp8266",
    "raspberry pi 4 board",
    "digital multimeter",
    "clamp meter",
    "soldering iron",
    "soldering station",
    "breadboard",
    "relay module",
    "ultrasonic sensor",
    "dht11 sensor",
    "l298n motor driver",
    "buck converter",
    "oled display 0.96 inch",
    "18650 battery holder",
    "wire stripper",
    "drill machine",
    "angle grinder",
    "safety helmet",
    "safety shoes",
    "industrial gloves",
    "cpvc elbow 1 inch",
    "cpvc pipe 1 inch",
    "ball valve 1 inch",
    "wedge anchor 10mm",
    "white cement",
    "tile adhesive",
    "tmt bar",
    "digital vernier caliper",
]


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return round(lower_value + ((upper_value - lower_value) * fraction), 3)


def _evaluate_query(
    client: TestClient,
    query: str,
    *,
    location: str | None,
    pincode: str | None,
) -> dict[str, object]:
    params = {"q": query}
    if location:
        params["location"] = location
    if pincode:
        params["pincode"] = pincode

    started_at = perf_counter()
    response = client.get("/api/v1/comparisons", params=params)
    elapsed_seconds = round(perf_counter() - started_at, 3)

    result: dict[str, object] = {
        "query": query,
        "status_code": response.status_code,
        "elapsed_seconds": elapsed_seconds,
    }
    if response.status_code != 200:
        result["error"] = response.text
        return result

    payload = response.json()
    best_option = payload.get("best_option") or {}
    diagnostics = payload.get("search_diagnostics") or {}
    primary_results = payload.get("results") or []
    related_results = payload.get("related_store_results") or []

    result.update(
        {
            "result_count": len(primary_results),
            "best_vendor": best_option.get("vendor"),
            "best_price": best_option.get("price"),
            "product_name": payload.get("product_name"),
            "top_products": [
                item.get("product_name")
                for item in primary_results[:3]
            ],
            "top_vendors": [
                item.get("vendor")
                for item in primary_results[:3]
            ],
            "related_vendors": [
                item.get("vendor")
                for item in related_results[:3]
            ],
            "coverage_status": diagnostics.get("coverage_status"),
            "sources_checked": diagnostics.get("sources_checked"),
            "filters": [
                filter_item.get("key")
                for filter_item in diagnostics.get("filters") or []
            ],
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the live hardware comparison corpus.")
    parser.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help="Location to pass to /comparisons. Defaults to Bengaluru.",
    )
    parser.add_argument(
        "--pincode",
        default=None,
        help="Optional Indian pincode to pass to /comparisons.",
    )
    args = parser.parse_args()

    settings = get_settings()
    app = create_app(settings)
    with TestClient(app) as client:
        results = [
            _evaluate_query(
                client,
                query,
                location=args.location,
                pincode=args.pincode,
            )
            for query in HARDWARE_LIVE_CORPUS
        ]

    latencies = sorted(
        result["elapsed_seconds"]
        for result in results
        if isinstance(result.get("elapsed_seconds"), (int, float))
    )
    successful = [result for result in results if result.get("status_code") == 200]
    with_results = [result for result in successful if result.get("result_count")]
    incomplete = [
        result
        for result in successful
        if result.get("coverage_status") in {"incomplete", "query_needs_clarification"}
    ]

    summary = {
        "query_count": len(results),
        "successful_requests": len(successful),
        "queries_with_results": len(with_results),
        "queries_without_results": len(successful) - len(with_results),
        "incomplete_coverage_queries": len(incomplete),
        "latency_p50_seconds": round(median(latencies), 3) if latencies else 0.0,
        "latency_p95_seconds": _percentile(latencies, 0.95),
        "slowest_query_seconds": latencies[-1] if latencies else 0.0,
    }

    print(
        json.dumps(
            {
                "summary": summary,
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
