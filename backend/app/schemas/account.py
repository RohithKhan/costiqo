from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.product import ProductSummary


class SavedProductCreateRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    product_url: str = Field(min_length=1, max_length=500)


class SavedProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_name: str
    product_url: str
    created_at: datetime


class SavedSearchCreateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)


class SavedSearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    location: str | None = None
    pincode: str | None = None
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AlertRuleCreateRequest(BaseModel):
    product_id: int | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    trigger_type: str = Field(default="price_below", max_length=32)
    target_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_target(self) -> "AlertRuleCreateRequest":
        if not self.product_id and not (self.query and self.query.strip()):
            raise ValueError("Provide either a product_id or a query for an alert rule.")
        return self


class AlertRuleUpdateRequest(BaseModel):
    is_active: bool | None = None
    target_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_update(self) -> "AlertRuleUpdateRequest":
        if self.is_active is None and self.target_price is None:
            raise ValueError("Provide at least one alert field to update.")
        return self


class AlertRuleResponse(BaseModel):
    id: int
    trigger_type: str
    target_price: float | None = None
    is_active: bool
    query: str | None = None
    location: str | None = None
    pincode: str | None = None
    created_at: datetime
    product: ProductSummary | None = None
