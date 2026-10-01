from .models import SourceDocument, SearchResult

MIN_QUOTE_LEN = 25


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


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
