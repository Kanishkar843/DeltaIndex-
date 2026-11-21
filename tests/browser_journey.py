"""Real React journey using only a test-owned server and temporary database."""

import json, os, secrets, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root = Path(__file__).resolve().parents[1]
assets = root / "docs/assets"
assets.mkdir(exist_ok=True)
with (
    tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp,
    socket.socket() as sock,
):
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    token = secrets.token_urlsafe(32)
    env = {
        **os.environ,
        "ADMIN_TOKEN": token,
        "DATABASE_URL": "sqlite:///" + str(Path(tmp) / "browser.db"),
        "EMBEDDING_MODE": "fixture",
    }
    env.pop("REDIS_URL", None)
    with (root / ".cache/browser-server.log").open("w") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
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
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path=os.getenv(
                        "CHROME_PATH",
                        "C:/Program Files/Google/Chrome/Application/chrome.exe",
                    ),
                    headless=True,
                )
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                base = f"http://127.0.0.1:{port}"
                for _ in range(90):
                    try:
                        if page.request.get(base + "/ready").ok:
                            break
                    except Exception:
                        pass
                    if proc.poll() is not None:
                        raise AssertionError("Test API exited")
                    time.sleep(0.5)
                page.goto(base, wait_until="networkidle")
                page.locator("#seed").click()
                expect(page.get_by_role("alert")).to_contain_text("Invalid admin token")
                page.locator("#token").fill(token)
                page.get_by_role("button", name="Connect controls").click()
                expect(page.locator("#status")).to_contain_text("Connected")
                page.locator("#seed").click()
                expect(page.locator("#status")).to_contain_text(
                    '"created":120', timeout=30000
                )
                expect(page.locator("#results article")).to_have_count(12)
                page.locator("#seed").click()
                expect(page.locator("#status")).to_contain_text(
                    '"unchanged":120', timeout=30000
                )
                page.get_by_role("button", name="Explain score").first.click()
                expect(page.get_by_role("dialog")).to_contain_text("Lexical rank")
                page.get_by_role("button", name="Useful match", exact=True).click()
                expect(page.locator("#status")).to_contain_text("Feedback saved")
                page.get_by_role("button", name="Save search", exact=True).click()
                expect(page.locator("#status")).to_contain_text("Search saved")
                page.get_by_role("button", name="Save profile", exact=True).click()
                expect(page.locator("#status")).to_contain_text("Profile saved")
                page.locator("#compare").click()
                expect(page.locator(".comparison article")).to_have_count(3)
                page.locator("#query").fill("no-such-words")
                page.get_by_label("Retrieval mode").select_option("keyword")
                page.get_by_role("button", name="Search →", exact=True).click()
                expect(page.locator("main")).to_contain_text("No matches")
                page.locator("#query").fill("python engineer")
                page.get_by_label("Retrieval mode").select_option("hybrid")
                page.get_by_role("button", name="Search →", exact=True).click()
                expect(page.locator("#results article")).to_have_count(12)
                page.locator("#token").fill("")
                page.screenshot(path=str(assets / "desktop.png"), full_page=True)
                page.get_by_role("button", name="Change theme").click()
                page.screenshot(path=str(assets / "light.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=str(assets / "mobile.png"), full_page=True)
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                )
                assert not errors, errors
                browser.close()
                (root / "docs/browser-report.json").write_text(
                    json.dumps(
                        {
                            "status": "PASSED",
                            "frontend": "React TypeScript",
                            "backend": "SQLite fixture mode, not PostgreSQL integration",
                            "checks": [
                                "authorization rejection",
                                "ingest 120",
                                "idempotent reingest",
                                "retrieval",
                                "score evidence",
                                "feedback",
                                "saved searches",
                                "profiles",
                                "three-mode comparison",
                                "empty results",
                                "dark/light/mobile",
                            ],
                            "page_errors": errors,
                        },
                        indent=2,
                    )
                )
                print("DeltaIndex React browser journey PASSED")
        finally:
            proc.terminate()
            proc.wait(timeout=15)
