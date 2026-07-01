from datetime import datetime
from pathlib import Path


MEMORY_FILE = Path("memory.txt")
NOTE_FILE = Path("data") / "memory.txt"


def save_memory(role, message):
    """Save one conversation line to a local memory text file."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] {role}: {message}\n"

    with MEMORY_FILE.open("a", encoding="utf-8") as file:
        file.write(line)


def save_note(note):
    """Save one user note to data/memory.txt."""
    NOTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    with NOTE_FILE.open("a", encoding="utf-8") as file:
        if NOTE_FILE.stat().st_size > 0:
            file.write("\n")

        file.write(f"[{now}]\n")
        file.write(note + "\n\n")


def list_notes():
    """Read saved notes from data/memory.txt as separate blocks."""
    if not NOTE_FILE.exists():
        return []

    with NOTE_FILE.open("r", encoding="utf-8") as file:
        content = file.read().strip()

    if content == "":
        return []

    return [note.strip() for note in content.split("\n\n") if note.strip() != ""]


def write_notes(notes):
    """Write all note blocks back to data/memory.txt."""
    NOTE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with NOTE_FILE.open("w", encoding="utf-8") as file:
        file.write("\n\n".join(notes))

        if len(notes) > 0:
            file.write("\n\n")


def delete_note(note_number):
    """Delete one note by its 1-based number and return whether it worked."""
    notes = list_notes()
    note_index = note_number - 1

    if note_index < 0 or note_index >= len(notes):
        return False

    del notes[note_index]
    write_notes(notes)
    return True


def delete_all_notes():
    """Delete every saved note from data/memory.txt."""
    write_notes([])


def search_notes(keyword):
    """Return notes that contain the search keyword."""
    notes = list_notes()

    return [note for note in notes if keyword.lower() in note.lower()]


def get_recent_notes(count):
    """Return the most recent notes using the requested count."""
    notes = list_notes()

    return notes[-count:]


def count_notes():
    """Return how many notes are currently saved."""
    return len(list_notes())
