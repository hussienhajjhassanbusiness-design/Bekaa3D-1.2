from enum import StrEnum


class ProductType(StrEnum):
    """Permanent classification of a product (glossary: Product Type)."""

    PHYSICAL = "physical"
    STL = "stl"


class PurchaseMode(StrEnum):
    """How a physical product may be bought (BR-001). Not a fulfillment method."""

    ONLINE_ONLY = "online_only"
    WHATSAPP_ONLY = "whatsapp_only"
    BOTH = "both"


class AcceptedPaymentMethods(StrEnum):
    """How a physical product may be paid at checkout (BR-019, ADR-048). Not a purchase mode."""

    ONLINE = "online"
    CASH = "cash"
    ONLINE_OR_CASH = "online_or_cash"
