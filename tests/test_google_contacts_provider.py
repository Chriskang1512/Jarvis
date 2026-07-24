import unittest
from types import SimpleNamespace

from jarvis.abilities.native.contacts import ContactAbility, ContactQuery
from jarvis.abilities.native.contacts.result import ContactResult
from jarvis.core.contacts import Contact
from jarvis.providers.google.config import GOOGLE_CONTACTS_READONLY_SCOPE, GOOGLE_CONTACTS_SCOPE, GoogleProviderConfig
from jarvis.providers.google.contacts import GoogleContactsProvider
from jarvis.voice.pipeline import extract_contact_ambiguous_clarification, format_confirmed_contact_candidate


class TestGoogleContactsProvider(unittest.TestCase):
    def test_google_contacts_search_maps_person_to_contact(self):
        service = FakePeopleService(
            search_response={
                "results": [
                    {
                        "person": {
                            "resourceName": "people/1",
                            "names": [{"displayName": "우수", "givenName": "우수"}],
                            "emailAddresses": [{"value": "woosu@example.com"}],
                            "phoneNumbers": [{"value": "010-1234-5678"}],
                            "birthdays": [{"date": {"month": 2, "day": 28}}],
                        }
                    }
                ]
            }
        )
        provider = GoogleContactsProvider(client=service)

        result = provider.get_contact(ContactQuery(action="get", display_name="우수", attribute="contact"))

        self.assertTrue(result.success)
        self.assertEqual(result.provider, "google_contacts")
        self.assertEqual(result.contact.display_name, "우수")
        self.assertEqual(result.contact.emails, ("woosu@example.com",))
        self.assertEqual(result.contact.phones, ("010-1234-5678",))
        self.assertEqual(result.contact.birthday, "02-28")
        self.assertEqual(result.contact.metadata["google_resource_name"], "people/1")
        self.assertEqual(result.contact.metadata["external_id"], "people/1")
        self.assertEqual(result.external_id, "people/1")
        self.assertIn("우수", result.to_natural_language())

    def test_google_contacts_email_lookup_formats_field(self):
        service = FakePeopleService(
            search_response={
                "results": [
                    {
                        "person": {
                            "resourceName": "people/2",
                            "names": [{"displayName": "김민수"}],
                            "emailAddresses": [{"value": "minsu@example.com"}],
                        }
                    }
                ]
            }
        )
        provider = GoogleContactsProvider(client=service)

        result = provider.get_contact(ContactQuery(action="get", display_name="김민수", attribute="email"))

        self.assertTrue(result.success)
        self.assertEqual(result.to_natural_language(), "김민수의 이메일은 minsu@example.com입니다.")

    def test_google_contacts_falls_back_to_connection_list_when_search_is_empty(self):
        service = FakePeopleService(
            search_response={"results": []},
            list_response={
                "connections": [
                    {
                        "resourceName": "people/4",
                        "names": [{"displayName": "\uc6b4\uc12d\uc774"}],
                        "phoneNumbers": [{"value": "010-0000-0000"}],
                    }
                ]
            },
        )
        provider = GoogleContactsProvider(client=service)

        result = provider.get_contact(ContactQuery(action="get", display_name="\uc6b4\uc12d\uc774", attribute="phone"))

        self.assertTrue(result.success)
        self.assertEqual(result.contact.display_name, "\uc6b4\uc12d\uc774")
        self.assertEqual(result.contact.phones, ("010-0000-0000",))

    def test_google_contacts_fallback_does_not_return_unmatched_first_contact(self):
        service = FakePeopleService(
            search_response={"results": []},
            list_response={
                "connections": [
                    {
                        "resourceName": "people/5",
                        "names": [{"displayName": "\ucd5c\uc6b0\uc218"}],
                        "phoneNumbers": [{"value": "010-1111-2222"}],
                    }
                ]
            },
        )
        provider = GoogleContactsProvider(client=service)

        result = provider.get_contact(ContactQuery(action="get", display_name="\uc544\uc57c", attribute="phone"))

        self.assertFalse(result.success)
        self.assertIsNone(result.contact)
        self.assertEqual(result.contacts, ())
        self.assertEqual(result.error_code, "contact_not_found")

    def test_google_contacts_fallback_does_not_autoselect_substring_name(self):
        service = FakePeopleService(
            search_response={"results": []},
            list_response={
                "connections": [
                    {
                        "resourceName": "people/6",
                        "names": [{"displayName": "\ucd5c\uc6b0\uc218"}],
                        "phoneNumbers": [{"value": "010-2222-3333"}],
                    }
                ]
            },
        )
        provider = GoogleContactsProvider(client=service)

        result = provider.get_contact(ContactQuery(action="get", display_name="\uc6b0\uc218", attribute="phone"))

        self.assertFalse(result.success)
        self.assertIsNone(result.contact)
        self.assertEqual(result.error_code, "contact_ambiguous")
        self.assertEqual(len(result.contacts), 1)
        self.assertIn("\ucd5c\uc6b0\uc218", result.message)

    def test_google_contacts_fallback_can_match_token_in_connection_name(self):
        service = FakePeopleService(
            search_response={"results": []},
            list_response={
                "connections": [
                    {
                        "resourceName": "people/7",
                        "names": [{"displayName": "\uc138\uc778\ud2b8\uc874\uc2a4-\uc2dd\uc74c, \ucd5c\uc6b0\uc218 \uc8fc\uc784"}],
                        "phoneNumbers": [{"value": "010-2222-3333"}],
                    }
                ]
            },
        )
        provider = GoogleContactsProvider(client=service)

        result = provider.get_contact(ContactQuery(action="get", display_name="\ucd5c\uc6b0\uc218", attribute="phone"))

        self.assertTrue(result.success)
        self.assertEqual(result.contact.display_name, "\uc138\uc778\ud2b8\uc874\uc2a4-\uc2dd\uc74c, \ucd5c\uc6b0\uc218 \uc8fc\uc784")
        self.assertEqual(result.contacts, (result.contact,))

    def test_google_contacts_fallback_does_not_choose_ambiguous_partial_match(self):
        service = FakePeopleService(
            search_response={"results": []},
            list_response={
                "connections": [
                    {
                        "resourceName": "people/8",
                        "names": [{"displayName": "\ucd5c\uc6b0\uc218"}],
                        "phoneNumbers": [{"value": "010-2222-3333"}],
                    },
                    {
                        "resourceName": "people/9",
                        "names": [{"displayName": "\uc6b0\uc218\uc601"}],
                        "phoneNumbers": [{"value": "010-3333-4444"}],
                    },
                ]
            },
        )
        provider = GoogleContactsProvider(client=service)

        result = provider.get_contact(ContactQuery(action="get", display_name="\uc6b0\uc218", attribute="phone"))

        self.assertFalse(result.success)
        self.assertIsNone(result.contact)
        self.assertEqual(result.error_code, "contact_ambiguous")
        self.assertEqual(len(result.contacts), 2)

    def test_google_contacts_partial_match_formats_clarification(self):
        service = FakePeopleService(
            search_response={"results": []},
            list_response={
                "connections": [
                    {
                        "resourceName": "people/10",
                        "names": [{"displayName": "\uc138\uc778\ud2b8\uc874\uc2a4-\uc2dd\uc74c, \ucd5c\uc6b0\uc218 \uc8fc\uc784"}],
                        "phoneNumbers": [{"value": "010-2222-3333"}],
                    }
                ]
            },
        )
        provider = GoogleContactsProvider(client=service)

        result = provider.get_contact(ContactQuery(action="get", display_name="\uc6b0\uc218", attribute="phone"))

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "contact_ambiguous")
        self.assertIn("\uc6b0\uc218", result.to_natural_language())
        self.assertIn("\ucd5c\uc6b0\uc218", result.to_natural_language())
        self.assertNotIn("010-2222-3333", result.to_natural_language())

    def test_contact_ambiguous_result_can_be_confirmed_from_pending_clarification(self):
        contact = Contact(
            id="person_choi_woosu",
            display_name="\uc138\uc778\ud2b8\uc874\uc2a4-\uc2dd\uc74c, \ucd5c\uc6b0\uc218 \uc8fc\uc784",
            phones=("010-2222-3333",),
            metadata={"provider": "google_contacts", "external_id": "people/10"},
        )
        contact_result = ContactResult(
            success=False,
            action="get",
            contacts=(contact,),
            changed_fields=("phone",),
            error_code="contact_ambiguous",
            message="'\uc6b0\uc218'\uc640 \uc815\ud655\ud788 \uc77c\uce58\ud558\ub294 \uc5f0\ub77d\ucc98\ub294 \uc5c6\uc2b5\ub2c8\ub2e4.",
        )
        intent_result = SimpleNamespace(tool_output=SimpleNamespace(data=contact_result), response=contact_result.message)

        pending = extract_contact_ambiguous_clarification(intent_result)

        self.assertIsNotNone(pending)
        self.assertEqual(pending["kind"], "contact_ambiguous")
        self.assertEqual(pending["attribute"], "phone")
        self.assertEqual(pending["contacts"][0]["metadata"]["external_id"], "people/10")
        self.assertIn("010-2222-3333", format_confirmed_contact_candidate(pending["contacts"][0], pending["attribute"]))

    def test_contact_ability_uses_google_provider_for_read(self):
        provider = GoogleContactsProvider(
            client=FakePeopleService(
                search_response={
                    "results": [
                        {
                            "person": {
                                "resourceName": "people/3",
                                "names": [{"displayName": "아야"}],
                                "phoneNumbers": [{"value": "+81 90-0000-0000"}],
                            }
                        }
                    ]
                }
            ),
            config=GoogleProviderConfig(scopes=(GOOGLE_CONTACTS_READONLY_SCOPE,)),
        )
        ability = ContactAbility(provider=provider)

        result = ability.execute({"text": "아야 전화번호 찾아줘"})

        self.assertTrue(result.success)
        self.assertEqual(result.data.provider, "google_contacts")
        self.assertEqual(result.data.to_natural_language(), "아야의 전화번호는 +81 90-0000-0000입니다.")


    def test_google_contacts_create_contact_uses_people_api(self):
        service = FakePeopleService(
            create_response={
                "resourceName": "people/new1",
                "names": [{"displayName": "\uc720\uc218"}],
                "phoneNumbers": [{"value": "010-1234-5678"}],
            }
        )
        provider = GoogleContactsProvider(client=service, config=GoogleProviderConfig(scopes=(GOOGLE_CONTACTS_SCOPE,)))

        result = provider.create_contact(
            ContactQuery(action="create", display_name="\uc720\uc218", phone="010-1234-5678", confirmed=True)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action, "create")
        self.assertEqual(result.external_id, "people/new1")
        self.assertEqual(service.created_body["names"][0]["displayName"], "\uc720\uc218")
        self.assertEqual(service.created_body["phoneNumbers"][0]["value"], "010-1234-5678")

    def test_google_contacts_update_uses_resource_name(self):
        service = FakePeopleService(
            get_response={
                "resourceName": "people/123",
                "etag": "etag-1",
                "names": [{"displayName": "\uc720\uc218"}],
                "phoneNumbers": [{"value": "010-0000-0000"}],
            },
            update_response={
                "resourceName": "people/123",
                "etag": "etag-2",
                "names": [{"displayName": "\uc720\uc218"}],
                "phoneNumbers": [{"value": "010-1234-5678"}],
            },
        )
        provider = GoogleContactsProvider(client=service, config=GoogleProviderConfig(scopes=(GOOGLE_CONTACTS_SCOPE,)))

        result = provider.update_contact(
            ContactQuery(action="update", external_id="people/123", display_name="\uc720\uc218", phone="010-1234-5678", confirmed=True)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.external_id, "people/123")
        self.assertEqual(service.updated_resource_name, "people/123")
        self.assertEqual(service.updated_person_fields, "phoneNumbers")
        self.assertEqual(service.updated_body["phoneNumbers"][0]["value"], "010-1234-5678")

    def test_google_contacts_update_rejects_non_google_contact_id(self):
        service = FakePeopleService()
        provider = GoogleContactsProvider(client=service, config=GoogleProviderConfig(scopes=(GOOGLE_CONTACTS_SCOPE,)))

        result = provider.update_contact(
            ContactQuery(action="update", contact_id="person_yusu", display_name="", phone="010-1234-5678", confirmed=True)
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "contact_not_found")
        self.assertIsNone(service.updated_resource_name)

    def test_google_contacts_update_stops_on_ambiguous_resolution(self):
        service = FakePeopleService(
            search_response={"results": []},
            list_response={
                "connections": [
                    {"resourceName": "people/1", "names": [{"displayName": "\ucd5c\uc6b0\uc218"}]},
                    {"resourceName": "people/2", "names": [{"displayName": "\uc6b0\uc218\uc601"}]},
                ]
            },
        )
        provider = GoogleContactsProvider(client=service, config=GoogleProviderConfig(scopes=(GOOGLE_CONTACTS_SCOPE,)))

        result = provider.update_contact(
            ContactQuery(action="update", display_name="\uc6b0\uc218", phone="010-1234-5678", confirmed=True)
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "contact_ambiguous")
        self.assertEqual(len(result.contacts), 2)
        self.assertIsNone(service.updated_resource_name)

    def test_contact_ability_google_write_waits_for_confirmation(self):
        provider = GoogleContactsProvider(client=FakePeopleService(), config=GoogleProviderConfig(scopes=(GOOGLE_CONTACTS_SCOPE,)))
        ability = ContactAbility(provider=provider)

        pending = ability.execute(
            {"action": "update", "display_name": "\uc720\uc218", "phone": "010-1234-5678", "attribute": "phone"}
        )

        self.assertTrue(pending.success)
        self.assertTrue(pending.data.requires_confirmation)
        self.assertEqual(pending.metadata["permission"], "confirm_required")
        self.assertIsNone(provider.client.updated_resource_name)


