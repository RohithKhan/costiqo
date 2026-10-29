from datetime import datetime

from pydantic import BaseModel, Field


class ScrapeJobRequest(BaseModel):
    query: str = Field(min_length=1, max_length=255)


class ScrapeJobResponse(BaseModel):
    id: str
    query: str
    status: str
    result_count: int
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class VendorStatusResponse(BaseModel):
    id: int
    name: str
    base_url: str
    is_active: bool
    scrape_strategy: str
    last_status: str | None = None
    last_scraped_at: datetime | None = None
