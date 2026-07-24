# Google Contacts

Sprint 17.2 added Google Contacts read through the shared Google provider
components. Sprint 17.3 adds safe Google Contacts create/update support.

## Scope

Implemented:

- Google People API client creation through `GoogleClientFactory`
- `GoogleContactsProvider`
- Search contacts by spoken name
- Create Google contacts after confirmation
- Update phone, email, and birthday after confirmation
- Update only through Google People API `resourceName` / `external_id`
- Map Google People API payloads to Jarvis `Contact`
- Format phone, email, birthday, and general contact responses

Not implemented:

- Google Contacts delete
- Contact sync
- Conflict resolution
- Gmail recipient selection

## OAuth

Contacts write requires the People API contacts scope:

```text
https://www.googleapis.com/auth/contacts
```

If an older token was created for read-only Contacts, re-run auth:

```powershell
cd C:\Projects\Jarvis
python scripts\google_contacts_auth.py
```

Then select the same Google account and allow the requested Calendar and
Contacts permissions.

## Runtime

Use the Google Contacts provider explicitly:

```powershell
cd C:\Projects\Jarvis
$env:JARVIS_CONTACTS_PROVIDER="google"
python voice_main.py
```

Example utterances:

```text
우수 연락처 알려줘
아야 전화번호 찾아줘
김민수 이메일 주소 알려줘
유수 연락처에 저장해
유수 전화번호를 010-1234-5678로 바꿔줘
유수 이메일은 yusu@example.com이야
```

Expected trace shape:

```text
[Contact] query action=get ...
[GoogleContacts] request action=search provider=google_contacts
[GoogleContacts] response contacts=N provider=google_contacts
[Contact] result action=get provider=google_contacts success=YES
```

Google objects stay inside the provider boundary. The rest of Jarvis receives a
normal `ContactResult` containing a Jarvis `Contact`.

## Safety

- Read actions are safe.
- Create and update require confirmation.
- Update must resolve to a Google `people/...` resourceName before calling the
  People API.
- Ambiguous contacts return clarification instead of updating the first match.
- Phone numbers and email addresses should be masked in durable logs; user-facing
  TTS may speak the requested value.
