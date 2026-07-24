# Google Calendar Provider

Sprint 17.1 extends the Google OAuth foundation with verified Google Calendar
read and write operations behind the existing Calendar Ability contract.

The core boundary stays unchanged:

```text
Jarvis Core
-> Calendar Ability
-> CalendarProvider
-> MockCalendarProvider / GoogleCalendarProvider
-> CalendarResult
```

Google API objects, credentials, authorization codes, and raw exceptions must
not leave the provider boundary.

## Configuration

The safe default remains mock:

```json
{
  "calendar": {
    "provider": "mock",
    "allow_mock_fallback": false,
    "timezone": "Asia/Seoul",
    "google_credentials_path": "data/credentials/google_token.json",
    "google_client_secret_path": "client_secret.json"
  }
}
```

To select Google locally:

```powershell
$env:JARVIS_CALENDAR_PROVIDER = "google"
$env:JARVIS_GOOGLE_TOKEN_PATH = "data/credentials/google_token.json"
$env:JARVIS_GOOGLE_CLIENT_SECRET_PATH = "client_secret.json"
python voice_main.py
```

To create the token interactively:

```powershell
python scripts/google_calendar_auth.py
```

Sprint 17.1 write support uses this scope:

```text
https://www.googleapis.com/auth/calendar
```

If an older read-only token was created during Sprint 17.0, re-run
`python scripts/google_calendar_auth.py` and grant the updated Calendar access.

## Credential Files

Credential files are intentionally ignored by git:

```text
data/credentials/
client_secret*.json
credentials*.json
*token*.json
```

Do not log tokens, client secrets, authorization codes, or authorization
headers.

## Supported Actions

Implemented:

- `list_events`
- `get_event`
- `create_event`
- `update_event`
- `delete_event`
- today / tomorrow / this week / next-event windows
- timed and all-day event mapping
- Google Calendar reminder overrides
- provider metadata and safe error codes

Write operations must be confirmed by the Permission Layer before the provider
is called. Create and update operations read the event back and verify title,
time, and explicit reminder override before reporting success.

## Manual Verification

With Google provider selected and credentials available:

```text
오늘 일정 알려줘
내일 일정 알려줘
이번 주 일정 알려줘
다음 주 일정 알려줘
다음 일정 알려줘
```

Expected trace shape:

```text
[Planner] step=1/1 calendar.list
[Dispatcher] intent=calendar selected=calendar provider=google
[GoogleCalendar] request action=list provider=google
[GoogleCalendar] response events=N provider=google
[Calendar] result provider=google success=YES
```

Write verification:

```text
내일 오후 3시에 우수 만나기 일정 잡고 1시간 전에 알려줘
응
그 일정 4시로 변경해줘
응
그 일정 삭제해줘
응
```

Expected write trace shape:

```text
[Calendar] permission action=create permission=confirm_required
[GoogleCalendar] request action=create provider=google
[GoogleCalendar] request action=get provider=google
[Calendar] result action=create provider=google success=YES
```

Error checks:

- Remove token file -> `AUTH_REQUIRED`
- Request unsupported scope -> `SCOPE_INSUFFICIENT`
- Provider timeout -> `PROVIDER_TIMEOUT`
- Malformed response -> `INVALID_PROVIDER_RESPONSE`
- Missing event target -> `EVENT_NOT_FOUND`
- Failed create/update/delete verification -> `CREATE_FAILED`, `UPDATE_FAILED`,
  or `DELETE_FAILED`

## Manual Integration Notes

Verified locally with the Google provider and account `lab810108@gmail.com`.

Observed results:

- Today query returned `2026-07-18 20:00 테스트`.
- Next week query returned `2026-07-19 15:00 테스트1`.
- Next event query returned the next upcoming Google Calendar event.

The provider follows the Google Calendar web view week boundary, which starts
on Sunday for the verified account. Phone-local Samsung Calendar events are not
visible to the Google provider unless they are synced into the selected Google
calendar.
