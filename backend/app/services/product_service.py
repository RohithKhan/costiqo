from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.queue_service import QueueService
    from app.services.scrape_service import ScrapeService
    from app.services.search_context_service import SearchContextService

from dataclasses import dataclass
import logging
import re

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.product import Product
from app.db.models.vendor_product import VendorProduct
from app.scrapers.base import ScrapedListing
from app.schemas.product import (
    ProductDetail,
    ProductSummary,
    SearchResponse,
    SearchSuggestion,
    SuggestionResponse,
    SuggestionStorePreview,
    VendorListingSummary,
)
from app.schemas.comparison import SearchDiagnosticsSummary, SearchFilterSummary
from app.scrapers.normalizers import has_identifier_conflict, listing_matches_query, match_score
from app.services.query_understanding_service import (
    QueryClarity,
    QueryUnderstanding,
    assess_query_clarity,
    understand_query,
)
from app.services.source_selection import (
    query_looks_like_hardware,
    select_query_suggestion_sources,
)
from app.utils.product_identity import are_model_keys_compatible
from app.utils.vendor_links import resolve_vendor_url
from app.utils.text_cleaner import tokenize


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiveSuggestionGroup:
    canonical_name: str
    brand: str | None
    category: str | None
    model_number: str | None
    image_url: str | None
    listings: list[ScrapedListing]


def select_best_listings_by_vendor(listings: list[VendorProduct]) -> list[VendorProduct]:
    listings_by_vendor: dict[str, VendorProduct] = {}

    for listing in listings:
        current_best = listings_by_vendor.get(listing.vendor.name)
        if current_best is None:
            listings_by_vendor[listing.vendor.name] = listing
            continue

        if (
            float(listing.current_price),
            -(listing.rating or 0),
            listing.vendor_product_name,
        ) < (
            float(current_best.current_price),
            -(current_best.rating or 0),
            current_best.vendor_product_name,
        ):
            listings_by_vendor[listing.vendor.name] = listing

    return sorted(
        listings_by_vendor.values(),
        key=lambda item: (
            float(item.current_price),
            -(item.rating or 0),
            item.vendor.name,
        ),
    )


def select_best_scraped_listings_by_vendor(listings: list[ScrapedListing]) -> list[ScrapedListing]:
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


