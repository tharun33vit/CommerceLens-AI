"""
LLM Client Abstraction, Gemini Client & Deterministic Mock
==========================================================
Provides the abstract base client, production Google Gemini client using google.genai,
bounded retries, rate limiting, token usage estimation, and a deterministic
mock client for offline testing and evaluation.
"""

import json
import logging
import os
import random
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from pydantic import ValidationError

from commercelens.llm.prompts import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    build_analysis_prompt,
)
from commercelens.llm.redact import is_quote_grounded, validate_and_filter_quotes
from commercelens.llm.schema import (
    ConfidenceBand,
    GenerationTelemetry,
    ReviewAnalysisOutput,
    ReviewTheme,
    SentimentLabel,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Exception Hierarchy for Granular Error Categorization
# ------------------------------------------------------------------------------
class GeminiClientError(RuntimeError):
    """Base exception for Gemini LLM client errors with explicit category classification."""

    def __init__(self, message: str, error_category: Optional[str] = None):
        super().__init__(message)
        self.error_category = error_category or self.__class__.__name__


class GeminiQuotaExhaustedError(GeminiClientError):
    """
    Raised when the Gemini API returns an explicit quota exhaustion error (e.g. 429 RESOURCE_EXHAUSTED).
    Signals that daily/project quotas are depleted and further calls will fail,
    so prompt batch termination is warranted rather than retrying or continuing.
    """

    def __init__(self, message: str):
        super().__init__(message, error_category="QuotaExhaustedError")


class GeminiTransientError(GeminiClientError):
    """
    Raised when Gemini API encounters a transient network or server error (e.g. HTTP 503, 500, 502, 504, timeout).
    Eligible for bounded exponential backoff retries.
    """

    def __init__(self, message: str, error_category: str = "ServiceUnavailable"):
        super().__init__(message, error_category=error_category)


class GeminiStructuredOutputError(GeminiClientError):
    """
    Base exception for structured output generation, parsing, and schema validation failures.
    Eligible for a small, bounded retry budget (e.g. 1 retry).
    """

    pass


class OutputTruncatedError(GeminiStructuredOutputError):
    """Raised when Gemini output is truncated because it exceeded max_output_tokens (finish_reason=MAX_TOKENS)."""

    def __init__(self, message: str):
        super().__init__(message, error_category="OutputTruncatedError")


class SafetyBlockedError(GeminiStructuredOutputError):
    """Raised when candidate content is blocked by Gemini safety or content filters."""

    def __init__(self, message: str):
        super().__init__(message, error_category="SafetyBlockedError")


class EmptyResponseError(GeminiStructuredOutputError):
    """Raised when Gemini returns an empty candidate or missing text response."""

    def __init__(self, message: str):
        super().__init__(message, error_category="EmptyResponseError")


class MalformedJSONError(GeminiStructuredOutputError):
    """Raised when Gemini output cannot be parsed as valid JSON (e.g. Unterminated string, syntax error)."""

    def __init__(self, message: str):
        super().__init__(message, error_category="JSONDecodeError")


class SchemaValidationError(GeminiStructuredOutputError):
    """Raised when JSON parsed successfully but failed Pydantic schema validation."""

    def __init__(self, message: str):
        super().__init__(message, error_category="SchemaValidationError")


def is_quota_exhausted_error(exc: Exception) -> bool:
    """
    Determines whether an exception indicates explicit Gemini daily/project quota exhaustion
    (e.g., 429 RESOURCE_EXHAUSTED, quota limit exceeded).
    Distinguishes quota exhaustion from transient service errors such as HTTP 503/500 or timeouts.
    """
    if isinstance(exc, GeminiQuotaExhaustedError):
        return True

    msg = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    # Never classify pure 500, 502, 503, 504, timeout, or connection blips as quota exhaustion
    transient_indicators = [
        "503",
        "502",
        "504",
        "500",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "internal server error",
        "connection reset",
        "connection refused",
        "timed out",
        "timeout",
        "unavailable",
    ]
    has_transient = any(t in msg for t in transient_indicators)
    has_quota = any(q in msg for q in ["quota", "resource_exhausted", "resourceexhausted"])
    if has_transient and not has_quota:
        return False

    # Check for quota-specific indicators
    quota_indicators = [
        "resource_exhausted",
        "resourceexhausted",
        "quota exceeded",
        "quota_exceeded",
        "daily quota",
        "exceeded your current quota",
        "free_tier_requests",
        "generatecontentrequestsperday",
    ]
    if any(indicator in msg for indicator in quota_indicators):
        return True
    if any(indicator in exc_type for indicator in quota_indicators):
        return True

    if "resource" in msg and "exhausted" in msg:
        return True
    if "quota" in msg and ("exhaust" in msg or "exceed" in msg or "limit" in msg or "check" in msg):
        return True

    # Check status / code attributes if present (e.g. google.genai APIError)
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    status = str(getattr(exc, "status", "")).lower()
    if "resource_exhausted" in status:
        return True
    if code == 429 and ("quota" in msg or "resource_exhausted" in msg or "exhausted" in msg or not msg):
        return True

    return False


def is_transient_service_error(exc: Exception) -> bool:
    """Check if exception represents a transient service or network failure eligible for retry."""
    if isinstance(exc, GeminiTransientError):
        return True
    msg = str(exc).lower()
    transient_indicators = [
        "503",
        "502",
        "504",
        "500",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "internal server error",
        "connection reset",
        "connection refused",
        "timed out",
        "timeout",
        "unavailable",
    ]
    return any(indicator in msg for indicator in transient_indicators)


class LLMClientBase(ABC):
    """Abstract interface for customer review intelligence providers."""

    @abstractmethod
    def analyze_review(self, sanitized_text: str) -> ReviewAnalysisOutput:
        """Analyze a single sanitized review text and return structured output."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the canonical model identifier."""
        pass

    @abstractmethod
    def get_token_usage(self) -> Dict[str, int]:
        """Return cumulative token usage and request statistics."""
        pass

    def get_last_telemetry(self) -> Optional[GenerationTelemetry]:
        """Return the most recent generation attempt telemetry."""
        return None

    def get_telemetry_history(self) -> List[GenerationTelemetry]:
        """Return all generation attempt telemetry recorded by this client."""
        return []


class GeminiLLMClient(LLMClientBase):
    """
    Production client for Google Gemini models using the official google-genai SDK.
    Features:
    - Native Pydantic structured output schema enforcement.
    - Explicit lowest thinking level ('low') for gemini-3.8-flash to minimize token waste.
    - Safe diagnostic telemetry per generation attempt (latency, finish reasons, token counts).
    - Bounded exponential backoff with jitter for transient errors (429, 503).
    - Rate-limiting interval between successive calls.
    - Cumulative token and request telemetry.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 10.0,
        request_interval: float = 0.5,
        max_output_tokens: int = 2048,
        thinking_level: Optional[str] = None,
        temperature: Optional[float] = None,
    ):
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key or not resolved_key.strip():
            raise ValueError(
                "GEMINI_API_KEY is not configured. Supply a valid key in .env or use MockLLMClient."
            )

        self._api_key = resolved_key.strip()
        self._model_name = (
            model_name
            or os.environ.get("GEMINI_MODEL", "").strip()
            or os.environ.get("LLM_MODEL", "").strip()
            or "gemini-3.8-flash"
        )
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.request_interval = request_interval
        self.max_output_tokens = max_output_tokens

        # Determine model-specific thinking level:
        # - gemini-3.5-flash-lite: use minimal thinking (optimal for high-throughput classification)
        # - gemini-3.8-flash: use lowest supported thinking level (low)
        if thinking_level is not None:
            self.thinking_level = thinking_level
        else:
            env_thinking = os.environ.get("GEMINI_THINKING_LEVEL", "").strip()
            if env_thinking:
                self.thinking_level = env_thinking
            elif "flash-lite" in self._model_name.lower() or "3.5" in self._model_name.lower():
                self.thinking_level = "minimal"
            else:
                self.thinking_level = "low"

        # Determine model-specific sampling parameters:
        # gemini-3.5-flash-lite does not support custom temperature/top_p/top_k.
        # Remove deprecated sampling settings where required by candidate model.
        if temperature is not None:
            self.temperature = temperature
        else:
            if "flash-lite" in self._model_name.lower() or "3.5" in self._model_name.lower():
                self.temperature = None
            else:
                self.temperature = 0.1

        # Initialize the official google-genai client
        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=self._api_key)
        self._types = types

        # Metrics telemetry
        self.total_prompt_tokens = 0
        self.total_candidate_tokens = 0
        self.total_requests = 0
        self.failed_requests = 0
        self._last_request_time = 0.0

        # Safe diagnostic telemetry records per attempt
        self.telemetry_history: List[GenerationTelemetry] = []
        self.last_telemetry: Optional[GenerationTelemetry] = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def get_token_usage(self) -> Dict[str, int]:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_candidate_tokens": self.total_candidate_tokens,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
        }

    def get_last_telemetry(self) -> Optional[GenerationTelemetry]:
        """Return the most recent generation attempt telemetry."""
        return self.last_telemetry

    def get_telemetry_history(self) -> List[GenerationTelemetry]:
        """Return all generation attempt telemetry recorded by this client."""
        return list(self.telemetry_history)

    def _record_telemetry(self, telemetry: GenerationTelemetry) -> None:
        """Safely records diagnostic telemetry without sensitive text, API keys, or raw payloads."""
        self.last_telemetry = telemetry
        self.telemetry_history.append(telemetry)
        logger.info(
            "Gemini attempt %d diagnostic: model=%s latency=%.3fs finish_reason=%s "
            "prompt_tokens=%s thought_tokens=%s candidate_tokens=%s text_length=%s "
            "validation=%s error_category=%s",
            telemetry.attempt_number,
            telemetry.model_identifier,
            telemetry.latency_seconds,
            telemetry.finish_reason if telemetry.finish_reason is not None else "N/A",
            telemetry.prompt_tokens if telemetry.prompt_tokens is not None else "N/A",
            telemetry.thought_tokens if telemetry.thought_tokens is not None else "N/A",
            telemetry.candidate_tokens if telemetry.candidate_tokens is not None else "N/A",
            telemetry.response_text_length if telemetry.response_text_length is not None else "N/A",
            telemetry.validation_result,
            telemetry.error_category if telemetry.error_category is not None else "none",
        )

    def _rate_limit_wait(self) -> None:
        """Enforce spacing between consecutive API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)

    def _build_generate_content_config(self) -> Any:
        """
        Builds GenerateContentConfig for google-genai SDK with:
        - Structured JSON schema enforcement via ReviewAnalysisOutput.
        - Model-tailored thinking level (minimal for gemini-3.5-flash-lite, low for gemini-3.8-flash).
        - Model-tailored sampling parameters (omitting deprecated temperature for gemini-3.5-flash-lite).
        - Configurable max_output_tokens token budget with adequate headroom.
        """
        thinking_config = None
        if hasattr(self._types, "ThinkingConfig"):
            try:
                level_enum = getattr(self._types, "ThinkingLevel", None)
                if level_enum is not None and hasattr(level_enum, self.thinking_level.upper()):
                    resolved_level = getattr(level_enum, self.thinking_level.upper())
                else:
                    resolved_level = self.thinking_level.upper()
                thinking_config = self._types.ThinkingConfig(thinking_level=resolved_level)
            except Exception as exc:
                logger.warning("Could not instantiate ThinkingConfig: %s", exc)

        config_kwargs: Dict[str, Any] = {
            "system_instruction": SYSTEM_INSTRUCTION,
            "max_output_tokens": self.max_output_tokens,
            "response_mime_type": "application/json",
            "response_schema": ReviewAnalysisOutput,
        }
        # Only pass temperature if supported and configured for the target model
        if self.temperature is not None:
            config_kwargs["temperature"] = self.temperature

        if thinking_config is not None:
            config_kwargs["thinking_config"] = thinking_config

        return self._types.GenerateContentConfig(**config_kwargs)

    @staticmethod
    def _extract_token_counts(
        usage_metadata: Any,
    ) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """
        Safely extracts prompt, thought, and candidate token counts from usage metadata.
        Strictly distinguishes missing metadata (None) from genuine zero token counts (0).
        """
        if usage_metadata is None:
            return None, None, None

        from unittest.mock import MagicMock

        if isinstance(usage_metadata, MagicMock):
            p = getattr(usage_metadata, "prompt_token_count", None)
            th = getattr(
                usage_metadata,
                "thoughts_token_count",
                getattr(usage_metadata, "thought_token_count", None),
            )
            c = getattr(usage_metadata, "candidates_token_count", None)
            return (
                int(p) if isinstance(p, (int, float)) and not isinstance(p, MagicMock) else None,
                int(th) if isinstance(th, (int, float)) and not isinstance(th, MagicMock) else None,
                int(c) if isinstance(c, (int, float)) and not isinstance(c, MagicMock) else None,
            )

        if isinstance(usage_metadata, dict):
            p = usage_metadata.get("prompt_token_count", usage_metadata.get("prompt_tokens"))
            th = usage_metadata.get(
                "thoughts_token_count",
                usage_metadata.get("thought_token_count", usage_metadata.get("thought_tokens")),
            )
            c = usage_metadata.get("candidates_token_count", usage_metadata.get("candidate_tokens"))
        else:
            p = getattr(
                usage_metadata,
                "prompt_token_count",
                getattr(usage_metadata, "prompt_tokens", None),
            )
            th = getattr(
                usage_metadata,
                "thoughts_token_count",
                getattr(
                    usage_metadata,
                    "thought_token_count",
                    getattr(usage_metadata, "thought_tokens", None),
                ),
            )
            c = getattr(
                usage_metadata,
                "candidates_token_count",
                getattr(usage_metadata, "candidate_tokens", None),
            )

        return (
            int(p) if p is not None else None,
            int(th) if th is not None else None,
            int(c) if c is not None else None,
        )

    @staticmethod
    def _extract_finish_reason(candidate: Any) -> Optional[str]:
        """Safely extracts finish reason string from candidate metadata."""
        if candidate is None:
            return None
        from unittest.mock import MagicMock

        fr = getattr(candidate, "finish_reason", None)
        if fr is None:
            return None
        if isinstance(fr, MagicMock):
            name = getattr(fr, "name", None)
            return str(name) if name and not isinstance(name, MagicMock) else None
        if isinstance(fr, str):
            return fr
        return getattr(fr, "name", str(fr))

    @staticmethod
    def _extract_raw_text(response: Any, candidate: Any) -> Optional[str]:
        """Safely extracts raw text content from response or candidate content parts."""
        from unittest.mock import MagicMock

        if hasattr(response, "text") and response.text and not isinstance(response.text, MagicMock):
            return response.text
        if candidate is not None and hasattr(candidate, "content") and candidate.content:
            parts = getattr(candidate.content, "parts", None)
            if parts and not isinstance(parts, MagicMock):
                text_parts = [
                    getattr(p, "text", "")
                    for p in parts
                    if hasattr(p, "text") and p.text and not isinstance(p.text, MagicMock)
                ]
                if text_parts:
                    return "".join(text_parts)
        return None

    def _extract_and_validate_response(
        self, response: Any, sanitized_text: str
    ) -> ReviewAnalysisOutput:
        """
        Inspects response structure, completion metadata, and finish reasons,
        safely parses structured JSON output, and validates against ReviewAnalysisOutput schema.
        Never performs fragile regex/string repair or silent field hallucination.
        """
        from unittest.mock import MagicMock

        # 1. Inspect candidates presence
        candidates = getattr(response, "candidates", None)
        if candidates is not None and not isinstance(candidates, MagicMock):
            if len(candidates) == 0:
                raise EmptyResponseError("Gemini response contained no candidate outputs.")

        candidate = None
        if candidates:
            try:
                candidate = candidates[0]
            except (IndexError, TypeError):
                candidate = None

        # 2. Inspect finish reason before parsing
        if candidate is not None:
            finish_reason = getattr(candidate, "finish_reason", None)
            if finish_reason is not None and not isinstance(finish_reason, MagicMock):
                finish_str = str(finish_reason).upper()
                if "MAX_TOKENS" in finish_str:
                    raise OutputTruncatedError(
                        f"Gemini output truncated: maximum output token limit reached (finish_reason={finish_reason})."
                    )
                if any(b in finish_str for b in ["SAFETY", "BLOCKLIST", "PROHIBITED"]):
                    raise SafetyBlockedError(
                        f"Gemini output candidate was blocked by content policy (finish_reason={finish_reason})."
                    )
                if "RECITATION" in finish_str:
                    raise SafetyBlockedError(
                        f"Gemini output candidate was blocked by recitation check (finish_reason={finish_reason})."
                    )

        # 3. Extract text from response or candidate content parts
        raw_text = self._extract_raw_text(response, candidate)

        if not raw_text or not raw_text.strip():
            raise EmptyResponseError("Gemini response contained empty or missing text content.")

        clean_text = raw_text.strip()
        # Clean markdown code fences if present (e.g. ```json ... ```)
        if clean_text.startswith("```"):
            first_newline = clean_text.find("\n")
            if first_newline != -1:
                clean_text = clean_text[first_newline + 1 :]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3].strip()

        # 4. Parse JSON without fragile repairs
        try:
            parsed_json = json.loads(clean_text)
        except json.JSONDecodeError as jde:
            logger.warning("Failed to decode JSON from Gemini structured output: %s", jde)
            raise MalformedJSONError(
                f"Malformed JSON in Gemini structured response: {jde.msg} (line {jde.lineno}, col {jde.colno})"
            ) from jde

        if not isinstance(parsed_json, dict):
            raise SchemaValidationError(
                f"Expected JSON object from model, but received {type(parsed_json).__name__}."
            )

        # 5. Enforce Pydantic schema validation
        try:
            validated_output = ReviewAnalysisOutput.model_validate(parsed_json)
        except ValidationError as ve:
            logger.warning("Gemini output failed schema validation: %s", ve)
            raise SchemaValidationError(f"Gemini output failed schema validation: {ve}") from ve

        # 6. Verify evidence quotes against source text
        valid_quotes, rejected_quotes = validate_and_filter_quotes(
            validated_output.evidence_quotes, sanitized_text
        )
        if rejected_quotes:
            logger.debug(
                "Filtered %d ungrounded quotes from Gemini response: %s",
                len(rejected_quotes),
                rejected_quotes,
            )
        validated_output.evidence_quotes = valid_quotes

        return validated_output

    def analyze_review(self, sanitized_text: str) -> ReviewAnalysisOutput:
        """
        Submits review text to Gemini with structured output configuration,
        diagnostic telemetry capture, and robust retry handling.
        """
        prompt = build_analysis_prompt(sanitized_text)
        config = self._build_generate_content_config()

        delay = self.initial_delay
        last_exception = None
        parse_retry_count = 0
        MAX_PARSE_RETRIES = 1  # Small, bounded retry budget for malformed JSON/schema output

        for attempt in range(1, self.max_retries + 1):
            attempt_start = time.perf_counter()
            response = None
            candidate = None
            finish_reason = None
            prompt_tokens = None
            thought_tokens = None
            candidate_tokens = None
            response_text_length = None
            validation_result = "api_error"
            error_category = None

            try:
                self._rate_limit_wait()
                self._last_request_time = time.time()
                self.total_requests += 1

                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                    config=config,
                )

                # Track token usage if provided in response metadata
                prompt_tokens, thought_tokens, candidate_tokens = self._extract_token_counts(
                    getattr(response, "usage_metadata", None)
                )
                if prompt_tokens is not None:
                    self.total_prompt_tokens += prompt_tokens
                if candidate_tokens is not None:
                    self.total_candidate_tokens += candidate_tokens

                candidates = getattr(response, "candidates", None)
                if candidates:
                    try:
                        candidate = candidates[0]
                    except (IndexError, TypeError):
                        candidate = None
                finish_reason = self._extract_finish_reason(candidate)

                raw_text = self._extract_raw_text(response, candidate)
                if raw_text is not None:
                    response_text_length = len(raw_text)

                # Validate response structure, metadata, finish reason, and schema
                validated_output = self._extract_and_validate_response(response, sanitized_text)

                latency = time.perf_counter() - attempt_start
                self._record_telemetry(
                    GenerationTelemetry(
                        model_identifier=self._model_name,
                        attempt_number=attempt,
                        latency_seconds=round(latency, 4),
                        error_category=None,
                        finish_reason=finish_reason,
                        prompt_tokens=prompt_tokens,
                        thought_tokens=thought_tokens,
                        candidate_tokens=candidate_tokens,
                        response_text_length=response_text_length,
                        validation_result="valid",
                    )
                )
                return validated_output

            except GeminiQuotaExhaustedError:
                # Immediate batch termination - re-raise without delay
                raise

            except Exception as e:
                last_exception = e
                self.failed_requests += 1
                latency = time.perf_counter() - attempt_start

                # Classify validation_result and error_category for diagnostic telemetry
                if isinstance(e, OutputTruncatedError):
                    validation_result = "truncated"
                    error_category = "OutputTruncatedError"
                    if finish_reason is None:
                        finish_reason = "MAX_TOKENS"
                elif isinstance(e, SafetyBlockedError):
                    validation_result = "safety_blocked"
                    error_category = "SafetyBlockedError"
                elif isinstance(e, EmptyResponseError):
                    validation_result = "empty"
                    error_category = "EmptyResponseError"
                elif isinstance(e, MalformedJSONError):
                    validation_result = "json_decode_error"
                    error_category = "JSONDecodeError"
                elif isinstance(e, SchemaValidationError):
                    validation_result = "schema_invalid"
                    error_category = "SchemaValidationError"
                elif is_quota_exhausted_error(e):
                    validation_result = "api_error"
                    error_category = "QuotaExhaustedError"
                elif is_transient_service_error(e):
                    validation_result = "api_error"
                    error_category = "ServiceUnavailable" if "503" in str(e) else "TransientAPIError"
                else:
                    validation_result = "api_error"
                    error_category = getattr(e, "error_category", type(e).__name__)

                self._record_telemetry(
                    GenerationTelemetry(
                        model_identifier=self._model_name,
                        attempt_number=attempt,
                        latency_seconds=round(latency, 4),
                        error_category=error_category,
                        finish_reason=finish_reason,
                        prompt_tokens=prompt_tokens,
                        thought_tokens=thought_tokens,
                        candidate_tokens=candidate_tokens,
                        response_text_length=response_text_length,
                        validation_result=validation_result,
                    )
                )

                # 1. Detect explicit daily/project quota exhaustion error
                if is_quota_exhausted_error(e):
                    logger.error(
                        "Gemini daily/project quota exhausted (attempt %d/%d): %s. "
                        "Terminating retries immediately to protect quota budget.",
                        attempt,
                        self.max_retries,
                        e,
                    )
                    raise GeminiQuotaExhaustedError(
                        f"Gemini API daily/project quota exhausted: {str(e)}"
                    ) from e

                # 2. Structured output failures (malformed JSON, truncated, schema invalid, safety blocked)
                if isinstance(e, GeminiStructuredOutputError):
                    parse_retry_count += 1
                    logger.warning(
                        "Gemini structured output failure (parse retry %d/%d, category: %s): %s",
                        parse_retry_count,
                        MAX_PARSE_RETRIES,
                        e.error_category,
                        e,
                    )
                    if parse_retry_count <= MAX_PARSE_RETRIES and attempt < self.max_retries:
                        time.sleep(0.5)
                        continue
                    else:
                        # Bounded structured retry budget exhausted: raise immediately with specific category
                        raise e

                # 3. Transient API/service errors (HTTP 503, 500, 502, 504, connection timeouts)
                logger.warning(
                    "Gemini API transient failure (attempt %d/%d): %s: %s",
                    attempt,
                    self.max_retries,
                    type(e).__name__,
                    e,
                )
                if attempt < self.max_retries:
                    # Exponential backoff with random jitter
                    jitter = random.uniform(0.1, 0.5)
                    sleep_time = min(delay + jitter, self.max_delay)
                    time.sleep(sleep_time)
                    delay *= 2.0
                else:
                    error_cat = "ServiceUnavailable" if "503" in str(e) else "TransientAPIError"
                    raise GeminiTransientError(
                        f"Failed to analyze review after {self.max_retries} attempts. Last error: {str(e)}",
                        error_category=error_cat,
                    ) from e

        # If loop completed without returning or re-raising
        if last_exception:
            raise last_exception
        raise GeminiClientError(f"Failed to analyze review after {self.max_retries} attempts.")


