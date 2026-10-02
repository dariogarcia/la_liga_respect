import unittest

from src.collection.extractor import (
    HeuristicQuoteExtractor,
    REFEREE_RE,
    is_candidate_document,
    was_quoted,
)
from src.collection.models import SourceDocument


def make_doc(text):
    return SourceDocument(
        url="https://www.as.com/a",
        title="t",
        text=text,
        published_at=None,
        source_name="as.com",
    )


class TestHeuristicExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = HeuristicQuoteExtractor()
        self.coach = "Diego Simeone"

    def extract(self, text, coach=None):
        return self.extractor.extract(coach or self.coach, "1", make_doc(text))

    def test_extracts_quoted_referee_speech(self):
        text = (
            "El técnico compareció ante los medios. "
            "Simeone declaró: «Creo que el árbitro lo hizo bien, fue un trabajo muy difícil», dijo."
        )
        quotes = self.extract(text)
        self.assertTrue(any("árbitro" in q["text"] for q in quotes))
        for q in quotes:
            self.assertNotIn("«", q["text"])

    def test_ignores_non_referee_text(self):
        text = "Simeone habló de la táctica del equipo y de las bajas. «Jugamos bien», dijo Simeone."
        quotes = self.extract(text)
        self.assertEqual(quotes, [])

    def test_ignores_quotes_from_other_speakers(self):
        text = (
            "Mourinho explotó en la rueda de prensa. "
            "«El árbitro ha decidido el partido, ha sido un escándalo enorme», afirmó el portugués."
        )
        quotes = self.extract(text)
        self.assertEqual(quotes, [])

    def test_attribution_via_previous_sentence(self):
        text = (
            "Simeone compareció ante los medios y analizó el encuentro.\n"
            "«El árbitro acertó en las decisiones complicadas del partido de hoy»."
        )
        quotes = self.extract(text)
        self.assertEqual(len(quotes), 1)
        self.assertIn("acertó", quotes[0]["text"])

    def test_attribution_inside_quote(self):
        text = "«Yo, Diego Simeone, siempre respeto al árbitro porque su trabajo es muy difícil», zanjó el técnico."
        quotes = self.extract(text)
        self.assertEqual(len(quotes), 1)

    def test_reported_speech_with_reporting_verb(self):
        text = "Simeone afirmó que el árbitro señaló una falta dudosa en el minuto 90 del encuentro."
        quotes = self.extract(text)
        self.assertEqual(len(quotes), 1)
        self.assertIn("árbitro", quotes[0]["text"])

    def test_narrative_without_attribution_is_excluded(self):
        # Journalist narration about the referee, not attributed to anyone.
        text = "El árbitro señaló una falta dudosa en el minuto 90 del encuentro disputado anoche."
        quotes = self.extract(text)
        self.assertEqual(quotes, [])

    def test_reported_speech_requires_reporting_verb(self):
        text = "Simeone habló del árbitro y del resto del partido ante los medios de comunicación."
        quotes = self.extract(text)
        self.assertEqual(quotes, [])

    def test_inherits_attribution_across_quote_run(self):
        # Presser pattern: attribution once, then a long quoted block.
        text = (
            "Simeone compareció tras el triunfo en el derbi.\n"
            "\"Fue un partido intenso, ante un rival con unas transiciones increíbles.\n"
            "El árbitro ya nos dijo que este tipo de jugadas no eran expulsión.\n"
            "Pero el partido lo ganamos\"."
        )
        quotes = self.extract(text)
        self.assertEqual(len(quotes), 1)
        self.assertIn("nos dijo", quotes[0]["text"])

    def test_does_not_inherit_across_epithet_attribution(self):
        text = (
            "Simeone compareció en la previa del derbi y pidió prudencia.\n"
            "Horas más tarde, el técnico blanco repasó el partido de nuevo.\n"
            "\"El árbitro ha sido un desastre y nos ha arruinado el partido entero\", dijo el portugués."
        )
        quotes = self.extract(text)
        self.assertEqual(quotes, [])

    def test_does_not_inherit_across_other_name_attribution(self):
        text = (
            "Simeone compareció en la previa del derbi y pidió prudencia.\n"
            "El conjunto blanco entrenó por la tarde a puerta cerrada.\n"
            "Por la noche, Mourinho dijo: \"El árbitro ha perjudicado al equipo durante todo el partido\"."
        )
        quotes = self.extract(text)
        self.assertEqual(quotes, [])

    def test_colon_attribution_sets_speaker(self):
        # "Simeone: \"...\"" attributes the whole quote block to Simeone,
        # never to the other coaches named inside it.
        text = (
            "Simeone: \"Por más que te llames Mourinho, Flick o Simeone no hay que pasar la línea.\n"
            "El árbitro ya nos dijo que estas jugadas no eran expulsión en este tipo de partidos\"."
        )
        self.assertEqual(len(self.extract(text)), 1)
        self.assertEqual(self.extract(text, coach="Hansi Flick"), [])

    def test_var_keyword(self):
        self.assertTrue(REFEREE_RE.search("el VAR revisó la jugada"))
        self.assertFalse(REFEREE_RE.search("hubo varias ocasiones de gol"))


