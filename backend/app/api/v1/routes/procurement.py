from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.procurement import OfflineQuoteResponse, PurchaseRecordResponse
from app.services.dependencies import procurement_service


router = APIRouter(prefix="/products", tags=["procurement"])


@router.get("/{product_id}/offline-quotes", response_model=list[OfflineQuoteResponse])
def get_offline_quotes(
    product_id: int,
    db: Session = Depends(get_db),
) -> list[OfflineQuoteResponse]:
    return procurement_service.list_offline_quotes(db, product_id)


@router.get("/{product_id}/purchases", response_model=list[PurchaseRecordResponse])
def get_purchase_records(
    product_id: int,
    db: Session = Depends(get_db),
) -> list[PurchaseRecordResponse]:
    return procurement_service.list_purchase_records(db, product_id)