class MockLLMClient(LLMClientBase):
    """
    Deterministic rule-based mock client simulating Brazilian Portuguese review intelligence.
    Employs regex keyword extraction to generate grounded, schema-compliant responses
    without calling external APIs.
    """

    def __init__(self, model_name: str = "mock-portuguese-nlp-v1"):
        self._model_name = model_name
        self.total_requests = 0
        self.telemetry_history: List[GenerationTelemetry] = []
        self.last_telemetry: Optional[GenerationTelemetry] = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def get_token_usage(self) -> Dict[str, int]:
        return {
            "total_prompt_tokens": self.total_requests * 180,
            "total_candidate_tokens": self.total_requests * 75,
            "total_requests": self.total_requests,
            "failed_requests": 0,
        }

    def get_last_telemetry(self) -> Optional[GenerationTelemetry]:
        return self.last_telemetry

    def get_telemetry_history(self) -> List[GenerationTelemetry]:
        return list(self.telemetry_history)

    def analyze_review(self, sanitized_text: str) -> ReviewAnalysisOutput:
        """
        Parses Portuguese review text deterministically and extracts genuine
        verbatim quotes directly from the input text.
        """
        self.total_requests += 1
        text_lower = sanitized_text.lower()

        # Keyword dictionaries for Portuguese e-commerce
        patterns = {
            ReviewTheme.DELIVERY_DELAY: [
                r"\batras(o|ou|ar|ados?)\b",
                r"\bdemor(ou|a|am|ando)\b",
                r"\bn[aã]o entreg(ue|ou|aram)\b",
                r"\bn[aã]o recebi\b",
                r"\bpassou do prazo\b",
                r"\bfora do prazo\b",
                r"\bainda n[aã]o chegou\b",
                r"\bdemorou muito\b",
                r"\bprazo de entrega\b",
            ],
            ReviewTheme.DELIVERY_TRACKING: [
                r"\brastre(io|amento|ar|ie)\b",
                r"\bc[oó]digo de rastreio\b",
                r"\bcorreios\b",
                r"\bsem atualiza[cç][aã]o\b",
            ],
            ReviewTheme.POSITIVE_DELIVERY_EXPERIENCE: [
                r"\bchegou antes\b",
                r"\bentrega r[aá]pida\b",
                r"\bsuper r[aá]pido\b",
                r"\bantes do prazo\b",
                r"\br[aá]pida entrega\b",
                r"\bmuito r[aá]pido\b",
                r"\bchegou no prazo\b",
                r"\bentregue no prazo\b",
                r"\bpontual\b",
            ],
            ReviewTheme.DAMAGED_OR_DEFECTIVE_PRODUCT: [
                r"\bquebr(ado|ou|ada)\b",
                r"\bcom defeito\b",
                r"\bestrag(ado|ou)\b",
                r"\bdanific(ado|ada)\b",
                r"\brachad(o|a)\b",
                r"\bn[aã]o funciona\b",
                r"\bpifou\b",
            ],
            ReviewTheme.PRODUCT_NOT_AS_DESCRIBED: [
                r"\bdiferente da foto\b",
                r"\bpropaganda enganosa\b",
                r"\bmodelo diferente\b",
                r"\bcor errada\b",
                r"\bveio outro\b",
                r"\btamanho errado\b",
            ],
            ReviewTheme.MISSING_OR_WRONG_ITEM: [
                r"\bfaltou\b",
                r"\bproduto errado\b",
                r"\bitem faltante\b",
                r"\bveio incompleto\b",
            ],
            ReviewTheme.POOR_PRODUCT_QUALITY: [
                r"\bp[eé]ssim(o|a)\b",
                r"\bqualidade ruim\b",
                r"\bmaterial fraco\b",
                r"\bbaixa qualidade\b",
                r"\bfr[aá]gil\b",
                r"\bruim\b",
            ],
            ReviewTheme.POSITIVE_PRODUCT_EXPERIENCE: [
                r"\b[oó]tim(o|a)\b",
                r"\bexcelente\b",
                r"\bmuito bom\b",
                r"\bmuito boa\b",
                r"\bmaravilhos(o|a)\b",
                r"\blindo\b",
                r"\blinda\b",
                r"\bperfeito\b",
                r"\badorei\b",
                r"\bgostei muito\b",
                r"\brecomendo\b",
                r"\bqualidade excelente\b",
            ],
            ReviewTheme.SELLER_COMMUNICATION: [
                r"\bvendedor n[aã]o responde\b",
                r"\bmau atendimento\b",
                r"\bsem resposta\b",
                r"\bsem contato\b",
            ],
            ReviewTheme.POSITIVE_SELLER_EXPERIENCE: [
                r"\bvendedor atencioso\b",
                r"\b[oó]timo atendimento\b",
                r"\batencioso\b",
            ],
            ReviewTheme.PACKAGING_ISSUE: [
                r"\bembalagem\b",
                r"\bcaixa amassada\b",
                r"\bmal embalado\b",
                r"\brasgad(o|a)\b",
            ],
            ReviewTheme.RETURN_OR_REFUND: [
                r"\bdevolver\b",
                r"\bdevolu[cç][aã]o\b",
                r"\bestorno\b",
                r"\breembolso\b",
                r"\bcancelamento\b",
            ],
        }

        detected_themes: List[ReviewTheme] = []
        quotes: List[str] = []

        for theme, regex_list in patterns.items():
            for pat in regex_list:
                m = re.search(pat, text_lower)
                if m:
                    if theme not in detected_themes:
                        detected_themes.append(theme)
                    # Extract the exact substring from the original text
                    start, end = m.span()
                    verbatim_quote = sanitized_text[start:end]
                    if verbatim_quote and verbatim_quote not in quotes:
                        quotes.append(verbatim_quote)

        # Classify polarity
        has_negative = any(
            t in [
                ReviewTheme.DELIVERY_DELAY,
                ReviewTheme.DAMAGED_OR_DEFECTIVE_PRODUCT,
                ReviewTheme.PRODUCT_NOT_AS_DESCRIBED,
                ReviewTheme.MISSING_OR_WRONG_ITEM,
                ReviewTheme.POOR_PRODUCT_QUALITY,
                ReviewTheme.SELLER_COMMUNICATION,
                ReviewTheme.PACKAGING_ISSUE,
                ReviewTheme.RETURN_OR_REFUND,
            ]
            for t in detected_themes
        )
        has_positive = any(
            t in [
                ReviewTheme.POSITIVE_PRODUCT_EXPERIENCE,
                ReviewTheme.POSITIVE_DELIVERY_EXPERIENCE,
                ReviewTheme.POSITIVE_SELLER_EXPERIENCE,
            ]
            for t in detected_themes
        )

        if has_negative and has_positive:
            sentiment = SentimentLabel.MIXED
        elif has_negative:
            sentiment = SentimentLabel.NEGATIVE
        elif has_positive:
            sentiment = SentimentLabel.POSITIVE
        elif len(sanitized_text.split()) <= 2 and any(
            w in text_lower for w in ["ok", "bom", "regular", "sim"]
        ):
            sentiment = SentimentLabel.NEUTRAL
            detected_themes.append(ReviewTheme.UNCLEAR)
        else:
            sentiment = SentimentLabel.UNCLEAR
            detected_themes.append(ReviewTheme.UNCLEAR)

        primary_theme = (
            detected_themes[0].value
            if detected_themes
            else ReviewTheme.UNCLEAR.value
        )
        all_themes = [t.value for t in detected_themes]

        # Flags
        delivery_related = any(
            t in [
                ReviewTheme.DELIVERY_DELAY.value,
                ReviewTheme.DELIVERY_TRACKING.value,
                ReviewTheme.POSITIVE_DELIVERY_EXPERIENCE.value,
            ]
            for t in all_themes
        ) or bool(re.search(r"\b(entrega|prazo|cheg|correios)\b", text_lower))

        product_quality_related = any(
            t in [
                ReviewTheme.DAMAGED_OR_DEFECTIVE_PRODUCT.value,
                ReviewTheme.PRODUCT_NOT_AS_DESCRIBED.value,
                ReviewTheme.POOR_PRODUCT_QUALITY.value,
                ReviewTheme.POSITIVE_PRODUCT_EXPERIENCE.value,
            ]
            for t in all_themes
        ) or bool(re.search(r"\b(produto|qualidade|defeito|material)\b", text_lower))

        seller_service_related = any(
            t in [
                ReviewTheme.SELLER_COMMUNICATION.value,
                ReviewTheme.POSITIVE_SELLER_EXPERIENCE.value,
            ]
            for t in all_themes
        )

        packaging_related = ReviewTheme.PACKAGING_ISSUE.value in all_themes
        returns_related = ReviewTheme.RETURN_OR_REFUND.value in all_themes
        payment_related = ReviewTheme.PAYMENT_OR_PRICING.value in all_themes

        summary = f"Cliente expressa sentimento {sentiment.value} com foco em {primary_theme}."

        output = ReviewAnalysisOutput(
            sentiment_label=sentiment,
            primary_theme=primary_theme,
            themes=all_themes,
            delivery_related=delivery_related,
            product_quality_related=product_quality_related,
            seller_service_related=seller_service_related,
            packaging_related=packaging_related,
            payment_or_pricing_related=payment_related,
            returns_or_refunds_related=returns_related,
            brief_summary=summary,
            evidence_quotes=quotes[:3],
            language="pt",
            confidence_band=ConfidenceBand.HIGH if quotes else ConfidenceBand.MEDIUM,
        )

        telemetry = GenerationTelemetry(
            model_identifier=self._model_name,
            attempt_number=1,
            latency_seconds=0.001,
            error_category=None,
            finish_reason="STOP",
            prompt_tokens=180,
            thought_tokens=0,
            candidate_tokens=75,
            response_text_length=len(summary),
            validation_result="valid",
        )
        self.last_telemetry = telemetry
        self.telemetry_history.append(telemetry)

        return output


