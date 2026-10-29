from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.offline_quote import OfflineQuote
from app.db.models.product import Product
from app.db.models.purchase_record import PurchaseRecord
from app.db.models.purchase_record_quote import PurchaseRecordQuote
from app.db.models.vendor_product import VendorProduct
from app.schemas.procurement import (
    LatestPurchaseSummary,
    OfflineQuoteCreateRequest,
    OfflineQuoteResponse,
    OfflineQuoteUpdateRequest,
    ProcurementStatusCount,
    ProcurementSummaryResponse,
    PurchaseRecordCreateRequest,
    PurchaseBenchmarkSummary,
    PurchaseRecordResponse,
    SupplierCompetitivenessSummary,
)
from app.utils.delivery_parser import infer_shipping_cost
from app.utils.time_utils import utc_now


class ProcurementService:
    QUOTE_STATUSES = {
        "draft",
        "submitted",
        "approved",
        "purchased",
        "closed",
        "expired",
    }
    ACTIVE_QUOTE_STATUSES = {"submitted", "approved"}
    FINAL_QUOTE_STATUSES = {"purchased", "closed", "expired"}
    QUOTE_STATUS_TRANSITIONS = {
        "draft": {"draft", "submitted", "closed", "expired"},
        "submitted": {"submitted", "approved", "closed", "expired"},
        "approved": {"approved", "purchased", "closed", "expired"},
        "purchased": {"purchased", "closed"},
        "closed": {"closed"},
        "expired": {"expired"},
    }
    EXPIRING_SOON_DAYS = 7

    def create_offline_quote(
        self,
        db: Session,
        payload: OfflineQuoteCreateRequest,
    ) -> OfflineQuoteResponse:
        self._ensure_product_exists(db, payload.product_id)
        now = utc_now()
        quote = OfflineQuote(
            product_id=payload.product_id,
            supplier_name=payload.supplier_name,
            quoted_price=Decimal(str(payload.quoted_price)),
            shipping_cost=Decimal(str(payload.shipping_cost)),
            currency=payload.currency,
            seller_location=payload.seller_location,
            pincode=payload.pincode,
            estimated_delivery_days=payload.estimated_delivery_days,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            quote_reference=payload.quote_reference,
            status=payload.status,
            supplier_score=payload.supplier_score,
            notes=payload.notes,
            valid_until=payload.valid_until,
            is_active=payload.is_active,
            submitted_at=now if payload.status in {"submitted", "approved", "purchased", "closed"} else None,
            approved_at=now if payload.status in {"approved", "purchased", "closed"} else None,
            closed_at=now if payload.status in self.FINAL_QUOTE_STATUSES else None,
        )
        self._apply_quote_lifecycle_state(
            quote,
            next_status=payload.status,
            now=now,
        )
        db.add(quote)
        db.commit()
        db.refresh(quote)
        return self.serialize_offline_quote(quote)

    def update_offline_quote(
        self,
        db: Session,
        quote_id: int,
        payload: OfflineQuoteUpdateRequest,
    ) -> OfflineQuoteResponse:
        quote = db.get(OfflineQuote, quote_id)
        if quote is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offline quote not found.",
            )

        self._refresh_quote_statuses(db, [quote])
        now = utc_now()
        if payload.valid_until is not None:
            quote.valid_until = payload.valid_until
        if payload.notes is not None:
            quote.notes = payload.notes
        if payload.supplier_score is not None:
            quote.supplier_score = payload.supplier_score
        if payload.quote_reference is not None:
            quote.quote_reference = payload.quote_reference
        if payload.is_active is not None:
            quote.is_active = payload.is_active
        if payload.status is not None:
            self._validate_quote_transition(quote.status, payload.status)
            self._apply_quote_lifecycle_state(
                quote,
                next_status=payload.status,
                now=now,
            )

        self._apply_expiry_if_needed(quote, now.date())
        db.commit()
        db.refresh(quote)
        return self.serialize_offline_quote(quote)

    def list_offline_quotes(self, db: Session, product_id: int) -> list[OfflineQuoteResponse]:
        self._ensure_product_exists(db, product_id)
        stmt = (
            select(OfflineQuote)
            .where(OfflineQuote.product_id == product_id)
            .order_by(OfflineQuote.is_active.desc(), OfflineQuote.created_at.desc())
        )
        quotes = list(db.scalars(stmt).all())
        self._refresh_quote_statuses(db, quotes)
        return [self.serialize_offline_quote(item) for item in quotes]

    def create_purchase_record(
        self,
        db: Session,
        payload: PurchaseRecordCreateRequest,
    ) -> PurchaseRecordResponse:
        product = self._ensure_product_exists(db, payload.product_id)
        purchased_at = payload.purchased_at or utc_now()
        related_quote_ids = payload.related_quote_ids

        related_quotes: list[OfflineQuote] = []
        if related_quote_ids:
            if len(related_quote_ids) != len(set(related_quote_ids)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Duplicate related quote IDs are not allowed.",
                )

            # Check if any requested quote is already associated with an existing purchase
            already_associated = list(
                db.scalars(
                    select(PurchaseRecordQuote.offline_quote_id).where(
                        PurchaseRecordQuote.offline_quote_id.in_(related_quote_ids)
                    )
                ).all()
            )
            if already_associated:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Quote ID {already_associated[0]} is already associated with a purchase.",
                )

            related_quotes = list(
                db.scalars(
                    select(OfflineQuote).where(
                        OfflineQuote.id.in_(related_quote_ids),
                        OfflineQuote.product_id == payload.product_id,
                    )
                ).all()
            )
            if len(related_quotes) != len(related_quote_ids):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="One or more related quotes were not found for this product.",
                )

            for quote in related_quotes:
                if quote.status == "purchased":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Quote ID {quote.id} has already been purchased.",
                    )
                self._validate_quote_transition(quote.status, "purchased")

        record = PurchaseRecord(
            product_id=payload.product_id,
            supplier_name=payload.supplier_name,
            unit_price=Decimal(str(payload.unit_price)),
            quantity=payload.quantity,
            shipping_cost=Decimal(str(payload.shipping_cost)),
            buyer_location=payload.buyer_location,
            pincode=payload.pincode,
            delivery_days=payload.delivery_days,
            reference_number=payload.reference_number,
            notes=payload.notes,
            purchased_at=purchased_at,
        )
        db.add(record)

        for quote in related_quotes:
            self._apply_quote_lifecycle_state(
                quote,
                next_status="purchased",
                now=purchased_at,
            )
            record.quote_associations.append(
                PurchaseRecordQuote(offline_quote=quote)
            )

        try:
            db.commit()
            db.refresh(record)
        except Exception:
            db.rollback()
            raise

        persisted_quote_ids = [assoc.offline_quote_id for assoc in record.quote_associations]
        return self.serialize_purchase_record(
            record,
            related_quote_ids=persisted_quote_ids,
            product=product,
        )

    def list_purchase_records(self, db: Session, product_id: int) -> list[PurchaseRecordResponse]:
        product = self._ensure_product_exists(db, product_id)
        stmt = (
            select(PurchaseRecord)
            .options(selectinload(PurchaseRecord.quote_associations))
            .where(PurchaseRecord.product_id == product_id)
            .order_by(PurchaseRecord.purchased_at.desc())
        )
        return [
            self.serialize_purchase_record(item, product=product)
            for item in db.scalars(stmt).all()
        ]

    def latest_purchase_summary(self, db: Session, product_id: int) -> LatestPurchaseSummary | None:
        stmt = (
            select(PurchaseRecord)
            .where(PurchaseRecord.product_id == product_id)
            .order_by(PurchaseRecord.purchased_at.desc())
        )
        record = db.scalar(stmt)
        if record is None:
            return None
        total_price = self._total_price(record.unit_price, record.shipping_cost, record.quantity)
        return LatestPurchaseSummary(
            supplier_name=record.supplier_name,
            unit_price=float(record.unit_price),
            quantity=record.quantity,
            shipping_cost=float(record.shipping_cost),
            total_price=total_price,
            buyer_location=record.buyer_location,
            delivery_days=record.delivery_days,
            purchased_at=record.purchased_at,
        )

    def procurement_summary(self, db: Session, product_id: int) -> ProcurementSummaryResponse:
        product = self._load_product_with_market_data(db, product_id)
        quotes = list(product.offline_quotes)
        self._refresh_quote_statuses(db, quotes)
        purchases = list(product.purchase_records)
        market_prices = self._market_prices(product)
        latest_purchase = purchases[0] if purchases else None
        active_quotes = [
            quote
            for quote in quotes
            if quote.is_active and quote.status in self.ACTIVE_QUOTE_STATUSES
        ]
        expiring_quotes = [
            quote for quote in active_quotes if self._is_expiring_soon(quote)
        ]

        breakdown = Counter(quote.status for quote in quotes)
        supplier_metrics: dict[str, dict[str, object]] = defaultdict(
            lambda: {
                "quote_totals": [],
                "purchase_prices": [],
                "quote_count": 0,
                "purchase_count": 0,
                "latest_quote_status": None,
            }
        )
        for quote in quotes:
            metrics = supplier_metrics[quote.supplier_name]
            metrics["quote_count"] = int(metrics["quote_count"]) + 1
            metrics["quote_totals"].append(
                float(quote.quoted_price) + float(quote.shipping_cost)
            )
            metrics["latest_quote_status"] = quote.status
        for purchase in purchases:
            metrics = supplier_metrics[purchase.supplier_name]
            metrics["purchase_count"] = int(metrics["purchase_count"]) + 1
            metrics["purchase_prices"].append(float(purchase.unit_price))

        best_online = market_prices["best"]
        supplier_competitiveness = [
            SupplierCompetitivenessSummary(
                supplier_name=supplier_name,
                quote_count=int(metrics["quote_count"]),
                purchase_count=int(metrics["purchase_count"]),
                best_quote_total_price=(
                    round(min(metrics["quote_totals"]), 2)
                    if metrics["quote_totals"]
                    else None
                ),
                average_quote_total_price=(
                    round(sum(metrics["quote_totals"]) / len(metrics["quote_totals"]), 2)
                    if metrics["quote_totals"]
                    else None
                ),
                average_purchase_unit_price=(
                    round(sum(metrics["purchase_prices"]) / len(metrics["purchase_prices"]), 2)
                    if metrics["purchase_prices"]
                    else None
                ),
                latest_quote_status=metrics["latest_quote_status"],
                competitiveness_label=self._competitiveness_label(
                    best_quote_total_price=(
                        min(metrics["quote_totals"]) if metrics["quote_totals"] else None
                    ),
                    best_online_price=best_online,
                ),
            )
            for supplier_name, metrics in sorted(supplier_metrics.items())
        ]

        latest_purchase_benchmark = (
            self._build_purchase_benchmark_summary(latest_purchase, market_prices)
            if latest_purchase is not None
            else None
        )

        return ProcurementSummaryResponse(
            product_id=product.id,
            product_name=product.canonical_name,
            active_quote_count=len(active_quotes),
            expiring_quote_count=len(expiring_quotes),
            approved_quote_count=sum(1 for quote in quotes if quote.status == "approved"),
            quote_status_breakdown=[
                ProcurementStatusCount(status=status_name, count=count)
                for status_name, count in sorted(breakdown.items())
            ],
            active_quotes=[self.serialize_offline_quote(quote) for quote in active_quotes[:10]],
            expiring_quotes=[self.serialize_offline_quote(quote) for quote in expiring_quotes[:10]],
            supplier_competitiveness=supplier_competitiveness,
            latest_purchase_benchmark=latest_purchase_benchmark,
        )

    def serialize_offline_quote(self, quote: OfflineQuote) -> OfflineQuoteResponse:
        total_price = float(quote.quoted_price) + float(quote.shipping_cost)
        days_until_expiry = self._days_until_expiry(quote)
        return OfflineQuoteResponse(
            id=quote.id,
            product_id=quote.product_id,
            supplier_name=quote.supplier_name,
            quoted_price=float(quote.quoted_price),
            shipping_cost=float(quote.shipping_cost),
            total_price=total_price,
            currency=quote.currency,
            seller_location=quote.seller_location,
            pincode=quote.pincode,
            estimated_delivery_days=quote.estimated_delivery_days,
            contact_name=quote.contact_name,
            contact_phone=quote.contact_phone,
            quote_reference=quote.quote_reference,
            status=quote.status,
            supplier_score=quote.supplier_score,
            notes=quote.notes,
            valid_until=quote.valid_until,
            days_until_expiry=days_until_expiry,
            is_expiring_soon=self._is_expiring_soon(quote),
            is_active=quote.is_active,
            submitted_at=quote.submitted_at,
            approved_at=quote.approved_at,
            closed_at=quote.closed_at,
            created_at=quote.created_at,
        )

    def serialize_purchase_record(
        self,
        record: PurchaseRecord,
        *,
        related_quote_ids: list[int] | None = None,
        product: Product | None = None,
    ) -> PurchaseRecordResponse:
        market_prices = self._market_prices(product) if product is not None else {"best": None, "median": None}
        if related_quote_ids is None:
            if hasattr(record, "quote_associations") and record.quote_associations:
                related_quote_ids = [assoc.offline_quote_id for assoc in record.quote_associations]
            else:
                related_quote_ids = []
        return PurchaseRecordResponse(
            id=record.id,
            product_id=record.product_id,
            supplier_name=record.supplier_name,
            unit_price=float(record.unit_price),
            quantity=record.quantity,
            shipping_cost=float(record.shipping_cost),
            total_price=self._total_price(record.unit_price, record.shipping_cost, record.quantity),
            buyer_location=record.buyer_location,
            pincode=record.pincode,
            delivery_days=record.delivery_days,
            reference_number=record.reference_number,
            notes=record.notes,
            related_quote_ids=related_quote_ids or [],
            market_best_price=market_prices["best"],
            market_median_price=market_prices["median"],
            delta_from_market_best_percent=self._delta_percent(
                float(record.unit_price),
                market_prices["best"],
            ),
            delta_from_market_median_percent=self._delta_percent(
                float(record.unit_price),
                market_prices["median"],
            ),
            purchased_at=record.purchased_at,
            created_at=record.created_at,
        )

    def _ensure_product_exists(self, db: Session, product_id: int) -> Product:
        product = db.get(Product, product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found.",
            )
        return product

    def _total_price(self, unit_price: Decimal | object, shipping_cost: Decimal | object, quantity: int) -> float:
        return float(unit_price) * quantity + float(shipping_cost)

    def _load_product_with_market_data(self, db: Session, product_id: int) -> Product:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.vendor_products).selectinload(VendorProduct.vendor),
                selectinload(Product.offline_quotes),
                selectinload(Product.purchase_records).selectinload(PurchaseRecord.quote_associations),
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

    def _market_prices(self, product: Product | None) -> dict[str, float | None]:
        if product is None:
            return {"best": None, "median": None}
        landed_prices: list[float] = []
        for listing in product.vendor_products:
            shipping_cost = infer_shipping_cost(listing.delivery_info) or 0.0
            landed_prices.append(round(float(listing.current_price) + shipping_cost, 2))
        if not landed_prices:
            return {"best": None, "median": None}
        sorted_prices = sorted(landed_prices)
        mid = len(sorted_prices) // 2
        if len(sorted_prices) % 2:
            median_price = sorted_prices[mid]
        else:
            median_price = round((sorted_prices[mid - 1] + sorted_prices[mid]) / 2, 2)
        return {
            "best": sorted_prices[0],
            "median": median_price,
        }

    def _build_purchase_benchmark_summary(
        self,
        purchase: PurchaseRecord,
        market_prices: dict[str, float | None],
    ) -> PurchaseBenchmarkSummary:
        unit_price = float(purchase.unit_price)
        total_price = self._total_price(
            purchase.unit_price,
            purchase.shipping_cost,
            purchase.quantity,
        )
        delta_best = self._delta_percent(unit_price, market_prices["best"])
        delta_median = self._delta_percent(unit_price, market_prices["median"])
        note = "No live market benchmark available."
        if delta_best is not None and delta_best <= 0:
            note = "Last paid price is at or below the current best online price."
        elif delta_best is not None:
            note = "Last paid price is above the current best online price."
        elif delta_median is not None and delta_median <= 0:
            note = "Last paid price is at or below the current market median."
        elif delta_median is not None:
            note = "Last paid price is above the current market median."

        return PurchaseBenchmarkSummary(
            supplier_name=purchase.supplier_name,
            purchased_at=purchase.purchased_at,
            unit_price=unit_price,
            total_price=total_price,
            market_best_price=market_prices["best"],
            market_median_price=market_prices["median"],
            delta_from_market_best_percent=delta_best,
            delta_from_market_median_percent=delta_median,
            benchmark_note=note,
        )

    def _validate_quote_transition(self, current_status: str, next_status: str) -> None:
        if next_status not in self.QUOTE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported quote status.",
            )
        allowed_statuses = self.QUOTE_STATUS_TRANSITIONS.get(current_status, {current_status})
        if next_status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Quote status cannot move from {current_status} to {next_status}.",
            )

    def _apply_quote_lifecycle_state(
        self,
        quote: OfflineQuote,
        *,
        next_status: str,
        now,
    ) -> None:
        quote.status = next_status
        if next_status in {"submitted", "approved", "purchased", "closed"} and quote.submitted_at is None:
            quote.submitted_at = now
        if next_status in {"approved", "purchased", "closed"} and quote.approved_at is None:
            quote.approved_at = now
        if next_status in self.FINAL_QUOTE_STATUSES:
            quote.closed_at = quote.closed_at or now
            quote.is_active = False
        else:
            quote.closed_at = None if next_status in {"draft", "submitted", "approved"} else quote.closed_at
            if next_status in self.ACTIVE_QUOTE_STATUSES:
                quote.is_active = True

    def _refresh_quote_statuses(self, db: Session, quotes: list[OfflineQuote]) -> None:
        if not quotes:
            return
        today = utc_now().date()
        changed = False
        for quote in quotes:
            changed = self._apply_expiry_if_needed(quote, today) or changed
        if changed:
            db.commit()

    def _apply_expiry_if_needed(self, quote: OfflineQuote, today: date) -> bool:
        if quote.valid_until is None:
            return False
        if quote.valid_until >= today:
            return False
        if quote.status in self.FINAL_QUOTE_STATUSES:
            return False
        quote.status = "expired"
        quote.is_active = False
        quote.closed_at = quote.closed_at or utc_now()
        return True

    def _days_until_expiry(self, quote: OfflineQuote) -> int | None:
        if quote.valid_until is None:
            return None
        return (quote.valid_until - utc_now().date()).days

    def _is_expiring_soon(self, quote: OfflineQuote) -> bool:
        days_until_expiry = self._days_until_expiry(quote)
        return bool(
            quote.is_active
            and days_until_expiry is not None
            and 0 <= days_until_expiry <= self.EXPIRING_SOON_DAYS
        )

    def _delta_percent(self, current: float, baseline: float | None) -> float | None:
        if baseline in (None, 0):
            return None
        return round(((current - baseline) / baseline) * 100, 2)

    def _competitiveness_label(
        self,
        *,
        best_quote_total_price: float | None,
        best_online_price: float | None,
    ) -> str:
        if best_quote_total_price is None:
            return "purchase-only"
        if best_online_price is None:
            return "quote-only"
        if best_quote_total_price <= best_online_price:
            return "beats-online"
        if best_quote_total_price <= best_online_price * 1.03:
            return "competitive"
        return "above-online"
