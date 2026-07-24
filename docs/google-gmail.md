# Google Gmail Read / Send / Reply

Sprint 17.4 added Gmail reads. Sprint 17.5 adds draft-first, confirmed send and
reply without expanding into mailbox mutation features.

## Scope

Jarvis requests these Gmail scopes:

```text
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.send
```

The helper auth script also requests the existing Calendar and Contacts write
scopes so one shared Google token can continue to support the already verified
Google providers.

## Setup

Place the Google OAuth client secret at:

```text
C:\Projects\Jarvis\client_secret.json
```

Then run:

```powershell
cd C:\Projects\Jarvis
python scripts\google_gmail_auth.py
```

After authorization, run the voice runtime with Gmail enabled:

```powershell
$env:JARVIS_MAIL_PROVIDER="google"
python voice_main.py
```

Optional full Google runtime:

```powershell
$env:JARVIS_CALENDAR_PROVIDER="google"
$env:JARVIS_CONTACTS_PROVIDER="google"
$env:JARVIS_MAIL_PROVIDER="google"
python voice_main.py
```

## Supported Utterances

```text
최근 메일 알려줘
안 읽은 메일 알려줘
오늘 온 메일 알려줘
OpenAI 메일 알려줘
GitHub 메일 알려줘
2번 읽어줘
아야에게 내일 오후 3시에 만나자고 메일 보내줘
test@example.com으로 테스트 메일 보내줘
그 메일에 확인했다고 답장해줘
```

## Runtime Path

```text
Voice Session
  |
OpenAI STT
  |
Semantic Transcript Layer
  |
Intent Parser / Planner
  |
Mail Ability / Google Contacts recipient resolution
  |
GoogleMailProvider
  |
MailResult / MailSendResult
  |
Formatter / TTS
```

## Safety

- Gmail read is `safe`.
- Compose is safe, but actual send and reply are always `confirm_required`.
- Confirmation executes the exact stored `OutgoingMail`; it does not parse the
  voice command again.
- Explicit email addresses take priority over exact Google Contacts names and
  aliases. Ambiguous contacts and contacts without email are blocked.
- Duplicate confirmed sends are blocked by a pending-action fingerprint.
- Sent recipient, subject, message ID, and thread ID are verified through a
  metadata-only Gmail read.
- Durable traces contain masked recipients, subject hashes, and body lengths,
  never full message bodies or full email addresses.
- Lists read sender and subject only.
- Hydrated message body text is used only for a selected message summary.
- Delete, trash, archive, label changes, attachment upload, forward, scheduled
  send, and bulk send remain out of scope.
- Google API objects stay inside the provider boundary; formatters receive
  internal `MailResult` / `MailMessage` models only.

## Provider Selection

```text
JARVIS_MAIL_PROVIDER=google
```

If the provider is not `google`, the Mail Ability remains registered but returns
an auth/provider-required result instead of calling Gmail.

## Manual Verification

Use a real Google account after OAuth:

```text
최근 메일 알려줘
오늘 온 메일 알려줘
GitHub 메일 알려줘
안 읽은 메일 알려줘
내 다른 Gmail 주소로 테스트 메일 보내줘
아야에게 내일 오후 3시에 만나자고 메일 보내줘
첫 번째 메일에 확인했다고 답장해줘
```

Expected trace shape:

```text
[Planner] step=1/1 mail.search
[GoogleAuth] credential_state=AUTHENTICATED
[Trace] google_gmail.request ...
[Trace] google_gmail.response messages=N
[Trace] mail.result success=true provider=google_gmail
[Trace] google_gmail.send.request to=a***@example.com subject_hash=... body_length=N
[Trace] google_gmail.send.response verified=true
```
