"""Find Udemy coupon links on public free-coupon listing sites (RSS feeds)."""

import logging
import re
import xml.etree.ElementTree as ET
from html import unescape

from . import config
from .http import get
from .models import Course

log = logging.getLogger(__name__)

UDEMY_LINK = re.compile(
    r"https?://(?:www\.)?udemy\.com/course/([\w-]+)/?\?(?:[^\"'<>\s]*&(?:amp;)?)?couponCode=([\w-]+)",
    re.IGNORECASE,
)
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}encoded"


def find_udemy_link(text: str) -> tuple[str, str] | None:
    """Return (course_url, coupon) for the first Udemy coupon link in text."""
    m = UDEMY_LINK.search(text or "")
    if not m:
        return None
    slug, coupon = m.group(1), m.group(2)
    return f"https://www.udemy.com/course/{slug}/", coupon


def parse_feed(xml_text: str, source: str) -> list[tuple[Course, str]]:
    """Parse an RSS feed into (course, item page URL). A course has an empty URL when the
    feed item itself has no Udemy link and the item page must be opened to find it."""
    out = []
    for title, page, body in _items(xml_text):
        found = find_udemy_link(body)
        course = Course(url=found[0] if found else "", coupon=found[1] if found else "",
                        title=title, source=source)
        out.append((course, page))
    return out


def _items(xml_text: str):
    """Yield (title, page link, text to search) per feed item. Falls back to a plain text scan when
    the feed is not valid XML (common with stray characters in WordPress feeds)."""
    text = xml_text.lstrip("\ufeff \r\n\t")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        for block in re.findall(r"<item\b.*?</item>", text, re.S | re.I):
            title = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S)
            link = re.search(r"<link>(.*?)</link>", block, re.S)
            page = link.group(1).strip() if link else ""
            yield (unescape(title.group(1).strip()) if title else ""), page, block
        return
    for item in root.iter("item"):
        page = (item.findtext("link") or "").strip()
        body = " ".join(filter(None, [item.findtext("description"), item.findtext(CONTENT_NS), page]))
        yield (item.findtext("title") or "").strip(), page, body


def scan_feeds(feeds: dict[str, str] | None = None) -> list[Course]:
    courses = []
    for source, url in (feeds or config.FEEDS).items():
        try:
            items = parse_feed(get(url).text, source)
        except Exception as e:  # one broken source must not stop the others
            log.warning("feed %s failed: %s", source, e)
            continue
        for course, page in items:
            if not course.url and page:
                try:
                    found = find_udemy_link(get(page).text)
                except Exception as e:
                    log.warning("page %s failed: %s", page, e)
                    found = None
                if not found:
                    continue
                course.url, course.coupon = found
            if course.url and course.coupon:
                courses.append(course)
        log.info("%s: %d feed items, %d coupon links so far", source, len(items), len(courses))
    return courses
