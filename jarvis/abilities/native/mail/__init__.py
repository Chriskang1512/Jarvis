from jarvis.abilities.native.mail.ability import MailAbility, create_ability
from jarvis.abilities.native.mail.parser import MailIntentParser
from jarvis.abilities.native.mail.provider import MailProvider
from jarvis.abilities.native.mail.query import MailQuery
from jarvis.abilities.native.mail.result import MailMessage, MailResult, MailSendResult, OutgoingMail

__all__ = [
    "MailAbility",
    "MailIntentParser",
    "MailProvider",
    "MailMessage",
    "MailQuery",
    "MailResult",
    "MailSendResult",
    "OutgoingMail",
    "create_ability",
]
