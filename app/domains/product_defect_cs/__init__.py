"""Product-defect customer-service domain extension point."""

from app.domains.product_defect_cs.prompts import (
    PRODUCT_DEFECT_PROMPT_REGISTRY,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
)

__all__ = [
    "PRODUCT_DEFECT_PROMPT_REGISTRY",
    "PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT",
]
