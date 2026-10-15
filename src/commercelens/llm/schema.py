"""
Review Intelligence Data Schema & Taxonomy
===========================================
Defines the Pydantic structured output models, controlled theme taxonomy,
sentiment labels, and database record models for customer review analysis.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"
    UNCLEAR = "unclear"


class ConfidenceBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewTheme(str, Enum):
    DELIVERY_DELAY = "delivery_delay"
    DELIVERY_TRACKING = "delivery_tracking"
    DAMAGED_OR_DEFECTIVE_PRODUCT = "damaged_or_defective_product"
    PRODUCT_NOT_AS_DESCRIBED = "product_not_as_described"
    MISSING_OR_WRONG_ITEM = "missing_or_wrong_item"
    POOR_PRODUCT_QUALITY = "poor_product_quality"
    SELLER_COMMUNICATION = "seller_communication"
    PACKAGING_ISSUE = "packaging_issue"
    PAYMENT_OR_PRICING = "payment_or_pricing"
    RETURN_OR_REFUND = "return_or_refund"
    POSITIVE_PRODUCT_EXPERIENCE = "positive_product_experience"
    POSITIVE_DELIVERY_EXPERIENCE = "positive_delivery_experience"
    POSITIVE_SELLER_EXPERIENCE = "positive_seller_experience"
    OTHER = "other"
    UNCLEAR = "unclear"


SUPPORTED_THEMES = [theme.value for theme in ReviewTheme]

# Taxonomy metadata mapping theme -> high level category
THEME_CATEGORY_MAPPING = {
    ReviewTheme.DELIVERY_DELAY.value: "delivery",
    ReviewTheme.DELIVERY_TRACKING.value: "delivery",
    ReviewTheme.POSITIVE_DELIVERY_EXPERIENCE.value: "delivery",
    ReviewTheme.DAMAGED_OR_DEFECTIVE_PRODUCT.value: "product",
    ReviewTheme.PRODUCT_NOT_AS_DESCRIBED.value: "product",
    ReviewTheme.MISSING_OR_WRONG_ITEM.value: "product",
    ReviewTheme.POOR_PRODUCT_QUALITY.value: "product",
    ReviewTheme.POSITIVE_PRODUCT_EXPERIENCE.value: "product",
    ReviewTheme.SELLER_COMMUNICATION.value: "seller",
    ReviewTheme.POSITIVE_SELLER_EXPERIENCE.value: "seller",
    ReviewTheme.PACKAGING_ISSUE.value: "packaging",
    ReviewTheme.PAYMENT_OR_PRICING.value: "payment",
    ReviewTheme.RETURN_OR_REFUND.value: "returns",
    ReviewTheme.OTHER.value: "other",
    ReviewTheme.UNCLEAR.value: "unclear",
}


class ReviewAnalysisOutput(BaseModel):
    """
    Structured output returned by the LLM for a single text-bearing review.
    Must strictly conform to this schema.
    """
    sentiment_label: SentimentLabel = Field(
        description="Overall sentiment of the review text: positive, neutral, negative, mixed, or unclear."
    )
    primary_theme: str = Field(
        description="Single primary theme from the controlled taxonomy representing the main topic."
    )
    themes: List[str] = Field(
        default_factory=list,
        description="All applicable themes from the controlled taxonomy supported by the review text."
    )
    delivery_related: bool = Field(
        default=False,
        description="True if review mentions delivery speed, delay, carrier tracking, or shipping logistics."
    )
    product_quality_related: bool = Field(
        default=False,
        description="True if review discusses physical product quality, defects, performance, or specifications."
    )
    seller_service_related: bool = Field(
        default=False,
        description="True if review mentions seller communication, customer service, or merchant responsiveness."
    )
    packaging_related: bool = Field(
        default=False,
        description="True if review mentions product packaging, protective box, or wrapping."
    )
    payment_or_pricing_related: bool = Field(
        default=False,
        description="True if review discusses price, payment method, invoice, or billing."
    )
    returns_or_refunds_related: bool = Field(
        default=False,
        description="True if review discusses returning the item, exchange, or refund issues."
    )
    brief_summary: str = Field(
        description="Concise factual summary (1-2 sentences) of reviewer comments in the source language."
    )
    evidence_quotes: List[str] = Field(
        default_factory=list,
        description="Short verbatim phrases extracted directly from the review text justifying the analysis."
    )
    language: str = Field(
        default="pt",
        description="Detected ISO 639-1 language code (e.g., 'pt', 'en', 'es', 'unclear')."
    )
    confidence_band: ConfidenceBand = Field(
        default=ConfidenceBand.MEDIUM,
        description="LLM self-estimated confidence band: low, medium, or high (not a calibrated probability)."
    )

    @field_validator("primary_theme")
    @classmethod
    def validate_primary_theme(cls, v: str) -> str:
        clean_v = v.strip().lower()
        if clean_v not in SUPPORTED_THEMES:
            return ReviewTheme.OTHER.value
        return clean_v

    @field_validator("themes")
    @classmethod
    def validate_themes(cls, v: List[str]) -> List[str]:
        valid = []
        for t in v:
            clean_t = t.strip().lower()
            if clean_t in SUPPORTED_THEMES and clean_t not in valid:
                valid.append(clean_t)
        return valid


class ReviewAnalysisRecord(ReviewAnalysisOutput):
    """
    Full persistence record including review identifiers, provenance, and audit metadata.
    """
    review_id: str
    order_id: str
    model_name: str
    prompt_version: str
    content_hash: str
    status: str = "completed"
    error_category: Optional[str] = None
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_parent_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for fact_review_analysis table insertion."""
        import json
        return {
            "review_id": self.review_id,
            "order_id": self.order_id,
            "sentiment_label": self.sentiment_label.value,
            "primary_theme": self.primary_theme,
            "delivery_related": self.delivery_related,
            "product_quality_related": self.product_quality_related,
            "seller_service_related": self.seller_service_related,
            "packaging_related": self.packaging_related,
            "payment_or_pricing_related": self.payment_or_pricing_related,
            "returns_or_refunds_related": self.returns_or_refunds_related,
            "brief_summary": self.brief_summary,
            "evidence_quotes": json.dumps(self.evidence_quotes, ensure_ascii=False),
            "language": self.language,
            "confidence_band": self.confidence_band.value,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "content_hash": self.content_hash,
            "status": self.status,
            "error_category": self.error_category,
            "processed_at": self.processed_at,
        }


