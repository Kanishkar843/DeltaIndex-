"""Documented Greenhouse GET adapter and bounded local JSON/JSONL input."""

import html, json, re, time
from html.parser import HTMLParser
from pathlib import Path
import httpx, ssl, truststore
from .core import Posting


class AdapterError(RuntimeError):
    pass


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(html.unescape(value))
    return " ".join(" ".join(parser.parts).split())


def greenhouse(board, transport=None, sleep=time.sleep):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", board):
        raise ValueError("Invalid public board token")
    with httpx.Client(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        timeout=15,
        transport=transport,
        follow_redirects=False,
    ) as client:
        for attempt in range(3):
            try:
                r = client.get(
                    f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
                    params={"content": "true"},
                )
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt < 2:
                        sleep(
                            min(4, float(r.headers.get("Retry-After", "1")))
                            if r.headers.get("Retry-After", "1").isdigit()
                            else 1
                        )
                        continue
                r.raise_for_status()
                if len(r.content) > 10_000_000:
                    raise AdapterError("Board response exceeds 10 MB")
                rows = r.json()["jobs"]
                if len(rows) > 2000:
                    raise AdapterError(
                        "Board exceeds batch limit; use a narrower approved source"
                    )
                return [
                    Posting(
                        external_id=str(j["id"]),
                        title=j["title"],
                        employer=board,
                        description=plain(j.get("content", "")) or j["title"],
                        location=j.get("location", {}).get("name") or "Unspecified",
                        remote="remote"
                        in j.get("location", {}).get("name", "").lower(),
                        skills=[],
                        synthetic=False,
                        url=j.get("absolute_url"),
                    ).model_dump()
                    for j in rows
                ]
            except (httpx.HTTPError, KeyError, ValueError) as error:
                if attempt == 2:
                    raise AdapterError(type(error).__name__) from None
                sleep(0.25 * 2**attempt)
    raise AdapterError("Source unavailable")


def local_file(path):
    p = Path(path)
    if p.stat().st_size > 10_000_000:
        raise ValueError("Input exceeds 10 MB")
    raw = p.read_text(encoding="utf-8-sig")
    rows = (
        [json.loads(line) for line in raw.splitlines() if line.strip()]
        if p.suffix == ".jsonl"
        else json.loads(raw)
    )
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError("Expected at most 2000 postings")
    return [Posting.model_validate(r).model_dump() for r in rows]
