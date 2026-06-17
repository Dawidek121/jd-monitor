import os
import re
import requests
from playwright.sync_api import sync_playwright

PRODUCT_URL = "https://jdsports.pl/meskie/buty/sneakersy/adidas-handball-spezial-szary-id8780"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")

def send_discord(message: str):
    if not WEBHOOK_URL:
        raise RuntimeError("Brakuje sekretu DISCORD_WEBHOOK w GitHub Actions.")
    r = requests.post(WEBHOOK_URL, json={"content": message}, timeout=20)
    r.raise_for_status()

def get_sizes():
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
        page.wait_for_timeout(6000)

        text = page.locator("body").inner_text()
        browser.close()

    found = set()

    # Szuka rozmiarów EU typu 40, 40 2/3, 41 1/3 itd.
    for m in re.findall(r"\b(3[6-9]|4[0-9]|5[0-2])(?:\s?(?:1/3|2/3))?\b", text):
        found.add(m.strip())

    # Dodatkowo sprawdzamy tekst przy przyciskach/elementach z rozmiarami
    sizes = []
    for line in text.splitlines():
        line = line.strip()
        if re.fullmatch(r"(3[6-9]|4[0-9]|5[0-2])(?:\s?(?:1/3|2/3))?", line):
            sizes.append(line)

    found.update(sizes)
    return sorted(found, key=lambda s: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)])

def main():
    sizes = get_sizes()

    if sizes:
        send_discord(
            "🔥 **JD Sports — możliwe dostępne rozmiary!**\n"
            f"Rozmiary wykryte na stronie: **{', '.join(sizes)}**\n"
            f"{PRODUCT_URL}"
        )
        print("Wysłano alert:", sizes)
    else:
        print("Brak wykrytych rozmiarów.")

if __name__ == "__main__":
    main()
