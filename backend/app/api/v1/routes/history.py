from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.history import ProductHistoryResponse, VendorHistoryResponse
from app.services.dependencies import history_service


router = APIRouter(tags=["history"])


@router.get("/products/{product_id}/history", response_model=ProductHistoryResponse)
def get_product_history(
    product_id: int,
    db: Session = Depends(get_db),
) -> ProductHistoryResponse:
    return history_service.get_product_history(db, product_id)


@router.get("/vendors/{vendor_product_id}/history", response_model=VendorHistoryResponse)
def get_vendor_history(
    vendor_product_id: int,
    db: Session = Depends(get_db),
) -> VendorHistoryResponse:
    return history_service.get_vendor_history(db, vendor_product_id)