class GenerationTelemetry(BaseModel):
    """
    Diagnostic telemetry captured per generation attempt without sensitive PII or raw text.
    Distinguishes missing metadata (None) from actual zero values (0).
    """

    model_identifier: str = Field(
        description="Configured model identifier (e.g. gemini-3.8-flash)"
    )
    attempt_number: int = Field(
        description="1-indexed attempt number for this review generation attempt"
    )
    latency_seconds: float = Field(
        description="Roundtrip latency in seconds for this attempt"
    )
    error_category: Optional[str] = Field(
        default=None,
        description="HTTP/API or parsing error category if failed (None if attempt succeeded)",
    )
    finish_reason: Optional[str] = Field(
        default=None,
        description="Candidate finish reason (e.g. STOP, MAX_TOKENS, SAFETY, None if missing)",
    )
    prompt_tokens: Optional[int] = Field(
        default=None,
        description="Prompt token count (None if metadata absent, 0 if genuinely 0)",
    )
    thought_tokens: Optional[int] = Field(
        default=None,
        description="Thinking/thought token count (None if metadata absent, 0 if genuinely 0)",
    )
    candidate_tokens: Optional[int] = Field(
        default=None,
        description="Candidate token count (None if metadata absent, 0 if genuinely 0)",
    )
    response_text_length: Optional[int] = Field(
        default=None,
        description="Length of candidate response text in characters (None if absent, 0 if empty string)",
    )
    validation_result: str = Field(
        description="Validation outcome: 'valid', 'schema_invalid', 'json_decode_error', 'truncated', 'safety_blocked', 'empty', or 'api_error'",
    )

