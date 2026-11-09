from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


START_URL = "https://books.toscrape.com/"
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
MAX_RETRY_DELAY = 30.0
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
FIELDS = [
    "title",
    "price_gbp",
    "availability",
    "rating",
    "product_url",
    "scraped_at",
]

BookRecord = dict[str, str | int | float]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_books(html: str, page_url: str) -> list[BookRecord]:
    """Extract book details from one Books to Scrape catalogue page."""
    soup = BeautifulSoup(html, "html.parser")
    scraped_at = datetime.now(timezone.utc).isoformat()
    books: list[BookRecord] = []

    for product in soup.select("article.product_pod"):
        title_link = product.select_one("h3 a")
        price_element = product.select_one(".price_color")
        availability_element = product.select_one(".availability")
        rating_element = product.select_one(".star-rating")

        if (
            title_link is None
            or price_element is None
            or availability_element is None
            or rating_element is None
        ):
            raise ValueError(f"A book is missing a required field on {page_url}")

        title = title_link.get("title") or title_link.get_text(strip=True)
        href = title_link.get("href")
        if not title or not isinstance(href, str):
            raise ValueError(f"A book has no title or product link on {page_url}")

        price_text = price_element.get_text(strip=True).replace("£", "").strip()
        try:
            price_gbp = float(price_text)
        except ValueError as exc:
            raise ValueError(
                f"Could not read the book price {price_text!r} on {page_url}"
            ) from exc

        rating_classes = rating_element.get("class", [])
        rating_name = next(
            (name for name in rating_classes if name in RATINGS), None
        )
        if rating_name is None:
            raise ValueError(f"A book has an unknown rating on {page_url}")

        books.append(
            {
                "title": title,
                "price_gbp": price_gbp,
                "availability": availability_element.get_text(" ", strip=True),
                "rating": RATINGS[rating_name],
                "product_url": urljoin(page_url, href),
                "scraped_at": scraped_at,
            }
        )

    return books


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), MAX_RETRY_DELAY)
            except ValueError:
                logger.warning("Ignoring invalid Retry-After value: %r", retry_after)

    return min(2**attempt, MAX_RETRY_DELAY)


def get_page(session: requests.Session, page_url: str) -> requests.Response:
    """Fetch a page, retrying temporary network errors and server responses."""
    for attempt in range(MAX_RETRIES + 1):
        response: requests.Response | None = None
        try:
            response = session.get(page_url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
        else:
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if isinstance(content_type, str) and "charset=" not in content_type.lower():
                    detected_encoding = response.apparent_encoding
                    if isinstance(detected_encoding, str) and detected_encoding:
                        response.encoding = detected_encoding
                return response
            if attempt == MAX_RETRIES:
                response.raise_for_status()

        delay = _retry_delay(response, attempt)
        logger.warning(
            "Temporary problem fetching %s; retrying in %.1f seconds (%d/%d)",
            page_url,
            delay,
            attempt + 1,
            MAX_RETRIES,
        )
        time.sleep(delay)

    raise RuntimeError(f"Unable to fetch {page_url} after {MAX_RETRIES} retries")


def scrape_books(pages: int, delay_seconds: float) -> list[BookRecord]:
    """Scrape up to the requested number of catalogue pages."""
    if pages < 1:
        raise ValueError("pages must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    records: list[BookRecord] = []
    page_url = START_URL

    with requests.Session() as session:
        session.headers.update(
            {"User-Agent": "DataEngineeringInternshipPractice/1.0"}
        )
        for page_number in range(pages):
            response = get_page(session, page_url)
            soup = BeautifulSoup(response.text, "html.parser")
            page_records = parse_books(response.text, page_url)
            records.extend(page_records)
            logger.info(
                "Read page %d and found %d books (total: %d)",
                page_number + 1,
                len(page_records),
                len(records),
            )

            next_link = soup.select_one("li.next a")
            if next_link is None or page_number == pages - 1:
                break

            next_href = next_link.get("href")
            if not isinstance(next_href, str):
                raise ValueError(f"The next-page link is invalid on {page_url}")

            page_url = urljoin(page_url, next_href)
            time.sleep(delay_seconds)

    return records


def write_csv(records: list[BookRecord], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)


def write_json(records: list[BookRecord], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as json_file:
        json.dump(records, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect paginated book listings from Books to Scrape."
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="maximum number of catalogue pages to read (20 books per page)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="seconds to wait between pages (default: 1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/books.csv"),
        help="CSV output path; a JSON file with the same base name is also written",
    )
    parser.add_argument(
        "--min-records",
        type=int,
        default=100,
        help="fail rather than save a smaller dataset (default: 100)",
    )
    args = parser.parse_args()

    if args.min_records < 0:
        parser.error("--min-records cannot be negative")

    try:
        records = scrape_books(args.pages, args.delay)
        if len(records) < args.min_records:
            raise ValueError(
                f"Only {len(records)} books were collected; "
                f"at least {args.min_records} are required. "
                "Try increasing --pages."
            )

        json_output = args.output.with_suffix(".json")
        write_csv(records, args.output)
        write_json(records, json_output)
    except (OSError, requests.RequestException, ValueError) as exc:
        parser.error(str(exc))

    logger.info(
        "Saved %d books to %s and %s",
        len(records),
        args.output,
        json_output,
    )


if __name__ == "__main__":
    main()
