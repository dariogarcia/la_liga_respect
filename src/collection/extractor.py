from typing import List, Dict, Any
from .models import SourceDocument

class QuoteExtractor:
    def extract(self, coach: str, game_id: str, document: SourceDocument) -> List[Dict[str, Any]]:
        """
        This method should call an LLM to extract verbatim quotes.
        For now, it returns a placeholder to maintain the pipeline.
        """
        # In the agentic version, the LLM handles this logic.
        return []
