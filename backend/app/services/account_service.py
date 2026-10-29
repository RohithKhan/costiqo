from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.security import get_password_hash, verify_password
from app.db.models.alert_rule import AlertRule
from app.db.models.product import Product
from app.db.models.saved_product import SavedProduct
from app.db.models.saved_search import SavedSearch
from app.db.models.user import User
from app.db.models.vendor_product import VendorProduct
from app.schemas.account import (
    AlertRuleCreateRequest,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
    ChangePasswordRequest,
    SavedProductCreateRequest,
    SavedProductResponse,
    SavedSearchCreateRequest,
    SavedSearchResponse,
)
from app.services.product_service import ProductService


class AccountService:
    def __init__(self, product_service: ProductService) -> None:
        self.product_service = product_service

    def list_saved_products(self, db: Session, user: User) -> list[SavedProductResponse]:
        self._ensure_saved_product_bookmark_schema(db)
        stmt = (
            select(SavedProduct)
            .where(SavedProduct.user_id == user.id)
            .order_by(SavedProduct.created_at.desc())
        )
        return [SavedProductResponse.model_validate(item) for item in db.scalars(stmt).all()]

    def create_saved_product(
        self,
        db: Session,
        user: User,
        payload: SavedProductCreateRequest,
    ) -> SavedProductResponse:
        self._ensure_saved_product_bookmark_schema(db)
        product_name = payload.product_name.strip()
        product_url = payload.product_url.strip()
        existing = db.scalar(
            select(SavedProduct).where(
                SavedProduct.user_id == user.id,
                SavedProduct.product_url == product_url,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This product link is already bookmarked.",
            )

        record = SavedProduct(
            user_id=user.id,
            product_name=product_name,
            product_url=product_url,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return SavedProductResponse.model_validate(record)

    def delete_saved_product(self, db: Session, user: User, saved_product_id: int) -> None:
        self._ensure_saved_product_bookmark_schema(db)
        record = db.scalar(
            select(SavedProduct).where(
                SavedProduct.id == saved_product_id,
                SavedProduct.user_id == user.id,
            )
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved product not found.",
            )
        db.delete(record)
        db.commit()

    def change_password(
        self,
        db: Session,
        user: User,
        payload: ChangePasswordRequest,
    ) -> None:
        if not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )
        user.password_hash = get_password_hash(payload.new_password)
        db.commit()

    def delete_account(self, db: Session, user: User) -> None:
        db.delete(user)
        db.commit()

    def list_saved_searches(self, db: Session, user: User) -> list[SavedSearchResponse]:
        stmt = (
            select(SavedSearch)
            .where(SavedSearch.user_id == user.id)
            .order_by(SavedSearch.created_at.desc())
        )
        return [SavedSearchResponse.model_validate(item) for item in db.scalars(stmt).all()]

    def create_saved_search(
        self,
        db: Session,
        user: User,
        payload: SavedSearchCreateRequest,
    ) -> SavedSearchResponse:
        query = payload.query.strip()
        location = payload.location.strip() if payload.location else None
        pincode = payload.pincode.strip() if payload.pincode else None

        existing = db.scalar(
            select(SavedSearch).where(
                SavedSearch.user_id == user.id,
                SavedSearch.query == query,
                SavedSearch.location == location,
                SavedSearch.pincode == pincode,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This search is already saved.",
            )

        record = SavedSearch(
            user_id=user.id,
            query=query,
            location=location,
            pincode=pincode,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return SavedSearchResponse.model_validate(record)

    def delete_saved_search(self, db: Session, user: User, saved_search_id: int) -> None:
        record = db.scalar(
            select(SavedSearch).where(
                SavedSearch.id == saved_search_id,
                SavedSearch.user_id == user.id,
            )
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved search not found.",
            )
        db.delete(record)
        db.commit()

    def list_alert_rules(self, db: Session, user: User) -> list[AlertRuleResponse]:
        stmt = (
            select(AlertRule)
            .options(
                selectinload(AlertRule.product)
                .selectinload(Product.vendor_products)
                .selectinload(VendorProduct.vendor)
            )
            .where(AlertRule.user_id == user.id)
            .order_by(AlertRule.is_active.desc(), AlertRule.created_at.desc())
        )
        return [self._serialize_alert_rule(item) for item in db.scalars(stmt).all()]

    def create_alert_rule(
        self,
        db: Session,
        user: User,
        payload: AlertRuleCreateRequest,
    ) -> AlertRuleResponse:
        if payload.product_id:
            self.product_service.get_product(db, payload.product_id)

        record = AlertRule(
            user_id=user.id,
            product_id=payload.product_id,
            query=payload.query.strip() if payload.query else None,
            location=payload.location.strip() if payload.location else None,
            pincode=payload.pincode.strip() if payload.pincode else None,
            trigger_type=payload.trigger_type,
            target_price=(
                Decimal(str(payload.target_price))
                if payload.target_price is not None
                else None
            ),
        )
        db.add(record)
        db.commit()
        return self._reload_alert_rule(db, record.id)

    def update_alert_rule(
        self,
        db: Session,
        user: User,
        alert_rule_id: int,
        payload: AlertRuleUpdateRequest,
    ) -> AlertRuleResponse:
        record = db.scalar(
            select(AlertRule).where(
                AlertRule.id == alert_rule_id,
                AlertRule.user_id == user.id,
            )
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert rule not found.",
            )

        if payload.is_active is not None:
            record.is_active = payload.is_active
        if payload.target_price is not None:
            record.target_price = Decimal(str(payload.target_price))

        db.commit()
        return self._reload_alert_rule(db, record.id)

    def delete_alert_rule(self, db: Session, user: User, alert_rule_id: int) -> None:
        record = db.scalar(
            select(AlertRule).where(
                AlertRule.id == alert_rule_id,
                AlertRule.user_id == user.id,
            )
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert rule not found.",
            )
        db.delete(record)
        db.commit()

    def _reload_alert_rule(self, db: Session, alert_rule_id: int) -> AlertRuleResponse:
        stmt = (
            select(AlertRule)
            .options(
                selectinload(AlertRule.product)
                .selectinload(Product.vendor_products)
                .selectinload(VendorProduct.vendor)
            )
            .where(AlertRule.id == alert_rule_id)
        )
        record = db.scalar(stmt)
        assert record is not None
        return self._serialize_alert_rule(record)

    def _serialize_alert_rule(self, record: AlertRule) -> AlertRuleResponse:
        return AlertRuleResponse(
            id=record.id,
            trigger_type=record.trigger_type,
            target_price=float(record.target_price) if record.target_price is not None else None,
            is_active=record.is_active,
            query=record.query,
            location=record.location,
            pincode=record.pincode,
            created_at=record.created_at,
            product=(
                self.product_service.build_product_summary(record.product)
                if record.product is not None
                else None
            ),
        )

    def _ensure_saved_product_bookmark_schema(self, db: Session) -> None:
        bind = db.get_bind()
        inspector = inspect(bind)
        if "saved_products" not in inspector.get_table_names():
            return

        columns = {column["name"] for column in inspector.get_columns("saved_products")}
        if {"product_name", "product_url"}.issubset(columns) and "product_id" not in columns:
            return

        if bind.dialect.name == "sqlite" and "product_id" in columns:
            self._rebuild_sqlite_saved_product_bookmarks(db, columns)
            return

        try:
            if "product_name" not in columns:
                db.execute(text("ALTER TABLE saved_products ADD COLUMN product_name VARCHAR(255)"))
            if "product_url" not in columns:
                db.execute(text("ALTER TABLE saved_products ADD COLUMN product_url VARCHAR(500)"))

            refreshed_columns = {
                column["name"] for column in inspect(bind).get_columns("saved_products")
            }
            if "product_id" in refreshed_columns:
                db.execute(
                    text(
                        """
                        UPDATE saved_products
                        SET
                          product_name = COALESCE(
                            (
                              SELECT products.canonical_name
                              FROM products
                              WHERE products.id = saved_products.product_id
                            ),
                            'Saved product'
                          ),
                          product_url = COALESCE(
                            (
                              SELECT vendor_products.vendor_product_url
                              FROM vendor_products
                              WHERE vendor_products.product_id = saved_products.product_id
                              ORDER BY vendor_products.current_price ASC
                              LIMIT 1
                            ),
                            '#legacy-product-' || saved_products.product_id
                          )
                        WHERE product_name IS NULL OR product_url IS NULL
                        """
                    )
                )
            db.commit()
        except Exception:
            db.rollback()
            raise

    def _rebuild_sqlite_saved_product_bookmarks(self, db: Session, columns: set[str]) -> None:
        legacy_name_expr = (
            "legacy.product_name,"
            if "product_name" in columns
            else ""
        )
        legacy_url_expr = (
            "legacy.product_url,"
            if "product_url" in columns
            else ""
        )
        try:
            db.execute(text("PRAGMA foreign_keys=OFF"))
            db.execute(text("DROP TABLE IF EXISTS saved_products_legacy_bookmark_migration"))
            db.execute(
                text(
                    "ALTER TABLE saved_products "
                    "RENAME TO saved_products_legacy_bookmark_migration"
                )
            )
            db.execute(text("DROP INDEX IF EXISTS ix_saved_products_user_id"))
            db.execute(text("DROP INDEX IF EXISTS ix_saved_products_product_id"))
            db.execute(
                text(
                    """
                    CREATE TABLE saved_products (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        product_name VARCHAR(255) NOT NULL,
                        product_url VARCHAR(500) NOT NULL,
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(id),
                        UNIQUE(user_id, product_url)
                    )
                    """
                )
            )
            db.execute(
                text(
                    """
                    INSERT OR IGNORE INTO saved_products (
                        id,
                        user_id,
                        product_name,
                        product_url,
                        created_at
                    )
                    SELECT
                        legacy.id,
                        legacy.user_id,
                        COALESCE(
                            {legacy_name_expr}
                            (
                                SELECT products.canonical_name
                                FROM products
                                WHERE products.id = legacy.product_id
                            ),
                            'Saved product'
                        ),
                        COALESCE(
                            {legacy_url_expr}
                            (
                                SELECT vendor_products.vendor_product_url
                                FROM vendor_products
                                WHERE vendor_products.product_id = legacy.product_id
                                ORDER BY vendor_products.current_price ASC
                                LIMIT 1
                            ),
                            '#legacy-product-' || legacy.product_id
                        ),
                        legacy.created_at
                    FROM saved_products_legacy_bookmark_migration AS legacy
                    """
                    .format(
                        legacy_name_expr=legacy_name_expr,
                        legacy_url_expr=legacy_url_expr,
                    )
                )
            )
            db.execute(text("CREATE INDEX ix_saved_products_user_id ON saved_products (user_id)"))
            db.execute(text("DROP TABLE saved_products_legacy_bookmark_migration"))
            db.execute(text("PRAGMA foreign_keys=ON"))
            db.commit()
        except Exception:
            db.rollback()
            raise