class FakePeopleService:
    def __init__(self, search_response=None, list_response=None, create_response=None, get_response=None, update_response=None, error=None):
        self.search_response = search_response if search_response is not None else {"results": []}
        self.list_response = list_response if list_response is not None else {"connections": []}
        self.create_response = create_response if create_response is not None else {}
        self.get_response = get_response if get_response is not None else {}
        self.update_response = update_response if update_response is not None else {}
        self.error = error
        self.created_body = None
        self.get_resource_name = None
        self.updated_resource_name = None
        self.updated_person_fields = None
        self.updated_body = None

    def people(self):
        return FakePeopleResource(self)


class FakePeopleResource:
    def __init__(self, service):
        self.service = service

    def searchContacts(self, **kwargs):
        self.kwargs = kwargs
        return FakeRequest(self.service.search_response, self.service.error)

    def createContact(self, **kwargs):
        self.service.created_body = kwargs.get("body")
        return FakeRequest(self.service.create_response, self.service.error)

    def get(self, **kwargs):
        self.service.get_resource_name = kwargs.get("resourceName")
        return FakeRequest(self.service.get_response, self.service.error)

    def updateContact(self, **kwargs):
        self.service.updated_resource_name = kwargs.get("resourceName")
        self.service.updated_person_fields = kwargs.get("updatePersonFields")
        self.service.updated_body = kwargs.get("body")
        return FakeRequest(self.service.update_response, self.service.error)

    def connections(self):
        return FakeConnectionsResource(self.service)


class FakeConnectionsResource:
    def __init__(self, service):
        self.service = service

    def list(self, **kwargs):
        self.kwargs = kwargs
        return FakeRequest(self.service.list_response, self.service.error)


class FakeRequest:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.response


if __name__ == "__main__":
    unittest.main()
