from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class Customer(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=8, max_length=20)
    national_id: Optional[str] = Field(None, description="KTP/Passport")
    address: Optional[str] = None

class Item(BaseModel):
    category: Literal["emas","gadget","elektronik","kendaraan","lainnya"]
    description: str = Field(..., min_length=3, max_length=200)
    estimated_value: float = Field(..., gt=0)
    weight_gram: Optional[float] = Field(None, gt=0)

class PawnTicket(BaseModel):
    customer_id: str
    item_id: str
    principal: float = Field(..., gt=0)
    monthly_interest_rate: float = Field(..., ge=0)
    start_date: datetime
    due_date: datetime
    status: Literal["active","redeemed","defaulted"] = "active"

class CreatePawnRequest(BaseModel):
    customer: Customer
    item: Item
    principal: float
    tenor_months: int = Field(..., ge=1, le=12)
    monthly_interest_rate: float = Field(..., ge=0)

class PaymentRequest(BaseModel):
    ticket_id: str
    amount: float = Field(..., gt=0)
