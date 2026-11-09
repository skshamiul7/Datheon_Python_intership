# Python for Data Engineering & Automation Internship

A four-week, hands-on project covering web scraping, data cleaning, database
loading, and scheduled ETL. The internship brief asks for at least two of the
four tasks; this repository is organized so we can build all four and submit
the strongest three.

## Plan

| Week | Focus | Deliverable |
|---|---|---|
| 1 | Setup and web scraping | At least 100 books exported to CSV |
| 2 | Data cleaning with Pandas | Cleaned dataset and validation report |
| 3 | Database ingestion | SQLite schema, idempotent upsert, verification |
| 4 | Scheduled ETL | End-to-end run, logs, alert summary, README and audit |

We'll use Books to Scrape, a website built for scraping practice. Keep requests
polite, use timeouts, and only scrape sites where you have permission.

## Setup (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run the commands below in Command Prompt
instead:

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

## Task 1: Autonomous Web Scraper & Data Extractor

This task uses [Books to Scrape](https://books.toscrape.com/), a practice
catalogue intended for scraping exercises. The scraper follows the site's
pagination and collects the book title, price in GBP, availability, star
rating, product URL, and UTC scrape time. It saves both CSV and JSON files.

Run the scraper from the repository root:

```powershell
python src\scrape_books.py
```

By default, it reads up to five pages (20 listings per page), waits one second
between pages, and writes `data\raw\books.csv` and `data\raw\books.json`. The
run fails with a clear error if it collects fewer than 100 records, so a short
or incomplete scrape is not mistaken for a finished deliverable. Requests use
a timeout and retry temporary network errors and rate-limit/server responses.
You can change the page count, delay, output path, or record minimum:

```powershell
python src\scrape_books.py --pages 5 --delay 1 --output data\raw\books.csv --min-records 100
```

Install the requirements if you have not already, then run the offline tests:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The Task 1 CSV and JSON files are kept in Git as part of the deliverable.
Other generated data and logs remain ignored. Run the scraper yourself before
submitting to refresh the dataset and verify the record count.

Please only scrape websites that permit it. This project intentionally uses a
practice site; keep the delay in place and do not use it to bypass access
controls or collect private data.

## Repository structure

```text
data/
  raw/
  processed/
logs/
src/
tests/
```

The Task 1 raw CSV and JSON files are included in Git; other generated datasets
and logs are ignored. Do not commit credentials, virtual environments, or other
private data.
