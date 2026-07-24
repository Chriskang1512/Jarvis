"""Korean formatter for Contact Ability results."""

import re


def format_contact_result(result):
    """Format one structured ContactResult for TTS."""
    if result.message:
        return result.message

    if result.requires_confirmation:
        return "연락처 작업을 진행할까요?"

    if not result.success:
        return error_message(result)

    if result.action == "create":
        return created_message(result.contact)

    if result.action == "update":
        return updated_message(result.contact, result.changed_fields)

    if result.action == "get":
        return get_message(result.contact, attribute_from_changed_fields(result.changed_fields))

    if result.action == "delete":
        name = getattr(result.contact, "display_name", "") or "해당 연락처"
        return f"{name}의 연락처를 삭제했습니다."

    if result.action == "list":
        if not result.contacts:
            return "저장된 연락처가 없습니다."
        names = ", ".join(getattr(contact, "display_name", "") for contact in result.contacts)
        return f"연락처는 {names}입니다."

    return "연락처 작업이 완료되었습니다."


def confirmation_message(query):
    """Return a confirmation prompt for a mutating contact query."""
    name = query.display_name or query.contact_id or "해당 연락처"

    if query.action == "create":
        return f"{name}를 연락처에 저장할까요?"

    if query.action == "delete":
        return f"{name}의 연락처를 삭제할까요?"

    if query.action == "update":
        if query.email:
            return f"{name}의 이메일을 {query.email}로 저장할까요?"
        if query.phone:
            return f"{name}의 전화번호를 저장할까요?"
        if query.birthday:
            return f"{name}의 생일을 {format_birthday(query.birthday)}로 저장할까요?"
        return f"{name}의 연락처를 수정할까요?"

    return "연락처 작업을 진행할까요?"


def created_message(contact):
    """Return create success text."""
    return f"{contact.display_name}를 연락처에 저장했습니다."


def updated_message(contact, changed_fields):
    """Return update success text from structured changed fields."""
    fields = set(changed_fields or ())

    if "email" in fields or "emails" in fields:
        return f"{contact.display_name}의 이메일을 저장했습니다."
    if "phone" in fields or "phones" in fields:
        return f"{contact.display_name}의 전화번호를 저장했습니다."
    if "birthday" in fields:
        return f"{contact.display_name}의 생일을 저장했습니다."
    return f"{contact.display_name}의 연락처를 수정했습니다."


def get_message(contact, attribute):
    """Return a contact recall response."""
    if contact is None:
        return "연락처를 찾지 못했습니다."

    name = contact.display_name

    if attribute == "email":
        if contact.emails:
            return f"{name}의 이메일은 {', '.join(contact.emails)}입니다."
        return f"{name}의 이메일은 아직 저장되어 있지 않습니다."

    if attribute == "phone":
        if contact.phones:
            return f"{name}의 전화번호는 {', '.join(contact.phones)}입니다."
        return f"{name}의 전화번호는 아직 저장되어 있지 않습니다."

    if attribute == "birthday":
        if contact.birthday:
            return f"{name}의 생일은 {format_birthday(contact.birthday)}입니다."
        return f"{name}의 생일은 아직 저장되어 있지 않습니다."

    parts = [f"이름은 {name}입니다."]

    if contact.emails:
        parts.append(f"이메일은 {', '.join(contact.emails)}입니다.")
    if contact.phones:
        parts.append(f"전화번호는 {', '.join(contact.phones)}입니다.")
    if contact.birthday:
        parts.append(f"생일은 {format_birthday(contact.birthday)}입니다.")

    if len(parts) == 1:
        parts.append("저장된 세부 정보는 아직 없습니다.")

    return " ".join(parts)


def error_message(result):
    """Return a user-facing error message."""
    if result.message:
        return result.message

    if result.error_code == "contact_not_found":
        return "연락처를 찾지 못했습니다."

    if result.error_code == "delete_failed":
        return "연락처를 삭제하지 못했습니다."

    if str(result.error_code or "").startswith("AUTH"):
        return result.message or "Google Contacts 인증이 필요합니다."

    return "연락처 작업을 완료하지 못했습니다."


def attribute_from_changed_fields(fields):
    """Use changed_fields as a generic attribute carrier for get results."""
    for field in fields or ():
        if field in {"email", "phone", "birthday", "contact"}:
            return field
    return "contact"


def format_birthday(value):
    """Format MM-DD or YYYY-MM-DD for Korean voice output."""
    text = str(value or "")

    if re.fullmatch(r"\d{2}-\d{2}", text):
        month, day = text.split("-")
        return f"{int(month)}월 {int(day)}일"

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        year, month, day = text.split("-")
        return f"{int(year)}년 {int(month)}월 {int(day)}일"

    return text
