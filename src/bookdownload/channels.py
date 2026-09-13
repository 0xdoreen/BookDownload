from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin

from .models import BookRequest, Candidate


DEFAULT_SELECTORS = {
    "search_input": "#searchFieldx",
    "search_submit": "#searchForm button[aria-label='Search']",
    "result": "#searchResultBox .book-item:not([hidden]) z-bookcard",
    "result_title": "[slot='title']",
    "result_author": "[slot='author']",
    "result_link": "a.title",
    "download_link": "a.dlButton[href*='/dl/']",
    "login_required": "a[href^='/login']",
}


class ChannelError(RuntimeError):
    pass


class LoginRequired(ChannelError):
    pass


class QuotaExceeded(ChannelError):
    pass


class AddressInvalid(ChannelError):
    pass


class AccessBlocked(ChannelError):
    pass


class DownloadChannel(Protocol):
    def search(self, book: BookRequest) -> list[Candidate]: ...

    def download(self, candidate: Candidate, destination: Path) -> Path: ...


@dataclass(slots=True)
class DryRunChannel:
    """Safe development channel that returns no remote candidates."""

    def search(self, book: BookRequest) -> list[Candidate]:
        return []

    def download(self, candidate: Candidate, destination: Path) -> Path:
        raise ChannelError("DryRunChannel 不执行下载")


class PlaywrightChannel:
    """Configurable authorized-browser adapter.

    Selectors are intentionally supplied by configuration because the channel page
    can change. Passwords are never accepted by this class. A persistent browser
    profile stores the user-created session locally.
    """

    def __init__(
        self,
        base_url: str,
        profile_dir: Path,
        selectors: dict[str, str],
        headless: bool = True,
        browser_channel: str | None = "chrome",
    ):
        self.base_url = base_url.rstrip("/")
        self.profile_dir = profile_dir
        self.selectors = {**DEFAULT_SELECTORS, **{key: value for key, value in selectors.items() if value}}
        self.headless = headless
        self.browser_channel = browser_channel

    def _launch_options(self) -> dict[str, object]:
        options: dict[str, object] = {"headless": self.headless, "accept_downloads": True}
        if self.browser_channel:
            options["channel"] = self.browser_channel
        return options

    def login(self) -> None:
        sync_playwright = _playwright()
        with sync_playwright() as playwright:
            options = self._launch_options()
            options["headless"] = False
            context = playwright.chromium.launch_persistent_context(str(self.profile_dir), **options)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(self.base_url, wait_until="domcontentloaded")
                input("请在浏览器中完成登录，确认成功后回到终端按 Enter：")
            finally:
                context.close()

    def search(self, book: BookRequest) -> list[Candidate]:
        required = {"search_input", "search_submit", "result", "result_title"}
        missing = sorted(required - self.selectors.keys())
        if missing:
            raise ChannelError(f"channel.json 缺少选择器：{', '.join(missing)}")
        sync_playwright = _playwright()
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(str(self.profile_dir), **self._launch_options())
            try:
                page = context.pages[0] if context.pages else context.new_page()
                response = page.goto(self.base_url, wait_until="domcontentloaded")
                self._check_response(response, self.base_url)
                query = " ".join(value for value in (book.title, book.author) if value)
                page.locator(self.selectors["search_input"]).fill(query)
                with page.expect_navigation(wait_until="domcontentloaded"):
                    page.locator(self.selectors["search_submit"]).click()
                self._raise_page_state(page)
                return [self._candidate_from_locator(item) for item in page.locator(self.selectors["result"]).all()]
            finally:
                context.close()

    def _candidate_from_locator(self, item) -> Candidate:
        def text(key: str) -> str | None:
            selector = self.selectors.get(key)
            if not selector:
                return None
            locator = item.locator(selector)
            return locator.first.inner_text().strip() if locator.count() else None

        title = text("result_title")
        if not title:
            raise ChannelError("候选结果缺少书名")
        year_text = item.get_attribute("year") or text("result_year")
        detail_url = item.get_attribute("href")
        download_url = item.get_attribute("download")
        if not detail_url and self.selectors.get("result_link"):
            detail_url = item.locator(self.selectors["result_link"]).first.get_attribute("href")
        return Candidate(
            title=title,
            author=text("result_author"),
            language=item.get_attribute("language") or text("result_language"),
            isbn=item.get_attribute("isbn"),
            publication_year=int(year_text) if year_text and year_text.isdigit() else None,
            file_format=item.get_attribute("extension") or text("result_format"),
            file_size=_parse_size(item.get_attribute("filesize")),
            detail_url=urljoin(self.base_url, detail_url) if detail_url else None,
            download_url=urljoin(self.base_url, download_url) if download_url else None,
        )

    def download(self, candidate: Candidate, destination: Path) -> Path:
        download_selector = self.selectors.get("download_link")
        if not download_selector:
            raise ChannelError("channel.json 缺少选择器：download_link")
        url = candidate.detail_url or candidate.download_url
        if not url:
            raise ChannelError("候选资源缺少详情页或下载地址")
        sync_playwright = _playwright()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(str(self.profile_dir), **self._launch_options())
            try:
                page = context.pages[0] if context.pages else context.new_page()
                response = page.goto(urljoin(self.base_url, url), wait_until="domcontentloaded")
                self._check_response(response, url)
                self._raise_page_state(page)
                with page.expect_download(timeout=60_000) as download_info:
                    page.locator(download_selector).first.click()
                download = download_info.value
                download.save_as(str(destination))
            finally:
                context.close()
        if not destination.is_file() or destination.stat().st_size == 0:
            raise ChannelError("下载未生成有效文件")
        return destination

    @staticmethod
    def _check_response(response, url: str) -> None:
        if not response:
            raise AddressInvalid(f"网站没有返回有效响应：{url}")
        if response.status in (401, 403):
            raise AccessBlocked(f"网站拒绝浏览器访问（HTTP {response.status}）：{url}")
        if response.status >= 400:
            raise AddressInvalid(f"网站地址不可用（HTTP {response.status}）：{url}")

    def _raise_page_state(self, page) -> None:
        login_selector = self.selectors.get("login_required")
        quota_selector = self.selectors.get("quota_exceeded")
        if login_selector and page.locator(login_selector).count():
            raise LoginRequired("浏览器会话已失效，请重新登录")
        if quota_selector and page.locator(quota_selector).count():
            raise QuotaExceeded("账号当前下载额度已用完")


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ChannelError('请安装浏览器依赖：uv pip install -e ".[browser]"') from exc
    return sync_playwright


def _parse_size(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.upper().replace(",", "").split()
    if len(parts) != 2:
        return None
    try:
        amount = float(parts[0])
    except ValueError:
        return None
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    multiplier = multipliers.get(parts[1])
    return int(amount * multiplier) if multiplier else None
