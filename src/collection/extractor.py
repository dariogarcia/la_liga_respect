import re
import unicodedata
from typing import Any, Dict, List

from ..utils import llm
from .models import SourceDocument

REFEREE_KEYWORDS = [
    r"árbitro", r"árbitra", r"árbitros", r"árbitras", r"arbitraje",
    r"arbitrajes", r"colegiado", r"colegiada", r"terna", r"referí",
    r"referee", r"officiat", r"\bvar\b",
]
REFEREE_RE = re.compile("|".join(REFEREE_KEYWORDS), re.IGNORECASE)

QUOTE_RE = re.compile(r'[«“"]([^»”"]{25,800})[»”"]')

MIN_QUOTE_LEN = 25
MAX_DOC_CHARS = 12000


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


# Reporting verbs used to attribute speech in Spanish press articles.
# Kept in raw (accented) form for matching raw text, and normalized
# (accent-stripped, lowercase) for matching _normalize()d text.
REPORTING_VERBS_RAW = (
    "dijo", "afirmó", "aseguró", "señaló", "consideró", "opinó",
    "reconoció", "lamentó", "criticó", "declaró", "apuntó", "explicó",
    "advirtió", "reclamó", "sentenció", "destacó", "valoró", "quiso",
    "recalcó", "aseveró", "comentó", "indicó", "reveló", "admitió",
    "soltó", "zanjó",
)
REPORTING_VERBS = tuple(_normalize(v) for v in REPORTING_VERBS_RAW)

# How many sentences a coach's last name mention remains a valid
# attribution context ("speaker state") for unattributed quotes.
MENTION_WINDOW = 12

# "...", dijo el portugués. / afirmó el técnico.  (post-quote epithet)
ATTR_EPITHET_RE = re.compile(
    r"\b(?:" + "|".join(REPORTING_VERBS) + r")\s+(?:el|la|los|las)\b"
)

# Mourinho dijo: "..."  (capitalized name + reporting verb, raw text)
ATTR_NAME_VERB_RE = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\s+(?:" + "|".join(REPORTING_VERBS_RAW) + r")\b"
)

# Simeone: "..."  (name + colon introducing a quote, raw text)
ATTR_NAME_COLON_RE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+):\s*[«\"“]")

# Mourinho, Flick o Simeone  (coordination of capitalized names)
NAME_ENUM_RE = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:,\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+"
    r"(?:\s+[oy]\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?"
)

# Common sentence-initial words that would otherwise look like names.
CAP_WORD_STOPWORDS = {
    "despues", "ahora", "tambien", "ademas", "antes", "luego",
    "entonces", "finalmente", "solamente", "unicamente",
    "posteriormente", "solto",
}

# First-person markers: evidence that unquoted text is direct speech
# rather than journalist narration.
FIRST_PERSON_RE = re.compile(
    r"\b(yo|me|mi|mis|nos|nosotros|nuestro|nuestra|creo|creemos|opino|"
    r"opine|pienso|pensamos|quiero|queremos|somos|estamos|jugamos|"
    r"ganamos|perdimos|vimos|dije|dijimos)\b"
)


def _name_tokens(coach: str) -> List[str]:
    return [_normalize(t) for t in coach.split() if len(t) > 2]


def is_candidate_document(coach: str, document: SourceDocument) -> bool:
    """
    Cheap local pre-filter run before (potentially LLM-backed) extraction.

    A document can only yield referee-related quotes from the coach if
    the article text mentions the coach (attribution needs a name
    mention) and talks about officiating (REFEREE_RE). Documents failing
    either check are skipped without an extraction call, which typically
    cuts LLM extraction from up to 6 calls per coach to 1-2.

    This is behavior-preserving for the heuristic extractor: its
    attribution and referee-keyword logic could never produce quotes
    from a document failing either check.
    """
    tokens = _name_tokens(coach)
    if not tokens:
        # No usable name tokens: cannot pre-filter safely.
        return True
    norm = _normalize(document.text)
    return _mentions(norm, tokens) and bool(REFEREE_RE.search(document.text))


def _mentions(text_normalized: str, tokens: List[str]) -> bool:
    return any(t in text_normalized for t in tokens)


def _attribution_target(raw: str, normalized: str, tokens: List[str]):
    """
    Classify explicit speech attribution in a sentence.

    Returns "self" when the sentence attributes speech to the target coach
    (name + colon or name + reporting verb), "other" when it attributes to
    someone else (epithet, or a different name), None when unclear.
    """
    if ATTR_EPITHET_RE.search(normalized):
        return "other"
    for pattern in (ATTR_NAME_COLON_RE, ATTR_NAME_VERB_RE):
        m = pattern.search(raw)
        if m and _normalize(m.group(1)) not in CAP_WORD_STOPWORDS:
            name = _normalize(m.group(1))
            return "self" if name in tokens else "other"
    return None