class TestIsCandidateDocument(unittest.TestCase):
    def test_keep_when_coach_mentioned_and_referee_keywords(self):
        doc = make_doc("Simeone analizó el partido y defendió al árbitro tras la polémica del VAR.")
        self.assertTrue(is_candidate_document("Diego Simeone", doc))

    def test_skip_when_coach_not_mentioned(self):
        doc = make_doc("Mourinho analizó el partido y criticó duramente al árbitro del encuentro.")
        self.assertFalse(is_candidate_document("Diego Simeone", doc))

    def test_skip_when_no_referee_keywords(self):
        doc = make_doc("Simeone habló de la táctica, las bajas y la preparación del derbi.")
        self.assertFalse(is_candidate_document("Diego Simeone", doc))

    def test_coach_name_match_tolerates_accents(self):
        doc = make_doc("Siméone elogió al árbitro del partido.")
        self.assertTrue(is_candidate_document("Diego Simeone", doc))

    def test_no_usable_name_tokens_passes_through(self):
        # "Ed" (<= 2 chars) yields no usable tokens: the filter cannot
        # judge safely, so the document is kept.
        doc = make_doc("El árbitro pitó un penalti dudoso.")
        self.assertTrue(is_candidate_document("Ed", doc))


if __name__ == "__main__":
    unittest.main()


class TestWasQuoted(unittest.TestCase):
    def test_quoted_about_anything_counts_as_coverage(self):
        # The coach is quoted about tactics (no referee mention): the
        # article still proves coverage.
        text = (
            "Diego Simeone compareció en sala de prensa. "
            "«Jugamos un gran partido y el equipo estuvo muy serio»"
        )
        self.assertTrue(was_quoted("Diego Simeone", make_doc(text)))

    def test_mention_without_quotes_is_not_coverage(self):
        text = "Diego Simeone vio el partido desde la grada con su cuerpo técnico."
        self.assertFalse(was_quoted("Diego Simeone", make_doc(text)))

    def test_other_speaker_quote_is_not_coverage(self):
        text = "El técnico del rival declaró: «El árbitro estuvo muy bien»."
        self.assertFalse(was_quoted("Diego Simeone", make_doc(text)))

    def test_no_name_tokens_is_not_coverage(self):
        self.assertFalse(was_quoted("X", make_doc("cualquier cosa")))


class TestHeuristicAssessCoverage(unittest.TestCase):
    def test_any_document_with_quotes_proves_coverage(self):
        docs = [
            make_doc("El rival entrenó en la mañana."),
            make_doc("Diego Simeone habló en la rueda de prensa: «El equipo estuvo muy bien en todo el partido»."),
        ]
        self.assertTrue(HeuristicQuoteExtractor().assess_coverage("Diego Simeone", docs))

    def test_no_quotes_anywhere_is_not_coverage(self):
        docs = [make_doc("El rival entrenó en la mañana.")]
        self.assertFalse(HeuristicQuoteExtractor().assess_coverage("Diego Simeone", docs))
