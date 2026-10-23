"""Always-free courses from providers worldwide: the curated catalog, Microsoft Learn's public
catalog API, and full-course videos from YouTube channel feeds."""

import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from . import config
from .http import get
from .models import Course

log = logging.getLogger(__name__)

CATALOG_FILE = Path(__file__).with_name("catalog.json")
MS_LEARN_URL = "https://learn.microsoft.com/api/catalog/?locale=en-us&type=learningPaths"
YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={id}"
ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def catalog(path: Path = CATALOG_FILE) -> list[Course]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [Course(url=r["url"], title=r["title"], provider=r["provider"], headline=r.get("headline", ""),
                   certificate=r.get("certificate", ""), topics=r.get("topics", []), kind="free",
                   source="catalog", language="english") for r in rows]


def parse_ms_learn(data: dict, since: datetime) -> list[Course]:
    out = []
    for p in data.get("learningPaths", []):
        modified = p.get("last_modified") or ""
        try:
            when = datetime.fromisoformat(modified.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < since:
            continue
        url = (p.get("url") or "").split("?")[0]
        if not url:
            continue
        out.append(Course(url=url, title=p.get("title", ""), headline=(p.get("summary") or "").strip(),
                          provider="Microsoft Learn", certificate="Free Microsoft Learn trophy",
                          hours=round((p.get("duration_in_minutes") or 0) / 60, 1), kind="free",
                          source="ms_learn", language="english", last_updated=modified[:10]))
    return out


def microsoft_learn(days: int = 14) -> list[Course]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return parse_ms_learn(get(MS_LEARN_URL, timeout=60).json(), since)


def parse_youtube(xml_text: str, provider: str, since: datetime) -> list[Course]:
    out = []
    root = ET.fromstring(xml_text)
    for entry in root.iter(f"{ATOM}entry"):
        title = entry.findtext(f"{ATOM}title") or ""
        if not any(w in title.lower() for w in config.YOUTUBE_TITLE_WORDS):
            continue  # skip shorts, talks and news; keep full courses
        published = entry.findtext(f"{ATOM}published") or ""
        try:
            if datetime.fromisoformat(published.replace("Z", "+00:00")) < since:
                continue
        except ValueError:
            continue
        link = entry.find(f"{ATOM}link")
        group = entry.find(f"{MEDIA}group")
        desc = group.findtext(f"{MEDIA}description") if group is not None else ""
        first_line = next((l.strip() for l in (desc or "").splitlines() if l.strip()), "")
        out.append(Course(url=link.get("href") if link is not None else "", title=title, headline=first_line[:200],
                          provider=f"{provider} (YouTube)", kind="free", source="youtube", language="english",
                          last_updated=published[:10]))
    return [c for c in out if c.url]


def youtube(days: int = 7) -> list[Course]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for provider, channel_id in config.YOUTUBE_CHANNELS.items():
        try:
            out += parse_youtube(get(YOUTUBE_FEED.format(id=channel_id)).text, provider, since)
        except Exception as e:
            log.warning("youtube %s failed: %s", provider, e)
    return out


def link_alive(url: str) -> bool:
    """False only when the page is clearly gone. Sites that block bots (403, 429) count as alive,
    because the curated links were checked by hand."""
    try:
        resp = requests.get(url, timeout=20, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException as e:
        log.info("link check %s: %s", url, e)
        return False
    return resp.status_code not in (404, 410) and resp.status_code < 500
