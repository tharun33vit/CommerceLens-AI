"""
CommerceLens AI — Review Intelligence & LLM Module
===================================================
Provides structured customer review intelligence, PII redaction,
Portuguese NLP modeling, Gemini API integration, and analytical reporting.
"""

from commercelens.llm.client import (
    EmptyResponseError,
    GeminiClientError,
    GeminiLLMClient,
    GeminiQuotaExhaustedError,
    GeminiStructuredOutputError,
    GeminiTransientError,
    LLMClientBase,
    MalformedJSONError,
    MockLLMClient,
    OutputTruncatedError,
    SafetyBlockedError,
    SchemaValidationError,
    get_llm_client,
    is_quota_exhausted_error,
    is_transient_service_error,
)
from commercelens.llm.pipeline import ReviewIntelligencePipeline
from commercelens.llm.prompts import PROMPT_VERSION, SYSTEM_INSTRUCTION
from commercelens.llm.redact import (
    is_quote_grounded,
    normalize_review_text,
    redact_personal_info,
    validate_and_filter_quotes,
)
from commercelens.llm.schema import (
    ConfidenceBand,
    GenerationTelemetry,
    ReviewAnalysisOutput,
    ReviewAnalysisRecord,
    ReviewTheme,
    SentimentLabel,
    SUPPORTED_THEMES,
)

__all__ = [
    "GenerationTelemetry",
    "GeminiClientError",
    "GeminiLLMClient",
    "GeminiQuotaExhaustedError",
    "GeminiTransientError",
    "GeminiStructuredOutputError",
    "OutputTruncatedError",
    "SafetyBlockedError",
    "EmptyResponseError",
    "MalformedJSONError",
    "SchemaValidationError",
    "is_quota_exhausted_error",
    "is_transient_service_error",
    "MockLLMClient",
    "LLMClientBase",
    "get_llm_client",
    "ReviewIntelligencePipeline",
    "PROMPT_VERSION",
    "SYSTEM_INSTRUCTION",
    "is_quote_grounded",
    "normalize_review_text",
    "redact_personal_info",
    "validate_and_filter_quotes",
    "ReviewAnalysisOutput",
    "ReviewAnalysisRecord",
    "ReviewTheme",
    "SentimentLabel",
    "ConfidenceBand",
    "SUPPORTED_THEMES",
]
