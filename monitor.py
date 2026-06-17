import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PRODUCT_URL = "https://jdsports.pl/meskie/buty/sneakersy/adidas-handball-spezial-szary-id8780"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK")
STATE_FILE = Path("state.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}


def send_discord(message: str) -> None:
    if not WEBHOOK_URL:
        raise RuntimeError("Brakuje sekretu DISCORD_WEBHOOK w GitHub Actions.")

    response = requests.post(WEBHOOK_URL, json={"content": message}, timeout=20)
    response.raise_for_status()


def load_previous_sizes() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("available_sizes", []))
    except Exception:
        return set()


def save_current_sizes(sizes: set[str]) -> None:
    STATE_FILE.write_text(
        json.dumps({"available_sizes": sorted(sizes)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_json_objects(text: str):
    """Finds embedded JSON-like blocks that may contain product availability data."""
    # This helps with many ecommerce pages that embed product data in scripts.
    for match in re.finditer(r"\{[^{}]*(?:availability|stock|sizes|variant|sku)[\s\S]*?\}", text, re.I):
        yield match.group(0)


def check_available_sizes() -> set[str]:
    response = requests.get(PRODUCT_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    available_sizes: set[str] = set()

    # Method 1: look for size buttons/options in HTML.
    size_pattern = re.compile(r"^(3[5-9]|4[0-9]|5[0-2])(?:\s?2/3|\s?1/3)?$|^\d{2}(?:\.5)?$|^\d{2}\s?⅔$|^\d{2}\s?⅓$")

    for el in soup.find_all(["button", "option", "li", "span", "div"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text or len(text) > 12:
            continue

        attrs = " ".join(
            str(el.get(attr, "")) for attr in ["class", "aria-label", "data-size", "data-stock", "disabled"]
        ).lower()

        is_size = bool(size_pattern.match(text)) or text.startswith("EU ")
        looks_disabled = any(word in attrs for word in ["disabled", "unavailable", "sold", "out-of-stock", "brak"])

        if is_size and not looks_disabled:
            clean = text.replace("EU", "").strip()
            available_sizes.add(clean)

    # Method 2: fallback search for JSON/inline data with inStock-like fields.
    for script in soup.find_all("script"):
        script_text = script.string or script.get_text(" ", strip=True)
        if not script_text:
            continue

        # Simple heuristic: catch fragments around sizes and stock flags.
        for size in re.findall(r'"(?:size|label|name)"\s*:\s*"?(EU\s*)?([3-5][0-9](?:\s?1/3|\s?2/3|\.5)?)"?', script_text, flags=re.I):
            candidate = size[1].strip()
            idx = script_text.find(candidate)
            window = script_text[max(0, idx - 250): idx + 400].lower()
            if any(x in window for x in ["instock", "in_stock", '"stock":true', '"available":true', "available"]):
                if not any(x in window for x in ["outofstock", "out_of_stock", '"stock":false', '"available":false']):
                    available_sizes.add(candidate)

    return available_sizes


def main() -> int:
    previous = load_previous_sizes()
    current = check_available_sizes()

    print(f"Poprzednio dostępne: {sorted(previous)}")
    print(f"Aktualnie dostępne: {sorted(current)}")

    new_sizes = current - previous

    if new_sizes:
        message = (
            "🔥 **JD Sports: pojawił się dostępny rozmiar!**\n"
            "👟 Adidas Handball Spezial szary ID8780\n"
            f"📏 Nowe rozmiary: **{', '.join(sorted(new_sizes))}**\n"
            f"🔗 {PRODUCT_URL}"
        )
        send_discord(message)
        print("Wysłano powiadomienie na Discord.")
    else:
        print("Brak nowych rozmiarów — bez powiadomienia.")

    save_current_sizes(current)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        raise
