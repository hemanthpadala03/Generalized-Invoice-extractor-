# validators.py
from pydantic import BaseModel, Field, validator
from typing import Optional

class LineItem(BaseModel):
    """Line item schema"""
    sl_no: int = Field(..., alias="Sl.No")
    description: str = Field(..., alias="Description")
    unit_price: float = Field(0.0, alias="UnitPrice")
    discount: float = Field(0.0, alias="Discount")
    qty: float = Field(1.0, alias="Qty")
    net_amount: float = Field(0.0, alias="NetAmount")
    tax_rate: str = Field("", alias="TaxRate")
    tax_type: str = Field("", alias="TaxType")
    tax_amount: float = Field(0.0, alias="TaxAmount")
    total_amount: float = Field(0.0, alias="TotalAmount")

    class Config:
        allow_population_by_field_name = True


class InvoiceData(BaseModel):
    """Invoice header schema"""
    invoice_type: str = "Tax Invoice"
    invoice_number: str = ""
    invoice_date: str = ""
    order_number: str = ""
    order_date: Optional[str] = ""
    seller_name: str = ""
    seller_address: str = ""
    seller_info: str = ""
    seller_gst: str = ""
    seller_pan: str = ""
    fssai_license: str = ""
    billing_address: str = ""
    shipping_address: str = ""
    billing_state_code: str = ""
    shipping_state_code: str = ""
    place_of_supply: str = ""
    place_of_delivery: str = ""
    invoice_details: str = ""
    amount_in_words: str = ""
    total_tax: float = 0.0
    total_amount: float = 0.0
    reverse_charge: str = "No"

    @validator("total_tax", "total_amount", pre=True)
    def convert_to_float(cls, v):
        try:
            return float(v) if v else 0.0
        except:
            return 0.0
