from dataclasses import dataclass
from collections.abc import Callable
from statistics import median
from datetime import datetime, timedelta, timezone
import logging
import re

from sqlalchemy.orm import Session

from app.schemas.comparison import (
    BenchmarkSummary,
    BestOption,
    ComparisonItem,
    ComparisonResponse,
    ProductGroupSummary,
    SearchDiagnosticsSummary,
    SearchFilterSummary,
)
from app.schemas.comparison import ComparisonRankingMode
from app.schemas.comparison import RelatedStoreLink
from app.schemas.product import ProductDetail, VendorListingSummary
from app.scrapers.base import ScrapedListing
from app.scrapers.normalizers import listing_matches_query, match_score
from app.schemas.procurement import LatestPurchaseSummary
from app.services.candidate_validation_service import (
    CandidateValidationResult,
    CandidateValidationService,
    RELATION_PRIORITY,
)
from app.services.decision_service import DecisionService
from app.services.offer_verification_service import OfferVerificationResult
from app.services.procurement_service import ProcurementService
from app.services.product_service import ProductService
from app.services.query_understanding_service import (
    QueryClarity,
    QueryUnderstanding,
    assess_query_clarity,
    understand_query,
)
from app.services.search_diagnostics import SearchDiagnostics, SearchFilterDiagnostic
from app.services.scrape_service import ScrapeService, SearchCoverageRequirement
from app.services.search_context_service import SearchContextService
from app.services.source_selection import (
    query_looks_like_hardware,
)
from app.utils.domain_trust import hostname_from_url, is_trusted_domain
from app.utils.delivery_parser import infer_delivery_days, infer_shipping_cost
from app.utils.product_identity import are_model_keys_compatible
from app.utils.time_utils import utc_now
from app.utils.vendor_links import build_vendor_search_url


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiveComparisonListing:
    id: int
    vendor: str
    vendor_product_name: str
    product_url: str
    current_price: float
    raw_price: str
    currency: str
    rating: float | None
    review_count: int
    delivery_info: str | None
    availability_status: str
    sentiment_score: float | None
    last_seen_at: datetime


@dataclass(slots=True)
class LiveProductGroup:
    canonical_name: str
    brand: str | None
    category: str | None
    model_number: str | None
    image_url: str | None
    listings: list[ScrapedListing]
    relation: str = "uncertain"
    match_confidence: float = 0.0
    validation_reason: str | None = None


@dataclass(slots=True)
class LiveProductDescriptor:
    canonical_name: str
    brand: str | None
    category: str | None


def select_best_live_listings_by_vendor(listings: list[ScrapedListing]) -> list[ScrapedListing]:
    listings_by_vendor: dict[str, ScrapedListing] = {}

    for listing in listings:
        current_best = listings_by_vendor.get(listing.vendor)
        if current_best is None:
            listings_by_vendor[listing.vendor] = listing
            continue

        if (
            float(listing.price),
            -(listing.rating or 0),
            listing.vendor_product_name,
        ) < (
            float(current_best.price),
            -(current_best.rating or 0),
            current_best.vendor_product_name,
        ):
            listings_by_vendor[listing.vendor] = listing

    return sorted(
        listings_by_vendor.values(),
        key=lambda item: (
            float(item.price),
            -(item.rating or 0),
            item.vendor,
        ),
    )


