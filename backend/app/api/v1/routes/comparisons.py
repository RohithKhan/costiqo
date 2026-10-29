import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_optional_user
from app.db.models.search_audit_log import SearchAuditLog
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.comparison import ComparisonProgressResponse, ComparisonRankingMode, ComparisonResponse
from app.services.dependencies import comparison_service, search_progress_service


router = APIRouter(prefix="/comparisons", tags=["comparisons"])
logger = logging.getLogger(__name__)


@router.get("", response_model=ComparisonResponse)
async def compare_products(
    request: Request,
    q: str = Query(..., min_length=1, max_length=255),
    location: str | None = Query(default=None, max_length=120),
    pincode: str | None = Query(default=None, max_length=12),
    ranking_mode: ComparisonRankingMode = Query(default="recommended"),
    progress_id: str | None = Query(default=None, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> ComparisonResponse:
    if progress_id:
        search_progress_service.start(progress_id)
    try:
        comparison = await comparison_service.compare(
            db,
            q,
            location=location,
            pincode=pincode,
            ranking_mode=ranking_mode,
            progress_callback=(
                (lambda offer_count: search_progress_service.update(progress_id, offer_count))
                if progress_id
                else None
            ),
        )
    except Exception:
        if progress_id:
            search_progress_service.fail(progress_id)
        raise
    if progress_id:
        search_progress_service.complete(progress_id, len(comparison.results))
    record_search_audit(
        db,
        request=request,
        current_user=current_user,
        query=q,
        location=location,
        pincode=comparison.pincode or pincode,
        ranking_mode=ranking_mode,
        result_count=len(comparison.results),
    )
    return comparison


@router.get("/progress/{progress_id}", response_model=ComparisonProgressResponse)
def get_comparison_progress(progress_id: str) -> ComparisonProgressResponse:
    progress = search_progress_service.get(progress_id)
    return ComparisonProgressResponse(
        progress_id=progress.progress_id,
        offer_count=progress.offer_count,
        status=progress.status,
    )


def record_search_audit(
    db: Session,
    *,
    request: Request,
    current_user: User | None,
    query: str,
    location: str | None,
    pincode: str | None,
    ranking_mode: ComparisonRankingMode,
    result_count: int,
) -> None:
    client_host = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    logger.info(
        "comparison_search user_id=%s user_email=%s query=%r pincode=%r result_count=%s",
        current_user.id if current_user else None,
        current_user.email if current_user else None,
        query,
        pincode,
        result_count,
    )
    try:
        db.add(
            SearchAuditLog(
                user_id=current_user.id if current_user else None,
                user_email=current_user.email if current_user else None,
                query=query.strip()[:255],
                location=location.strip()[:120] if location else None,
                pincode=pincode.strip()[:12] if pincode else None,
                ranking_mode=ranking_mode,
                result_count=result_count,
                client_host=client_host[:80] if client_host else None,
                user_agent=user_agent[:1000] if user_agent else None,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("search_audit_log_failed")
