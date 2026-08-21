import hashlib

def quote_hash(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def deduplicate_quotes(quotes: list) -> list:
    seen = set()
    unique = []
    for q in quotes:
        h = quote_hash(q["text"])
        if h not in seen:
            seen.add(h)
            unique.append(q)
    return unique
