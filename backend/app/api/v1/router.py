from fastapi import APIRouter

from app.api.v1.routes import (
    account,
    admin,
    auth,
    comparisons,
    history,
    locations,
    procurement,
    products,
    reviews,
    vendors,
)


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(account.router)
api_router.include_router(locations.router)
api_router.include_router(products.router)
api_router.include_router(comparisons.router)
api_router.include_router(reviews.router)
api_router.include_router(history.router)
api_router.include_router(procurement.router)
api_router.include_router(vendors.router)
api_router.include_router(admin.router)
