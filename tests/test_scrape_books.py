import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from src.scrape_books import (
    FIELDS,
    get_page,
    parse_books,
    scrape_books,
    write_csv,
    write_json,
)


def book_page(title: str, href: str, next_page: str | None = None) -> str:
    next_link = (
        f'<li class="next"><a href="{next_page}">next</a></li>'
        if next_page
        else ""
    )
    return f"""
    <html><body>
      <article class="product_pod">
        <p class="star-rating Three"></p>
        <h3><a href="{href}" title="{title}">{title}</a></h3>
        <p class="price_color">£12.34</p>
        <p class="availability">In stock</p>
      </article>
      <ul class="pager">{next_link}</ul>
    </body></html>
    """


class ParseBooksTests(unittest.TestCase):
    def test_extracts_book_details_and_resolves_product_url(self) -> None:
        records = parse_books(
            book_page("A Sample Book", "sample-book_1/index.html"),
            "https://books.toscrape.com/catalogue/page-1.html",
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "A Sample Book")
        self.assertEqual(records[0]["price_gbp"], 12.34)
        self.assertEqual(records[0]["availability"], "In stock")
        self.assertEqual(records[0]["rating"], 3)
        self.assertEqual(
            records[0]["product_url"],
            "https://books.toscrape.com/catalogue/sample-book_1/index.html",
        )
        self.assertTrue(str(records[0]["scraped_at"]).endswith("+00:00"))

    def test_rejects_a_book_with_missing_required_data(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing a required field"):
            parse_books(
                '<article class="product_pod"><h3><a title="Incomplete"></a></h3></article>',
                "https://books.toscrape.com/",
            )


class ScrapeBooksTests(unittest.TestCase):
    @patch("src.scrape_books.time.sleep")
    @patch("src.scrape_books.requests.Session")
    def test_follows_pagination_and_waits_between_pages(
        self, session_factory: Mock, sleep: Mock
    ) -> None:
        session = Mock()
        session_factory.return_value.__enter__.return_value = session
        session.get.side_effect = [
            Mock(
                text=book_page(
                    "First book",
                    "catalogue/first/index.html",
                    next_page="catalogue/page-2.html",
                ),
                status_code=200,
            ),
            Mock(
                text=book_page("Second book", "catalogue/second/index.html"),
                status_code=200,
            ),
        ]

        records = scrape_books(pages=2, delay_seconds=0.25)

        self.assertEqual([record["title"] for record in records], ["First book", "Second book"])
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(
            session.get.call_args_list[1].args[0],
            "https://books.toscrape.com/catalogue/page-2.html",
        )
        sleep.assert_called_once_with(0.25)
        self.assertEqual(session.get.call_args.kwargs["timeout"], 20)
        self.assertIn("User-Agent", session.headers.update.call_args.args[0])

    def test_retries_a_temporary_connection_error(self) -> None:
        session = Mock()
        session.get.side_effect = [
            requests.ConnectionError("temporary network issue"),
            Mock(
                status_code=200,
                text="ok",
                headers={"Content-Type": "text/html"},
                apparent_encoding="utf-8",
            ),
        ]

        with patch("src.scrape_books.time.sleep") as sleep:
            response = get_page(session, "https://books.toscrape.com/")

        self.assertEqual(response.text, "ok")
        self.assertEqual(response.encoding, "utf-8")
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_retries_a_temporary_server_response(self) -> None:
        session = Mock()
        session.get.side_effect = [
            Mock(status_code=503, headers={"Retry-After": "0"}),
            Mock(status_code=200, text="ok"),
        ]

        with patch("src.scrape_books.time.sleep") as sleep:
            response = get_page(session, "https://books.toscrape.com/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(0.0)

    def test_rejects_invalid_page_and_delay_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "pages must be at least 1"):
            scrape_books(pages=0, delay_seconds=1)
        with self.assertRaisesRegex(ValueError, "delay_seconds cannot be negative"):
            scrape_books(pages=1, delay_seconds=-1)


class OutputTests(unittest.TestCase):
    def test_writes_csv_and_json_with_the_expected_fields(self) -> None:
        record = {
            "title": "A Sample Book",
            "price_gbp": 12.34,
            "availability": "In stock",
            "rating": 3,
            "product_url": "https://books.toscrape.com/catalogue/sample/index.html",
            "scraped_at": "2026-11-09T00:00:00+00:00",
        }

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "nested" / "books.csv"
            json_path = csv_path.with_suffix(".json")
            write_csv([record], csv_path)
            write_json([record], json_path)

            with csv_path.open(encoding="utf-8", newline="") as csv_file:
                csv_rows = list(csv.DictReader(csv_file))
            json_rows = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(list(csv_rows[0]), FIELDS)
        self.assertEqual(csv_rows[0]["title"], "A Sample Book")
        self.assertEqual(json_rows, [record])


if __name__ == "__main__":
    unittest.main()
