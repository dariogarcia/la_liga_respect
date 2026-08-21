from typing import List, Dict, Any
from .models import SourceDocument

class QuoteExtractor:
    def extract(self, coach: str, game_id: str, document: SourceDocument) -> List[Dict[str, Any]]:
        """
        Extracts verbatim referee-related quotes for a specific coach.
        Returns a request for the LLM agent to perform the extraction.
        """
        return [{
            "status": "AGENT_REQUIRED",
            "coach": coach,
            "document_text": document.text,
            "instruction": "Extract verbatim quotes from the text where the coach discusses the referee. "
                            "Return as JSON: [{'text': '...', 'referee_related': True}]"
        }]
