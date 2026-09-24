"""The extraction contract.

These models do double duty. They validate what comes back, and their JSON
schema is handed to the model as a tool definition, which means the field
descriptions below are prompt text rather than documentation for you. Edit
them with that in mind.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Deliverable(BaseModel):
    type: str = Field(description="One of: reel, story, ugc_video, static_post")
    count: int = Field(description="How many of this deliverable the contract requires")


class LineItem(BaseModel):
    description: str = Field(description="The line item text exactly as written on the invoice")
    quantity: int = Field(description="Quantity billed on this line")
    unit_price: float | None = Field(default=None, description="Price per unit in USD, digits only")
    amount: float | None = Field(default=None, description="Line total in USD, digits only")


class ContractFields(BaseModel):
    """Every field is optional on purpose.

    A required field forces the model to produce something even when the
    document does not contain it, which is how you manufacture
    hallucinations. Optional fields with a null default give the model a
    legitimate way to say "not present". The missing_reference cases in the
    corpus exist specifically to measure whether it takes that option.
    """

    creator_name: str | None = Field(
        default=None,
        description="Name of the creator or counterparty, copied exactly as written including any suffix such as LLC or Inc.")
    contract_id: str | None = Field(
        default=None, description="Agreement number, for example MC-2026-4418")
    rate_usd: float | None = Field(
        default=None,
        description="Total contracted fee in USD as a number. If the document writes the fee in words, convert it to digits.")
    deliverables: list[Deliverable] = Field(
        default_factory=list, description="Every deliverable the contract requires")
    usage_window_start: date | None = None
    usage_window_end: date | None = None
    payment_terms_days: int | None = Field(
        default=None, description="Net payment terms in days, for example 30")


class InvoiceFields(BaseModel):
    vendor_name: str | None = Field(
        default=None, description="Who is billing, copied exactly as written")
    billing_on_behalf_of: str | None = Field(
        default=None,
        description="If an agency is billing for a creator, the creator's name. Null if the invoice does not say.")
    invoice_number: str | None = None
    invoice_date: date | None = None
    contract_reference: str | None = Field(
        default=None,
        description="Contract number cited on the invoice. Return null if the invoice does not cite one. Never infer it.")
    line_items: list[LineItem] = Field(default_factory=list)
    total_usd: float | None = Field(
        default=None, description="Total amount due in USD as a number")
