"""
Text Sanitization, Redaction & Evidence Verification
====================================================
Provides text normalization, personal-contact redaction (PII protection),
and verbatim evidence quote grounding verification for Brazilian Portuguese reviews.
"""

import re
import unicodedata
from typing import List, Optional, Tuple


# Regex patterns for Brazilian contact / identity details
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)
PHONE_REGEX = re.compile(
    r"(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\s?\d{4}|\d{4})[-.\s]?\d{4}\b"
)
CPF_REGEX = re.compile(
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"
)


def redact_personal_info(text: str) -> str:
    """
    Redact confidently identifiable personal contact information (email, phone, CPF)
    from customer review text before transmitting to external LLM APIs.
    """
    if not text:
        return ""
    
    sanitized = EMAIL_REGEX.sub("[EMAIL]", text)
    sanitized = CPF_REGEX.sub("[CPF]", sanitized)
    sanitized = PHONE_REGEX.sub("[PHONE]", sanitized)
    return sanitized


def normalize_review_text(title: Optional[str], message: Optional[str]) -> str:
    """
    Combines title and message into a coherent, clean input string.
    Preserves Portuguese accentuation and grammatical structure while removing
    control characters and non-printable whitespace.
    """
    parts = []
    if title and isinstance(title, str) and title.strip():
        parts.append(title.strip())
    if message and isinstance(message, str) and message.strip():
        parts.append(message.strip())

    if not parts:
        return ""

    combined = " - ".join(parts) if len(parts) > 1 else parts[0]
    # Normalize multiple whitespace, tabs, and newlines
    combined = re.sub(r"[\r\n\t]+", " ", combined)
    combined = re.sub(r"\s{2,}", " ", combined)
    return combined.strip()


def strip_accents_and_punct(text: str) -> str:
    """Helper to normalize text for fuzzy quote grounding check."""
    # Decompose unicode to remove diacritics
    nfkd = unicodedata.normalize("NFKD", text)
    without_accents = "".join([c for c in nfkd if not unicodedata.combining(c)])
    # Lowercase and replace non-alphanumeric with single space
    cleaned = re.sub(r"[^\w\s]", " ", without_accents.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def is_quote_grounded(quote: str, source_text: str) -> bool:
    """
    Programmatically verifies whether an evidence quote extracted by the LLM
    is genuinely grounded in the source review text.

    Uses a two-tier check:
    1. Exact case-insensitive substring match.
    2. Accent/punctuation-normalized substring match (to forgive minor punctuation stripping).
    """
    if not quote or not source_text:
        return False
    
    clean_quote = quote.strip()
    if not clean_quote:
        return False

    # 1. Exact case-insensitive substring
    if clean_quote.lower() in source_text.lower():
        return True

    # 2. Relaxed match ignoring punctuation/accents
    norm_quote = strip_accents_and_punct(clean_quote)
    norm_source = strip_accents_and_punct(source_text)
    if norm_quote and norm_quote in norm_source:
        return True

    return False


def validate_and_filter_quotes(quotes: List[str], source_text: str) -> Tuple[List[str], List[str]]:
    """
    Validates a list of evidence quotes against the source text.
    Returns:
        (valid_quotes, rejected_quotes)
    """
    valid = []
    rejected = []
    for q in quotes:
        if is_quote_grounded(q, source_text):
            valid.append(q.strip())
        else:
            rejected.append(q.strip())
    return valid, rejected
