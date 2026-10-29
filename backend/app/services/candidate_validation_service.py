from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import Any

import httpx

from app.scrapers.base import ScrapedListing
from app.scrapers.normalizers import match_score


logger = logging.getLogger(__name__)


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"

MATCH_RELATIONS = {
    "exact_match",
    "same_product_variant",
    "same_category_alternative",
    "compatible_accessory_or_part",
    "bundle_or_kit",
    "unrelated",
    "uncertain",
}

ACCEPTED_RELATIONS = {
    "exact_match",
    "same_product_variant",
    "same_category_alternative",
    "compatible_accessory_or_part",
    "bundle_or_kit",
}
PRECISE_QUERY_ACCEPTED_RELATIONS = {
    "exact_match",
    "same_product_variant",
}

RELATION_PRIORITY = {
    "exact_match": 0,
    "same_product_variant": 1,
    "same_category_alternative": 2,
    "bundle_or_kit": 3,
    "compatible_accessory_or_part": 4,
    "uncertain": 5,
    "unrelated": 99,
}


@dataclass(frozen=True, slots=True)
class CandidateValidationResult:
    index: int
    relation: str
    confidence: float
    canonical_product: str
    is_match: bool | None = None
    product_family: str | None = None
    variant: str | None = None
    reason: str | None = None
    source: str = "heuristic"

    @property
    def accepted(self) -> bool:
        if self.is_match is False:
            return False
        return self.relation in ACCEPTED_RELATIONS


