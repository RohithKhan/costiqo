from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.admin import VendorStatusResponse
from app.services.dependencies import scrape_service


router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=list[VendorStatusResponse])
def list_vendors(db: Session = Depends(get_db)) -> list[VendorStatusResponse]:
    return [
        VendorStatusResponse(
            id=vendor.id,
            name=vendor.name,
            base_url=vendor.base_url,
            is_active=vendor.is_active,
            scrape_strategy=vendor.scrape_strategy,
            last_status=vendor.last_status,
            last_scraped_at=vendor.last_scraped_at,
        )
        for vendor in scrape_service.list_vendors(db)
    ]
