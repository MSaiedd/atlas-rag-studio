"""Capture the actual locally running workspace after a real-model walkthrough."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    report = json.loads(Path("reports/live-api-smoke.json").read_text())
    selected = next(
        case for case in report["cases"] if case["state"] == "complete" and case["citations"]
    )
    directory = Path("docs/screenshots")
    directory.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1050}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.locator(".conversation-link > button:first-child").filter(
            has_text=selected["question"][:100]
        ).click()
        expect(page.locator(".answer-prose").first).to_be_visible()
        page.get_by_role("button", name="Open source 1", exact=True).first.click()
        page.screenshot(path=str(directory / "chat.png"))
        for name, filename in [
            ("Knowledge", "knowledge.png"),
            ("Evaluations", "evaluations.png"),
            ("Fine-tuning", "tuning.png"),
        ]:
            page.locator("nav").get_by_role("button", name=name).click()
            page.screenshot(path=str(directory / filename))
        phone = browser.new_page(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        phone.goto(args.url)
        expect(phone.get_by_role("textbox", name="Ask your knowledge")).to_be_visible()
        assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth")
        phone.screenshot(path=str(directory / "mobile.png"))
        assert not errors, errors
        browser.close()
    print("Captured actual workspace, recorded evaluation/training and mobile screenshots.")


if __name__ == "__main__":
    main()
