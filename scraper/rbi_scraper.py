"""
RBI circular scraper.

Fetches the circular index from rbi.org.in, parses listing rows,
and downloads PDFs to a local directory. Produces RawCircularMetadata
for each circular found.
"""

import re
import time
from datetime import date, datetime
from pathlib import Path

import requests
import structlog
from bs4 import BeautifulSoup

from models.chunk import RawCircularMetadata

logger = structlog.get_logger(__name__)

RBI_INDEX_URL = (
    "https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx"
)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.rbi.org.in/",
}
REQUEST_TIMEOUT = 30
RETRY_LIMIT = 3
RETRY_BACKOFF = 2  # seconds


def _get_with_retry(url: str, session: requests.Session) -> requests.Response:
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning(
                "request_failed",
                url=url,
                attempt=attempt,
                error=str(exc),
            )
            if attempt < RETRY_LIMIT:
                time.sleep(RETRY_BACKOFF * attempt)
    raise RuntimeError(f"Failed to fetch {url} after {RETRY_LIMIT} attempts")


def _parse_date(raw: str) -> date | None:
    """Try multiple RBI date formats. Return None if unparseable."""
    raw = raw.strip()
    for fmt in ("%B %d, %Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    logger.warning("unparseable_date", raw=raw)
    return None


def _normalize_circular_id(raw: str) -> str | None:
    """
    RBI circular IDs appear in several forms:
      RBI/2024-25/67
      RBI/DPSS/2023-24/123
    Normalize to 'RBI/...' — return None if pattern not found.
    """
    match = re.search(r"RBI[/\w\-]+\d+", raw)
    return match.group(0) if match else None


def _fetch_pdf_url(detail_url: str, session: requests.Session) -> str | None:
    """
    Visit a circular detail page and return the direct PDF download URL.

    RBI detail pages (BS_CircularIndexDisplay.aspx?Id=N) contain a link to
    rbidocs.rbi.org.in/rdocs/.../*.PDF — that is the canonical PDF URL.
    Returns None if no PDF link is found.
    """
    try:
        resp = _get_with_retry(detail_url, session)
    except RuntimeError as exc:
        logger.warning("detail_page_fetch_failed", url=detail_url, error=str(exc))
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "rbidocs.rbi.org.in" in href and href.upper().endswith(".PDF"):
            return href
    logger.warning("pdf_link_not_found_on_detail_page", url=detail_url)
    return None


def _fetch_index_page(
    session: requests.Session,
    year: int | None = None,
) -> BeautifulSoup:
    """
    Fetch the RBI circular index page for a given calendar year.

    The RBI site is ASP.NET WebForms. The default GET returns the current
    fiscal year. To fetch a different year, we must:
      1. GET the page to harvest __VIEWSTATE / __EVENTVALIDATION tokens
      2. POST back with hdnYear=<year>&hdnMonth=0 (all months)

    year=None returns the current year via simple GET (faster).
    """
    resp = _get_with_retry(RBI_INDEX_URL, session)
    if year is None:
        return BeautifulSoup(resp.text, "lxml")

    # Extract ASP.NET postback tokens
    init_soup = BeautifulSoup(resp.text, "lxml")
    viewstate = (init_soup.find("input", {"name": "__VIEWSTATE"}) or {}).get("value", "")
    vsgen = (init_soup.find("input", {"name": "__VIEWSTATEGENERATOR"}) or {}).get("value", "")
    evval = (init_soup.find("input", {"name": "__EVENTVALIDATION"}) or {}).get("value", "")

    post_data = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": viewstate,
        "__VIEWSTATEGENERATOR": vsgen,
        "__EVENTVALIDATION": evval,
        "hdnYear": str(year),
        "hdnMonth": "0",  # 0 = all months
        "btn": "click",
    }
    post_headers = {**REQUEST_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            post_resp = session.post(
                RBI_INDEX_URL,
                data=post_data,
                headers=post_headers,
                timeout=REQUEST_TIMEOUT,
            )
            post_resp.raise_for_status()
            return BeautifulSoup(post_resp.text, "lxml")
        except requests.RequestException as exc:
            logger.warning("postback_failed", year=year, attempt=attempt, error=str(exc))
            if attempt < RETRY_LIMIT:
                time.sleep(RETRY_BACKOFF * attempt)
    raise RuntimeError(f"Failed to fetch index for year {year} after {RETRY_LIMIT} attempts")


def scrape_index(year_filter: int | None = None) -> list[RawCircularMetadata]:
    """
    Fetch and parse the RBI circular index page.

    Index rows have 5 columns:
      [0] circular_id + short title (link text)
      [1] date (DD.M.YYYY)
      [2] department
      [3] subject / full title
      [4] addressees

    The link in column 0 leads to a detail page, not a PDF.
    We follow each detail page to retrieve the actual PDF URL.

    Args:
        year_filter: if provided, POST back to the RBI site to fetch circulars
                     from that calendar year (e.g. 2024 fetches 2024 circulars).
                     None fetches the current fiscal year via simple GET.

    Returns:
        List of RawCircularMetadata — one per parseable circular row.
    """
    scrape_time = datetime.utcnow()
    session = requests.Session()

    logger.info("scraping_index", url=RBI_INDEX_URL, year_filter=year_filter)
    soup = _fetch_index_page(session, year=year_filter)

    rows = soup.select("table tr")
    logger.info("rows_found", count=len(rows))

    results: list[RawCircularMetadata] = []
    skipped = 0

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        link_tag = row.find("a", href=True)
        if not link_tag:
            skipped += 1
            continue

        href = link_tag["href"]

        # Resolve the detail page URL
        if href.startswith("http"):
            detail_url = href
        elif href.startswith("/"):
            detail_url = f"https://www.rbi.org.in{href}"
        else:
            detail_url = f"https://www.rbi.org.in/Scripts/{href}"

        # Cell 0 contains the circular_id prefix + short label
        raw_id_text = cells[0].get_text(strip=True)
        circular_id = _normalize_circular_id(raw_id_text)
        if not circular_id:
            logger.warning(
                "circular_id_not_found",
                row_text=raw_id_text[:120],
            )
            skipped += 1
            continue

        # Cell 1 is the date in DD.M.YYYY format
        effective_date = _parse_date(cells[1].get_text(strip=True))
        if effective_date is None:
            logger.warning(
                "effective_date_not_found",
                circular_id=circular_id,
            )
            skipped += 1
            continue

        # Cell 3 is the full subject / title
        circular_title = cells[3].get_text(strip=True) or raw_id_text

        # Follow the detail page to get the actual PDF URL
        pdf_url = _fetch_pdf_url(detail_url, session)
        if not pdf_url:
            logger.warning(
                "pdf_url_not_found",
                circular_id=circular_id,
                detail_url=detail_url,
            )
            skipped += 1
            continue

        results.append(
            RawCircularMetadata(
                circular_id=circular_id,
                circular_title=circular_title,
                effective_date=effective_date,
                pdf_url=pdf_url,
                scraped_at=scrape_time,
            )
        )
        time.sleep(0.5)  # polite delay between detail page requests

    logger.info(
        "index_scrape_complete",
        parsed=len(results),
        skipped=skipped,
    )
    return results


def download_pdf(
    metadata: RawCircularMetadata,
    dest_dir: Path,
    session: requests.Session | None = None,
) -> Path:
    """
    Download a single circular PDF to dest_dir.

    File is named by circular_id with slashes replaced by underscores.
    Returns the local path. Raises RuntimeError on download failure.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = metadata.circular_id.replace("/", "_") + ".pdf"
    dest_path = dest_dir / safe_name

    if dest_path.exists():
        logger.info("pdf_already_exists", path=str(dest_path))
        return dest_path

    _session = session or requests.Session()
    logger.info("downloading_pdf", circular_id=metadata.circular_id, url=metadata.pdf_url)

    resp = _get_with_retry(metadata.pdf_url, _session)
    dest_path.write_bytes(resp.content)

    logger.info(
        "pdf_downloaded",
        circular_id=metadata.circular_id,
        size_kb=len(resp.content) // 1024,
        path=str(dest_path),
    )
    return dest_path


def download_all(
    circulars: list[RawCircularMetadata],
    dest_dir: Path,
    delay: float = 1.0,
) -> dict[str, Path]:
    """
    Download all PDFs with a polite delay between requests.

    Returns mapping of circular_id → local path.
    Failed downloads are logged and excluded from the result.
    """
    session = requests.Session()
    results: dict[str, Path] = {}

    for meta in circulars:
        try:
            path = download_pdf(meta, dest_dir, session)
            results[meta.circular_id] = path
        except RuntimeError as exc:
            logger.error(
                "pdf_download_failed",
                circular_id=meta.circular_id,
                error=str(exc),
            )
        time.sleep(delay)

    logger.info(
        "bulk_download_complete",
        downloaded=len(results),
        failed=len(circulars) - len(results),
    )
    return results
