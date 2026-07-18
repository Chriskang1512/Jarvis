import unittest

from jarvis.voice.pipeline import VoicePipeline
from jarvis.voice.semantic import SemanticTranscriptContext, SemanticTranscriptNormalizer
from jarvis.voice.semantic.graph import EDGE_COMPANY, EntityEdge, EntityGraph, EntityNode


class TestSemanticTranscriptLayer(unittest.TestCase):
    """Test semantic transcript normalization before intent parsing."""

    def test_corrects_known_person_alias_in_participant_context(self):
        normalizer = SemanticTranscriptNormalizer()
        context = SemanticTranscriptContext(
            pending_field="participants",
            known_people=("아야", "유이", "유리"),
        )

        result = normalizer.normalize("아이랑 유이", "아이랑 유이", context)

        self.assertEqual(result.semantic_text, "아야랑 유이")
        self.assertEqual([(entity.type, entity.value) for entity in result.resolved_entities], [("person", "아야"), ("person", "유이")])
        self.assertEqual(result.corrections[0].source, "아이")
        self.assertEqual(result.corrections[0].target, "아야")
        self.assertEqual(result.corrections[0].entity_source, "known_person")
        self.assertEqual(result.corrections[0].resolver, "KnownPeopleResolver")
        self.assertGreaterEqual(result.corrections[0].confidence, 0.9)
        self.assertFalse(result.requires_clarification)

    def test_corrects_known_place_alias_in_location_context(self):
        normalizer = SemanticTranscriptNormalizer()
        context = SemanticTranscriptContext(
            pending_field="location",
            known_places=("서울역", "롯데월드"),
        )

        result = normalizer.normalize("설립으로 바꿔", "설립으로 바꿔", context)

        self.assertEqual(result.semantic_text, "서울역으로 바꿔")
        self.assertEqual([(entity.type, entity.value) for entity in result.resolved_entities], [("place", "서울역")])
        self.assertEqual(result.resolved_entities[0].id, "place_seoul_station")
        self.assertEqual(result.resolved_entities[0].source, "known_place")
        self.assertEqual(result.resolved_entities[0].resolver, "KnownPlaceResolver")
        self.assertGreaterEqual(result.resolved_entities[0].confidence, 0.9)

    def test_turns_person_to_calendar_meeting_hint(self):
        normalizer = SemanticTranscriptNormalizer()

        result = normalizer.normalize("아야한테 일정 등록해", "아야한테 일정 등록해", SemanticTranscriptContext())

        self.assertEqual(result.semantic_text, "아야 만나기 일정 등록해")
        self.assertIn(("person", "아야"), [(entity.type, entity.value) for entity in result.resolved_entities])
        self.assertTrue(any(correction.reason == "calendar_person_meeting_hint" for correction in result.corrections))
        self.assertTrue(any(correction.resolver == "CalendarPhraseResolver" for correction in result.corrections))

    def test_ambiguous_person_requires_clarification(self):
        normalizer = SemanticTranscriptNormalizer()
        context = SemanticTranscriptContext(
            pending_field="participants",
            known_people=("아야", "아이"),
        )

        result = normalizer.normalize("아이", "아이", context)

        self.assertEqual(result.semantic_text, "아이")
        self.assertTrue(result.requires_clarification)
        self.assertIn("아야", result.clarification_question)
        self.assertIn("아이", result.clarification_question)

    def test_semantic_result_contains_resolver_trace_and_history(self):
        normalizer = SemanticTranscriptNormalizer()
        context = SemanticTranscriptContext(
            pending_field="location",
            known_places=("서울역",),
        )

        result = normalizer.normalize("설립으로 바꿔", "설립으로 바꿔", context)

        self.assertIn("raw", [step.stage for step in result.history])
        self.assertIn("resolver", [step.stage for step in result.history])
        self.assertIn("resolved", [step.stage for step in result.history])
        self.assertTrue(any(trace.resolver == "KnownPlaceResolver" for trace in result.resolver_traces))
        self.assertTrue(any(trace.status == "matched" for trace in result.resolver_traces))

    def test_resolved_entity_dict_includes_brain_graph_fields(self):
        normalizer = SemanticTranscriptNormalizer()

        result = normalizer.normalize("아야랑 유이", "아야랑 유이", SemanticTranscriptContext())
        entities = result.entity_dicts()

        aya = next(entity for entity in entities if entity["id"] == "person_aya")
        self.assertEqual(aya["type"], "person")
        self.assertEqual(aya["value"], "아야")
        self.assertEqual(aya["source"], "known_person")
        self.assertEqual(aya["resolver"], "KnownPeopleResolver")
        self.assertGreaterEqual(aya["confidence"], 0.9)

    def test_entity_cache_records_hits_and_invalidates_by_version(self):
        normalizer = SemanticTranscriptNormalizer()
        context = SemanticTranscriptContext(
            pending_field="location",
            known_places=("서울역",),
            known_entities_version="v1",
        )

        normalizer.normalize("서울역으로 바꿔", "서울역으로 바꿔", context)
        normalizer.normalize("서울역으로 바꿔", "서울역으로 바꿔", context)
        metrics = normalizer.entity_cache.metrics()

        self.assertGreaterEqual(metrics["cache_hit"], 1)

        versioned_context = SemanticTranscriptContext(
            pending_field="location",
            known_places=("서울역",),
            known_entities_version="v2",
        )
        normalizer.normalize("서울역으로 바꿔", "서울역으로 바꿔", versioned_context)
        metrics = normalizer.entity_cache.metrics()
        self.assertGreaterEqual(metrics["cache_miss"], 2)
        self.assertGreaterEqual(metrics["cache_invalidations"], 1)

    def test_entity_graph_crud_merge_and_cross_resolver_poc(self):
        graph = EntityGraph()
        graph.add_node(
            EntityNode(
                id="person_aya",
                type="person",
                name="아야",
                aliases=("아야", "アヤ"),
                sources=("memory",),
                confidence_by_source={"memory": 0.92},
            )
        )
        graph.add_node(
            EntityNode(
                id="person_aya",
                type="person",
                name="아야",
                aliases=("아야", "aya"),
                sources=("contacts",),
                confidence_by_source={"contacts": 0.98},
            )
        )
        graph.add_node(EntityNode(id="place_hotel", type="place", name="호텔", aliases=("호텔",), sources=("memory",)))
        graph.add_edge(
            EntityEdge(
                source_id="person_aya",
                type=EDGE_COMPANY,
                target_id="place_hotel",
                source="memory",
                confidence=0.92,
            )
        )

        self.assertIn("contacts", graph.get_node("person_aya").sources)
        self.assertEqual(graph.neighbors("person_aya", EDGE_COMPANY)[0].id, "place_hotel")

        normalizer = SemanticTranscriptNormalizer()
        context = SemanticTranscriptContext(entity_graph=graph)
        result = normalizer.normalize("아야 회사", "아야 회사", context)

        self.assertIn(("place", "호텔"), [(entity.type, entity.value) for entity in result.resolved_entities])
        self.assertEqual(result.resolver_traces[0].resolver, "ContactEntityResolver")
        self.assertEqual(len(result.resolver_traces), 6)
        self.assertEqual(
            [trace.resolver for trace in result.resolver_traces if trace.status == "matched"],
            ["KnownPeopleResolver", "CrossResolver"],
        )
        hotel = next(entity for entity in result.resolved_entities if entity.id == "place_hotel")
        self.assertEqual(hotel.source, "entity_graph")
        self.assertTrue(graph.remove_edge("person_aya", EDGE_COMPANY, target_id="place_hotel"))
        self.assertTrue(graph.remove_node("place_hotel"))

    def test_pipeline_routes_semantic_text_after_user_vocabulary(self):
        pipeline = VoicePipeline(
            wake_listener=object(),
            stt_provider=FixedSTTProvider("아야한테 일정 등록해"),
            chat_service=object(),
            tts_provider=object(),
        )

        self.assertEqual(pipeline.listen_and_normalize_stt(), "아야 만나기 일정 등록해")


class FixedSTTProvider:
    """Minimal STT provider for semantic pipeline tests."""

    def __init__(self, text):
        self.text = text

    def listen(self):
        return self.text


if __name__ == "__main__":
    unittest.main()
