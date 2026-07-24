import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from jarvis.abilities.native.calendar.query import CalendarQuery
from jarvis.config.loader import create_config_from_dict
from jarvis.providers.google.auth import GoogleAuthManager, GoogleAuthStatus
from jarvis.providers.google.calendar.mapper import GoogleCalendarMapper, google_exclusive_end_display_date
from jarvis.providers.google.calendar.provider import GoogleCalendarProvider
from jarvis.providers.google.config import GOOGLE_CALENDAR_READONLY_SCOPE, GOOGLE_CALENDAR_SCOPE, GoogleProviderConfig
from jarvis.providers.google.context import GoogleProviderContext
from jarvis.providers.google.credentials import GoogleCredentialStore
from jarvis.providers.google.error_mapper import GoogleErrorMapper
from jarvis.providers.google.metadata import GoogleProviderMetadata
from jarvis.providers.google.request_executor import GoogleRequestExecutor


class TestGoogleCalendarProvider(unittest.TestCase):
    def test_missing_credentials_requires_auth(self):
        missing_path = Path("tmp") / "tests" / "missing_google_token.json"
        manager = GoogleAuthManager(
            GoogleProviderConfig(credentials_path=str(missing_path))
        )

        self.assertEqual(manager.get_auth_status().status, GoogleAuthStatus.AUTH_REQUIRED)

    def test_scope_validation_blocks_excess_scope(self):
        manager = GoogleAuthManager(
            GoogleProviderConfig(scopes=(GOOGLE_CALENDAR_READONLY_SCOPE, "https://www.googleapis.com/auth/drive"))
        )

        self.assertEqual(manager.get_auth_status().status, GoogleAuthStatus.SCOPE_INSUFFICIENT)

    def test_expired_refreshable_detection(self):
        credentials = FakeCredentials(valid=False, expired=True, refresh_token="refresh", scopes=[GOOGLE_CALENDAR_READONLY_SCOPE])
        manager = GoogleAuthManager(GoogleProviderConfig(), credentials=credentials)

        self.assertEqual(manager.get_auth_status().status, GoogleAuthStatus.EXPIRED_REFRESHABLE)

    def test_refresh_success(self):
        credentials = FakeCredentials(valid=False, expired=True, refresh_token="refresh", scopes=[GOOGLE_CALENDAR_READONLY_SCOPE])
        manager = GoogleAuthManager(GoogleProviderConfig(credentials_path=""), credentials=credentials)

        refreshed = manager.refresh_credentials()

        self.assertTrue(refreshed.valid)
        self.assertFalse(refreshed.expired)

    def test_refresh_failure(self):
        credentials = FakeCredentials(
            valid=False,
            expired=True,
            refresh_token="refresh",
            scopes=[GOOGLE_CALENDAR_READONLY_SCOPE],
            refresh_error=RuntimeError("temporary"),
        )
        manager = GoogleAuthManager(GoogleProviderConfig(), credentials=credentials)

        with self.assertRaises(Exception):
            manager.refresh_credentials()

    def test_timed_event_mapping_timezone(self):
        mapper = GoogleCalendarMapper("Asia/Seoul")
        event = mapper.to_calendar_event(
            {
                "id": "g1",
                "summary": "회의",
                "start": {"dateTime": "2026-07-18T01:00:00Z"},
                "location": "서울역",
                "attendees": [{"email": "aya@example.com"}],
            }
        )

        self.assertEqual(event.id, "g1")
        self.assertEqual(event.date, "2026-07-18")
        self.assertEqual(event.time, "10:00")
        self.assertEqual(event.location, "서울역")
        self.assertEqual(event.participants, ["aya@example.com"])

    def test_all_day_event_mapping_and_exclusive_end(self):
        mapper = GoogleCalendarMapper("Asia/Seoul")
        event = mapper.to_calendar_event({"id": "g2", "summary": "휴가", "start": {"date": "2026-07-18"}})

        self.assertEqual(event.date, "2026-07-18")
        self.assertEqual(event.time, "")
        self.assertEqual(google_exclusive_end_display_date("2026-07-19").isoformat(), "2026-07-18")

    def test_malformed_response_maps_to_result_error(self):
        provider = GoogleCalendarProvider(client=FakeCalendarService(response={"items": [object()]}))

        result = provider.list_events(CalendarQuery(date="today"))

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "INVALID_PROVIDER_RESPONSE")
        self.assertNotIn("object", result.to_natural_language())

    def test_fake_client_provider_lists_events(self):
        provider = GoogleCalendarProvider(
            client=FakeCalendarService(
                response={
                    "items": [
                        {
                            "id": "event-1",
                            "summary": "아야 만나기",
                            "start": {"dateTime": "2026-07-18T15:00:00+09:00"},
                        }
                    ]
                }
            )
        )

        result = provider.list_events(CalendarQuery(date="2026-07-18"))

        self.assertTrue(result.success)
        self.assertEqual(result.provider, "google")
        self.assertEqual(result.count, 1)
        self.assertEqual(result.events[0].title, "아야 만나기")
        self.assertEqual(result.events[0].time, "15:00")
        self.assertGreaterEqual(result.execution_time_ms, 0)

    def test_get_event_uses_internal_model(self):
        provider = GoogleCalendarProvider(
            client=FakeCalendarService(
                get_response={
                    "id": "event-2",
                    "summary": "점심",
                    "start": {"date": "2026-07-19"},
                }
            )
        )

        result = provider.get_event("event-2")

        self.assertTrue(result.success)
        self.assertEqual(result.events[0].id, "event-2")
        self.assertEqual(result.events[0].title, "점심")

    def test_writes_are_feature_disabled(self):
        provider = GoogleCalendarProvider(client=FakeCalendarService(response={"items": []}))

        result = provider.create_event(CalendarQuery(action="create", title="회의"))

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CREATE_FAILED")

    def test_create_event_inserts_reminder_and_verifies(self):
        service = FakeCalendarService()
        provider = GoogleCalendarProvider(client=service)

        result = provider.create_event(
            CalendarQuery(
                action="create",
                title="우수 만나기",
                date="2026-07-19",
                time="15:00",
                remind_before_minutes=60,
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.provider, "google")
        self.assertEqual(result.events[0].title, "우수 만나기")
        self.assertEqual(result.events[0].time, "15:00")
        self.assertEqual(result.events[0].reminder_minutes, [60])
        self.assertEqual(service.last_insert_body["reminders"]["overrides"][0]["minutes"], 60)
        self.assertIn("1시간 전 알림", result.to_natural_language())

    def test_update_event_patches_and_verifies(self):
        service = FakeCalendarService(
            get_response={
                "id": "event-2",
                "summary": "우수 만나기",
                "start": {"dateTime": "2026-07-19T15:00:00+09:00"},
            }
        )
        provider = GoogleCalendarProvider(client=service)

        result = provider.update_event(
            CalendarQuery(
                action="update",
                event_id="event-2",
                title="우수 만나기",
                date="2026-07-19",
                time="16:00",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.events[0].time, "16:00")
        self.assertEqual(service.last_patch_body["start"]["dateTime"], "2026-07-19T16:00:00+09:00")

    def test_delete_event_verifies_not_found(self):
        service = FakeCalendarService(
            get_response={
                "id": "event-3",
                "summary": "치과",
                "start": {"dateTime": "2026-07-19T15:00:00+09:00"},
            },
            delete_not_found_after=True,
        )
        provider = GoogleCalendarProvider(client=service)

        result = provider.delete_event(CalendarQuery(action="delete", event_id="event-3"))

        self.assertTrue(result.success)
        self.assertEqual(result.count, 1)

    def test_calendar_config_loader(self):
        config = create_config_from_dict(
            {
                "calendar": {
                    "provider": "google",
                    "allow_mock_fallback": False,
                    "timezone": "Asia/Seoul",
                    "google_credentials_path": "data/credentials/google_token.json",
                }
            }
        )

        self.assertEqual(config.calendar.provider, "google")
        self.assertFalse(config.calendar.allow_mock_fallback)
        self.assertEqual(config.calendar.timezone, "Asia/Seoul")

    def test_google_common_components_compose_calendar_provider(self):
        config = GoogleProviderConfig(credentials_path="", scopes=(GOOGLE_CALENDAR_SCOPE,))
        error_mapper = GoogleErrorMapper()
        executor = GoogleRequestExecutor(error_mapper=error_mapper)
        context = GoogleProviderContext.create(config=config, error_mapper=error_mapper, request_executor=executor)
        provider = GoogleCalendarProvider(client=FakeCalendarService(response={"items": []}), context=context)

        result = provider.list_events(CalendarQuery(date="today"))

        self.assertTrue(result.success)
        self.assertIs(provider.request_executor, executor)
        self.assertIs(provider.error_mapper, error_mapper)
        self.assertEqual(result.provider, "google")

    def test_google_credential_store_and_metadata_contract(self):
        store = GoogleCredentialStore("tmp/tests/google_token_contract.json")
        metadata = GoogleProviderMetadata(service="calendar", action="list", scopes=(GOOGLE_CALENDAR_SCOPE,))

        self.assertFalse(store.exists())
        self.assertEqual(store.redact({"access_token": "secret", "safe": "ok"})["access_token"], "[REDACTED]")
        self.assertEqual(metadata.to_dict()["service"], "calendar")


class FakeCredentials:
    def __init__(self, valid=True, expired=False, refresh_token="", scopes=None, refresh_error=None):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.scopes = scopes or [GOOGLE_CALENDAR_READONLY_SCOPE]
        self.refresh_error = refresh_error

    def refresh(self, request):
        if self.refresh_error:
            raise self.refresh_error
        self.valid = True
        self.expired = False

    def to_json(self):
        return "{}"


class FakeCalendarService:
    def __init__(self, response=None, get_response=None, error=None, delete_not_found_after=False):
        self.response = response if response is not None else {"items": []}
        self.get_response = get_response if get_response is not None else {}
        self.error = error
        self.delete_not_found_after = delete_not_found_after
        self.deleted_event_ids = set()
        self.last_insert_body = None
        self.last_patch_body = None
        self.events_by_id = {}

        if isinstance(self.get_response, dict) and self.get_response.get("id"):
            self.events_by_id[self.get_response["id"]] = dict(self.get_response)

    def events(self):
        return FakeEventsResource(self)


class FakeEventsResource:
    def __init__(self, service):
        self.service = service

    def list(self, **kwargs):
        self.kwargs = kwargs
        return FakeRequest(self.service.response, self.service.error)

    def get(self, **kwargs):
        self.kwargs = kwargs
        event_id = kwargs.get("eventId", "")

        if event_id in self.service.deleted_event_ids:
            return FakeRequest({}, FakeHttpError(404))

        response = self.service.events_by_id.get(event_id, self.service.get_response)
        return FakeRequest(response, self.service.error)

    def insert(self, **kwargs):
        self.kwargs = kwargs
        body = dict(kwargs.get("body") or {})
        self.service.last_insert_body = body
        event_id = body.get("id") or "event-created"
        response = dict(body)
        response["id"] = event_id
        self.service.events_by_id[event_id] = response
        return FakeRequest(response, self.service.error)

    def patch(self, **kwargs):
        self.kwargs = kwargs
        event_id = kwargs.get("eventId", "")
        body = dict(kwargs.get("body") or {})
        self.service.last_patch_body = body
        current = dict(self.service.events_by_id.get(event_id, self.service.get_response) or {})
        current.update(body)
        current["id"] = event_id
        self.service.events_by_id[event_id] = current
        return FakeRequest(current, self.service.error)

    def delete(self, **kwargs):
        self.kwargs = kwargs
        event_id = kwargs.get("eventId", "")
        if self.service.delete_not_found_after:
            self.service.deleted_event_ids.add(event_id)
        return FakeRequest({}, self.service.error)


class FakeRequest:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.response


class FakeResponse:
    def __init__(self, status):
        self.status = status


class FakeHttpError(Exception):
    def __init__(self, status):
        super().__init__(str(status))
        self.resp = FakeResponse(status)


if __name__ == "__main__":
    unittest.main()
