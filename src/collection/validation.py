from .models import SourceDocument, SearchResult

def validate_extractions(extracted_quotes: list, document: SourceDocument) -> list:
    """
    Verifies that the extracted quote exists verbatim in the source text.
    """
    validated = []
    for q in extracted_quotes:
        if q["text"] in document.text:
            validated.append(q)
    return validated
