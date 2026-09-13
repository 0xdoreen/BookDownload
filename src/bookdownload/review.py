from __future__ import annotations

from dataclasses import replace

from .models import BookRequest


EDITABLE_FIELDS = {
    "title",
    "translated_title",
    "author",
    "series",
    "volume",
    "language",
    "isbn",
    "publication_year",
    "edition",
    "ar",
    "lexile",
    "notes",
}


def apply_review_command(books: list[BookRequest], command: str) -> str:
    operation, _, arguments = command.strip().partition(" ")
    operation = operation.casefold()
    if operation in {"delete", "d"}:
        index = _index(arguments, books)
        removed = books.pop(index)
        return f"已删除：{removed.title}"
    if operation in {"edit", "e"}:
        index_text, _, assignment = arguments.partition(" ")
        index = _index(index_text, books)
        field, separator, value = assignment.partition("=")
        field = field.strip()
        if not separator or field not in EDITABLE_FIELDS:
            raise ValueError(f"字段格式应为 field=value；可编辑字段：{', '.join(sorted(EDITABLE_FIELDS))}")
        parsed: object = value.strip() or None
        if field == "publication_year" and parsed is not None:
            parsed = int(str(parsed))
        if field == "ar" and parsed is not None:
            parsed = float(str(parsed))
        setattr(books[index], field, parsed)
        if field == "author" and parsed:
            books[index].warnings = [warning for warning in books[index].warnings if warning != "缺少作者"]
        return f"已修改第 {index + 1} 项的 {field}"
    if operation in {"split", "s"}:
        index_text, _, titles_text = arguments.partition(" ")
        index = _index(index_text, books)
        titles = [title.strip() for title in titles_text.split("|") if title.strip()]
        if len(titles) < 2:
            raise ValueError("拆分格式：split 序号 新书名1 | 新书名2")
        original = books[index]
        replacements = [replace(original, title=title, raw_text=f"{original.raw_text}\n[拆分为] {title}") for title in titles]
        books[index : index + 1] = replacements
        return f"已将第 {index + 1} 项拆成 {len(replacements)} 项"
    if operation in {"merge", "m"}:
        left_text, _, right_text = arguments.partition(" ")
        left_index = _index(left_text, books)
        right_index = _index(right_text, books)
        if left_index == right_index:
            raise ValueError("不能合并同一个项目")
        left, right = books[left_index], books[right_index]
        for field in EDITABLE_FIELDS - {"title"}:
            if getattr(left, field) in (None, "") and getattr(right, field) not in (None, ""):
                setattr(left, field, getattr(right, field))
        left.raw_text = f"{left.raw_text}\n[合并]\n{right.raw_text}"
        left.warnings = sorted(set(left.warnings + right.warnings))
        books.pop(right_index)
        return f"已合并，保留书名：{left.title}"
    raise ValueError("未知命令")


def review_interactively(books: list[BookRequest], preview) -> bool:
    while True:
        preview(books)
        print("\n命令：y 确认；n 取消；edit 序号 field=value；delete 序号；")
        print("      split 序号 新书名1 | 新书名2；merge 序号1 序号2；help 查看字段")
        command = input("> ").strip()
        if command.casefold() in {"y", "yes"}:
            return True
        if command.casefold() in {"n", "no", "q", "quit"}:
            return False
        if command.casefold() in {"help", "h", "?"}:
            print("可编辑字段：" + ", ".join(sorted(EDITABLE_FIELDS)))
            continue
        try:
            print(apply_review_command(books, command))
        except (ValueError, IndexError) as exc:
            print(f"命令无效：{exc}")


def _index(value: str, books: list[BookRequest]) -> int:
    try:
        index = int(value.strip()) - 1
    except ValueError as exc:
        raise ValueError("序号必须是整数") from exc
    if index < 0 or index >= len(books):
        raise IndexError(f"序号超出范围：{index + 1}")
    return index
