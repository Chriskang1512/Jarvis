from datetime import datetime
from pathlib import Path


MEMORY_FILE = Path("memory.txt")


def save_memory(role, message):
    """Save one conversation line to a local memory text file."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] {role}: {message}\n"

    with MEMORY_FILE.open("a", encoding="utf-8") as file:
        file.write(line)