class CandidateValidationService:
    """Classifies scraped candidates relative to the user's query.

    Direct scrapers remain responsible for facts such as price and URL. This
    service only decides candidate relevance and grouping.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "google/gemini-2.5-flash",
        enabled: bool = True,
        timeout_seconds: float = 3,
        max_candidates: int = 12,
        batch_size: int = 4,
        parallel_batches: int = 3,
    ) -> None:
        self.configure(
            api_key=api_key,
            model=model,
            enabled=enabled,
            timeout_seconds=timeout_seconds,
            max_candidates=max_candidates,
            batch_size=batch_size,
            parallel_batches=parallel_batches,
        )

    def configure(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        enabled: bool | None = None,
        timeout_seconds: float | None = None,
        max_candidates: int | None = None,
        batch_size: int | None = None,
        parallel_batches: int | None = None,
    ) -> None:
        self.api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
        if model is not None:
            self.model = model.strip() or "google/gemini-2.5-flash"
        elif not hasattr(self, "model"):
            self.model = "google/gemini-2.5-flash"
        if enabled is not None:
            self.enabled = enabled
        elif not hasattr(self, "enabled"):
            self.enabled = True
        if timeout_seconds is not None:
            self.timeout_seconds = max(float(timeout_seconds), 0.5)
        elif not hasattr(self, "timeout_seconds"):
            self.timeout_seconds = 3
        if max_candidates is not None:
            self.max_candidates = max(int(max_candidates), 1)
        elif not hasattr(self, "max_candidates"):
            self.max_candidates = 12
        if batch_size is not None:
            self.batch_size = max(int(batch_size), 1)
        elif not hasattr(self, "batch_size"):
            self.batch_size = 4
        if parallel_batches is not None:
            self.parallel_batches = max(int(parallel_batches), 1)
        elif not hasattr(self, "parallel_batches"):
            self.parallel_batches = 3

    async def validate(
        self,
        query: str,
        listings: list[ScrapedListing],
    ) -> dict[int, CandidateValidationResult]:
        fallback = self._fallback_validate(query, listings)
        if not listings or not self.enabled or not self.api_key:
            return fallback

        selected_indices = self._selected_indices(query, listings)
        if not selected_indices:
            return fallback

        try:
            llm_results = await self._validate_batches_with_openrouter(query, listings, selected_indices)
        except Exception as exc:
            logger.warning(
                "candidate_validation_fallback query=%s model=%s error_type=%s error=%s",
                query,
                self.model,
                type(exc).__name__,
                exc,
            )
            return fallback

        merged = dict(fallback)
        for result in llm_results:
            if 0 <= result.index < len(listings):
                merged[result.index] = result
        return self._apply_precision_gate(query, merged, listings)

    async def _validate_batches_with_openrouter(
        self,
        query: str,
        listings: list[ScrapedListing],
        selected_indices: list[int],
    ) -> list[CandidateValidationResult]:
        indexed_listings = [
            (index, listings[index])
            for index in selected_indices
        ]
        batches = [
            indexed_listings[index:index + self.batch_size]
            for index in range(0, len(indexed_listings), self.batch_size)
        ]
        if not batches:
            return []

        semaphore = asyncio.Semaphore(self.parallel_batches)

        async def validate_batch(batch: list[tuple[int, ScrapedListing]]) -> list[CandidateValidationResult]:
            async with semaphore:
                return await self._validate_with_openrouter(query, batch)

        batch_results = await asyncio.gather(
            *(validate_batch(batch) for batch in batches)
        )
        return [
            result
            for results in batch_results
            for result in results
        ]

    def _selected_indices(self, query: str, listings: list[ScrapedListing]) -> list[int]:
        indexed = [
            (
                index,
                listing,
                match_score(
                    query,
                    listing.vendor_product_name,
                    listing.canonical_name,
                    listing.brand,
                    listing.category,
                    listing.model_number,
                ),
            )
            for index, listing in enumerate(listings)
        ]
        relevance_ranked = sorted(
            indexed,
            key=lambda item: (
                -item[2],
                float(item[1].price),
                item[1].vendor.lower(),
                item[1].vendor_product_name.lower(),
            )
        )
        price_ranked = sorted(
            indexed,
            key=lambda item: (
                float(item[1].price),
                -item[2],
                item[1].vendor.lower(),
                item[1].vendor_product_name.lower(),
            ),
        )
        selection_limit = min(len(indexed), max(self.max_candidates, 24))
        relevance_quota = max(selection_limit // 2, min(self.max_candidates, selection_limit))
        selected: list[int] = []
        seen: set[int] = set()

        for index, _, _ in relevance_ranked[:relevance_quota]:
            selected.append(index)
            seen.add(index)

        for index, _, _ in price_ranked:
            if len(selected) >= selection_limit:
                break
            if index in seen:
                continue
            selected.append(index)
            seen.add(index)

        return selected

    async def _validate_with_openrouter(
        self,
        query: str,
        indexed_listings: list[tuple[int, ScrapedListing]],
    ) -> list[CandidateValidationResult]:
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Classify ecommerce candidates relative to the query and confirm whether "
                        "the sellable item itself matches what the user is trying to buy. Return "
                        "only compact JSON in this exact shape: "
                        "{\"c\":[[index,is_match,\"relation\",confidence]]}. No prose, "
                        "no markdown, no extra keys. Never infer or change prices."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "q": query,
                            "relations": sorted(MATCH_RELATIONS),
                            "rules": [
                                "exact_match: requested product.",
                                "For a category query, exact_match means an actual product in that category.",
                                "same_product_variant: same family, different color/storage/capacity/model/pack/spec.",
                                "same_category_alternative: useful alternative in same category.",
                                "compatible_accessory_or_part: item is related to, used with, replacement for, or compatible with the requested product, but is not the requested product itself.",
                                "bundle_or_kit: bundle/kit containing requested product/category.",
                                "unrelated: not useful for query.",
                                "uncertain: insufficient information.",
                                "is_match is true only when the sellable item is the thing the user asked to buy.",
                                "For query 'washing machine', a washing machine is is_match=true; inlet pipes, outlet pipes, hoses, covers, adapters, stands, and spare parts are is_match=false.",
                                "For query 'washing machine pipe', a washing machine pipe can be is_match=true.",
                                "If query words appear only as a fitment, compatibility, replacement, or use target, do not mark exact_match.",
                                "If the listing title changes the sellable item into a different product than the query, classify it as related or unrelated, not exact_match.",
                                "Any product type can be exact_match only when it is the thing the query asks for.",
                            ],
                            "items": [
                                self._candidate_payload(index, listing)
                                for index, listing in indexed_listings
                            ],
                            "item_fields": ["index", "vendor", "title", "brand", "category", "model"],
                            "out": {
                                "c": [
                                    [0, True, "exact_match", 0.95],
                                    [1, False, "compatible_accessory_or_part", 0.9],
                                ]
                            },
                        },
                        ensure_ascii=True,
                    ),
                },
            ],
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                OPENROUTER_CHAT_COMPLETIONS_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://costiqo.local",
                    "X-Title": "Costiqo",
                },
            )
        response.raise_for_status()
        payload = response.json()
        content = (
            ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
            if isinstance(payload, dict)
            else None
        )
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter response did not include JSON content.")

        parsed = self._parse_json_object(content)
        rows = self._validation_rows(parsed)
        if not isinstance(rows, list):
            raise RuntimeError("OpenRouter validation JSON did not include candidates.")

        listings_by_index = dict(indexed_listings)
        results: list[CandidateValidationResult] = []
        for row in rows:
            result = self._coerce_result(row, listings_by_index)
            if result is not None:
                results.append(result)
        return results

    def _candidate_payload(self, index: int, listing: ScrapedListing) -> list[Any]:
        return [
            index,
            listing.vendor,
            listing.vendor_product_name or listing.canonical_name,
            listing.brand or "",
            listing.category or "",
            listing.model_number or "",
        ]

    def _parse_json_object(self, content: str) -> Any:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        return json.loads(stripped)

    def _validation_rows(self, parsed: Any) -> list[Any] | None:
        if isinstance(parsed, dict):
            rows = parsed.get("c")
            if isinstance(rows, list):
                return rows
            rows = parsed.get("candidates")
            if isinstance(rows, list):
                return rows
            rows = parsed.get("results")
            if isinstance(rows, list):
                return rows
        if isinstance(parsed, list):
            return parsed
        return None

    def _coerce_result(
        self,
        row: Any,
        listings_by_index: dict[int, ScrapedListing] | None = None,
    ) -> CandidateValidationResult | None:
        if isinstance(row, (list, tuple)):
            if len(row) < 2:
                return None
            try:
                index = int(row[0])
            except (TypeError, ValueError):
                return None
            if len(row) >= 4 and self._looks_like_match_value(row[1]):
                match_value = row[1]
                relation_value = row[2]
                confidence_value = row[3]
            else:
                match_value = None
                relation_value = row[1]
                confidence_value = row[2] if len(row) > 2 else 0.5
            listing = (listings_by_index or {}).get(index)
            return self._build_openrouter_result(
                index=index,
                match_value=match_value,
                relation_value=relation_value,
                confidence_value=confidence_value,
                canonical_product=(
                    (listing.canonical_name or listing.vendor_product_name)
                    if listing is not None
                    else ""
                ),
                product_family=listing.category if listing is not None else None,
                variant=listing.model_number if listing is not None else None,
                reason=None,
            )

        if not isinstance(row, dict):
            return None
        try:
            index = int(row.get("index"))
        except (TypeError, ValueError):
            return None
        listing = (listings_by_index or {}).get(index)
        return self._build_openrouter_result(
            index=index,
            match_value=(
                row.get("is_match")
                if "is_match" in row
                else row.get("match")
            ),
            relation_value=row.get("relation") or "uncertain",
            confidence_value=row.get("confidence"),
            canonical_product=(
                str(row.get("canonical_product") or "").strip()
                or (
                    (listing.canonical_name or listing.vendor_product_name)
                    if listing is not None
                    else ""
                )
            ),
            product_family=(
                self._optional_text(row.get("product_family"))
                or (listing.category if listing is not None else None)
            ),
            variant=(
                self._optional_text(row.get("variant"))
                or (listing.model_number if listing is not None else None)
            ),
            reason=self._optional_text(row.get("reason")),
        )

    def _build_openrouter_result(
        self,
        *,
        index: int,
        match_value: Any,
        relation_value: Any,
        confidence_value: Any,
        canonical_product: str,
        product_family: str | None,
        variant: str | None,
        reason: str | None,
    ) -> CandidateValidationResult:
        relation = str(relation_value or "uncertain").strip().lower()
        if relation not in MATCH_RELATIONS:
            relation = "uncertain"
        return CandidateValidationResult(
            index=index,
            relation=relation,
            confidence=self._coerce_confidence(confidence_value),
            canonical_product=canonical_product,
            is_match=self._coerce_match(match_value),
            product_family=self._optional_text(product_family),
            variant=self._optional_text(variant),
            reason=reason,
            source="openrouter",
        )

    def _fallback_validate(
        self,
        query: str,
        listings: list[ScrapedListing],
    ) -> dict[int, CandidateValidationResult]:
        results = {
            index: self._fallback_result(query, index, listing)
            for index, listing in enumerate(listings)
        }
        return self._apply_precision_gate(query, results, listings)

    def _fallback_result(
        self,
        query: str,
        index: int,
        listing: ScrapedListing,
    ) -> CandidateValidationResult:
        title = listing.vendor_product_name or listing.canonical_name
        score = match_score(
            query,
            title,
            listing.brand,
            listing.category,
            listing.model_number,
        )
        query_tokens = set(_tokens(query))
        candidate_tokens = set(_tokens(title, listing.brand, listing.category, listing.model_number))
        shared_tokens = query_tokens & candidate_tokens
        shared_non_numeric_tokens = {
            token
            for token in shared_tokens
            if not token.isdigit()
        }
        has_relation_context = self._has_relationship_context(query_tokens, title)
        overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens), 1)
        compact_query = _compact(query)
        compact_title = _compact(title)

        if query_tokens and shared_tokens and not shared_non_numeric_tokens:
            relation = "unrelated"
            confidence = min(score, 0.1)
        elif has_relation_context and shared_non_numeric_tokens:
            relation = "compatible_accessory_or_part"
            confidence = max(min(score, 0.7), 0.55)
        elif compact_query and len(compact_query) >= 4 and compact_query in compact_title:
            relation = "exact_match"
            confidence = max(score, 0.8)
        elif score >= 0.72 or overlap >= 0.75:
            relation = "exact_match"
            confidence = max(score, overlap)
        elif score >= 0.45 or overlap >= 0.35:
            relation = "same_category_alternative"
            confidence = max(score, overlap, 0.45)
        elif score >= 0.25 or overlap > 0:
            relation = "uncertain"
            confidence = max(score, overlap, 0.25)
        else:
            relation = "unrelated"
            confidence = max(score, overlap)

        return CandidateValidationResult(
            index=index,
            relation=relation,
            confidence=round(min(max(confidence, 0.0), 1.0), 4),
            canonical_product=listing.canonical_name or title,
            is_match=None,
            product_family=listing.category or None,
            variant=listing.model_number or None,
            reason="Generic lexical fallback validation.",
            source="heuristic",
        )

    def _has_relationship_context(self, query_tokens: set[str], title: str) -> bool:
        if not query_tokens:
            return False
        title_tokens = _tokens(title)
        if not query_tokens.issubset(set(title_tokens)):
            return False
        relationship_tokens = {
            "compatible",
            "compatibility",
            "fit",
            "fitment",
            "fits",
            "for",
            "replacement",
            "replicate",
            "suitable",
            "supports",
        }
        return bool(set(title_tokens) & relationship_tokens)

    def _apply_precision_gate(
        self,
        query: str,
        results: dict[int, CandidateValidationResult],
        listings: list[ScrapedListing],
    ) -> dict[int, CandidateValidationResult]:
        if not self._query_requires_precise_relation(query):
            return results
        anchors = self._precise_query_anchors(query)

        gated: dict[int, CandidateValidationResult] = {}
        for index, result in results.items():
            listing = listings[index] if 0 <= index < len(listings) else None
            candidate_text = self._candidate_compact_text(listing, result)
            has_precise_anchor = not anchors or any(
                anchor in candidate_text
                for anchor in anchors
            )
            if result.relation in PRECISE_QUERY_ACCEPTED_RELATIONS and has_precise_anchor:
                gated[index] = result
                continue
            gated[index] = CandidateValidationResult(
                index=result.index,
                relation="unrelated",
                confidence=min(result.confidence, 0.2),
                canonical_product=result.canonical_product,
                is_match=False,
                product_family=result.product_family,
                variant=result.variant,
                reason=(
                    "Rejected category alternative for precise model query."
                    if not result.reason
                    else f"{result.reason} Rejected category alternative for precise model query."
                ),
                source=result.source,
            )
        return gated

    def _query_requires_precise_relation(self, query: str) -> bool:
        tokens = _tokens(query)
        if not tokens:
            return False
        if any(
            any(character.isalpha() for character in token)
            and any(character.isdigit() for character in token)
            for token in tokens
        ):
            return True
        return (
            any(token.isdigit() for token in tokens)
            and any(any(character.isalpha() for character in token) for token in tokens)
        )

    def _precise_query_anchors(self, query: str) -> tuple[str, ...]:
        tokens = _tokens(query)
        anchors: list[str] = []
        anchors.extend(
            token
            for token in tokens
            if len(token) > 3 or len(tokens) > 1
            if any(character.isalpha() for character in token)
            and any(character.isdigit() for character in token)
        )
        for left, right in zip(tokens, tokens[1:]):
            combined = f"{left}{right}"
            if any(character.isalpha() for character in combined) and any(
                character.isdigit() for character in combined
            ):
                anchors.append(combined)
        if not anchors:
            anchors.extend(
                token
                for token in tokens
                if len(token) > 3
                if any(character.isalpha() for character in token)
                and any(character.isdigit() for character in token)
            )
        return tuple(dict.fromkeys(anchors))

    def _candidate_compact_text(
        self,
        listing: ScrapedListing | None,
        result: CandidateValidationResult,
    ) -> str:
        if listing is None:
            return _compact(" ".join(filter(None, [result.canonical_product, result.variant])))
        return _compact(
            " ".join(
                filter(
                    None,
                    [
                        listing.vendor_product_name,
                        listing.brand,
                        listing.category,
                    ],
                )
            )
        )

    def _coerce_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.5
        return round(min(max(confidence, 0.0), 1.0), 4)

    def _looks_like_match_value(self, value: Any) -> bool:
        if isinstance(value, bool):
            return True
        if isinstance(value, (int, float)):
            return value in (0, 1)
        if isinstance(value, str):
            return value.strip().lower() in {
                "true",
                "false",
                "yes",
                "no",
                "match",
                "not_match",
                "not-match",
                "mismatch",
                "0",
                "1",
            }
        return False

    def _coerce_match(self, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
            return None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "match", "1"}:
                return True
            if normalized in {"false", "no", "not_match", "not-match", "mismatch", "0"}:
                return False
        return None

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def _tokens(*values: str | None) -> list[str]:
    return [
        token
        for value in values
        if value
        for token in re.findall(r"[a-z0-9]+", value.lower())
    ]


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())
