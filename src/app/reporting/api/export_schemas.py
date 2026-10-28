"""`DataExportRead` (api-endpoints.md 9.1): documents the streamed body. Its parts are the
domain's export records, so the schema and the body cannot drift apart (ADR-046)."""

from datetime import datetime

from pydantic import BaseModel

from app.reporting.domain.data_export import (
    ExportAddress,
    ExportContactMessage,
    ExportOffer,
    ExportOrder,
    ExportProfile,
    ExportReview,
)


class DataExportRead(BaseModel):
    format_version: int
    exported_at: datetime
    profile: ExportProfile
    addresses: list[ExportAddress]
    orders: list[ExportOrder]
    reviews: list[ExportReview]
    offers: list[ExportOffer]
    contact_messages: list[ExportContactMessage]
