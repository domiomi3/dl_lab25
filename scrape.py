#!/usr/bin/env python3
import argparse, asyncio, csv, os, re, time, unicodedata
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

from tqdm import tqdm
import requests
from bs4 import BeautifulSoup
from slugify import slugify
from playwright.async_api import async_playwright

# ───────── constants ─────────
BASE     = "https://mensa.fachschaft.tf/"
DAY_URL  = BASE + "?date={}"                # YYYY-MM-DD
# ─────────────────────────────


def squash(text: str) -> str:
    """ASCII-fold and collapse whitespace."""
    return re.sub(
        r"\s+", " ",
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    ).strip()


def daterange(start: date, stop: date):
    step = timedelta(days=1) * (1 if start <= stop else -1)
    d = start
    while True:
        yield d
        if d == stop:
            break
        d += step


# ───────── scraper ─────────
async def scrape(start: date, stop: date, out_dir: Path):
    rows = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        for day in tqdm(daterange(start, stop), desc="Scraping"):
            url = DAY_URL.format(day.isoformat())
            try:
                await page.goto(url, wait_until="networkidle", timeout=40_000)
            except Exception:
                continue
            await page.wait_for_timeout(800)

            soup = BeautifulSoup(await page.content(), "html.parser")

            for h2 in soup.find_all("h2", string=re.compile(r"\bMensa\b", re.I)):
                mensa = squash(h2.get_text()).replace(",", " ").replace(";", " ")
                container = h2.find_next("div")
                if not container:
                    continue

                for card in container.find_all("a", href=True):
                    # 1 — description
                    p_tag = card.select_one("div.text-sm > p")
                    if not p_tag:
                        continue
                    lines = [
                        ln.strip() for ln in p_tag.stripped_strings
                        if not re.match(r"^(beilagensalat|regio[- ]?apfel)", ln, re.I)
                    ]
                    if not lines:
                        continue
                    description = " ".join(lines).replace("-------------", " ")
                    description = description.replace(",", " ").replace(";", " ")
                    description = squash(description)

                    # 2 — diet badge
                    diet = next(
                        (t.get_text(" ", strip=True)
                         for t in card.select("div.inline-flex")
                         if t.get_text(strip=True)),
                        "Nicht-vegetarisch"
                    ).replace(",", " ").replace(";", " ")

                    # 3 — type label
                    dish_type = (
                        card.find("span").get_text(" ", strip=True)
                        if card.find("span") else "meal"
                    ).replace(",", " ").replace(";", " ")

                    # 4 — image URL
                    img_url = None
                    img_tag = card.find("img")
                    if img_tag:
                        img_url = (
                            img_tag.get("src")
                            or img_tag.get("data-src")
                            or (img_tag.get("srcset", "").split(",")[0].split()[0]
                                if img_tag.get("srcset") else None)
                        )
                    if not img_url:
                        bg = card.select_one("div[style*=background-image]")
                        if bg and "background-image" in bg["style"]:
                            m = re.search(r'url\(["\']?(.*?)["\']?\)', bg["style"])
                            if m:
                                img_url = m.group(1)
                    if not img_url:
                        continue
                    img_url = urljoin(BASE, img_url)

                    # 5 — download (once)
                    day_dir = out_dir / day.isoformat()
                    day_dir.mkdir(parents=True, exist_ok=True)
                    ext   = Path(urlparse(img_url).path).suffix or ".jpg"
                    fname = f"{slugify(mensa)}_{slugify(dish_type)}{ext}"
                    fpath = day_dir / fname
                    try:
                        if not fpath.exists():
                            r = requests.get(img_url, timeout=20); r.raise_for_status()
                            fpath.write_bytes(r.content)
                    except Exception:
                        continue

                    # 6 — append row
                    rows.append([
                        description,
                        "no",          # Beilagensalat
                        "no",          # Regio Apfel
                        dish_type,
                        diet,
                        mensa,
                        str(fpath),
                    ])

        await browser.close()
    return rows


# ───────── CSV writer ─────────
def save_csv(rows, csv_path):
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(
            fh, delimiter=",", quoting=csv.QUOTE_NONE, escapechar="\\"
        )
        writer.writerow([
            "description", "Beilagensalat", "Regio Apfel",
            "type", "diet", "mensa", "image_path"
        ])
        writer.writerows(rows)
    print(f"{len(rows)} meal rows written → {csv_path}")


# ───────── disk-usage helper ─────────
def folder_size(path: Path) -> int:
    """Return total bytes under *path*."""
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            total += (Path(root) / f).stat().st_size
    return total


def human(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


# ───────── main ─────────
if __name__ == "__main__":
    cli = argparse.ArgumentParser(
        description="Scrape mensa.fachschaft.tf for a date range "
                    "or the last N days (default 10)."
    )
    cli.add_argument("-o", "--out_dir",  default="images",    help="image folder")
    cli.add_argument("-c", "--csv_name", default="meals_raw", help="CSV filename prefix")
    cli.add_argument("-d", "--days_back", type=int, default=10,
                     help="days back from today (ignored if --start is used)")
    cli.add_argument("--start", type=str, help="start date YYYY-MM-DD")
    cli.add_argument("--stop",  type=str, help="stop  date YYYY-MM-DD")
    args = cli.parse_args()

    # decide span
    if args.start or args.stop:
        if not (args.start and args.stop):
            cli.error("Specify BOTH --start and --stop.")
        try:
            start = date.fromisoformat(args.start)
            stop  = date.fromisoformat(args.stop)
        except ValueError as e:
            cli.error(f"Bad date: {e}")
    else:
        start = date.today()
        stop  = start - timedelta(days=args.days_back - 1)

    t0 = time.perf_counter()

    out_path = Path(args.out_dir)
    rows = asyncio.run(scrape(start, stop, out_path))
    csv_file = f"{args.csv_name}_{start}_{stop}.csv"
    save_csv(rows, csv_file)

    # disk usage
    size_bytes = folder_size(out_path)
    print(f"📦 images saved under {out_path}/ take {human(size_bytes)}")

    print(f"⌛ finished in {time.perf_counter() - t0:,.1f}s")
