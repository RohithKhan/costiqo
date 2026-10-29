from fastapi import APIRouter, Query

from app.schemas.location import PincodeVerificationResponse
from app.services.dependencies import search_context_service


router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/pincode", response_model=PincodeVerificationResponse)
async def verify_pincode(
    pincode: str = Query(..., min_length=6, max_length=12),
) -> PincodeVerificationResponse:
    details = await search_context_service.verify_pincode(pincode)
    return PincodeVerificationResponse(**details)
