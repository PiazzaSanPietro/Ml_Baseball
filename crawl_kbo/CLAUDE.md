# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A web scraper for the official KBO (Korea Baseball Organization) website (`https://www.koreabaseball.com`). The project is designed to crawl **all categories of KBO statistics** — player records, team records, standings, schedules, and any other data the site exposes. Currently implemented: player records (hitters, pitchers, fielders, base runners). More categories will be added over time.

The target site uses ASP.NET WebForms with PostBack-based pagination, which requires specific handling described below.

## Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Run the crawler
python main.py
# or
python kbo_crawler.py
```

## Tech Stack

- Python 3.14+, `uv` package manager
- `requests` — HTTP requests and session management
- `beautifulsoup4` — HTML parsing
- `pandas` — DataFrame → CSV export

## Architecture

### Entry Points

- `main.py` — thin wrapper that calls `kbo_crawler.main()`
- `kbo_crawler.py` — full crawler implementation

### Crawling Flow

1. **GET** the first page → acquire session cookies and hidden form fields
2. **Paginate via POST** — parse `__doPostBack()` targets → set `__EVENTTARGET` → repeat POST requests
3. **Parse** — extract table data using `tData` class selector with fallback selectors
4. **Save** — write UTF-8-sig CSV files to `data/` (UTF-8-sig preserves Korean text in Excel)

### Key Functions in `kbo_crawler.py`

| Function | Role |
|---|---|
| `extract_form_fields(soup)` | Extracts all hidden form inputs (VIEWSTATE, EVENTVALIDATION, etc.) from `<form id="mainForm">` |
| `parse_postback_target(href)` | Parses target from `javascript:__doPostBack('target','arg')` href |
| `get_pager_info(soup)` | Detects pagination buttons and their PostBack targets |
| `parse_table(soup)` | Extracts headers and rows with multiple fallback selectors |
| `crawl_record(name, path)` | Crawls all pages for a single target URL; returns `(headers, rows)` |
| `save_csv(name, headers, rows)` | Saves collected data as CSV under `data/` |

### Adding New Crawl Targets

New record categories are added by extending the `TARGETS` dict in `kbo_crawler.py`:

```python
TARGETS = {
    # Currently implemented — player records
    "타자_기본기록": "/Record/Player/HitterBasic/Basic1.aspx",
    ...
    # Future additions — team records, standings, schedules, etc.
    "팀_기본기록": "/Record/Team/...",
}
```

The core `crawl_record(name, path)` function is generic and works for any KBO page that follows the same ASP.NET PostBack pattern. If a new section uses a structurally different page (e.g., no pagination, different table markup, or a non-WebForms layout), a separate crawler function may be needed.

## Critical ASP.NET PostBack Notes

Full details are in `KBO_CRAWLING_TIPS.md`. The most important points:

**`__EVENTTARGET` must be set AFTER merging hidden fields.** The hidden form contains `__EVENTTARGET=""` — if you merge it after setting your target, it overwrites your value and the server always returns page 1.

```python
# Wrong — hidden dict overwrites __EVENTTARGET
post_data = {"__EVENTTARGET": next_target, **hidden}

# Correct — set after merging
hidden["__EVENTTARGET"] = next_target
post_data = hidden
```

**Pagination links are in `href`, not `onclick`.** BeautifulSoup's `onclick=True` selector misses them — filter on `href` containing `__doPostBack` and `ucPager`.

**Reuse `requests.Session()`** across all requests within a single crawl target to maintain ASP.NET session cookies.

**Request delays:** 0.5s between pages, 1s between different record categories.
