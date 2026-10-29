from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.product import Product
from app.db.models.vendor_product import VendorProduct
from app.schemas.history import (
    HistoryPoint,
    ProductHistoryResponse,
    VendorHistoryResponse,
    VendorHistorySeries,
)
from app.services.product_service import select_best_listings_by_vendor


class HistoryService:
    def get_product_history(self, db: Session, product_id: int) -> ProductHistoryResponse:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.vendor_products).selectinload(VendorProduct.vendor),
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

        history = [
            VendorHistorySeries(
                vendor_product_id=listing.id,
                vendor=listing.vendor.name,
                points=[
                    HistoryPoint(
                        timestamp=snapshot.scraped_at,
                        price=float(snapshot.price),
                    )
                    for snapshot in listing.price_snapshots
                ],
            )
            for listing in select_best_listings_by_vendor(product.vendor_products)
        ]
        return ProductHistoryResponse(
            product_id=product.id,
            product_name=product.canonical_name,
            history=history,
        )

    def get_vendor_history(self, db: Session, vendor_product_id: int) -> VendorHistoryResponse:
        stmt = (
            select(VendorProduct)
            .options(
                selectinload(VendorProduct.vendor),
                selectinload(VendorProduct.product),
                selectinload(VendorProduct.price_snapshots),
            )
            .where(VendorProduct.id == vendor_product_id)
        )
        vendor_product = db.scalar(stmt)
        if vendor_product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor product not found.",
            )

        return VendorHistoryResponse(
            vendor_product_id=vendor_product.id,
            vendor=vendor_product.vendor.name,
            product_name=vendor_product.product.canonical_name,
            history=[
                HistoryPoint(timestamp=snapshot.scraped_at, price=float(snapshot.price))
                for snapshot in vendor_product.price_snapshots
            ],
        )
