"""Manual Google Calendar read/write smoke test for Jarvis."""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.abilities.native.calendar.query import CalendarQuery
from jarvis.config.loader import ConfigurationLoader
from jarvis.providers.google.auth import GoogleAuthManager, GoogleAuthStatus
from jarvis.providers.google.calendar.provider import GoogleCalendarProvider
from jarvis.providers.google.config import (
    GOOGLE_CALENDAR_SCOPE,
    GOOGLE_CONTACTS_SCOPE,
    GOOGLE_GMAIL_MODIFY_SCOPE,
    GoogleProviderConfig,
)


def main():
    """Run a safe Google Calendar smoke test."""
    args = parse_args()
    config = load_google_config()
    manager = GoogleAuthManager(config)
    status = manager.get_auth_status()

    print("========== Google Calendar Smoke ==========")
    print(f"Auth Status : {status.status.value}")
    print(f"Scopes      : {len(status.scopes or config.scopes)}")
    print("Provider    : google")
    print("===========================================")

    if status.status not in {
        GoogleAuthStatus.AUTHENTICATED,
        GoogleAuthStatus.EXPIRED_REFRESHABLE,
    }:
        print("Google Calendar authentication is required.")
        print(r"Run: python scripts\google_calendar_auth.py")
        return 2

    provider = GoogleCalendarProvider(config=config)

    if args.read:
        read_result = provider.list_events(
            CalendarQuery(date=args.date, timezone=config.timezone)
        )
        print_result("READ", read_result)

    if args.delete_event_id:
        delete_result = provider.delete_event(
            CalendarQuery(action="delete", event_id=args.delete_event_id)
        )
        print_result("DELETE", delete_result)
        return 0 if delete_result.success else 4

    if not args.create_smoke:
        print("No write performed. Pass --create-smoke to create a test event.")
        return 0

    smoke_date = args.smoke_date or (date.today() + timedelta(days=1)).isoformat()
    create_result = provider.create_event(
        CalendarQuery(
            action="create",
            title=args.title,
            date=smoke_date,
            time=args.time,
            timezone=config.timezone,
            remind_before_minutes=args.reminder_minutes,
            raw_text=f"{args.title} {smoke_date} {args.time}",
        )
    )
    print_result("CREATE", create_result)

    if not create_result.success:
        return 3

    created_event_id = create_result.events[0].id if create_result.events else ""
    exit_code = 0

    try:
        if args.update_time:
            update_result = provider.update_event(
                CalendarQuery(
                    action="update",
                    event_id=created_event_id,
                    date=smoke_date,
                    time=args.update_time,
                    timezone=config.timezone,
                )
            )
            print_result("UPDATE", update_result)
            if not update_result.success:
                exit_code = 5
            else:
                read_back = provider.get_event(created_event_id)
                print_result("READ_BACK", read_back)
                if not read_back.success or not read_back.events:
                    print("verification : FAILED (event could not be read back)")
                    exit_code = 6
                else:
                    actual_time = read_back.events[0].time or ""
                    verified = actual_time.startswith(args.update_time)
                    print(f"verification : {'PASSED' if verified else 'FAILED'}")
                    print(f"expected_time: {args.update_time}")
                    print(f"actual_time  : {actual_time or '-'}")
                    if not verified:
                        exit_code = 7
    finally:
        if args.cleanup and created_event_id:
            delete_result = provider.delete_event(
                CalendarQuery(action="delete", event_id=created_event_id)
            )
            print_result("DELETE", delete_result)
            if not delete_result.success and exit_code == 0:
                exit_code = 8

    return exit_code


def parse_args():
    """Parse CLI args."""
    parser = argparse.ArgumentParser(
        description="Jarvis Google Calendar write smoke test"
    )
    parser.add_argument(
        "--read",
        action="store_true",
        help="Read events for the selected date before writing.",
    )
    parser.add_argument(
        "--date",
        default="today",
        help="Read date scope: today, tomorrow, week, next_week, next, or YYYY-MM-DD.",
    )
    parser.add_argument(
        "--create-smoke",
        action="store_true",
        help="Create a real Google Calendar smoke-test event.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the created smoke-test event after verification.",
    )
    parser.add_argument(
        "--delete-event-id",
        default="",
        help="Delete a specific Google Calendar event id.",
    )
    parser.add_argument(
        "--title",
        default="Jarvis Calendar ReadBack Smoke Test",
        help="Smoke-test event title.",
    )
    parser.add_argument(
        "--smoke-date",
        default="",
        help="Smoke-test event date, default tomorrow.",
    )
    parser.add_argument("--time", default="15:00", help="Initial start time.")
    parser.add_argument(
        "--update-time",
        default="",
        help="Update the created event and verify this start time.",
    )
    parser.add_argument(
        "--reminder-minutes",
        type=int,
        default=60,
        help="Google Calendar popup reminder minutes.",
    )
    return parser.parse_args()


def load_google_config():
    """Load Jarvis config and force Google Calendar write scope."""
    runtime_config = ConfigurationLoader().load()
    return GoogleProviderConfig(
        credentials_path=runtime_config.calendar.google_credentials_path,
        client_secret_path=runtime_config.calendar.google_client_secret_path,
        scopes=(
            GOOGLE_CALENDAR_SCOPE,
            GOOGLE_CONTACTS_SCOPE,
            GOOGLE_GMAIL_MODIFY_SCOPE,
        ),
        timezone=runtime_config.calendar.timezone,
    )


def print_result(label, result):
    """Print a safe concise CalendarResult summary."""
    print(f"========== {label} ==========")
    print(f"success     : {bool(result.success)}")
    print(f"provider    : {result.provider}")
    print(f"action      : {result.action}")
    print(f"error_code  : {result.error_code or '-'}")
    print(f"events      : {len(result.events)}")
    print(f"duration_ms : {result.execution_time_ms}")

    for index, event in enumerate(result.events, start=1):
        reminders = ",".join(str(value) for value in event.reminder_minutes) or "-"
        print(
            f"{index}. id={event.id} date={event.date} time={event.time or '-'} "
            f"title={event.title} reminder={reminders}"
        )

    if result.message:
        print(f"message     : {result.message}")


if __name__ == "__main__":
    raise SystemExit(main())
