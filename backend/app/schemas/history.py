from datetime import datetime

from pydantic import BaseModel


class HistoryPoint(BaseModel):
    timestamp: datetime
    price: float


class VendorHistorySeries(BaseModel):
    vendor_product_id: int
    vendor: str
    points: list[HistoryPoint]


class ProductHistoryResponse(BaseModel):
    product_id: int
    product_name: str
    history: list[VendorHistorySeries]


class VendorHistoryResponse(BaseModel):
    vendor_product_id: int
    vendor: str
    product_name: str
    history: list[HistoryPoint]
