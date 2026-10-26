"""Desktop/phone browser regression using a disposable, explicitly simulated model backend."""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    screenshots = root / "reports/browser"
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="atlas-browser-") as temporary:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update(
            ATLAS_DATA_DIR=temporary,
            ATLAS_DATABASE_URL=f"sqlite:///{temporary}/atlas.db",
            ATLAS_AUTH_MODE="local",
            ATLAS_MODEL_LOADING="false",
            ATLAS_WORKER_ENABLED="true",
        )
        address = f"http://127.0.0.1:{port}"
        with (Path(temporary) / "server.log").open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "scripts.fixture_server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(100):
                    try:
                        if httpx.get(address + "/ready", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError((Path(temporary) / "server.log").read_text())
                    time.sleep(0.1)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(address)
                    page.get_by_role("button", name="New collection", exact=True).click()
                    page.get_by_label("Name", exact=True).fill("Browser policies")
                    page.get_by_label("Description", exact=True).fill(
                        "Disposable browser regression"
                    )
                    page.get_by_role("button", name="Create collection", exact=True).click()
                    expect(page.get_by_role("dialog")).not_to_be_visible()
                    page.get_by_role(
                        "button", name="Add knowledge sources", exact=True
                    ).first.click()
                    page.get_by_label("Choose documents").set_input_files(
                        {
                            "name": "refund-policy.md",
                            "mimeType": "text/markdown",
                            "buffer": b"# Refund policy\nRefund requests require review within fourteen days. <script>window.atlasXss=true</script>",
                        }
                    )
                    expect(page.get_by_role("dialog")).not_to_be_visible(timeout=10000)
                    for _ in range(100):
                        if httpx.get(address + "/api/documents").json()[0]["status"] == "ready":
                            break
                        time.sleep(0.1)
                    page.get_by_role("textbox", name="Ask your knowledge").fill(
                        "What is the refund window?"
                    )
                    page.get_by_role("button", name="Send question").click()
                    expect(
                        page.get_by_text("The refund window is fourteen days", exact=False)
                    ).to_be_visible(timeout=15000)
                    page.get_by_role("button", name="Open source 1", exact=True).click()
                    expect(page.locator("#source-1")).to_be_visible()
                    page.get_by_role("button", name="Mark answer helpful").click()
                    page.get_by_role("button", name="Inspect run").click()
                    expect(page.get_by_role("dialog", name="Inside this answer")).to_be_visible()
                    page.get_by_role("button", name="Close dialog").click()
                    page.get_by_role("button", name="Open document", exact=True).click()
                    expect(page.get_by_role("dialog")).to_contain_text(
                        "<script>window.atlasXss=true</script>"
                    )
                    assert page.evaluate("window.atlasXss !== true")
                    page.get_by_role("button", name="Close dialog").click()
                    page.screenshot(path=str(screenshots / "desktop.png"), full_page=True)
                    phone = browser.new_page(
                        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
                    )
                    phone.on("pageerror", lambda error: errors.append(str(error)))
                    phone.goto(address)
                    expect(phone.get_by_role("textbox", name="Ask your knowledge")).to_be_visible()
                    assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    phone.get_by_role("button", name="Open navigation").click()
                    phone.locator("nav").get_by_role("button", name="Knowledge").click()
                    expect(phone.get_by_role("heading", name="Knowledge library.")).to_be_visible()
                    assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    phone.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
                    assert not errors, errors
                    browser.close()
                print(
                    "PASS: real browser upload/index/chat/citations/feedback/trace/preview, escaped document text, mobile navigation and layout. Neural components were simulated."
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
