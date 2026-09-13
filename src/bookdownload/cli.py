from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .channels import DEFAULT_SELECTORS, ChannelError, PlaywrightChannel
from .models import BookStatus
from .parser import parse_booklist
from .review import review_interactively
from .storage import QueueStore, row_to_book
from .worker import QueueWorker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bookdownload", description="本地电子书下载任务管理器")
    parser.add_argument("--data-dir", type=Path, default=Path.cwd() / ".bookdownload")
    sub = parser.add_subparsers(dest="command", required=True)

    import_cmd = sub.add_parser("import", help="解析书单并加入下载列表")
    import_cmd.add_argument("booklist", type=Path)
    import_cmd.add_argument("--output", type=Path, required=True)
    import_cmd.add_argument("--yes", action="store_true", help="跳过交互确认")

    list_cmd = sub.add_parser("list", help="查看下载列表")
    list_cmd.add_argument("--status", choices=[status.value for status in BookStatus])
    list_cmd.add_argument("--json", action="store_true")

    for command, help_text in (
        ("pause", "暂停项目"),
        ("resume", "继续项目"),
        ("cancel", "取消项目"),
        ("retry", "重试失败项目"),
        ("remove", "从列表删除项目，不删除文件"),
    ):
        item_cmd = sub.add_parser(command, help=help_text)
        item_cmd.add_argument("item_id")

    worker_cmd = sub.add_parser("worker", help="处理到期的下载项目")
    worker_cmd.add_argument("--once", action="store_true")
    worker_cmd.add_argument("--poll-seconds", type=int, default=30)
    worker_cmd.add_argument("--dry-run", action="store_true", help="不访问网站，仅验证调度")
    worker_cmd.add_argument("--headed", action="store_true", help="调试用：保持浏览器可见")

    config_cmd = sub.add_parser("configure", help="配置网站地址和页面选择器")
    config_cmd.add_argument("--url", required=True)
    config_cmd.add_argument("--selectors", type=Path, help="包含 CSS 选择器的 JSON 文件")

    sub.add_parser("login", help="打开可见浏览器，由用户完成登录")

    report_cmd = sub.add_parser("report", help="导出本地任务报告")
    report_cmd.add_argument("--output", type=Path, required=True, help="报告文件名前缀或目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console_encoding()
    args = build_parser().parse_args(argv)
    store = QueueStore(args.data_dir)
    if args.command == "import":
        return _import(args, store)
    if args.command == "list":
        return _list(args, store)
    if args.command == "remove":
        if not store.delete(args.item_id):
            print("未找到项目，或项目正在下载，无法删除。", file=sys.stderr)
            return 1
        print(f"已从列表删除 {args.item_id}；已下载文件未被删除。")
        return 0
    if args.command in {"pause", "resume", "cancel", "retry"}:
        return _change_status(args.command, args.item_id, store)
    if args.command == "configure":
        return _configure(args, store)
    if args.command == "login":
        try:
            _live_channel(store, headless=False, require_ready=False).login()
        except ChannelError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        resumed = 0
        for row in store.list_items(BookStatus.LOGIN_REQUIRED):
            store.update_status(row["id"], BookStatus.PENDING)
            resumed += 1
        print("登录会话已经保存在本机浏览器配置目录。")
        if resumed:
            print(f"已恢复 {resumed} 个等待登录的项目。")
        return 0
    if args.command == "report":
        return _report(args, store)
    if args.command == "worker":
        if args.dry_run:
            due = store.due_items()
            print(f"当前有 {len(due)} 个到期项目；dry-run 未修改队列。")
            return 0
        try:
            channel = _live_channel(store, headless=not args.headed, require_ready=True)
        except ChannelError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        worker = QueueWorker(store, channel)
        if args.once:
            print(f"本次处理 {worker.run_once()} 个项目。")
        else:
            print("worker 已启动；按 Ctrl+C 停止。")
            try:
                worker.run_forever(max(1, args.poll_seconds))
            except KeyboardInterrupt:
                print("worker 已停止；队列已保存。")
        return 0
    return 2


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _import(args: argparse.Namespace, store: QueueStore) -> int:
    if not args.booklist.is_file():
        print(f"书单不存在：{args.booklist}", file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    books = parse_booklist(args.booklist)
    if not books:
        print("没有解析到图书。", file=sys.stderr)
        return 1
    if args.yes:
        _print_preview(books)
    else:
        if not review_interactively(books, _print_preview):
            print("已取消，未修改下载列表。")
            return 0
    ids = store.add_books(books, args.output, args.booklist)
    print(f"已加入 {len(ids)} 本；任务 ID：{ids[0]} … {ids[-1]}")
    return 0


def _print_preview(books) -> None:
    print(f"{'序号':<5} {'书名':<38} {'作者':<24} {'系列':<16} {'难度'}")
    print("-" * 105)
    for index, book in enumerate(books, 1):
        metrics = " ".join(value for value in (book.lexile, f"AR {book.ar:g}" if book.ar else None) if value)
        warning = f" [警告：{'、'.join(book.warnings)}]" if book.warnings else ""
        print(f"{index:<5} {book.title[:36]:<38} {(book.author or '-')[:22]:<24} {(book.series or '-')[:14]:<16} {metrics}{warning}")


def _list(args: argparse.Namespace, store: QueueStore) -> int:
    status = BookStatus(args.status) if args.status else None
    rows = store.list_items(status)
    if args.json:
        payload = []
        for row in rows:
            item = dict(row)
            item["book"] = row_to_book(row).as_dict()
            del item["book_json"]
            payload.append(item)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("下载列表为空。")
        return 0
    print(f"{'ID':<14} {'状态':<18} {'书名':<40} {'下次尝试'}")
    print("-" * 100)
    for row in rows:
        book = row_to_book(row)
        print(f"{row['id']:<14} {row['status']:<18} {book.title[:38]:<40} {row['next_attempt_at'] or '-'}")
    return 0


def _change_status(command: str, item_id: str, store: QueueStore) -> int:
    row = store.get(item_id)
    if not row:
        print(f"未找到项目：{item_id}", file=sys.stderr)
        return 1
    transitions = {
        "pause": BookStatus.PAUSED,
        "resume": BookStatus.PENDING,
        "cancel": BookStatus.CANCELLED,
        "retry": BookStatus.PENDING,
    }
    invalid = {
        "pause": {BookStatus.COMPLETED.value, BookStatus.CANCELLED.value},
        "resume": {BookStatus.COMPLETED.value, BookStatus.DOWNLOADING.value},
        "cancel": {BookStatus.COMPLETED.value},
        "retry": {BookStatus.COMPLETED.value, BookStatus.DOWNLOADING.value},
    }
    if row["status"] in invalid[command]:
        print(f"当前状态 {row['status']} 不允许执行 {command}。", file=sys.stderr)
        return 1
    store.update_status(item_id, transitions[command])
    print(f"{item_id} → {transitions[command].value}")
    return 0


def _configure(args: argparse.Namespace, store: QueueStore) -> int:
    selectors: dict[str, str] = {}
    if args.selectors:
        try:
            selectors = json.loads(args.selectors.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"无法读取选择器配置：{exc}", file=sys.stderr)
            return 2
        if not isinstance(selectors, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in selectors.items()
        ):
            print("选择器配置必须是字符串键值组成的 JSON 对象。", file=sys.stderr)
            return 2
    config = {"base_url": args.url.rstrip("/"), "browser_channel": "chrome", "selectors": selectors}
    config_path = store.data_dir / "channel.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"配置已保存：{config_path}")
    if not selectors:
        print("将使用当前已验证的内置页面选择器；网站变化时可通过 --selectors 覆盖。")
    return 0


def _live_channel(store: QueueStore, *, headless: bool, require_ready: bool) -> PlaywrightChannel:
    config_path = store.data_dir / "channel.json"
    if not config_path.is_file():
        raise ChannelError("尚未配置网站。请先执行：bookdownload configure --url <有效地址>")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChannelError(f"网站配置无效：{exc}") from exc
    base_url = config.get("base_url")
    if not isinstance(base_url, str) or not base_url.startswith(("https://", "http://")):
        raise ChannelError("channel.json 中的 base_url 无效")
    selectors = config.get("selectors", {})
    if not isinstance(selectors, dict):
        raise ChannelError("channel.json 中的 selectors 必须是 JSON 对象")
    if require_ready:
        required = {"search_input", "search_submit", "result", "result_title", "result_link", "download_link"}
        merged = {**DEFAULT_SELECTORS, **{key: value for key, value in selectors.items() if value}}
        missing = sorted(key for key in required if not merged.get(key))
        if missing:
            raise ChannelError(f"网站选择器尚未配置完整：{', '.join(missing)}")
    browser_channel = config.get("browser_channel", "chrome")
    if browser_channel is not None and not isinstance(browser_channel, str):
        raise ChannelError("channel.json 中的 browser_channel 必须是字符串或 null")
    return PlaywrightChannel(
        base_url,
        store.data_dir / "browser-profile",
        selectors,
        headless=headless,
        browser_channel=browser_channel,
    )


def _report(args: argparse.Namespace, store: QueueStore) -> int:
    output = args.output
    if output.suffix:
        base = output.with_suffix("")
    elif output.exists() and output.is_dir():
        base = output / "bookdownload-report"
    else:
        base = output
    base.parent.mkdir(parents=True, exist_ok=True)
    rows = store.list_items()
    payload = []
    for row in rows:
        item = dict(row)
        item["book"] = row_to_book(row).as_dict()
        del item["book_json"]
        payload.append(item)
    json_path = base.with_suffix(".json")
    csv_path = base.with_suffix(".csv")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    columns = [
        "id", "status", "title", "author", "series", "volume", "lexile", "ar",
        "output_dir", "attempts", "next_attempt_at", "last_error", "result_path",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item in payload:
            book = item["book"]
            writer.writerow({
                "id": item["id"], "status": item["status"], "title": book["title"],
                "author": book["author"], "series": book["series"], "volume": book["volume"],
                "lexile": book["lexile"], "ar": book["ar"], "output_dir": item["output_dir"],
                "attempts": item["attempts"], "next_attempt_at": item["next_attempt_at"],
                "last_error": item["last_error"], "result_path": item["result_path"],
            })
    print(f"已导出：{json_path}")
    print(f"已导出：{csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
