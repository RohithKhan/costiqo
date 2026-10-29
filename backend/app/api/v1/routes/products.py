from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.comparison import ComparisonRankingMode
from app.schemas.product import ProductDetail, SearchResponse, SuggestionResponse, VendorListingSummary
from app.services.dependencies import comparison_service, product_service


router = APIRouter(prefix="/products", tags=["products"])


@router.get("/search", response_model=SearchResponse)
async def search_products(
    q: str = Query(..., min_length=1, max_length=255),
    location: str | None = Query(default=None, max_length=120),
    pincode: str | None = Query(default=None, max_length=12),
    db: Session = Depends(get_db),
) -> SearchResponse:
    return await product_service.search(
        db,
        q,
        location=location,
        pincode=pincode,
    )


@router.get("/suggestions", response_model=SuggestionResponse)
async def suggest_products(
    q: str = Query(..., min_length=1, max_length=255),
    location: str | None = Query(default=None, max_length=120),
    pincode: str | None = Query(default=None, max_length=12),
    limit: int = Query(default=6, ge=1, le=10),
    db: Session = Depends(get_db),
) -> SuggestionResponse:
    return await product_service.suggest(
        db,
        q,
        location=location,
        pincode=pincode,
        limit=limit,
    )


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: int,
    location: str | None = Query(default=None, max_length=120),
    pincode: str | None = Query(default=None, max_length=12),
    ranking_mode: ComparisonRankingMode = Query(default="recommended"),
    db: Session = Depends(get_db),
) -> ProductDetail:
    return await comparison_service.build_product_detail(
        db,
        product_id,
        location=location,
        pincode=pincode,
        ranking_mode=ranking_mode,
    )


@router.get("/{product_id}/vendors", response_model=list[VendorListingSummary])
def get_product_vendors(
    product_id: int,
    db: Session = Depends(get_db),
) -> list[VendorListingSummary]:
    return product_service.get_product_vendors(db, product_id)
