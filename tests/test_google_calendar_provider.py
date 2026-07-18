import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from jarvis.abilities.native.calendar.query import CalendarQuery
from jarvis.config.loader import create_config_from_dict
from jarvis.providers.google.auth import GoogleAuthManager, GoogleAuthStatus
from jarvis.providers.google.calendar.mapper import GoogleCalendarMapper, google_exclusive_end_display_date
from jarvis.providers.google.calendar.provider import GoogleCalendarProvider
from jarvis.providers.google.config import GOOGLE_CALENDAR_READONLY_SCOPE, GoogleProviderConfig


class TestGoogleCalendarProvider(unittest.TestCase):
    def test_missing_credentials_requires_auth(self):
        missing_path = Path("tmp") / "tests" / "missing_google_token.json"
        manager = GoogleAuthManager(
            GoogleProviderConfig(credentials_path=str(missing_path))
        )

        self.assertEqual(manager.get_auth_status().status, GoogleAuthStatus.AUTH_REQUIRED)

    def test_scope_validation_blocks_excess_scope(self):
        manager = GoogleAuthManager(
            GoogleProviderConfig(scopes=(GOOGLE_CALENDAR_READONLY_SCOPE, "https://www.googleapis.com/auth/gmail.readonly"))
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
        self.assertEqual(result.error_code, "FEATURE_NOT_ENABLED")

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
    def __init__(self, response=None, get_response=None, error=None):
        self.response = response if response is not None else {"items": []}
        self.get_response = get_response if get_response is not None else {}
        self.error = error

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
        return FakeRequest(self.service.get_response, self.service.error)


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
