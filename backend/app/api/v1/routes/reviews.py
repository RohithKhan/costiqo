from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models.product import Product
from app.db.models.vendor_product import VendorProduct
from app.db.session import get_db
from app.schemas.review import ProductSentimentResponse, ReviewItem, ReviewsResponse
from app.services.dependencies import sentiment_service


router = APIRouter(prefix="/products", tags=["reviews"])


@router.get("/{product_id}/reviews", response_model=ReviewsResponse)
def get_product_reviews(
    product_id: int,
    db: Session = Depends(get_db),
) -> ReviewsResponse:
    stmt = (
        select(Product)
        .options(
            selectinload(Product.vendor_products).selectinload(VendorProduct.vendor),
            selectinload(Product.vendor_products).selectinload(VendorProduct.reviews),
        )
        .where(Product.id == product_id)
    )
    product = db.scalar(stmt)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    review_items: list[ReviewItem] = []
    for listing in product.vendor_products:
        for review in listing.reviews:
            review_items.append(
                ReviewItem(
                    id=review.id,
                    vendor=listing.vendor.name,
                    title=review.title,
                    body=review.body,
                    rating=review.rating,
                    review_date=review.review_date,
                )
            )
    review_items.sort(
        key=lambda item: (
            item.review_date.isoformat() if item.review_date else "",
            item.vendor,
        ),
        reverse=True,
    )
    return ReviewsResponse(product_id=product.id, reviews=review_items)


@router.get("/{product_id}/sentiment", response_model=ProductSentimentResponse)
def get_product_sentiment(
    product_id: int,
    db: Session = Depends(get_db),
) -> ProductSentimentResponse:
    return sentiment_service.get_product_sentiment(db, product_id)