def get_llm_client(
    force_mock: bool = False,
    require_live: bool = False,
    model_name: Optional[str] = None,
    thinking_level: Optional[str] = None,
    temperature: Optional[float] = None,
) -> LLMClientBase:
    """
    Factory function resolving the LLM client.
    - If force_mock is True: returns MockLLMClient.
    - If require_live is True: requires GEMINI_API_KEY and returns GeminiLLMClient.
      Raises ValueError if GEMINI_API_KEY is missing or invalid.
    - If neither is explicitly forced: attempts GeminiLLMClient if GEMINI_API_KEY is configured.
      If GEMINI_API_KEY is absent, returns MockLLMClient for offline testing.
      If GEMINI_API_KEY is present but invalid, raises an error (no silent fallback).
    """
    if force_mock:
        logger.info("Operating in MockLLMClient mode (forced mock).")
        return MockLLMClient()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    resolved_model = (
        model_name
        or os.environ.get("GEMINI_MODEL", "").strip()
        or os.environ.get("LLM_MODEL", "").strip()
        or "gemini-3.8-flash"
    )

    if require_live:
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured in .env. "
                "Supply a valid key or pass --mock to run offline."
            )
        logger.info(
            "Initializing production GeminiLLMClient (live mode required, model=%s).",
            resolved_model,
        )
        return GeminiLLMClient(
            api_key=api_key,
            model_name=resolved_model,
            thinking_level=thinking_level,
            temperature=temperature,
        )

    if api_key:
        logger.info(
            "Initializing production GeminiLLMClient with configured GEMINI_API_KEY (model=%s).",
            resolved_model,
        )
        return GeminiLLMClient(
            api_key=api_key,
            model_name=resolved_model,
            thinking_level=thinking_level,
            temperature=temperature,
        )

    logger.info("Operating in MockLLMClient mode (deterministic Portuguese NLP).")
    return MockLLMClient()