def _in_enumeration(raw: str, tokens: List[str]) -> bool:
    """True when the coach's name appears inside a list of other names."""
    for m in NAME_ENUM_RE.finditer(raw):
        if _mentions(_normalize(m.group(0)), tokens):
            return True
    return False


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= MIN_QUOTE_LEN]


class HeuristicQuoteExtractor:
    """
    Fallback extractor: finds referee-related quoted speech without an LLM.

    Attribution heuristics, in order of strength:
    1. Explicit attribution to the coach: name + colon ("Simeone: \"...\"")
       or name + reporting verb ("Simeone declaró"), or the coach's name
       in the quote itself, the sentence, or the previous one.
    2. Speaker-state inheritance: unattributed quotes are assigned to the
       coach when his name was mentioned within the last MENTION_WINDOW
       sentences (presser articles attribute once, then quote at length).
       The state is reset by any sentence attributing speech to someone
       else, and names listed in enumerations ("Mourinho, Flick o
       Simeone") never set the state.
    3. Unquoted text counts only as reported speech (coach name plus a
       reporting verb) or inherited direct speech (first-person markers).

    Quotes are flagged as low confidence.
    """

    def extract(self, coach: str, game_id: str, document: SourceDocument) -> List[Dict[str, Any]]:
        tokens = _name_tokens(coach)
        sentences = _split_sentences(document.text)
        norm = [_normalize(s) for s in sentences]
        quotes = []
        last_mention = None
        for i, sentence in enumerate(sentences):
            attr = _attribution_target(sentence, norm[i], tokens)
            mentions = _mentions(norm[i], tokens)
            if attr == "self":
                last_mention = i
            elif attr == "other":
                last_mention = None
            elif mentions and not _in_enumeration(sentence, tokens):
                last_mention = i
            if not REFEREE_RE.search(sentence):
                continue
            prev_ok = i > 0 and _mentions(norm[i - 1], tokens) and (
                _attribution_target(sentences[i - 1], norm[i - 1], tokens) != "other"
                and not _in_enumeration(sentences[i - 1], tokens)
            )
            in_context = (mentions and attr != "other") or prev_ok
            inherited = (
                last_mention is not None
                and (i - last_mention) <= MENTION_WINDOW
                and attr != "other"
            )
            matches = QUOTE_RE.findall(sentence)
            if matches:
                for m in matches:
                    if not REFEREE_RE.search(m):
                        continue
                    if in_context or _mentions(_normalize(m), tokens) or inherited:
                        quotes.append({"text": m.strip(), "referee_related": True, "confidence": "low"})
            elif (in_context and any(v in norm[i] for v in REPORTING_VERBS)) or (
                inherited and FIRST_PERSON_RE.search(norm[i])
            ):
                quotes.append({"text": sentence, "referee_related": True, "confidence": "low"})
        return quotes


class LLMQuoteExtractor:
    """
    Extracts verbatim referee-related quotes for a specific coach using an LLM.
    Requires LLM_API_KEY (or PROVIDER_API_KEY).
    """

    def extract(self, coach: str, game_id: str, document: SourceDocument) -> List[Dict[str, Any]]:
        system = (
            "You are a precise information extraction engine. You extract verbatim quotes "
            "from sports press articles. You never invent or paraphrase text. "
            "Respond only with JSON."
        )
        user = (
            f"From the article below, extract the verbatim sentences (exact substring copies, "
            f"in the original language) spoken by or attributed to the coach '{coach}' "
            f"that refer to the referee, officiating, VAR, or a specific refereeing decision. "
            f"Do NOT include sentences spoken by other people. "
            f"If the article contains no such quotes from this coach, return an empty list.\n\n"
            f"Respond as JSON: {{\"quotes\": [{{\"text\": \"...\", \"referee_related\": true}}]}}\n\n"
            f"ARTICLE:\n{document.text[:MAX_DOC_CHARS]}"
        )
        data = llm.llm_chat(system, user, json_mode=True, temperature=0.0)
        quotes = []
        for q in data.get("quotes", []):
            text = (q.get("text") or "").strip()
            if text and q.get("referee_related", True):
                quotes.append({"text": text, "referee_related": True, "confidence": "llm"})
        return quotes


def get_extractor():
    if llm.llm_available():
        return LLMQuoteExtractor()
    print("No LLM API key configured, falling back to heuristic quote extraction (lower quality).")
    return HeuristicQuoteExtractor()
