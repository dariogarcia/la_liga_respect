import re

from .models import SourceDocument, SearchResult

MIN_QUOTE_LEN = 25

# Line breaks inside articles often separate a word from the punctuation
# that follows it ("minuto 60\n,"). Whitespace-collapsing alone turns that
# into "60 ,", which then fails a substring match against a quote's "60,".
_WS_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?…])")


def _normalize(text: str) -> str:
    collapsed = " ".join(text.split())
    return _WS_BEFORE_PUNCT.sub(r"\1", collapsed).casefold()


def validate_extractions(extracted_quotes: list, document: SourceDocument) -> list:
    """
    Verifies that each extracted quote exists (whitespace-insensitively) in the
    cleaned source text, to guarantee verbatim provenance.
    """
    doc_norm = _normalize(document.text)
    validated = []
    for q in extracted_quotes:
        text = q.get("text") if isinstance(q, dict) else None
        if not text or len(text) < MIN_QUOTE_LEN:
            continue
        if _normalize(text) in doc_norm:
            validated.append(q)
    return validated