class ProductService:
    SUGGESTION_EXPENSIVE_SOURCE_NAMES = {
        "amazon",
        "flipkart",
        "reliance-digital",
        "robu",
    }

    def __init__(
        self,
        scrape_service: "ScrapeService",
        search_context_service: "SearchContextService",
        queue_service: "QueueService",
    ) -> None:
        self.scrape_service = scrape_service
        self.search_context_service = search_context_service
        self.queue_service = queue_service

    async def search(
        self,
        db: Session,
        query: str,
        *,
        location: str | None = None,
        pincode: str | None = None,
    ) -> SearchResponse:
        query_understanding = understand_query(query.strip())
        normalized_query = query_understanding.corrected_query
        query_clarity = assess_query_clarity(normalized_query, query_understanding)
        if not query_clarity.is_clear:
            return SearchResponse(
                query=normalized_query,
                results=[],
                search_diagnostics=self._build_query_clarity_diagnostics(
                    normalized_query,
                    query_understanding,
                    query_clarity,
                    location=location,
                    pincode=pincode,
                ),
            )

        search_context = await self.search_context_service.build(
            location=location,
            pincode=pincode,
        )
        if normalized_query:
            source_names = self._select_primary_source_names(normalized_query)
            await self.scrape_service.scrape_query(
                db,
                normalized_query,
                context=search_context,
                source_profile="primary",
                source_names=source_names,
            )
            self.queue_service.enqueue_background_refresh(
                normalized_query,
                context=search_context,
            )
        products = self.match_products(db, normalized_query)
        return SearchResponse(
            query=normalized_query,
            results=[self.build_product_summary(product, query=normalized_query) for product in products],
        )

    async def suggest(
        self,
        db: Session,
        query: str,
        *,
        location: str | None = None,
        pincode: str | None = None,
        limit: int = 6,
    ) -> SuggestionResponse:
        normalized_query = understand_query(query.strip()).corrected_query
        source_names = self._select_live_suggestion_sources(normalized_query, limit=5)
        source_labels = self._suggestion_source_labels(source_names)
        if len(normalized_query) < 2:
            return SuggestionResponse(query=normalized_query, sources=source_labels, results=[])

        search_context = await self.search_context_service.build(
            location=location,
            pincode=pincode,
        )
        live_listings = await self.scrape_service.fetch_live_listings(
            normalized_query,
            context=search_context,
            source_profile="primary",
            source_names=source_names,
        )
        live_results = self.build_live_search_suggestions(
            normalized_query,
            live_listings,
            limit=limit,
        )
        if live_results:
            return SuggestionResponse(
                query=normalized_query,
                sources=source_labels,
                results=live_results,
            )

        products = self.suggest_products(db, normalized_query, limit=limit)
        return SuggestionResponse(
            query=normalized_query,
            sources=source_labels,
            results=[self.build_search_suggestion(product) for product in products],
        )

    def match_products(self, db: Session, query: str) -> list[Product]:
        products = self._load_products(db, query=query)
        scored_products: list[tuple[float, int, float, Product]] = []
        for product in products:
            if not product.vendor_products:
                continue
            if has_identifier_conflict(
                query,
                product.canonical_name,
                product.brand,
                product.category,
                product.model_number,
            ):
                continue
            if query and not listing_matches_query(
                query,
                product.canonical_name,
                product.brand,
                product.category,
                product.model_number,
            ):
                continue
            score = self.score_product(query, product)
            if query and score < 0.35:
                continue

            vendor_count = self.matching_vendor_count(product, query=query)
            if query and vendor_count == 0:
                continue

            best_price = self.best_price_value(product, query=query)
            scored_products.append(
                (
                    score,
                    vendor_count,
                    best_price if best_price is not None else float("inf"),
                    product,
                )
            )

        scored_products.sort(key=lambda item: (-item[0], -item[1], item[2], item[3].canonical_name))
        return [product for _, _, _, product in scored_products]

    def suggest_products(
        self,
        db: Session,
        query: str,
        *,
        limit: int = 6,
    ) -> list[Product]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        products = self._load_products(db, query=normalized_query, limit=max(limit * 10, 60))
        scored_products: list[tuple[float, float, float, Product]] = []
        compact_query = self._compact_query(normalized_query)
        query_lower = normalized_query.lower()
        requires_precise_model_match = self._query_requires_precise_model_match(normalized_query)

        for product in products:
            if not product.vendor_products:
                continue

            haystack = " ".join(
                filter(
                    None,
                    (
                        product.canonical_name,
                        product.brand,
                        product.category,
                        product.model_number,
                    ),
                )
            )
            haystack_lower = haystack.lower()
            compact_haystack = self._compact_query(haystack)
            score = self.score_product(normalized_query, product)
            strict_match = listing_matches_query(
                normalized_query,
                product.canonical_name,
                product.brand,
                product.category,
                product.model_number,
            )
            has_conflict = has_identifier_conflict(
                normalized_query,
                product.canonical_name,
                product.brand,
                product.category,
                product.model_number,
            )
            if has_conflict:
                continue

            contains_query = query_lower in haystack_lower
            compact_match = len(compact_query) >= 3 and compact_query in compact_haystack
            prefix_match = any(
                token.startswith(query_lower)
                for token in haystack_lower.split()
                if token
            )
            if requires_precise_model_match:
                if not (strict_match or contains_query or compact_match):
                    continue
            elif not (strict_match or contains_query or compact_match or prefix_match or score >= 0.25):
                continue

            suggestion_score = score
            if strict_match:
                suggestion_score = max(suggestion_score, 0.98)
            elif contains_query:
                suggestion_score = max(suggestion_score, 0.96)
            elif compact_match:
                suggestion_score = max(suggestion_score, 0.9)
            elif prefix_match:
                suggestion_score = max(suggestion_score, 0.72)

            best_price = self.best_price_value(product)
            vendor_count = len(select_best_listings_by_vendor(product.vendor_products))
            scored_products.append(
                (
                    suggestion_score,
                    float(vendor_count),
                    best_price if best_price is not None else float("inf"),
                    product,
                )
            )

        scored_products.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                item[2],
                item[3].canonical_name,
            )
        )
        return [product for _, _, _, product in scored_products[:limit]]

    def get_product_detail(self, db: Session, product_id: int) -> ProductDetail:
        product = self.get_product(db, product_id)
        summary = self.build_product_summary(product)
        return ProductDetail(
            **summary.model_dump(),
            created_at=product.created_at,
            vendors=self.build_vendor_summaries(product),
        )

    def get_product_vendors(self, db: Session, product_id: int) -> list[VendorListingSummary]:
        product = self.get_product(db, product_id)
        return self.build_vendor_summaries(product)

    def get_product(self, db: Session, product_id: int) -> Product:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.vendor_products).selectinload(VendorProduct.vendor),
                selectinload(Product.vendor_products).selectinload(VendorProduct.sentiment_summary),
                selectinload(Product.vendor_products).selectinload(VendorProduct.price_snapshots),
            )
            .where(Product.id == product_id)
        )
        product = db.scalar(stmt)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found.",
            )
        return product

    def build_product_summary(self, product: Product, *, query: str | None = None) -> ProductSummary:
        best_listing = self._best_listing(product, query=query)
        return ProductSummary(
            id=product.id,
            canonical_name=product.canonical_name,
            brand=product.brand,
            category=product.category,
            model_number=product.model_number,
            image_url=product.image_url,
            best_price=float(best_listing.current_price) if best_listing else None,
            best_vendor=best_listing.vendor.name if best_listing else None,
            best_product_url=(
                resolve_vendor_url(
                    best_listing.vendor.name,
                    best_listing.vendor_product_url,
                    best_listing.vendor_product_name,
                )
                if best_listing
                else None
            ),
            vendor_count=self.matching_vendor_count(product, query=query),
        )

    def build_vendor_summaries(
        self,
        product: Product,
        *,
        query: str | None = None,
    ) -> list[VendorListingSummary]:
        listings = select_best_listings_by_vendor(
            self._matching_vendor_products(product, query=query)
        )
        return [self._serialize_vendor_listing(listing) for listing in listings]

    def build_search_suggestion(self, product: Product) -> SearchSuggestion:
        best_listing = self._best_listing(product)
        source_stores = [
            SuggestionStorePreview(
                vendor=listing.vendor.name,
                price=float(listing.current_price),
            )
            for listing in select_best_listings_by_vendor(product.vendor_products)[:4]
        ]
        return SearchSuggestion(
            id=product.id,
            canonical_name=product.canonical_name,
            brand=product.brand,
            category=product.category,
            image_url=product.image_url,
            best_price=float(best_listing.current_price) if best_listing else None,
            best_vendor=best_listing.vendor.name if best_listing else None,
            vendor_count=len(select_best_listings_by_vendor(product.vendor_products)),
            live_store_count=len(source_stores),
            source_stores=source_stores,
        )

    def build_live_search_suggestions(
        self,
        query: str,
        live_listings: list[ScrapedListing],
        *,
        limit: int,
    ) -> list[SearchSuggestion]:
        if not live_listings:
            return []

        matched_listings = [
            listing
            for listing in live_listings
            if listing_matches_query(
                query,
                listing.canonical_name,
                listing.vendor_product_name,
                listing.brand,
                listing.category,
                listing.model_number,
            )
        ]
        matched_listings.sort(
            key=lambda listing: (
                -self._live_suggestion_match_score(query, listing),
                float(listing.price),
                listing.canonical_name.lower(),
            )
        )

        groups: list[LiveSuggestionGroup] = []
        for listing in matched_listings:
            matching_group = next(
                (
                    group
                    for group in groups
                    if self._live_suggestion_group_matches_listing(group, listing)
                ),
                None,
            )
            if matching_group is None:
                groups.append(
                    LiveSuggestionGroup(
                        canonical_name=listing.canonical_name,
                        brand=listing.brand,
                        category=listing.category,
                        model_number=listing.model_number,
                        image_url=listing.image_url,
                        listings=[listing],
                    )
                )
                continue
            matching_group.listings.append(listing)

        scored_suggestions: list[tuple[float, int, float, SearchSuggestion]] = []
        for index, group in enumerate(groups):
            best_vendor_listings = select_best_scraped_listings_by_vendor(group.listings)
            if not best_vendor_listings:
                continue
            live_stores = [
                SuggestionStorePreview(
                    vendor=listing.vendor,
                    price=float(listing.price),
                )
                for listing in best_vendor_listings[:4]
            ]
            best_listing = best_vendor_listings[0]
            suggestion = SearchSuggestion(
                id=-(index + 1),
                canonical_name=group.canonical_name,
                brand=group.brand,
                category=group.category,
                image_url=group.image_url,
                best_price=float(best_listing.price),
                best_vendor=best_listing.vendor,
                vendor_count=len(best_vendor_listings),
                live_store_count=len(live_stores),
                source_stores=live_stores,
            )
            scored_suggestions.append(
                (
                    max(self._live_suggestion_match_score(query, listing) for listing in group.listings),
                    suggestion.live_store_count,
                    suggestion.best_price if suggestion.best_price is not None else float("inf"),
                    suggestion,
                )
            )

        if query_looks_like_hardware(query):
            scored_suggestions.sort(
                key=lambda item: (
                    -int(item[0] * 20),
                    item[2],
                    -item[1],
                    item[3].canonical_name,
                )
            )
        else:
            scored_suggestions.sort(
                key=lambda item: (
                    -item[0],
                    -item[1],
                    item[2],
                    item[3].canonical_name,
                )
            )
        return [suggestion for _, _, _, suggestion in scored_suggestions[:limit]]

    def score_product(self, query: str, product: Product) -> float:
        if not query:
            return 1.0

        score = match_score(
            query,
            product.canonical_name,
            product.brand,
            product.category,
            product.model_number,
        )
        if has_identifier_conflict(
            query,
            product.canonical_name,
            product.brand,
            product.category,
            product.model_number,
        ):
            return 0.0
        if score >= 0.35:
            return score

        compact_query = self._compact_query(query)
        compact_product = self._compact_query(
            " ".join(
                filter(
                    None,
                    (
                        product.canonical_name,
                        product.brand,
                        product.category,
                        product.model_number,
                    ),
                )
            )
        )
        if len(compact_query) >= 5 and compact_query in compact_product:
            return 0.8

        return score

    def best_price_value(self, product: Product, *, query: str | None = None) -> float | None:
        return self._best_price(product, query=query)

    @staticmethod
    def _build_product_search_filter(query: str):
        if not query or not query.strip():
            return None
        raw_tokens = [tok.strip().lower() for tok in re.split(r"[\s\-_/]+", query) if len(tok.strip()) >= 2]
        compact = "".join(ch for ch in query.lower() if ch.isalnum())
        tokens: list[str] = []
        seen = set()
        for tok in raw_tokens:
            if tok not in seen:
                seen.add(tok)
                tokens.append(tok)
        if len(compact) >= 3 and compact not in seen:
            tokens.append(compact)

        if not tokens:
            return None

        clauses = []
        for tok in tokens[:8]:
            clean_tok = "".join(ch for ch in tok if ch.isalnum() or ch in ".-")
            if not clean_tok:
                continue
            pattern = f"%{clean_tok}%"
            clauses.extend(
                [
                    Product.canonical_name.ilike(pattern),
                    Product.brand.ilike(pattern),
                    Product.model_number.ilike(pattern),
                    Product.category.ilike(pattern),
                ]
            )
        return or_(*clauses) if clauses else None

    def _load_products(
        self,
        db: Session,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[Product]:
        stmt = select(Product).options(
            selectinload(Product.vendor_products).selectinload(VendorProduct.vendor),
            selectinload(Product.vendor_products).selectinload(VendorProduct.sentiment_summary),
        )
        if query:
            filter_clause = self._build_product_search_filter(query)
            if filter_clause is not None:
                stmt = stmt.where(filter_clause)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(db.scalars(stmt).unique().all())

    def _load_products_by_ids(self, db: Session, product_ids: list[int]) -> dict[int, Product]:
        if not product_ids:
            return {}

        stmt = (
            select(Product)
            .options(
                selectinload(Product.vendor_products).selectinload(VendorProduct.vendor),
                selectinload(Product.vendor_products).selectinload(VendorProduct.sentiment_summary),
            )
            .where(Product.id.in_(product_ids))
        )
        products = db.scalars(stmt).unique().all()
        return {product.id: product for product in products}

    def _best_listing(self, product: Product, *, query: str | None = None) -> VendorProduct | None:
        listings = select_best_listings_by_vendor(
            self._matching_vendor_products(product, query=query)
        )
        return listings[0] if listings else None

    def _best_price(self, product: Product, *, query: str | None = None) -> float | None:
        listing = self._best_listing(product, query=query)
        return float(listing.current_price) if listing else None

    def matching_vendor_count(self, product: Product, *, query: str | None = None) -> int:
        return len(
            select_best_listings_by_vendor(
                self._matching_vendor_products(product, query=query)
            )
        )

    def _select_primary_source_names(self, query: str) -> list[str] | None:
        configured_sources = list(self.scrape_service.primary_sources or [])
        return configured_sources or None

    def _select_live_suggestion_sources(self, query: str, *, limit: int) -> list[str]:
        configured_sources = self.scrape_service.primary_sources or list(self.scrape_service.scrapers_by_source)
        safe_sources = [
            source_name
            for source_name in configured_sources
            if not self._source_is_expensive_for_suggestions(source_name)
        ]
        return select_query_suggestion_sources(safe_sources, query, limit=limit)

    def _source_is_expensive_for_suggestions(self, source_name: str) -> bool:
        if source_name in self.SUGGESTION_EXPENSIVE_SOURCE_NAMES:
            return True
        scraper = self.scrape_service.scrapers_by_source.get(source_name)
        if scraper is None:
            return False
        scrape_strategy = getattr(scraper, "scrape_strategy", "")
        return "live-playwright" in scrape_strategy

    def _suggestion_source_labels(self, source_names: list[str]) -> list[str]:
        labels: list[str] = []
        for source_name in source_names:
            scraper = self.scrape_service.scrapers_by_source.get(source_name)
            if scraper is None:
                continue
            if scraper.vendor_name not in labels:
                labels.append(scraper.vendor_name)
        return labels

    def _matching_vendor_products(
        self,
        product: Product,
        *,
        query: str | None = None,
    ) -> list[VendorProduct]:
        if not query:
            return list(product.vendor_products)

        return [
            listing
            for listing in product.vendor_products
            if listing_matches_query(
                query,
                listing.vendor_product_name,
                product.brand,
                product.category,
            )
        ]

    def _serialize_vendor_listing(self, listing: VendorProduct) -> VendorListingSummary:
        resolved_url = resolve_vendor_url(
            listing.vendor.name,
            listing.vendor_product_url,
            listing.vendor_product_name,
        )
        warnings: list[str] = []
        if resolved_url.startswith("#"):
            warnings.append("missing_vendor_url")
        if not listing.raw_price:
            warnings.append("missing_raw_price")
        if warnings:
            logger.warning(
                "normalization_warning listing_id=%s vendor=%s product=%s warnings=%s",
                listing.id,
                listing.vendor.name,
                listing.vendor_product_name,
                ",".join(warnings),
            )
        return VendorListingSummary(
            id=listing.id,
            vendor=listing.vendor.name,
            vendor_product_name=listing.vendor_product_name,
            product_url=resolved_url,
            current_price=float(listing.current_price),
            raw_price=listing.raw_price,
            currency=listing.currency,
            rating=listing.rating,
            review_count=listing.review_count,
            delivery_info=listing.delivery_info,
            availability_status=listing.availability_status,
            sentiment_score=(
                float(listing.sentiment_summary.sentiment_score)
                if listing.sentiment_summary
                else None
            ),
            last_seen_at=listing.last_seen_at,
        )

    def _live_suggestion_group_matches_listing(
        self,
        group: LiveSuggestionGroup,
        listing: ScrapedListing,
    ) -> bool:
        if group.model_number and listing.model_number:
            return are_model_keys_compatible(group.model_number, listing.model_number)

        if group.brand and listing.brand and group.brand.lower() != listing.brand.lower():
            return False
        if group.category and listing.category and group.category.lower() != listing.category.lower():
            return False

        return (
            match_score(
                group.canonical_name,
                listing.canonical_name,
                listing.vendor_product_name,
                listing.model_number,
            )
            >= 0.82
        )

    def _live_suggestion_match_score(self, query: str, listing: ScrapedListing) -> float:
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

    def _compact_query(self, value: str) -> str:
        return "".join(tokenize(value))

    def _query_requires_precise_model_match(self, query: str) -> bool:
        informative_tokens = [
            token
            for token in tokenize(query)
            if any(character.isdigit() for character in token) or len(token) >= 4
        ]
        return len(informative_tokens) >= 2 or any(
            any(character.isdigit() for character in token)
            for token in informative_tokens
        )

    def _build_query_clarity_diagnostics(
        self,
        query: str,
        understanding: QueryUnderstanding,
        clarity: QueryClarity,
        *,
        location: str | None,
        pincode: str | None,
    ) -> SearchDiagnosticsSummary:
        return SearchDiagnosticsSummary(
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
            filters=[
                SearchFilterSummary(
                    key="query_clarity",
                    label="Query clarity",
                    detail=clarity.detail or "Enter a clearer product name, category, brand, or model number.",
                    active=True,
                    removed_count=0,
                )
            ],
        )
