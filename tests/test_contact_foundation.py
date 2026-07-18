import unittest

from jarvis.core.contacts import ContactAlias, ContactCommandParser, ContactRepository, ContactResolver, InMemoryContactStorage
from jarvis.core.contacts.contact import contact_id_for_name, new_contact
from jarvis.core.contacts.resolver import sync_contact_to_graph
from jarvis.voice.semantic import SemanticTranscriptContext, SemanticTranscriptNormalizer
from jarvis.voice.semantic.graph import (
    EDGE_BIRTHDAY,
    EDGE_COMPANY,
    EDGE_COUNTRY,
    EDGE_EMAIL,
    EDGE_LANGUAGE,
    EDGE_PHONE,
    EDGE_RELATIONSHIP,
    EDGE_TIMEZONE,
    EDGE_WORKS_AT,
    EntityGraph,
)


class TestContactMemoryFoundation(unittest.TestCase):
    """Test Sprint 14 Contact Memory Foundation."""

    def test_contact_parser_handles_required_sprint_sentences(self):
        parser = ContactCommandParser()

        store = parser.parse("아야를 연락처에 저장해")
        email = parser.parse("유이 이메일은 test@test.com")
        birthday = parser.parse("아야 생일은 2월 28일")
        contact = parser.parse("아야 연락처 알려줘")
        email_recall = parser.parse("유이 이메일 알려줘")
        birthday_recall = parser.parse("아야 생일 언제야")

        self.assertEqual(store.action, "store")
        self.assertEqual(store.name, "아야")
        self.assertEqual(email.attribute, "email")
        self.assertEqual(email.value, "test@test.com")
        self.assertEqual(birthday.attribute, "birthday")
        self.assertEqual(birthday.value, "02-28")
        self.assertEqual(contact.attribute, "contact")
        self.assertEqual(email_recall.attribute, "email")
        self.assertEqual(birthday_recall.attribute, "birthday")

    def test_contact_repository_stores_and_recalls_person_properties(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
        resolver = ContactResolver(repository=repository)

        self.assertTrue(resolver.handle("아야를 연락처에 저장해").success)
        self.assertTrue(resolver.handle("유이 이메일은 test@test.com").success)
        self.assertTrue(resolver.handle("아야 생일은 2월 28일").success)

        aya = repository.resolve("아야")
        yui = repository.resolve("유이")

        self.assertEqual(aya.id, "person_aya")
        self.assertEqual(aya.birthday, "02-28")
        self.assertEqual(yui.emails, ("test@test.com",))
        self.assertIn("2월 28일", resolver.handle("아야 생일 언제야").message)
        self.assertIn("test@test.com", resolver.handle("유이 이메일 알려줘").message)

    def test_contact_resolver_feeds_semantic_layer_before_known_people(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
        repository.ensure("아야", aliases=("아이", "Aya"))

        normalizer = SemanticTranscriptNormalizer()
        context = SemanticTranscriptContext(
            pending_field="participants",
            contact_repository=repository,
            known_people=("아야",),
        )

        result = normalizer.normalize("아이랑 유이", "아이랑 유이", context)
        aya = next(entity for entity in result.resolved_entities if entity.id == "person_aya")

        self.assertEqual(result.semantic_text, "아야랑 유이")
        self.assertEqual(aya.source, "contacts,known_person")
        self.assertEqual(aya.resolver, "ContactEntityResolver")
        self.assertGreaterEqual(aya.confidence, 0.95)

    def test_contact_syncs_to_entity_graph_with_property_edges(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
        contact = repository.ensure("아야", aliases=("Aya",), emails=("aya@example.com",), birthday="02-28")
        graph = EntityGraph()

        node = sync_contact_to_graph(graph, contact)

        self.assertEqual(node.id, "person_aya")
        self.assertEqual(graph.get_node("person_aya").type, "person")
        self.assertEqual(graph.find_edges(source_id="person_aya", edge_type=EDGE_EMAIL)[0].target_id, "email_aya_example_com")
        self.assertEqual(graph.find_edges(source_id="person_aya", edge_type=EDGE_BIRTHDAY)[0].value, "02-28")

    def test_calendar_participants_can_resolve_to_contact_ids(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
        repository.ensure("아야")
        repository.ensure("유이")

        self.assertEqual(repository.resolve_participant_ids(["아야", "유이", "새 사람"]), ["person_aya", "person_yui", "새 사람"])

    def test_contact_id_is_canonical_entity_graph_id(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
        contact = repository.ensure("아야")
        graph = EntityGraph()

        sync_contact_to_graph(graph, contact)

        self.assertEqual(contact.id, "person_aya")
        self.assertEqual(contact.id, contact_id_for_name("Aya"))
        self.assertEqual(contact.id, contact_id_for_name("あや"))
        self.assertIsNotNone(graph.get_node(contact.id))

    def test_contact_repository_merges_aliases_into_one_canonical_contact(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)

        aya = repository.create("아야", aliases=("あや",))
        merged = repository.merge(aya.id, new_contact("Aya", emails=("aya@example.com",), source="memory", confidence=0.91))
        ensured = repository.ensure("あや", phones=("010-1234-5678",))

        self.assertEqual(len(repository.list()), 1)
        self.assertEqual(merged.id, "person_aya")
        self.assertEqual(ensured.id, "person_aya")
        self.assertIn("Aya", repository.find_by_id("person_aya").aliases)
        self.assertIn("あや", repository.find_by_id("person_aya").aliases)
        self.assertEqual(repository.find_by_alias("Aya").id, "person_aya")
        self.assertEqual(repository.find_by_alias("あや").id, "person_aya")

    def test_contact_provenance_confidence_and_interface_methods(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)

        contact = repository.create("아야", source="manual", confidence=0.88, verified=True)
        updated = repository.update(contact.id, tags=("friend",), source="memory", confidence=0.92)

        self.assertEqual(repository.find_by_id("person_aya").id, "person_aya")
        self.assertEqual(repository.find_by_name("아야").id, "person_aya")
        self.assertEqual(updated.source, "memory")
        self.assertEqual(updated.confidence, 0.92)
        self.assertTrue(updated.verified)
        self.assertTrue(repository.delete("person_aya"))
        self.assertIsNone(repository.find_by_id("person_aya"))

    def test_contact_revision_increments_and_versions_cache_key(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)

        contact = repository.create("아야")
        updated = repository.update(contact.id, emails=("aya@example.com",))
        merged = repository.merge(contact.id, new_contact("Aya", phones=("010-1111-2222",)))

        self.assertEqual(contact.revision, 1)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(merged.revision, 3)
        self.assertIn("person_aya:r3", repository.known_entities_version())

    def test_contact_alias_records_keep_alias_type(self):
        contact = new_contact(
            "아야",
            aliases=("Aya", "あや"),
            alias_records=(ContactAlias("아이", type="phonetic", source="user_vocab", confidence=0.91),),
        )

        alias_types = {alias.value: alias.type for alias in contact.alias_records}
        alias_sources = {alias.value: alias.source for alias in contact.alias_records}

        self.assertEqual(alias_types["아야"], "official")
        self.assertEqual(alias_types["Aya"], "romanized")
        self.assertEqual(alias_types["あや"], "official")
        self.assertEqual(alias_types["아이"], "phonetic")
        self.assertEqual(alias_sources["아이"], "user_vocab")

    def test_contact_locale_metadata_and_edges_sync_to_graph(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)
        contact = repository.create(
            "아야",
            language="ja",
            timezone="Asia/Tokyo",
            country="Japan",
            metadata={"relationship": "user_friend", "works_at": "hotel"},
            confidence=0.93,
        )
        graph = EntityGraph()

        sync_contact_to_graph(graph, contact)

        self.assertEqual(graph.find_edges(source_id="person_aya", edge_type=EDGE_COUNTRY)[0].value, "Japan")
        self.assertEqual(graph.find_edges(source_id="person_aya", edge_type=EDGE_LANGUAGE)[0].value, "ja")
        self.assertEqual(graph.find_edges(source_id="person_aya", edge_type=EDGE_TIMEZONE)[0].value, "Asia/Tokyo")
        self.assertEqual(graph.find_edges(source_id="person_aya", edge_type=EDGE_RELATIONSHIP)[0].value, "user_friend")
        self.assertEqual(graph.find_edges(source_id="person_aya", edge_type=EDGE_WORKS_AT)[0].value, "hotel")
        self.assertEqual(graph.find_edges(source_id="person_aya", edge_type=EDGE_COMPANY)[0].value, "hotel")

    def test_contact_revision_history_restore_and_undo(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)

        contact = repository.create("아야")
        repository.update(contact.id, emails=("aya@example.com",))
        repository.update(contact.id, birthday="1991-02-28")

        current = repository.find_by_id("person_aya")
        self.assertEqual(current.revision, 3)
        self.assertEqual([item.action for item in repository.get_revision_history("person_aya")], ["created", "updated", "updated"])
        self.assertEqual(repository.latest_revision("person_aya"), 3)

        restored = repository.restore_revision("person_aya", 2)
        self.assertEqual(restored.revision, 4)
        self.assertEqual(restored.emails, ("aya@example.com",))
        self.assertEqual(restored.birthday, "")
        self.assertEqual(repository.metrics.contact_restored, 1)

        undone = repository.undo_last_change("person_aya")
        self.assertIsNotNone(undone)
        self.assertGreaterEqual(undone.revision, 5)
        self.assertEqual(repository.events[-1].event_type, "ContactRestored")
        self.assertEqual(repository.events[-1].aggregate_id, "person_aya")
        self.assertTrue(repository.events[-1].event_id.startswith("CE-"))

    def test_contact_validation_and_lock_policy(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)

        with self.assertRaises(ValueError):
            repository.create("아야", emails=("abc@",))

        with self.assertRaises(ValueError):
            repository.create("아야", birthday="1991-99-99")

        contact = repository.create("아야", emails=("aya@example.com",), verified=True)

        with self.assertRaises(PermissionError):
            repository.update(contact.id, emails=("guess@example.com",), source="llm_guess", confidence=0.7)

        updated = repository.update(contact.id, emails=("aya2@example.com",), source="manual", confidence=1.0)
        self.assertIn("aya2@example.com", updated.emails)

        confirmed = repository.update(contact.id, birthday="1991-02-28", source="user_confirmed", confidence=0.95)
        self.assertEqual(confirmed.birthday, "1991-02-28")

    def test_contact_entity_graph_auto_sync_and_patch(self):
        graph = EntityGraph()
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False, entity_graph=graph)

        contact = repository.create("아야", phones=("010-1111-2222",), birthday="1991-02-28")
        self.assertEqual(graph.get_node(contact.id).revision, 1)
        self.assertEqual(graph.find_edges(source_id=contact.id, edge_type=EDGE_PHONE)[0].revision, 1)

        repository.update(contact.id, birthday="1992-03-01")
        birthdays = graph.find_edges(source_id=contact.id, edge_type=EDGE_BIRTHDAY)

        self.assertEqual(len(birthdays), 1)
        self.assertEqual(birthdays[0].value, "1992-03-01")
        self.assertEqual(graph.get_node(contact.id).revision, 2)
        self.assertEqual(birthdays[0].revision, 2)

    def test_contact_events_metrics_interaction_and_importance(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)

        contact = repository.create("아야", favorite=True, importance="friend", metadata={"relationship": "friend"})
        repository.record_interaction(contact.id, "calendar", timestamp="2026-07-17")
        current = repository.find_by_id(contact.id)

        self.assertTrue(current.favorite)
        self.assertEqual(current.importance, "friend")
        self.assertEqual(current.metadata["last_calendar"], "2026-07-17")
        self.assertEqual(current.metadata["interaction_count"], 1)
        self.assertEqual(repository.events[0].type, "ContactCreated")
        self.assertEqual(repository.events[0].event_type, "ContactCreated")
        self.assertEqual(repository.events[0].aggregate_id, contact.id)
        self.assertIn("event_id", repository.events[0].to_dict())
        self.assertEqual(repository.metrics.event_count, len(repository.events))
        self.assertGreaterEqual(repository.metrics.history_size, 2)

    def test_contact_delete_is_hard_delete_and_metrics_separate_events_from_revisions(self):
        repository = ContactRepository(storage=InMemoryContactStorage(), seed_defaults=False)

        contact = repository.create("아야")
        repository.update(contact.id, emails=("aya@example.com",))
        self.assertTrue(repository.delete(contact.id))

        self.assertIsNone(repository.find_by_id(contact.id))
        self.assertEqual(repository.events[-1].event_type, "ContactDeleted")
        self.assertEqual(repository.metrics.event_count, 3)
        self.assertEqual(repository.metrics.revision_count, 0)


if __name__ == "__main__":
    unittest.main()
