from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.admin import ScrapeJobRequest, ScrapeJobResponse, VendorStatusResponse
from app.schemas.procurement import (
    OfflineQuoteCreateRequest,
    OfflineQuoteResponse,
    OfflineQuoteUpdateRequest,
    ProcurementSummaryResponse,
    PurchaseRecordCreateRequest,
    PurchaseRecordResponse,
)
from app.services.dependencies import procurement_service
from app.services.dependencies import queue_service
from app.services.dependencies import scrape_service


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/scrape", response_model=ScrapeJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape(
    payload: ScrapeJobRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ScrapeJobResponse:
    job = await queue_service.trigger_admin_scrape(db, payload.query)
    return ScrapeJobResponse(
        id=job.id,
        query=job.query,
        status=job.status,
        result_count=job.result_count,
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/jobs/{job_id}", response_model=ScrapeJobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ScrapeJobResponse:
    job = scrape_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scrape job not found.",
        )
    return ScrapeJobResponse(
        id=job.id,
        query=job.query,
        status=job.status,
        result_count=job.result_count,
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/vendors", response_model=list[VendorStatusResponse])
def get_vendor_statuses(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[VendorStatusResponse]:
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


@router.post("/offline-quotes", response_model=OfflineQuoteResponse, status_code=status.HTTP_201_CREATED)
def create_offline_quote(
    payload: OfflineQuoteCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> OfflineQuoteResponse:
    return procurement_service.create_offline_quote(db, payload)


@router.patch("/offline-quotes/{quote_id}", response_model=OfflineQuoteResponse)
def update_offline_quote(
    quote_id: int,
    payload: OfflineQuoteUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> OfflineQuoteResponse:
    return procurement_service.update_offline_quote(db, quote_id, payload)


@router.post("/purchases", response_model=PurchaseRecordResponse, status_code=status.HTTP_201_CREATED)
def create_purchase_record(
    payload: PurchaseRecordCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> PurchaseRecordResponse:
    return procurement_service.create_purchase_record(db, payload)


@router.get("/procurement/summary", response_model=ProcurementSummaryResponse)
def get_procurement_summary(
    product_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> ProcurementSummaryResponse:
    return procurement_service.procurement_summary(db, product_id)
