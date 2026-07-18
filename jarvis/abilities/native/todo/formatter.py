"""Todo formatter."""

from jarvis.core.todos.todo import TODO_ACTIVE, TODO_COMPLETED


def format_todo_result(result):
    """Return natural Korean response for TodoResult."""
    if result.message:
        return result.message

    if not result.success:
        return error_message(result)

    if result.requires_confirmation:
        return confirmation_message(result.action)

    if result.action == "create":
        return f"{getattr(result.todo, 'title', '할 일')} 할 일을 추가했습니다."

    if result.action == "complete":
        if len(result.todos or ()) > 1:
            return f"{format_todo_group(result.todos)}을 완료했습니다."
        return f"{getattr(result.todo, 'title', '할 일')}을 완료했습니다."

    if result.action == "delete":
        if len(result.todos or ()) > 1:
            return f"{format_todo_group(result.todos)}을 삭제했습니다."
        return f"{getattr(result.todo, 'title', '할 일')}을 삭제했습니다."

    if result.action == "restore":
        return f"{getattr(result.todo, 'title', '할 일')}을 복원했습니다."

    if result.action == "list":
        return list_message(result.todos)

    if result.action == "update":
        return f"{getattr(result.todo, 'title', '할 일')}을 수정했습니다."

    return "처리했습니다."


def confirmation_message(action):
    """Return confirmation prompt."""
    if action == "delete":
        return "할 일을 삭제하려면 확인이 필요합니다. 삭제할까요?"
    if action == "complete":
        return "할 일을 완료 처리할까요?"
    return "할 일을 저장하려면 확인이 필요합니다. 저장할까요?"


def list_message(todos):
    """Return list response."""
    items = list(todos or ())

    if len(items) == 0:
        return "할 일이 없습니다."

    lines = [f"할 일은 {len(items)}건입니다."]

    for index, todo in enumerate(items, start=1):
        status = "완료" if getattr(todo, "status", "") == TODO_COMPLETED else "진행 중"
        due = f" ({getattr(todo, 'due_at', '')})" if getattr(todo, "due_at", "") else ""
        lines.append(f"{index}. {todo.title}{due} - {status}")

    return "\n".join(lines)


def error_message(result):
    """Return error response."""
    if result.error_code == "todo_not_found":
        return "해당 할 일을 찾지 못했습니다."
    if result.error_code == "title_required":
        return "할 일 제목을 말씀해 주세요."
    return "할 일을 처리하지 못했습니다."


def format_todo_group(todos):
    """Return a compact label for multiple todos."""
    items = list(todos or ())

    if len(items) == 0:
        return "할 일"

    if len(items) == 1:
        return getattr(items[0], "title", "할 일")

    return f"{getattr(items[0], 'title', '할 일')} 외 {len(items) - 1}건"


def status_for_action(action):
    """Return list status for an action if needed."""
    if action == "completed":
        return TODO_COMPLETED
    return TODO_ACTIVE
