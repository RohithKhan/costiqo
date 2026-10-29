from pydantic import BaseModel


class PincodeVerificationResponse(BaseModel):
    pincode: str
    district: str
    state: str
    office_name: str | None = None
    location: str
