import json
import os
import re
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

PRODUCT_URL = "https://jdsports.pl/meskie/buty/sneakersy/adidas-handball-spezial-szary-id8780"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")

STATE_FILE = Path("state.json")

# Ten rozmiar jest teraz dostępny i ma być ignorowany
IGNORED_SIZES = {"46 2/3"}

# Rozmiary, których realnie szukamy dla tego modelu
VALID_SIZES = {
    "40", "40 2/3", "41 1/3", "42", "42 2/3",
    "43 1/3", "44", "44 2/3", "45 1/3", "46", "46 2/3"
}


def load_previous_sizes() -> set[str]:
    if not STATE_FILE.exists():
        return set()

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("available_sizes", []))
    except Exception:
        return set()


def save_current_sizes(sizes: set[str]) -> None:
    data = {
        "available_sizes": sorted(sizes),
        "ignored_sizes": sorted(IGNORED_SIZES),
        "product_url": PRODUCT_URL,
    }
    STATE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def send_discord(sizes: list[str]) -> None:
    if not WEBHOOK_URL:
        raise RuntimeError("Brakuje sekretu DISCORD_WEBHOOK w GitHub Actions.")

    message = (
        "🔥 **JD Sports — pojawił się nowy rozmiar!**\n"
        f"Nowe rozmiary: **{', '.join(sizes)}**\n"
        f"{PRODUCT_URL}"
    )

    response = requests.post(WEBHOOK_URL, json={"content": message}, timeout=20)
    response.raise_for_status()


def clean_size(text: str) -> str | None:
    text = " ".join(text.replace("\n", " ").split())
    text = text.replace("EU", "").strip()

    match = re.search(r"\b(40|40 2/3|41 1/3|42|42 2/3|43 1/3|44|44 2/3|45 1/3|46|46 2/3)\b", text)

    if not match:
        return None

    size = match.group(1).strip()
    if size in VALID_SIZES:
        return size

    return None


def check_available_sizes() -> set[str]:
    available = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="pl-PL",
        )

        page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)

        # Najpierw sprawdzamy przyciski, bo rozmiary zwykle są buttonami.
        buttons = page.locator("button").all()

        for button in buttons:
            try:
                text = button.inner_text(timeout=1000)
                size = clean_size(text)

                if not size:
                    continue

                disabled = button.is_disabled()
                aria_disabled = button.get_attribute("aria-disabled")
                class_name = button.get_attribute("class") or ""

                unavailable_words = [
                    "disabled",
                    "unavailable",
                    "sold",
                    "out",
                    "brak",
                    "niedost",
                ]

                looks_unavailable = (
                    disabled
                    or aria_disabled == "true"
                    or any(word in class_name.lower() for word in unavailable_words)
                )

                if not looks_unavailable:
                    available.add(size)

            except Exception:
                continue

        browser.close()

    # Ignorujemy rozmiar dostępny już teraz
    return available - IGNORED_SIZES


def sort_sizes(sizes: set[str]) -> list[str]:
    order = [
        "40", "40 2/3", "41 1/3", "42", "42 2/3",
        "43 1/3", "44", "44 2/3", "45 1/3", "46", "46 2/3"
    ]
    return [size for size in order if size in sizes]


def main() -> int:
    previous = load_previous_sizes()
    current = check_available_sizes()

    new_sizes = current - previous

    print("Poprzednie rozmiary:", sort_sizes(previous))
    print("Aktualne rozmiary:", sort_sizes(current))
    print("Nowe rozmiary:", sort_sizes(new_sizes))

    if new_sizes:
        send_discord(sort_sizes(new_sizes))

    save_current_sizes(current)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