class ComparisonService:
    BROAD_QUERY_SCORE_WINDOW = 0.02
    FRESH_PRICE_WINDOW = timedelta(hours=6)
    LIVE_SEARCH_FOREGROUND_TIMEOUT_SECONDS = 4.0
    AMAZON_FOREGROUND_TIMEOUT_SECONDS = 6.0
    ROBU_FOREGROUND_TIMEOUT_SECONDS = 7.0
    LIVE_SEARCH_COVERAGE_TIMEOUT_SECONDS = 7.0
    MAX_LIVE_RESULTS_PER_VENDOR = 3
    TRUSTED_PRICE_CONFIDENCE = 0.5
    MAIN_RESULT_RELATIONS = {
        "exact_match",
        "same_product_variant",
    }
    QUERY_REQUESTED_RELATED_RELATIONS = {
        "compatible_accessory_or_part",
        "bundle_or_kit",
    }
    HARDWARE_RANKING_ACCESSORY_TOKENS = {
        "backboard",
        "breakout",
        "carrier",
        "debugger",
        "downloader",
        "expansion",
        "expension",
        "header",
        "programmer",
        "shield",
    }
    HARDWARE_RANKING_SPECIALIZED_TOKENS = {
        "a1s",
        "audio",
        "beetle",
        "c2",
        "c3",
        "c6",
        "cam",
        "display",
        "ethernet",
        "feather",
        "h2",
        "jtag",
        "lan8720",
        "lcd",
        "lora",
        "oled",
        "poe",
        "prog",
        "s2",
        "s3",
        "sc01",
        "tft",
        "touch",
        "touchscreen",
        "wt32",
        "wrover",
    }
    HARDWARE_FITTING_VARIANT_PENALTIES = {
        ("3", "way"): 0.18,
        ("3way",): 0.18,
        ("45", "deg"): 0.08,
        ("45", "degree"): 0.08,
        ("brass",): 0.05,
        ("female",): 0.05,
        ("male",): 0.05,
        ("reducer",): 0.08,
        ("reducing",): 0.08,
        ("tee",): 0.18,
        ("threaded",): 0.05,
    }
    HARDWARE_SOURCE_PRIORITY = (
        "moglix",
        "robu",
        "electronicscomp",
        "ibo",
        "global-electronics",
        "amazon",
    )
    SOURCE_VENDOR_NAMES = {
        "amazon": "Amazon",
        "croma": "Croma",
        "electronicscomp": "ElectronicsComp",
        "flipkart": "Flipkart",
        "global-electronics": "Global Electronics",
        "ibo": "IBO",
        "moglix": "Moglix",
        "poorvika": "Poorvika",
        "reliance-digital": "Reliance Digital",
        "robu": "Robu",
    }
    MAINSTREAM_VENDOR_ORDER = (
        "Moglix",
        "Robu",
        "ElectronicsComp",
        "IBO",
        "Global Electronics",
        "Amazon",
        "Flipkart",
        "Reliance Digital",
        "Poorvika",
        "Croma",
        "Vijay Sales",
        "Apple",
        "HP",
        "Dell",
        "Lenovo",
        "Samsung",
        "Tata Cliq",
        "JioMart",
    )

    def __init__(
        self,
        scrape_service: ScrapeService,
        product_service: ProductService,
        procurement_service: ProcurementService,
        search_context_service: SearchContextService,
        queue_service: "QueueService",
        offer_verification_service: "OfferVerificationService",
        decision_service: DecisionService,
        candidate_validation_service: CandidateValidationService | None = None,
        trusted_vendor_domains: tuple[str, ...] = (),
        degraded_source_names: tuple[str, ...] | list[str] = (),
    ) -> None:
        self.scrape_service = scrape_service
        self.product_service = product_service
        self.procurement_service = procurement_service
        self.search_context_service = search_context_service
        self.queue_service = queue_service
        self.offer_verification_service = offer_verification_service
        self.decision_service = decision_service
        self.candidate_validation_service = (
            candidate_validation_service
            or CandidateValidationService(enabled=False)
        )
        self.trusted_vendor_domains = trusted_vendor_domains
        self.degraded_source_names = tuple(
            source_name.strip().lower()
            for source_name in degraded_source_names
            if source_name and source_name.strip()
        )

    async def compare(
        self,
        db: Session,
        query: str,
        *,
        location: str | None = None,
        pincode: str | None = None,
        ranking_mode: ComparisonRankingMode = "recommended",
        progress_callback: Callable[[int], None] | None = None,
    ) -> ComparisonResponse:
        query_understanding = understand_query(query.strip())
        normalized_query = query_understanding.corrected_query
        query_clarity = assess_query_clarity(normalized_query, query_understanding)
        if not query_clarity.is_clear:
            search_diagnostics = self._build_query_clarity_diagnostics(
                normalized_query,
                query_understanding,
                query_clarity,
                location=location,
                pincode=pincode,
            )
            return ComparisonResponse(
                query=normalized_query,
                ranking_mode=ranking_mode,
                location=location,
                pincode=pincode,
                results=[],
                search_diagnostics=self._build_search_diagnostics_summary(search_diagnostics),
            )

        search_context = await self.search_context_service.build(
            location=location,
            pincode=pincode,
        )
        live_search_diagnostics: SearchDiagnostics | None = None
        if normalized_query:
            primary_source_names = self._select_primary_source_names(normalized_query)
            coverage_requirements = self._build_live_search_coverage_requirements(
                normalized_query,
                primary_source_names,
            )
            foreground_timeout_seconds = self.LIVE_SEARCH_FOREGROUND_TIMEOUT_SECONDS
            live_listings, live_search_diagnostics = await self.scrape_service.fetch_live_listings_with_diagnostics(
                normalized_query,
                context=search_context,
                source_profile="primary",
                source_names=primary_source_names,
                foreground_timeout_seconds=foreground_timeout_seconds,
                source_foreground_timeout_seconds=self._source_foreground_timeout_overrides(
                    primary_source_names,
                    normalized_query,
                ),
                coverage_timeout_seconds=(
                    max(self.LIVE_SEARCH_COVERAGE_TIMEOUT_SECONDS, foreground_timeout_seconds)
                    if coverage_requirements
                    else None
                ),
                coverage_requirements=coverage_requirements,
                progress_callback=progress_callback,
            )
            self._apply_query_understanding_to_diagnostics(
                live_search_diagnostics,
                query_understanding,
                source_names=primary_source_names,
            )

            if live_listings:
                live_response = await self._build_live_comparison(
                    db,
                    normalized_query,
                    live_listings,
                    location=search_context.location,
                    pincode=search_context.pincode,
                    ranking_mode=ranking_mode,
                    search_diagnostics=live_search_diagnostics,
                )
                if live_response.results:
                    return live_response

            self.queue_service.enqueue_background_refresh(
                normalized_query,
                context=search_context,
            )

        products = self.product_service.match_products(db, normalized_query)
        if not products:
            return ComparisonResponse(
                query=normalized_query,
                ranking_mode=ranking_mode,
                location=search_context.location,
                pincode=search_context.pincode,
                results=[],
                search_diagnostics=self._build_search_diagnostics_summary(live_search_diagnostics),
            )

        product = self._select_product(products, normalized_query)
        listings = self.product_service.build_vendor_summaries(
            product,
            query=normalized_query,
        )
        verification_results = await self.offer_verification_service.verify_vendor_summaries(
            listings
        )
        return self.build_for_product(
            db,
            product,
            query=normalized_query,
            location=search_context.location,
            pincode=search_context.pincode,
            ranking_mode=ranking_mode,
            listings=listings,
            verification_results=verification_results,
            matched_products=products,
        )

    async def _build_live_comparison(
        self,
        db: Session,
        query: str,
        live_listings: list[ScrapedListing],
        *,
        location: str | None = None,
        pincode: str | None = None,
        ranking_mode: ComparisonRankingMode = "recommended",
        search_diagnostics: SearchDiagnostics | None = None,
    ) -> ComparisonResponse:
        validation_results = await self.candidate_validation_service.validate(
            query,
            live_listings,
        )
        self._apply_candidate_validation_to_diagnostics(
            search_diagnostics,
            query,
            validation_results,
        )
        groups = self._group_live_listings(
            query,
            live_listings,
            validation_results=validation_results,
        )
        if not groups:
            return ComparisonResponse(
                query=query,
                ranking_mode=ranking_mode,
                location=location,
                pincode=pincode,
                results=[],
                search_diagnostics=self._build_search_diagnostics_summary(search_diagnostics),
            )

        selected_group = self._select_live_group(groups, query)
        matched_product = self._resolve_catalog_product_for_live_group(
            db,
            selected_group,
            query=query,
        )
        latest_purchase = (
            self.procurement_service.latest_purchase_summary(db, matched_product.id)
            if matched_product is not None
            else None
        )
        selected_listings = self._build_live_vendor_listings(selected_group)
        verification_inputs = [
            self._build_live_vendor_summary(listing)
            for listing in selected_listings
        ]
        verification_results = await self.offer_verification_service.verify_vendor_summaries(
            verification_inputs
        )

        selected_comparison_items = [
            self._build_online_item(
                listing,
                latest_purchase=latest_purchase,
                verification_result=verification_results.get(listing.id),
            )
            for listing in selected_listings
        ]
        if matched_product is not None:
            selected_comparison_items.extend(
                self._build_offline_items(
                    db,
                    matched_product.id,
                    latest_purchase=latest_purchase,
                )
            )
        selected_comparison_items.sort(key=self._comparison_sort_key)
        additional_live_items = self._build_additional_live_group_items(
            groups=groups,
            selected_group=selected_group,
            selected_items=selected_comparison_items,
            latest_purchase=latest_purchase,
        )
        all_comparison_items = self._limit_live_results_per_vendor([
            *selected_comparison_items,
            *additional_live_items,
        ])
        benchmark = self._build_benchmark(all_comparison_items, latest_purchase)
        all_comparison_items = [
            self._with_reasonability(item, benchmark, latest_purchase)
            for item in all_comparison_items
        ]
        decision_summary = self.decision_service.build_summary(
            all_comparison_items,
            location=location,
            pincode=pincode,
        )
        recommended_items = self.decision_service.sort_items(
            all_comparison_items,
            "recommended",
            location=location,
            pincode=pincode,
        )
        ranked_items = self._sort_items_by_lowest_price(all_comparison_items)
        selected_product = LiveProductDescriptor(
            canonical_name=selected_group.canonical_name,
            brand=selected_group.brand,
            category=selected_group.category,
        )
        related_store_results = self._build_live_related_store_results(
            query=query,
            groups=groups,
            selected_group=selected_group,
            selected_listings_count=len(selected_listings),
            selected_product=selected_product,
            primary_items=ranked_items,
            latest_purchase=latest_purchase,
        )
        related_store_links = self._build_related_store_links(
            query=query,
            selected_product=selected_product,
            primary_items=ranked_items,
            related_store_results=related_store_results,
        )
        product_groups = self._build_live_product_groups(
            groups=groups,
            selected_group=selected_group,
            selected_items=ranked_items,
            latest_purchase=latest_purchase,
        )
        return ComparisonResponse(
            query=query,
            ranking_mode=ranking_mode,
            product_id=matched_product.id if matched_product is not None else None,
            product_name=selected_group.canonical_name,
            product_image_url=selected_group.image_url,
            location=location,
            pincode=pincode,
            latest_purchase=latest_purchase,
            benchmark=benchmark,
            best_option=self._build_best_option(recommended_items),
            decision_summary=decision_summary,
            results=ranked_items,
            product_groups=product_groups,
            related_store_results=related_store_results,
            related_store_links=related_store_links,
            search_diagnostics=self._build_search_diagnostics_summary(search_diagnostics),
        )

    def _group_live_listings(
        self,
        query: str,
        live_listings: list[ScrapedListing],
        *,
        validation_results: dict[int, CandidateValidationResult] | None = None,
    ) -> list[LiveProductGroup]:
        groups: list[LiveProductGroup] = []
        validation_results = validation_results or {}
        query_understanding = understand_query(query)
        indexed_listings = list(enumerate(live_listings))
        indexed_listings.sort(
            key=lambda item: (
                RELATION_PRIORITY.get(
                    validation_results.get(item[0]).relation
                    if validation_results.get(item[0]) is not None
                    else "uncertain",
                    RELATION_PRIORITY["uncertain"],
                ),
                -(
                    validation_results.get(item[0]).confidence
                    if validation_results.get(item[0]) is not None
                    else self._live_match_score(query, item[1])
                ),
                float(item[1].price),
                item[1].canonical_name.lower(),
            )
        )

        for index, listing in indexed_listings:
            validation = validation_results.get(index)
            if validation is not None and not self._validation_is_main_result(
                validation,
                query_understanding,
            ):
                continue
            relation = validation.relation if validation is not None else "uncertain"
            confidence = (
                validation.confidence
                if validation is not None
                else self._live_match_score(query, listing)
            )
            canonical_name = (
                validation.canonical_product
                if validation is not None and validation.canonical_product
                else listing.canonical_name
            )
            group_key = self._group_key(canonical_name)
            matching_group = next(
                (
                    group
                    for group in groups
                    if self._group_key(group.canonical_name) == group_key
                ),
                None,
            )
            if matching_group is None:
                groups.append(
                    LiveProductGroup(
                        canonical_name=canonical_name,
                        brand=listing.brand,
                        category=(
                            validation.product_family
                            if validation is not None and validation.product_family
                            else listing.category
                        ),
                        model_number=listing.model_number,
                        image_url=listing.image_url,
                        listings=[listing],
                        relation=relation,
                        match_confidence=confidence,
                        validation_reason=(
                            validation.reason if validation is not None else None
                        ),
                    )
                )
                continue

            matching_group.listings.append(listing)
            if confidence > matching_group.match_confidence:
                matching_group.match_confidence = confidence
                matching_group.validation_reason = (
                    validation.reason if validation is not None else matching_group.validation_reason
                )
            if RELATION_PRIORITY.get(relation, 99) < RELATION_PRIORITY.get(matching_group.relation, 99):
                matching_group.relation = relation

        return groups

    def _select_live_group(
        self,
        groups: list[LiveProductGroup],
        query: str,
    ) -> LiveProductGroup:
        ranked_groups: list[tuple[int, float, int, float, float, str, LiveProductGroup]] = []
        for group in groups:
            best_vendor_listings = select_best_live_listings_by_vendor(group.listings)
            if not best_vendor_listings:
                continue
            raw_score = max(self._live_match_score(query, listing) for listing in group.listings)
            ranked_groups.append(
                (
                    RELATION_PRIORITY.get(group.relation, RELATION_PRIORITY["uncertain"]),
                    group.match_confidence,
                    len(best_vendor_listings),
                    min(float(listing.price) for listing in best_vendor_listings),
                    raw_score,
                    group.canonical_name.lower(),
                    group,
                )
            )

        ranked_groups.sort(
            key=lambda item: (
                item[0],
                -item[1],
                -item[2],
                item[3],
                -item[4],
                item[5],
            )
        )
        return ranked_groups[0][6]

    def _group_key(self, value: str | None) -> str:
        normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
        return normalized or "unknown"

    def _build_live_product_groups(
        self,
        *,
        groups: list[LiveProductGroup],
        selected_group: LiveProductGroup,
        selected_items: list[ComparisonItem],
        latest_purchase: LatestPurchaseSummary | None,
    ) -> list[ProductGroupSummary]:
        summaries: list[ProductGroupSummary] = []
        selected_by_url = {
            item.product_url: item
            for item in selected_items
        }

        ordered_groups = sorted(
            groups,
            key=lambda group: (
                0 if group is selected_group else 1,
                RELATION_PRIORITY.get(group.relation, RELATION_PRIORITY["uncertain"]),
                -group.match_confidence,
                min(float(listing.price) for listing in group.listings),
                group.canonical_name.lower(),
            ),
        )

        for group in ordered_groups[:8]:
            if group is selected_group:
                items = selected_items
            else:
                items = [
                    selected_by_url.get(listing.product_url)
                    or self._build_online_item(
                        listing,
                        latest_purchase=latest_purchase,
                    )
                    for listing in self._build_live_vendor_listings(group)
                ]
                items.sort(key=self._comparison_sort_key)

            if not items:
                continue
            summaries.append(
                ProductGroupSummary(
                    label=group.canonical_name,
                    relation=group.relation,
                    confidence=round(group.match_confidence, 4),
                    result_count=len(items),
                    results=items[:6],
                )
            )
        return summaries

    def _build_additional_live_group_items(
        self,
        *,
        groups: list[LiveProductGroup],
        selected_group: LiveProductGroup,
        selected_items: list[ComparisonItem],
        latest_purchase: LatestPurchaseSummary | None,
    ) -> list[ComparisonItem]:
        seen_urls = {
            item.product_url
            for item in selected_items
            if item.product_url and not item.product_url.startswith("#")
        }
        seen_keys = {
            (
                item.vendor.lower(),
                item.product_name.lower(),
                round(item.price, 2),
            )
            for item in selected_items
        }
        candidates: list[tuple[int, float, float, str, ComparisonItem]] = []
        id_offset = len(selected_items)

        ordered_groups = sorted(
            (group for group in groups if group is not selected_group),
            key=lambda group: (
                RELATION_PRIORITY.get(group.relation, RELATION_PRIORITY["uncertain"]),
                -group.match_confidence,
                min(float(listing.price) for listing in group.listings),
                group.canonical_name.lower(),
            ),
        )

        for group in ordered_groups:
            for listing in self._build_live_vendor_listings(group, id_offset=id_offset):
                id_offset += 1
                if listing.product_url in seen_urls:
                    continue
                listing_key = (
                    listing.vendor.lower(),
                    listing.vendor_product_name.lower(),
                    round(float(listing.current_price), 2),
                )
                if listing_key in seen_keys:
                    continue
                seen_urls.add(listing.product_url)
                seen_keys.add(listing_key)
                item = self._build_online_item(
                    listing,
                    latest_purchase=latest_purchase,
                )
                candidates.append(
                    (
                        RELATION_PRIORITY.get(group.relation, RELATION_PRIORITY["uncertain"]),
                        item.landed_price,
                        item.price,
                        item.product_name,
                        item,
                    )
                )

        candidates.sort(key=lambda candidate: candidate[:4])
        return [candidate[-1] for candidate in candidates]

    def _limit_live_results_per_vendor(
        self,
        items: list[ComparisonItem],
    ) -> list[ComparisonItem]:
        vendor_counts: dict[str, int] = {}
        limited_items: list[ComparisonItem] = []

        for item in self._sort_items_by_lowest_price(self._dedupe_comparison_items(items)):
            if item.source_type != "online":
                limited_items.append(item)
                continue
            vendor_key = item.vendor.strip().lower()
            current_count = vendor_counts.get(vendor_key, 0)
            if current_count >= self.MAX_LIVE_RESULTS_PER_VENDOR:
                continue
            vendor_counts[vendor_key] = current_count + 1
            limited_items.append(item)

        return limited_items

    def _dedupe_comparison_items(
        self,
        items: list[ComparisonItem],
    ) -> list[ComparisonItem]:
        seen_urls: set[str] = set()
        seen_offer_keys: set[tuple[str, str, str, float, float]] = set()
        deduped: list[ComparisonItem] = []

        for item in self._sort_items_by_lowest_price(items):
            url_key = item.product_url.strip()
            if (
                item.source_type == "online"
                and url_key
                and not url_key.startswith("#")
                and url_key in seen_urls
            ):
                continue

            offer_key = (
                item.source_type,
                item.vendor.strip().lower(),
                self._group_key(item.product_name),
                round(item.price, 2),
                round(item.landed_price, 2),
            )
            if offer_key in seen_offer_keys:
                continue

            if item.source_type == "online" and url_key and not url_key.startswith("#"):
                seen_urls.add(url_key)
            seen_offer_keys.add(offer_key)
            deduped.append(item)

        return deduped

    def _sort_items_by_lowest_price(
        self,
        items: list[ComparisonItem],
    ) -> list[ComparisonItem]:
        return sorted(
            items,
            key=lambda item: (
                item.landed_price,
                item.price,
                -item.price_confidence,
                item.vendor.lower(),
                item.product_name.lower(),
            ),
        )

    def _adjusted_live_group_score(
        self,
        query: str,
        group: LiveProductGroup,
        *,
        raw_score: float,
    ) -> float:
        return max(raw_score - self._hardware_group_penalty(query, group), 0.0)

    def _hardware_group_penalty(
        self,
        query: str,
        group: LiveProductGroup,
    ) -> float:
        query_tokens = self._comparison_tokens(query)
        candidate_tokens = self._comparison_tokens(group.canonical_name, group.model_number)
        if not query_tokens or not candidate_tokens:
            return 0.0

        query_token_set = set(query_tokens)
        candidate_token_set = set(candidate_tokens)
        penalty = 0.0

        accessory_tokens = (
            candidate_token_set & self.HARDWARE_RANKING_ACCESSORY_TOKENS
        ) - query_token_set
        penalty += 0.08 * len(accessory_tokens)

        specialized_tokens = (
            candidate_token_set & self.HARDWARE_RANKING_SPECIALIZED_TOKENS
        ) - query_token_set
        penalty += 0.04 * len(specialized_tokens)
        penalty += 0.02 * self._candidate_only_model_token_count(
            query_token_set,
            candidate_token_set,
        )
        penalty += self._hardware_fitting_penalty(
            query_tokens,
            candidate_tokens,
        )

        if not query_token_set & {"pack", "pcs", "set"} and candidate_token_set & {"pack", "pcs", "set"}:
            penalty += 0.04

        return min(penalty, 0.24)

    def _candidate_only_model_token_count(
        self,
        query_tokens: set[str],
        candidate_tokens: set[str],
    ) -> int:
        return sum(
            1
            for token in candidate_tokens - query_tokens
            if 2 <= len(token) <= 4
            and any(character.isdigit() for character in token)
            and any(character.isalpha() for character in token)
        )

    def _hardware_fitting_penalty(
        self,
        query_tokens: list[str],
        candidate_tokens: list[str],
    ) -> float:
        penalty = 0.0
        for phrase_tokens, phrase_penalty in self.HARDWARE_FITTING_VARIANT_PENALTIES.items():
            if self._contains_token_phrase(query_tokens, phrase_tokens):
                continue
            if self._contains_token_phrase(candidate_tokens, phrase_tokens):
                penalty += phrase_penalty
        return penalty

    def _contains_token_phrase(
        self,
        tokens: list[str],
        phrase_tokens: tuple[str, ...],
    ) -> bool:
        phrase_length = len(phrase_tokens)
        if phrase_length == 0 or len(tokens) < phrase_length:
            return False
        return any(
            tuple(tokens[index:index + phrase_length]) == phrase_tokens
            for index in range(len(tokens) - phrase_length + 1)
        )

    def _comparison_tokens(self, *values: str | None) -> list[str]:
        return [
            token
            for value in values
            if value
            for token in re.findall(r"[a-z0-9]+", value.lower())
        ]

    def _select_primary_source_names(self, query: str) -> list[str] | None:
        configured_sources = list(getattr(self.scrape_service, "primary_sources", []) or [])
        if query_looks_like_hardware(query):
            hardware_sources = [
                source_name
                for source_name in self.HARDWARE_SOURCE_PRIORITY
                if source_name in configured_sources
            ]
            return hardware_sources or configured_sources or None
        return configured_sources or None

    def _source_foreground_timeout_overrides(
        self,
        source_names: list[str] | None,
        query: str,
    ) -> dict[str, float]:
        source_set = set(source_names or [])
        timeouts: dict[str, float] = {}
        if "amazon" in source_set:
            timeouts["Amazon"] = self.AMAZON_FOREGROUND_TIMEOUT_SECONDS
        if "robu" in source_set and query_looks_like_hardware(query):
            timeouts["Robu"] = self.ROBU_FOREGROUND_TIMEOUT_SECONDS
        return timeouts

    def _apply_candidate_validation_to_diagnostics(
        self,
        diagnostics: SearchDiagnostics | None,
        query: str,
        validation_results: dict[int, CandidateValidationResult],
    ) -> None:
        if diagnostics is None or not validation_results:
            return
        query_understanding = understand_query(query)
        sources = {
            result.source
            for result in validation_results.values()
            if result.source
        }
        accepted_count = sum(
            1
            for result in validation_results.values()
            if self._validation_is_main_result(result, query_understanding)
        )
        diagnostics.observed_offer_count = max(
            diagnostics.observed_offer_count,
            len(validation_results),
        )
        diagnostics.matched_offer_count = accepted_count
        diagnostics.add_filter(
            SearchFilterDiagnostic(
                key="candidate_relation_validation",
                label="Candidate relation validation",
                detail=(
                    "Confirmed direct-scraper candidates against the requested "
                    "sellable product using OpenRouter when available, with lexical fallback."
                ),
                source=",".join(sorted(sources)) or None,
                active=True,
                removed_count=len(validation_results) - accepted_count,
            )
        )

    def _validation_is_main_result(
        self,
        validation: CandidateValidationResult,
        query_understanding: QueryUnderstanding,
    ) -> bool:
        if validation.is_match is False:
            return False
        if validation.is_match is True:
            if validation.relation in {"unrelated", "uncertain"}:
                return False
            if validation.relation in self.QUERY_REQUESTED_RELATED_RELATIONS:
                return query_understanding.accessory_intent
            return True
        if validation.relation in self.MAIN_RESULT_RELATIONS:
            return True
        if (
            query_understanding.accessory_intent
            and validation.relation in self.QUERY_REQUESTED_RELATED_RELATIONS
        ):
            return True
        return False

    def _apply_query_understanding_to_diagnostics(
        self,
        diagnostics: SearchDiagnostics | None,
        understanding: QueryUnderstanding,
        *,
        source_names: list[str] | None,
    ) -> None:
        if diagnostics is None:
            return
        diagnostics.intent = understanding.intent
        diagnostics.corrected_query = (
            understanding.corrected_query
            if understanding.corrected_query.lower() != understanding.original_query.lower()
            else None
        )
        diagnostics.match_confidence = understanding.confidence
        diagnostics.source_groups_checked = self._source_group_labels(source_names)
        if any(
            filter_item.key == "source_coverage_incomplete"
            for filter_item in diagnostics.filters
        ):
            diagnostics.coverage_status = "incomplete"
        elif any(
            filter_item.key == "source_coverage_wait"
            for filter_item in diagnostics.filters
        ):
            diagnostics.coverage_status = "covered_after_wait"
        else:
            diagnostics.coverage_status = "complete"

    def _source_group_labels(self, source_names: list[str] | None) -> list[str]:
        labels: list[str] = []
        source_set = set(source_names or [])
        if source_set & {"moglix", "robu", "electronicscomp", "ibo", "global-electronics"}:
            labels.append("hardware stores")
        if source_set & {"amazon", "flipkart", "poorvika", "reliance-digital", "croma"}:
            labels.append("mainstream stores")
        return labels

    def _build_live_search_coverage_requirements(
        self,
        query: str,
        source_names: list[str] | None,
    ) -> tuple[SearchCoverageRequirement, ...]:
        return ()

    def _available_search_vendors(self, source_names: list[str] | None) -> set[str]:
        configured_source_names = (
            source_names
            or list(getattr(self.scrape_service, "primary_sources", []) or [])
        )
        scrapers_by_source = getattr(self.scrape_service, "scrapers_by_source", {}) or {}
        available_vendors: set[str] = set()
        for source_name in configured_source_names:
            normalized_source_name = source_name.strip().lower()
            scraper = scrapers_by_source.get(normalized_source_name)
            if scraper is not None:
                available_vendors.add(scraper.vendor_name)
            mapped_vendor = self.SOURCE_VENDOR_NAMES.get(normalized_source_name)
            if mapped_vendor is not None:
                available_vendors.add(mapped_vendor)
        return available_vendors

    def _build_live_vendor_listings(
        self,
        group: LiveProductGroup,
        *,
        id_offset: int = 0,
    ) -> list[LiveComparisonListing]:
        now = utc_now()
        return [
            LiveComparisonListing(
                id=-(id_offset + index + 1),
                vendor=listing.vendor,
                vendor_product_name=listing.vendor_product_name,
                product_url=listing.product_url,
                current_price=float(listing.price),
                raw_price=listing.raw_price,
                currency=listing.currency,
                rating=listing.rating,
                review_count=listing.review_count,
                delivery_info=listing.delivery_info,
                availability_status=listing.availability_status,
                sentiment_score=None,
                last_seen_at=now,
            )
            for index, listing in enumerate(self._ordered_live_group_listings(group.listings))
        ]

    def _ordered_live_group_listings(
        self,
        listings: list[ScrapedListing],
    ) -> list[ScrapedListing]:
        deduped_by_url: dict[str, ScrapedListing] = {}
        no_url_listings: list[ScrapedListing] = []
        for listing in listings:
            if not listing.product_url:
                no_url_listings.append(listing)
                continue
            current = deduped_by_url.get(listing.product_url)
            if current is None or (
                float(listing.price),
                -(listing.rating or 0),
                listing.vendor_product_name,
            ) < (
                float(current.price),
                -(current.rating or 0),
                current.vendor_product_name,
            ):
                deduped_by_url[listing.product_url] = listing

        return sorted(
            [*deduped_by_url.values(), *no_url_listings],
            key=lambda item: (
                float(item.price),
                -(item.rating or 0),
                item.vendor.lower(),
                item.vendor_product_name.lower(),
                item.product_url,
            ),
        )

    def _build_live_related_store_results(
        self,
        *,
        query: str,
        groups: list[LiveProductGroup],
        selected_group: LiveProductGroup,
        selected_listings_count: int,
        selected_product: LiveProductDescriptor,
        primary_items: list[ComparisonItem],
        latest_purchase: LatestPurchaseSummary | None,
    ) -> list[ComparisonItem]:
        related_items = list(primary_items[1:7]) if primary_items else []
        if len(related_items) >= 6:
            return related_items

        seen_vendors = {item.vendor for item in primary_items}
        seen_vendors.update(item.vendor for item in related_items)
        seen_urls = {item.product_url for item in primary_items}
        seen_urls.update(item.product_url for item in related_items)
        candidates: list[tuple[int, float, float, str, ComparisonItem]] = []
        id_offset = selected_listings_count

        for group in groups:
            if group is selected_group:
                continue
            for listing in self._build_live_vendor_listings(group, id_offset=id_offset):
                id_offset += 1
                if listing.vendor in seen_vendors or listing.product_url in seen_urls:
                    continue
                item = self._build_online_item(
                    listing,
                    latest_purchase=latest_purchase,
                )
                candidates.append(
                    (
                        RELATION_PRIORITY.get(group.relation, RELATION_PRIORITY["uncertain"]),
                        item.landed_price,
                        item.price,
                        item.product_name,
                        item,
                    )
                )

        candidates.sort(key=lambda item: item[:4])
        for _, _, _, _, item in candidates:
            if item.vendor in seen_vendors or item.product_url in seen_urls:
                continue
            related_items.append(item)
            seen_vendors.add(item.vendor)
            seen_urls.add(item.product_url)
            if len(related_items) >= 6:
                break

        return related_items

    def _live_group_has_variant_conflict(
        self,
        selected_group: LiveProductGroup,
        candidate_group: LiveProductGroup,
    ) -> bool:
        selected_tokens = self._variant_tokens(
            selected_group.canonical_name,
            selected_group.model_number,
        )
        candidate_tokens = self._variant_tokens(
            candidate_group.canonical_name,
            candidate_group.model_number,
        )
        restricted_variants = {"max", "mini", "plus", "pro", "ultra"}
        return any(
            token in candidate_tokens and token not in selected_tokens
            for token in restricted_variants
        )

    def _variant_tokens(self, *values: str | None) -> set[str]:
        return {
            token
            for value in values
            if value
            for token in re.findall(r"[a-z0-9]+", value.lower())
        }

    def _build_live_vendor_summary(
        self,
        listing: LiveComparisonListing,
    ) -> VendorListingSummary:
        return VendorListingSummary(
            id=listing.id,
            vendor=listing.vendor,
            vendor_product_name=listing.vendor_product_name,
            product_url=listing.product_url,
            current_price=listing.current_price,
            raw_price=listing.raw_price,
            currency=listing.currency,
            rating=listing.rating,
            review_count=listing.review_count,
            delivery_info=listing.delivery_info,
            availability_status=listing.availability_status,
            sentiment_score=listing.sentiment_score,
            last_seen_at=listing.last_seen_at,
        )

    def _live_group_matches_listing(
        self,
        group: LiveProductGroup,
        listing: ScrapedListing,
    ) -> bool:
        if self._live_listing_has_variant_conflict(group, listing):
            return False
        if self._live_listing_has_storage_conflict(group, listing):
            return False

        title_score = self._live_group_title_score(group, listing)
        model_keys_compatible = True
        if group.model_number and listing.model_number:
            model_keys_compatible = are_model_keys_compatible(
                group.model_number,
                listing.model_number,
            )
        if group.model_number and listing.model_number and model_keys_compatible:
            return True

        if (
            group.brand
            and listing.brand
            and group.brand.lower() != listing.brand.lower()
        ):
            return False
        if (
            group.category
            and listing.category
            and group.category.lower() != listing.category.lower()
            and title_score < 0.85
        ):
            return False

        if group.model_number and listing.model_number and not model_keys_compatible:
            if title_score < 0.85:
                return False

        return title_score >= 0.82

    def _live_group_title_score(
        self,
        group: LiveProductGroup,
        listing: ScrapedListing,
    ) -> float:
        return match_score(
            group.canonical_name,
            listing.canonical_name,
            listing.vendor_product_name,
            listing.model_number,
        )

    def _live_listing_has_variant_conflict(
        self,
        group: LiveProductGroup,
        listing: ScrapedListing,
    ) -> bool:
        group_tokens = self._variant_tokens(group.canonical_name, group.model_number)
        listing_tokens = self._variant_tokens(
            listing.canonical_name,
            listing.vendor_product_name,
            listing.model_number,
        )
        restricted_variants = {"max", "mini", "plus", "pro", "ultra"}
        return bool((group_tokens ^ listing_tokens) & restricted_variants)

    def _live_listing_has_storage_conflict(
        self,
        group: LiveProductGroup,
        listing: ScrapedListing,
    ) -> bool:
        group_storage = self._storage_tokens(group.canonical_name, group.model_number)
        listing_storage = self._storage_tokens(
            listing.canonical_name,
            listing.vendor_product_name,
            listing.model_number,
        )
        return group_storage != listing_storage and bool(group_storage or listing_storage)

    def _storage_tokens(self, *values: str | None) -> set[str]:
        tokens = [
            token
            for value in values
            if value
            for token in re.findall(r"[a-z0-9]+", value.lower())
        ]
        storage_tokens: set[str] = set()
        for index, token in enumerate(tokens):
            compact_match = re.fullmatch(r"(\d+)(gb|tb)", token)
            if compact_match:
                storage_tokens.add(f"{compact_match.group(1)}{compact_match.group(2)}")
                continue
            if (
                token.isdigit()
                and index + 1 < len(tokens)
                and tokens[index + 1] in {"gb", "tb"}
            ):
                storage_tokens.add(f"{token}{tokens[index + 1]}")
        return storage_tokens

    def _live_match_score(self, query: str, listing: ScrapedListing) -> float:
        return max(
            match_score(
                query,
                listing.canonical_name,
                listing.brand,
                listing.category,
                listing.model_number,
            ),
            match_score(
                query,
                listing.vendor_product_name,
                listing.brand,
                listing.category,
                listing.model_number,
            ),
        )

    def _resolve_catalog_product_for_live_group(
        self,
        db: Session,
        group: LiveProductGroup,
        *,
        query: str,
    ):
        candidates = self.product_service.match_products(db, group.canonical_name or query)
        ranked_candidates: list[tuple[float, object]] = []
        for candidate in candidates:
            if group.brand and candidate.brand and candidate.brand.lower() != group.brand.lower():
                continue
            if group.category and candidate.category and candidate.category.lower() != group.category.lower():
                continue

            score = match_score(
                group.canonical_name or query,
                candidate.canonical_name,
                candidate.brand,
                candidate.category,
                candidate.model_number,
            )
            if (
                group.model_number
                and candidate.model_number
                and are_model_keys_compatible(group.model_number, candidate.model_number)
            ):
                score += 0.2
            ranked_candidates.append((score, candidate))

        ranked_candidates.sort(
            key=lambda item: (
                -item[0],
                item[1].canonical_name,
            )
        )
        return ranked_candidates[0][1] if ranked_candidates else None

    def build_for_product(
        self,
        db: Session,
        product,
        *,
        query: str,
        location: str | None = None,
        pincode: str | None = None,
        ranking_mode: ComparisonRankingMode = "recommended",
        listings: list | None = None,
        verification_results: dict[int, OfferVerificationResult] | None = None,
        matched_products: list | None = None,
    ) -> ComparisonResponse:
        listings = listings or self.product_service.build_vendor_summaries(product)
        latest_purchase = self.procurement_service.latest_purchase_summary(db, product.id)
        comparison_items = self._build_comparison_items(
            db,
            product.id,
            listings,
            latest_purchase=latest_purchase,
            verification_results=verification_results or {},
        )
        decision_summary = self.decision_service.build_summary(
            comparison_items,
            location=location,
            pincode=pincode,
        )
        recommended_items = self.decision_service.sort_items(
            comparison_items,
            "recommended",
            location=location,
            pincode=pincode,
        )
        ranked_items = (
            recommended_items
            if ranking_mode == "recommended"
            else self.decision_service.sort_items(
                comparison_items,
                ranking_mode,
                location=location,
                pincode=pincode,
            )
        )
        related_store_results = self._build_related_store_results(
            db,
            query=query,
            selected_product=product,
            primary_items=ranked_items,
            matched_products=matched_products or [product],
            latest_purchase=latest_purchase,
        )
        related_store_links = self._build_related_store_links(
            query=query,
            selected_product=product,
            primary_items=ranked_items,
            related_store_results=related_store_results,
        )
        return ComparisonResponse(
            query=query,
            ranking_mode=ranking_mode,
            product_id=product.id,
            product_name=(
                recommended_items[0].product_name
                if recommended_items
                else product.canonical_name
            ),
            product_image_url=product.image_url,
            location=location,
            pincode=pincode,
            latest_purchase=latest_purchase,
            benchmark=self._build_benchmark(comparison_items, latest_purchase),
            best_option=self._build_best_option(recommended_items),
            decision_summary=decision_summary,
            results=ranked_items,
            related_store_results=related_store_results,
            related_store_links=related_store_links,
        )

    async def build_product_detail(
        self,
        db: Session,
        product_id: int,
        *,
        location: str | None = None,
        pincode: str | None = None,
        ranking_mode: ComparisonRankingMode = "recommended",
    ) -> ProductDetail:
        product = self.product_service.get_product(db, product_id)
        summary = self.product_service.build_product_summary(product)
        listings = self.product_service.build_vendor_summaries(product)
        verification_results = await self.offer_verification_service.verify_vendor_summaries(
            listings
        )
        comparison = self.build_for_product(
            db,
            product,
            query=product.canonical_name,
            location=location,
            pincode=pincode,
            ranking_mode=ranking_mode,
            listings=listings,
            verification_results=verification_results,
            matched_products=[product],
        )
        return ProductDetail(
            **summary.model_dump(),
            created_at=product.created_at,
            vendors=listings,
            comparison=comparison,
            offline_quotes=self.procurement_service.list_offline_quotes(db, product.id),
        )

    def _select_product(self, products: list, query: str):
        if len(products) == 1:
            return products[0]

        ranked = []
        for product in products:
            score = self.product_service.score_product(query, product)
            vendor_count = self.product_service.matching_vendor_count(product, query=query)
            best_price = self.product_service.best_price_value(product, query=query)
            ranked.append((score, vendor_count, best_price, product))

        top_score = max(score for score, _, _, _ in ranked)
        candidates = [
            item
            for item in ranked
            if item[0] >= top_score - self.BROAD_QUERY_SCORE_WINDOW
        ]
        candidates.sort(
            key=lambda item: (
                -item[1],
                item[2],
                -item[0],
                item[3].canonical_name,
            )
        )
        return candidates[0][3]

    def _build_related_store_results(
        self,
        db: Session,
        *,
        query: str,
        selected_product,
        primary_items: list[ComparisonItem],
        matched_products: list,
        latest_purchase: LatestPurchaseSummary | None,
    ) -> list[ComparisonItem]:
        if not primary_items:
            return []

        preferred_vendors = set(self._preferred_mainstream_vendors(selected_product, query=query))
        best_vendor_product_id = primary_items[0].vendor_product_id
        related_items = [
            item
            for item in primary_items
            if item.vendor_product_id != best_vendor_product_id
            and item.vendor in preferred_vendors
        ]
        seen_vendor_names = {item.vendor for item in related_items}
        blocked_vendor_names = {primary_items[0].vendor}
        blocked_listing_ids = {item.vendor_product_id for item in primary_items}

        fallback_candidates: list[tuple[int, float, float, str, object]] = []
        for product in matched_products:
            if product.id == selected_product.id:
                continue

            product_score = self.product_service.score_product(query, product)
            for listing in self.product_service.build_vendor_summaries(product):
                if listing.id in blocked_listing_ids:
                    continue
                if listing.vendor not in preferred_vendors:
                    continue
                if listing.vendor in blocked_vendor_names or listing.vendor in seen_vendor_names:
                    continue
                fallback_candidates.append(
                    (
                        self._vendor_priority(listing.vendor),
                        -product_score,
                        listing.current_price,
                        listing.vendor_product_name,
                        listing,
                    )
                )

        fallback_candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                item[3],
            )
        )

        for _, _, _, _, listing in fallback_candidates:
            if listing.vendor in seen_vendor_names:
                continue
            related_items.append(
                self._build_online_item(
                    listing,
                    latest_purchase=latest_purchase,
                )
            )
            seen_vendor_names.add(listing.vendor)
            if len(related_items) >= 6:
                break

        return related_items

    def _build_related_store_links(
        self,
        *,
        query: str,
        selected_product,
        primary_items: list[ComparisonItem],
        related_store_results: list[ComparisonItem],
    ) -> list[RelatedStoreLink]:
        minimum_store_count = 3
        covered_store_count = len(related_store_results)
        if covered_store_count >= minimum_store_count:
            return []

        vendor_search_query = selected_product.canonical_name or query
        seen_vendors = {item.vendor for item in related_store_results}
        if primary_items:
            seen_vendors.add(primary_items[0].vendor)

        fallback_links: list[RelatedStoreLink] = []
        for vendor_name in self._preferred_mainstream_vendors(selected_product, query=query):
            if vendor_name in seen_vendors:
                continue
            fallback_links.append(
                RelatedStoreLink(
                    vendor=vendor_name,
                    product_url=build_vendor_search_url(vendor_name, vendor_search_query),
                    search_label=vendor_search_query,
                    note="Direct store search for this product.",
                )
            )
            seen_vendors.add(vendor_name)
            if covered_store_count + len(fallback_links) >= minimum_store_count:
                break

        return fallback_links

    def _preferred_mainstream_vendors(self, product, *, query: str | None = None) -> list[str]:
        vendor_pool: list[str] = []
        category = (product.category or "").strip().lower()
        brand = (product.brand or "").strip()
        product_text = " ".join(
            part
            for part in (
                query,
                getattr(product, "canonical_name", None),
                getattr(product, "model_number", None),
                getattr(product, "category", None),
            )
            if part
        )

        hardware_category = any(
            token in category
            for token in (
                "hardware",
                "arduino",
                "robotics",
                "component",
                "module",
                "sensor",
            )
        )
        electronics_category = any(
            token in category
            for token in (
                "phone",
                "mobile",
                "smartphone",
                "laptop",
                "computer",
                "tablet",
                "audio",
                "wearable",
                "tv",
                "appliance",
                "electronics",
            )
        )

        if hardware_category or query_looks_like_hardware(product_text):
            vendor_pool.extend(
                [
                    "Moglix",
                    "Robu",
                    "ElectronicsComp",
                    "IBO",
                    "Global Electronics",
                    "Amazon",
                    "Flipkart",
                    "Reliance Digital",
                    "Poorvika",
                    "Croma",
                    "Vijay Sales",
                ]
            )
        elif electronics_category:
            vendor_pool.extend(
                [
                    "Amazon",
                    "Flipkart",
                    "Reliance Digital",
                    "Poorvika",
                    "Croma",
                    "Vijay Sales",
                    "Moglix",
                    "Robu",
                    "ElectronicsComp",
                    "IBO",
                    "Global Electronics",
                ]
            )
        else:
            vendor_pool.extend(
                ["Amazon", "Flipkart", "Reliance Digital", "Poorvika", "Tata Cliq", "JioMart"]
            )

        if brand and brand in self.MAINSTREAM_VENDOR_ORDER:
            vendor_pool.insert(0, brand)

        ordered_vendors = vendor_pool + list(self.MAINSTREAM_VENDOR_ORDER)
        unique_vendors: list[str] = []
        for vendor_name in ordered_vendors:
            if vendor_name in unique_vendors:
                continue
            unique_vendors.append(vendor_name)
        return [
            vendor_name
            for vendor_name in unique_vendors
            if vendor_name not in self._degraded_vendor_names()
        ]

    def _vendor_priority(self, vendor_name: str) -> int:
        try:
            return self.MAINSTREAM_VENDOR_ORDER.index(vendor_name)
        except ValueError:
            return len(self.MAINSTREAM_VENDOR_ORDER)

    def _degraded_vendor_names(self) -> set[str]:
        degraded_vendors: set[str] = set()
        for source_name in self.degraded_source_names:
            mapped_vendor = self.SOURCE_VENDOR_NAMES.get(source_name)
            if mapped_vendor is not None:
                degraded_vendors.add(mapped_vendor)
        return degraded_vendors

    def _build_search_diagnostics_summary(
        self,
        diagnostics: SearchDiagnostics | None,
    ) -> SearchDiagnosticsSummary | None:
        if diagnostics is None:
            return None
        return SearchDiagnosticsSummary(
            query=diagnostics.query,
            source_profile=diagnostics.source_profile,
            location=diagnostics.location,
            pincode=diagnostics.pincode,
            intent=diagnostics.intent,
            corrected_query=diagnostics.corrected_query,
            source_groups_checked=diagnostics.source_groups_checked,
            coverage_status=diagnostics.coverage_status,
            match_confidence=diagnostics.match_confidence,
            sources_checked=diagnostics.sources_checked,
            observed_offer_count=diagnostics.observed_offer_count,
            matched_offer_count=diagnostics.matched_offer_count,
            filters=[
                SearchFilterSummary(
                    key=filter_item.key,
                    label=filter_item.label,
                    detail=filter_item.detail,
                    source=filter_item.source,
                    active=filter_item.active,
                    removed_count=filter_item.removed_count,
                )
                for filter_item in diagnostics.filters
            ],
        )

    def _build_query_clarity_diagnostics(
        self,
        query: str,
        understanding: QueryUnderstanding,
        clarity: QueryClarity,
        *,
        location: str | None,
        pincode: str | None,
    ) -> SearchDiagnostics:
        diagnostics = SearchDiagnostics(
            query=query,
            source_profile="preflight",
            location=location,
            pincode=pincode,
            intent=understanding.intent,
            corrected_query=(
                understanding.corrected_query
                if understanding.corrected_query.lower() != understanding.original_query.lower()
                else None
            ),
            coverage_status="query_needs_clarification",
            match_confidence=understanding.confidence,
            sources_checked=[],
            observed_offer_count=0,
            matched_offer_count=0,
        )
        diagnostics.add_filter(
            SearchFilterDiagnostic(
                key="query_clarity",
                label="Query clarity",
                detail=clarity.detail or "Enter a clearer product name, category, brand, or model number.",
                active=True,
                removed_count=0,
            )
        )
        return diagnostics

    def _build_online_item(
        self,
        listing,
        *,
        latest_purchase: LatestPurchaseSummary | None,
        verification_result: OfferVerificationResult | None = None,
    ) -> ComparisonItem:
        vendor_domain = hostname_from_url(listing.product_url)
        shipping_cost = infer_shipping_cost(listing.delivery_info)
        verification_status = (
            verification_result.status
            if verification_result is not None
            else self._price_verification_status(listing)
        )
        effective_price = (
            verification_result.verified_price
            if verification_result is not None and verification_result.verified_price is not None
            else listing.current_price
        )
        landed_price = round(effective_price + (shipping_cost or 0), 2)
        if verification_status == "stale" and listing.last_seen_at is not None:
            logger.info(
                "stale_offer vendor=%s listing_id=%s last_seen_at=%s",
                listing.vendor,
                listing.id,
                listing.last_seen_at,
            )
        elif verification_status == "mismatch_detected":
            logger.warning(
                "comparison_price_warning vendor=%s listing_id=%s displayed_price=%.2f raw_price=%s verified_price=%s",
                listing.vendor,
                listing.id,
                listing.current_price,
                listing.raw_price,
                verification_result.verified_price if verification_result is not None else None,
            )
        elif verification_status == "incomplete":
            logger.warning(
                "comparison_price_incomplete vendor=%s listing_id=%s product_url=%s",
                listing.vendor,
                listing.id,
                listing.product_url,
            )
        return ComparisonItem(
            vendor_product_id=listing.id,
            vendor=listing.vendor,
            vendor_domain=vendor_domain,
            vendor_is_trusted=is_trusted_domain(vendor_domain, self.trusted_vendor_domains),
            product_name=listing.vendor_product_name,
            price=effective_price,
            displayed_price=effective_price,
            raw_price=listing.raw_price,
            rating=listing.rating,
            review_count=listing.review_count,
            delivery_info=listing.delivery_info,
            sentiment_score=listing.sentiment_score,
            availability_status=listing.availability_status,
            product_url=listing.product_url,
            shipping_cost=shipping_cost,
            estimated_delivery_days=infer_delivery_days(listing.delivery_info),
            seller_location=None,
            seller_pincode=None,
            landed_price=landed_price,
            source_type="online",
            price_verification_status=verification_status,
            price_confidence=(
                verification_result.confidence
                if verification_result is not None
                else self._price_confidence(verification_status)
            ),
            verified_price=(
                verification_result.verified_price
                if verification_result is not None
                else None
            ),
            price_verified_at=(
                verification_result.checked_at
                if verification_result is not None
                else None
            ),
            last_seen_at=listing.last_seen_at,
            reasonability_label="unknown",
            delta_from_median_percent=None,
            delta_from_last_purchase_percent=self._delta_percent(
                landed_price,
                latest_purchase.unit_price if latest_purchase else None,
            ),
        )

    def _build_offline_items(
        self,
        db: Session,
        product_id: int,
        *,
        latest_purchase: LatestPurchaseSummary | None,
    ) -> list[ComparisonItem]:
        items: list[ComparisonItem] = []
        for quote in self.procurement_service.list_offline_quotes(db, product_id):
            if not quote.is_active or quote.status not in {"submitted", "approved"}:
                continue
            landed_price = quote.quoted_price + quote.shipping_cost
            items.append(
                ComparisonItem(
                    vendor_product_id=-quote.id,
                    vendor=f"Offline · {quote.supplier_name}",
                    vendor_domain=None,
                    vendor_is_trusted=False,
                    product_name=f"Offline quote from {quote.supplier_name}",
                    price=quote.quoted_price,
                    displayed_price=quote.quoted_price,
                    rating=None,
                    review_count=0,
                    delivery_info=(
                        f"{quote.estimated_delivery_days} day estimate"
                        if quote.estimated_delivery_days is not None
                        else None
                    ),
                    sentiment_score=None,
                    availability_status="quoted",
                    product_url="#offline-quote",
                    shipping_cost=quote.shipping_cost,
                    estimated_delivery_days=quote.estimated_delivery_days,
                    seller_location=quote.seller_location,
                    seller_pincode=quote.pincode,
                    landed_price=landed_price,
                    source_type="offline",
                    price_verification_status="supplier-quoted",
                    price_confidence=self._price_confidence("supplier-quoted"),
                    verified_price=quote.quoted_price,
                    price_verified_at=quote.created_at,
                    last_seen_at=quote.created_at,
                    reasonability_label="unknown",
                    delta_from_median_percent=None,
                    delta_from_last_purchase_percent=self._delta_percent(
                        landed_price,
                        latest_purchase.unit_price if latest_purchase else None,
                    ),
                )
            )
        return items

    def _build_benchmark(
        self,
        comparison_items: list[ComparisonItem],
        latest_purchase: LatestPurchaseSummary | None,
    ) -> BenchmarkSummary | None:
        if not comparison_items:
            return None
        landed_prices = [item.landed_price for item in comparison_items]
        return BenchmarkSummary(
            min_price=min(landed_prices),
            max_price=max(landed_prices),
            average_price=round(sum(landed_prices) / len(landed_prices), 2),
            median_price=round(float(median(landed_prices)), 2),
            offer_count=len(landed_prices),
            last_purchase_unit_price=latest_purchase.unit_price if latest_purchase else None,
        )

    def _with_reasonability(
        self,
        item: ComparisonItem,
        benchmark: BenchmarkSummary | None,
        latest_purchase: LatestPurchaseSummary | None,
    ) -> ComparisonItem:
        if benchmark is None:
            return item

        delta_from_median = self._delta_percent(item.landed_price, benchmark.median_price)
        delta_from_last_purchase = self._delta_percent(
            item.landed_price,
            latest_purchase.unit_price if latest_purchase else None,
        )
        label = "fair"
        if delta_from_median is not None:
            if delta_from_median <= -10:
                label = "below-market"
            elif delta_from_median >= 10:
                label = "above-market"

        return item.model_copy(
            update={
                "reasonability_label": label,
                "delta_from_median_percent": delta_from_median,
                "delta_from_last_purchase_percent": delta_from_last_purchase,
            }
        )

    def _build_comparison_items(
        self,
        db: Session,
        product_id: int,
        listings: list,
        *,
        latest_purchase: LatestPurchaseSummary | None,
        verification_results: dict[int, OfferVerificationResult],
    ) -> list[ComparisonItem]:
        comparison_items = [
            self._build_online_item(
                listing,
                latest_purchase=latest_purchase,
                verification_result=verification_results.get(listing.id),
            )
            for listing in listings
        ]
        comparison_items.extend(
            self._build_offline_items(
                db,
                product_id,
                latest_purchase=latest_purchase,
            )
        )
        comparison_items.sort(key=self._comparison_sort_key)
        benchmark = self._build_benchmark(comparison_items, latest_purchase)
        return [
            self._with_reasonability(item, benchmark, latest_purchase)
            for item in comparison_items
        ]

    def _build_best_option(self, comparison_items: list[ComparisonItem]) -> BestOption | None:
        best_listing = comparison_items[0] if comparison_items else None
        if best_listing is None:
            return None
        return BestOption(
            vendor=best_listing.vendor,
            price=best_listing.price,
            product_url=best_listing.product_url,
            vendor_product_id=best_listing.vendor_product_id,
        )

    def _comparison_sort_key(self, item: ComparisonItem) -> tuple[int, float, float, str]:
        trust_bucket = 0 if item.price_confidence >= self.TRUSTED_PRICE_CONFIDENCE else 1
        return (
            trust_bucket,
            item.landed_price,
            item.price,
            item.vendor,
        )

    def _price_verification_status(self, listing) -> str:
        if not listing.product_url:
            return "incomplete"
        if self._raw_price_mismatch(listing):
            return "mismatch_detected"
        if listing.last_seen_at is None:
            return "fresh_unverified"
        observed_at = self._normalize_timestamp(listing.last_seen_at)
        age = self._now() - observed_at
        if age <= self.FRESH_PRICE_WINDOW:
            return "fresh_unverified"
        return "stale"

    def _price_confidence(self, status: str) -> float:
        return {
            "verified": 1.0,
            "supplier-quoted": 0.9,
            "fresh_unverified": 0.7,
            "stale": 0.35,
            "mismatch_detected": 0.0,
            "incomplete": 0.15,
        }.get(status, 0.25)

    def _now(self):
        from app.utils.time_utils import utc_now

        return utc_now()

    def _normalize_timestamp(self, value):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _raw_price_mismatch(self, listing) -> bool:
        raw_amount = self._extract_amount(listing.raw_price)
        if raw_amount is None:
            return False
        return abs(raw_amount - float(listing.current_price)) > 0.01

    def _extract_amount(self, raw_price: str | None) -> float | None:
        if not raw_price:
            return None
        match = re.search(r"(\d[\d,]*(?:\.\d+)?)", raw_price)
        if match is None:
            return None
        return float(match.group(1).replace(",", ""))

    def _delta_percent(self, current: float, baseline: float | None) -> float | None:
        if baseline in (None, 0):
            return None
        return round(((current - baseline) / baseline) * 100, 2)
