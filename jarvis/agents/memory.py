from jarvis.memory.store import (
    count_notes,
    delete_all_notes,
    delete_note,
    get_recent_notes,
    list_notes,
    save_note,
    search_notes,
)


def handle_memory_command(command):
    """Handle a memory command by saving or showing notes."""
    if is_delete_all_command(command):
        return delete_all_notes_by_command()

    if is_count_command(command):
        return show_note_count()

    if is_recent_command(command):
        return show_recent_notes()

    if is_delete_command(command):
        return delete_note_by_command(command)

    if is_search_command(command):
        return search_notes_by_command(command)

    if is_show_command(command):
        return show_notes()

    note = extract_note(command)

    if note == "":
        return "Selected Agent: Memory. 기억할 내용을 함께 입력해주세요."

    save_note(note)
    return f"Selected Agent: Memory. 기억했습니다: {note}"


def is_count_command(command):
    """Check whether the user wants to count saved notes."""
    return "개수" in command


def is_recent_command(command):
    """Check whether the user wants to see recent notes."""
    return "최근" in command


def is_delete_command(command):
    """Check whether the user wants to delete a note."""
    return "삭제" in command


def is_delete_all_command(command):
    """Check whether the user wants to delete every saved note."""
    return "전체" in command and "삭제" in command


def is_search_command(command):
    """Check whether the user wants to search saved notes."""
    return "검색" in command


def is_show_command(command):
    """Check whether the user wants to see saved notes."""
    show_keywords = ["보여줘", "조회", "목록", "확인"]

    for keyword in show_keywords:
        if keyword in command:
            return True

    return False


def show_note_count():
    """Return the number of saved notes."""
    total_count = count_notes()

    return f"Selected Agent: Memory. 현재 저장된 메모 : {total_count}개"


def show_recent_notes():
    """Return the most recent 5 saved notes."""
    notes = get_recent_notes(5)

    if len(notes) == 0:
        return "Selected Agent: Memory. 아직 저장된 메모가 없습니다."

    return "Selected Agent: Memory. 최근 메모입니다:\n\n" + format_notes(notes)


def delete_note_by_command(command):
    """Delete the note number written in the user command."""
    note_number = extract_number(command)

    if note_number is None:
        return "Selected Agent: Memory. 삭제할 메모 번호를 입력해주세요."

    if delete_note(note_number):
        return f"Selected Agent: Memory. {note_number}번 메모를 삭제했습니다."

    return f"Selected Agent: Memory. {note_number}번 메모는 존재하지 않습니다."


def delete_all_notes_by_command():
    """Ask once before deleting every saved note."""
    answer = input("메모 전체를 삭제합니다 : y/n ").strip().lower()

    if answer == "y":
        delete_all_notes()
        return "Selected Agent: Memory. 전체 메모를 삭제했습니다."

    return "Selected Agent: Memory. 전체 메모 삭제를 취소했습니다."


def search_notes_by_command(command):
    """Search saved notes using the keyword from the user command."""
    keyword = extract_search_keyword(command)

    if keyword == "":
        return "Selected Agent: Memory. 검색할 단어를 입력해주세요."

    notes = search_notes(keyword)

    if len(notes) == 0:
        return f"Selected Agent: Memory. '{keyword}'가 포함된 메모가 없습니다."

    return (
        f"Selected Agent: Memory. '{keyword}' 검색 결과입니다:\n\n"
        + format_notes(notes)
    )


def show_notes():
    """Return saved notes as numbered readable blocks."""
    notes = list_notes()

    if len(notes) == 0:
        return "Selected Agent: Memory. 아직 저장된 메모가 없습니다."

    return "Selected Agent: Memory. 저장된 메모입니다:\n\n" + format_notes(notes)


def format_notes(notes):
    """Format many saved notes as numbered readable blocks."""
    blocks = []
    divider = "-----------------------"

    for number, note in enumerate(notes, start=1):
        block = format_note_block(number, note)
        blocks.append(block)

    return "".join(blocks) + divider


def format_note_block(number, note):
    """Format one saved note with a divider and number."""
    divider = "-----------------------"
    return f"{divider}\n\n{number}.\n{note}\n\n"


def extract_note(command):
    """Remove simple memory command words and return only the note text."""
    note = command.strip()
    memory_words = ["기억해", "기억", "저장해", "저장", "메모해", "메모"]

    for word in memory_words:
        if note.startswith(word):
            note = note[len(word):].strip()
            break

    return note


def extract_number(command):
    """Find the first number in the user command."""
    number_text = ""

    for character in command:
        if character.isdigit():
            number_text += character
        elif number_text != "":
            return int(number_text)

    if number_text == "":
        return None

    return int(number_text)


def extract_search_keyword(command):
    """Remove search command words and return the search keyword."""
    keyword = command.strip()
    search_words = ["메모 검색", "기억 검색", "검색"]

    for word in search_words:
        if keyword.startswith(word):
            keyword = keyword[len(word):].strip()
            break

    return keyword
