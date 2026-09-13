# BookDownload

[简体中文](#简体中文) · [English](#english)

BookDownload is a local, resumable ebook queue and browser-assisted download tool. It parses structured reading lists, lets you review the results, stores jobs in SQLite, ranks search candidates, and downloads authorized content through a configurable Playwright browser adapter.

> [!IMPORTANT]
> Use BookDownload only for content you are authorized to access. It does not bypass CAPTCHAs, account quotas, DRM, authentication, or other access controls.

## 简体中文

### 功能简介

BookDownload 面向需要批量整理和获取电子书的本地工作流，当前版本支持：

- 从 UTF-8 文本书单解析书名、中文译名、作者、系列、ISBN、AR 和 Lexile 等字段
- 导入前预览，并通过交互命令编辑、删除、拆分或合并条目
- 使用 SQLite 持久化任务队列，支持暂停、恢复、取消、重试和状态筛选
- 按书名、作者、系列/卷次、语言、年份和完整性对候选资源评分
- 对低置信度、字段冲突或疑似非完整正文的候选标记人工复核
- 使用本地持久化浏览器会话执行已授权下载
- 遇到登录失效、额度耗尽或站点拒绝访问时安全暂停或延期
- 按图书元数据生成 Windows 兼容文件名，并避免覆盖同名文件
- 导出 JSON 和 CSV 任务报告

### 环境要求

- Python 3.11 或更高版本
- 推荐使用 [uv](https://docs.astral.sh/uv/)
- 如需连接网站：本机 Chrome，以及 Playwright Python 包
- `bookdownload.ps1` 为 Windows PowerShell 启动脚本；核心 Python CLI 可在其他平台运行

### 安装

克隆仓库后，在项目目录执行：

```powershell
uv sync
```

仅使用书单解析、队列管理和报告功能时，不需要浏览器依赖。如需执行浏览器下载：

```powershell
uv sync --extra browser
```

项目默认调用本机 Chrome，因此通常不需要额外下载 Playwright Chromium。如果你在配置中将 `browser_channel` 改为 `null`，则需要安装 Playwright 管理的浏览器：

```powershell
uv run playwright install chromium
```

### 快速开始

Windows 用户可直接使用仓库内的启动脚本：

```powershell
.\bookdownload.ps1 import ".\示例1.txt" --output ".\downloads"
.\bookdownload.ps1 list
```

也可以通过 `uv` 运行 CLI，适用于 Windows、macOS 和 Linux：

```bash
uv run bookdownload import "./示例1.txt" --output "./downloads"
uv run bookdownload list
```

导入时会显示解析预览。确认前可以使用以下交互命令：

```text
y                                      确认导入
n                                      取消导入
edit 2 author=Katherine Rundell        修改字段
delete 3                               删除条目
split 4 Book One | Book Two            拆分条目
merge 5 6                              合并条目
help                                   查看可编辑字段
```

在自动化脚本中可通过 `--yes` 跳过交互确认：

```powershell
.\bookdownload.ps1 import ".\books.txt" --output ".\downloads" --yes
```

### 书单格式

解析器接受 UTF-8 或带 BOM 的 UTF-8 文本。每个条目以编号和 Markdown 粗体书名开头，后续可包含阅读难度和说明：

```markdown
1. **The Explorer**（Katherine Rundell）
AR：5.4｜Lexile：740L
一群孩子在亚马逊丛林展开求生冒险。

2. **Rooftoppers《屋顶上的索菲》**（Katherine Rundell）
AR：5.0｜Lexile：700L
```

系列合集可在一个编号项下使用多个 `《书名》` 行，解析器会将它们拆成独立任务。仓库中的 [`示例1.txt`](./示例1.txt) 提供了完整示例。

### 队列管理

```powershell
.\bookdownload.ps1 list
.\bookdownload.ps1 list --status pending
.\bookdownload.ps1 list --json
.\bookdownload.ps1 pause <任务ID>
.\bookdownload.ps1 resume <任务ID>
.\bookdownload.ps1 cancel <任务ID>
.\bookdownload.ps1 retry <任务ID>
.\bookdownload.ps1 remove <任务ID>
```

`remove` 只删除队列记录，不会删除已经下载的文件。数据库、网站配置和浏览器配置默认保存在当前目录的 `.bookdownload/` 中；可在子命令前使用全局参数 `--data-dir` 更改位置：

```powershell
.\bookdownload.ps1 --data-dir "D:\BookData" list
```

常见任务状态包括 `pending`、`review_required`、`completed`、`paused`、`quota_wait`、`login_required`、`not_found`、`failed` 和 `cancelled`。

### 配置网站与登录

BookDownload 不会自动发现、推荐或切换网站地址。请仅配置你有权使用的网站：

```powershell
.\bookdownload.ps1 configure --url "https://your-authorized-site.example"
.\bookdownload.ps1 login
```

`login` 会打开可见浏览器。请自行完成登录，然后回到终端按 Enter；程序不会接收或保存你的密码，登录状态保存在本机 `.bookdownload/browser-profile/`。

页面结构发生变化时，可提供自定义 CSS 选择器：

```powershell
.\bookdownload.ps1 configure `
  --url "https://your-authorized-site.example" `
  --selectors ".\selectors.json"
```

`selectors.json` 示例：

```json
{
  "search_input": "#search",
  "search_submit": "button[type='submit']",
  "result": ".book-result",
  "result_title": ".title",
  "result_author": ".author",
  "result_language": ".language",
  "result_year": ".year",
  "result_format": ".format",
  "result_link": "a.details",
  "download_link": "a.download",
  "login_required": "a[href*='login']",
  "quota_exceeded": ".quota-warning"
}
```

其中 `search_input`、`search_submit`、`result`、`result_title`、`result_link` 和 `download_link` 是执行 worker 所需的关键选择器。配置文件中的值会覆盖内置默认值。

### 执行下载任务

先用 dry-run 检查当前到期任务，过程不会访问网站或修改队列：

```powershell
.\bookdownload.ps1 worker --once --dry-run
```

处理一轮到期任务：

```powershell
.\bookdownload.ps1 worker --once
```

持续轮询队列，并在额度等待到期后自动续跑：

```powershell
.\bookdownload.ps1 worker --poll-seconds 30
```

worker 默认使用无头浏览器。排查站点兼容问题时可以增加 `--headed`，但该选项不会绕过站点限制：

```powershell
.\bookdownload.ps1 worker --once --headed
```

### 导出报告

```powershell
.\bookdownload.ps1 report --output ".\reports\latest"
```

该命令会生成 `latest.json` 和 `latest.csv`。

### 开发与测试

```powershell
uv sync --extra dev
uv run pytest
```

项目采用 `src` 布局，主要模块位于 `src/bookdownload/`，测试位于 `tests/`。

### 当前限制

- 网站适配依赖页面 CSS 选择器；网站改版后可能需要更新配置。
- `review_required` 会保留匹配原因和冲突信息，但当前版本尚未提供候选审批 CLI。
- 当前只避免覆盖同名文件，尚未进行文件哈希或内容级去重。
- 下载是否成功仍受目标网站、账号权限、额度和网络环境影响。
- 浏览器 worker 为同步、单进程实现。

### 安全与隐私

- 登录凭据直接输入目标网站，BookDownload 不会接收或保存密码。
- 队列数据、配置、报告和浏览器会话默认保留在本机，除非你主动移动或发布它们。
- 仓库的 `.gitignore` 已排除 `.bookdownload/`、虚拟环境、缓存、覆盖率文件和构建产物。
- 分享选择器文件前请检查其内容，切勿提交浏览器会话或密钥。

### 参与贡献

欢迎提交 Issue 和 Pull Request。提交代码变更前，请附上清晰的复现步骤或使用场景，并运行完整测试。

仓库目前尚未包含许可证文件。在分发修改版本或接受外部贡献前，请先添加合适的开源许可证。

---

## English

### Features

BookDownload is designed for local, batch-oriented ebook workflows. The current version can:

- Parse titles, translated titles, authors, series, ISBNs, AR levels, and Lexile measures from UTF-8 reading lists
- Preview imported entries and edit, delete, split, or merge them interactively
- Persist the queue in SQLite with pause, resume, cancel, retry, and status-filtering commands
- Rank search candidates by title, author, series/volume, language, year, and completeness
- Flag low-confidence, conflicting, or potentially incomplete candidates for manual review
- Download authorized content through a persistent local browser session
- Pause or defer work safely when login expires, quota is exhausted, or access is blocked
- Generate Windows-safe filenames from book metadata without overwriting existing files
- Export queue reports in JSON and CSV formats

### Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) is recommended
- For website access: local Chrome and the Playwright Python package
- `bookdownload.ps1` is a Windows PowerShell launcher; the underlying Python CLI is cross-platform

### Installation

After cloning the repository, run this from the project directory:

```powershell
uv sync
```

Browser dependencies are not required for parsing lists, managing the queue, or exporting reports. To enable browser downloads, run:

```powershell
uv sync --extra browser
```

The default configuration uses locally installed Chrome, so downloading Playwright's Chromium build is normally unnecessary. If you set `browser_channel` to `null` in the configuration, install it with:

```powershell
uv run playwright install chromium
```

### Quick start

On Windows, use the included launcher:

```powershell
.\bookdownload.ps1 import ".\示例1.txt" --output ".\downloads"
.\bookdownload.ps1 list
```

Alternatively, run the CLI through `uv` on Windows, macOS, or Linux:

```bash
uv run bookdownload import "./示例1.txt" --output "./downloads"
uv run bookdownload list
```

Import displays a preview before changing the queue. The interactive review prompt accepts:

```text
y                                      Confirm the import
n                                      Cancel the import
edit 2 author=Katherine Rundell        Edit a field
delete 3                               Delete an entry
split 4 Book One | Book Two            Split an entry
merge 5 6                              Merge two entries
help                                   Show editable fields
```

Use `--yes` to skip confirmation in automation:

```bash
uv run bookdownload import "./books.txt" --output "./downloads" --yes
```

### Reading-list format

The parser accepts UTF-8 text with or without a BOM. Each entry starts with a number and a Markdown bold title, followed by optional reading metrics and notes:

```markdown
1. **The Explorer**（Katherine Rundell）
AR：5.4｜Lexile：740L
A group of children must survive in the Amazon rainforest.

2. **Rooftoppers《屋顶上的索菲》**（Katherine Rundell）
AR：5.0｜Lexile：700L
```

A series entry may contain multiple `《Title》` lines under one numbered heading; each line becomes a separate queue item. See [`示例1.txt`](./示例1.txt) for a complete example.

### Queue management

```bash
uv run bookdownload list
uv run bookdownload list --status pending
uv run bookdownload list --json
uv run bookdownload pause <ITEM_ID>
uv run bookdownload resume <ITEM_ID>
uv run bookdownload cancel <ITEM_ID>
uv run bookdownload retry <ITEM_ID>
uv run bookdownload remove <ITEM_ID>
```

`remove` deletes only the queue record and never deletes a downloaded file. The database, channel configuration, and browser profile are stored in `.bookdownload/` under the current directory by default. Place the global `--data-dir` option before the subcommand to use another location:

```bash
uv run bookdownload --data-dir "./book-data" list
```

Common states include `pending`, `review_required`, `completed`, `paused`, `quota_wait`, `login_required`, `not_found`, `failed`, and `cancelled`.

### Channel configuration and login

BookDownload does not discover, recommend, or switch website addresses. Configure only a website you are authorized to use:

```bash
uv run bookdownload configure --url "https://your-authorized-site.example"
uv run bookdownload login
```

`login` opens a visible browser. Complete authentication yourself, return to the terminal, and press Enter. BookDownload never accepts or stores your password; the authenticated session stays in the local `.bookdownload/browser-profile/` directory.

If the page structure differs or changes, provide custom CSS selectors:

```bash
uv run bookdownload configure \
  --url "https://your-authorized-site.example" \
  --selectors "./selectors.json"
```

Example `selectors.json`:

```json
{
  "search_input": "#search",
  "search_submit": "button[type='submit']",
  "result": ".book-result",
  "result_title": ".title",
  "result_author": ".author",
  "result_language": ".language",
  "result_year": ".year",
  "result_format": ".format",
  "result_link": "a.details",
  "download_link": "a.download",
  "login_required": "a[href*='login']",
  "quota_exceeded": ".quota-warning"
}
```

The worker requires `search_input`, `search_submit`, `result`, `result_title`, `result_link`, and `download_link`. Values from the configuration override the built-in defaults.

### Running the worker

Inspect the number of due jobs without visiting a website or changing the queue:

```bash
uv run bookdownload worker --once --dry-run
```

Process one batch of due jobs:

```bash
uv run bookdownload worker --once
```

Keep polling and resume automatically after a quota wait expires:

```bash
uv run bookdownload worker --poll-seconds 30
```

The worker is headless by default. Add `--headed` to diagnose website compatibility in a visible browser; it does not bypass website restrictions:

```bash
uv run bookdownload worker --once --headed
```

### Reports

```bash
uv run bookdownload report --output "./reports/latest"
```

This creates `latest.json` and `latest.csv`.

### Development and testing

```bash
uv sync --extra dev
uv run pytest
```

The package uses a `src` layout. Application modules live in `src/bookdownload/`, and tests live in `tests/`.

### Current limitations

- Website integration depends on CSS selectors and may require updates after a site redesign.
- `review_required` retains match reasons and blockers, but this release does not yet include a candidate-approval CLI.
- Existing filenames are preserved, but file hashes and content-level deduplication are not implemented.
- Downloads still depend on the target website, account permissions, quotas, and network conditions.
- The browser worker is synchronous and single-process.

## Security and privacy

- Credentials are entered directly into the website and are never handled by BookDownload.
- Queue data, configuration, reports, and browser sessions remain local unless you move or publish them.
- `.bookdownload/`, virtual environments, caches, coverage files, and build artifacts are excluded by the repository's `.gitignore`.
- Review selector files before sharing them, and never commit session profiles or secrets.

## Contributing

Issues and pull requests are welcome. Please include a clear reproduction or use case and run the test suite before submitting code changes.

No license file is currently included. Add a license before distributing modified copies or accepting external contributions.
