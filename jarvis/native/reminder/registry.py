from jarvis.native.reminder.engine import ReminderEngine


_DEFAULT_ENGINE = None


def get_default_reminder_engine():
    """Return process-wide reminder engine."""
    global _DEFAULT_ENGINE

    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = ReminderEngine()

    return _DEFAULT_ENGINE


def set_default_reminder_engine(engine):
    """Set process-wide reminder engine."""
    global _DEFAULT_ENGINE
    _DEFAULT_ENGINE = engine
    return _DEFAULT_ENGINE
