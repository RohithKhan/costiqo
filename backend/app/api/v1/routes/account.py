from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.account import (
    AlertRuleCreateRequest,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
    ChangePasswordRequest,
    SavedProductCreateRequest,
    SavedProductResponse,
    SavedSearchCreateRequest,
    SavedSearchResponse,
)
from app.services.dependencies import account_service


router = APIRouter(prefix="/me", tags=["account"])


@router.get("/saved-products", response_model=list[SavedProductResponse])
def list_saved_products(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedProductResponse]:
    return account_service.list_saved_products(db, current_user)


@router.post(
    "/saved-products",
    response_model=SavedProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_product(
    payload: SavedProductCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedProductResponse:
    return account_service.create_saved_product(db, current_user, payload)


@router.delete("/saved-products/{saved_product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_product(
    saved_product_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    account_service.delete_saved_product(db, current_user, saved_product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    account_service.change_password(db, current_user, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    account_service.delete_account(db, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/saved-searches", response_model=list[SavedSearchResponse])
def list_saved_searches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedSearchResponse]:
    return account_service.list_saved_searches(db, current_user)


@router.post(
    "/saved-searches",
    response_model=SavedSearchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_search(
    payload: SavedSearchCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedSearchResponse:
    return account_service.create_saved_search(db, current_user, payload)


@router.delete("/saved-searches/{saved_search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search(
    saved_search_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    account_service.delete_saved_search(db, current_user, saved_search_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/alerts", response_model=list[AlertRuleResponse])
def list_alert_rules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AlertRuleResponse]:
    return account_service.list_alert_rules(db, current_user)


@router.post("/alerts", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertRuleResponse:
    return account_service.create_alert_rule(db, current_user, payload)


@router.patch("/alerts/{alert_rule_id}", response_model=AlertRuleResponse)
def update_alert_rule(
    alert_rule_id: int,
    payload: AlertRuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AlertRuleResponse:
    return account_service.update_alert_rule(db, current_user, alert_rule_id, payload)


@router.delete("/alerts/{alert_rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    alert_rule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    account_service.delete_alert_rule(db, current_user, alert_rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
