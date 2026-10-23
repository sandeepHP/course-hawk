"""Find Udemy coupon links on public free-coupon listing sites (RSS feeds)."""

import logging
import re
import xml.etree.ElementTree as ET

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
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        page = (item.findtext("link") or "").strip()
        body = " ".join(filter(None, [item.findtext("description"), item.findtext(CONTENT_NS), page]))
        found = find_udemy_link(body)
        course = Course(url=found[0] if found else "", coupon=found[1] if found else "",
                        title=title, source=source)
        out.append((course, page))
    return out


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
        log.info("%s: %d coupon links", source, len(items))
    return courses
