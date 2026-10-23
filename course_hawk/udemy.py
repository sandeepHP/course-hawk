"""Verify a coupon against Udemy itself: course details from the course page, the price with the
coupon from the JSON endpoint the course page calls. A course whose price cannot be read is never
treated as free."""

import json
import logging
import re

from .http import get
from .models import Course

log = logging.getLogger(__name__)

COMPONENTS_URL = ("https://www.udemy.com/api-2.0/course-landing-components/{id}/me/"
                  "?components=purchase,redeem_coupon,discount_expiration&couponCode={coupon}")

_ID_PATTERNS = [
    re.compile(r'data-clp-course-id="(\d+)"'),
    re.compile(r'"course_id"\s*:\s*(\d+)'),
    re.compile(r'"courseId"\s*:\s*(\d+)'),
]


def _first(patterns, text, cast=str):
    for p in patterns:
        m = p.search(text)
        if m:
            try:
                return cast(m.group(1))
            except ValueError:
                continue
    return None


def _json_ld(html: str) -> dict:
    for block in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Course":
                return item
    return {}


def parse_course_page(html: str, course: Course) -> Course:
    course.course_id = _first(_ID_PATTERNS, html, int)
    ld = _json_ld(html)
    rating = ld.get("aggregateRating") or {}
    course.title = ld.get("name") or course.title
    course.headline = ld.get("description") or course.headline
    course.rating = float(rating.get("ratingValue") or 0) or (
        _first([re.compile(r'"avg_rating"\s*:\s*([\d.]+)'), re.compile(r'"rating"\s*:\s*([\d.]+)')], html, float) or 0.0)
    course.num_reviews = int(rating.get("ratingCount") or 0) or (
        _first([re.compile(r'"num_reviews"\s*:\s*(\d+)')], html, int) or 0)
    course.students = _first([re.compile(r'"num_subscribers"\s*:\s*(\d+)'),
                              re.compile(r'"num_students"\s*:\s*(\d+)')], html, int) or 0
    seconds = _first([re.compile(r'"content_length_video"\s*:\s*(\d+)')], html, int)
    if seconds:
        course.hours = round(seconds / 3600, 1)
    else:
        course.hours = _first([re.compile(r'"content_info_short"\s*:\s*"([\d.]+) (?:total )?hours?')], html, float) or 0.0
    lang = ld.get("inLanguage") or _first([re.compile(r'"locale"\s*:\s*\{[^}]*"simple_english_title"\s*:\s*"([^"]+)"')], html)
    course.language = {"en": "english", "hi": "hindi"}.get(str(lang).lower()[:2], str(lang or "").lower())
    course.last_updated = _first([re.compile(r'"last_update_date"\s*:\s*"(\d{4}-\d{2}-\d{2})')], html) or ""
    course.instructor = _first([re.compile(r'"visible_instructors"\s*:\s*\[\s*\{[^}]*?"title"\s*:\s*"([^"]+)"')], html) or ""
    if not course.instructor:
        author = ld.get("creator") or ld.get("author") or []
        author = author[0] if isinstance(author, list) and author else author
        course.instructor = author.get("name", "") if isinstance(author, dict) else ""
    return course


def parse_components(data: dict, course: Course) -> Course:
    """Read the price with the coupon. Leaves course.price None when the shape is unknown."""
    purchase = (data.get("purchase") or {}).get("data") or {}
    pricing = purchase.get("pricing_result") or {}
    price = (pricing.get("price") or {}).get("amount")
    list_price = (pricing.get("list_price") or {}).get("amount")
    if price is None:  # older response shape
        payment = ((data.get("buy_button") or {}).get("button") or {}).get("payment_data") or {}
        price = (payment.get("purchasePrice") or {}).get("amount")
        list_price = list_price or (payment.get("originalPrice") or {}).get("amount")
    attempts = (data.get("redeem_coupon") or {}).get("discount_attempts") or []
    applied = any(a.get("code", "").upper() == course.coupon.upper() and a.get("status") == "applied"
                  for a in attempts)
    if attempts and not applied:
        price = None  # coupon rejected; whatever price is shown is not the coupon price
    course.price = float(price) if price is not None else None
    course.list_price = float(list_price or course.list_price or 0)
    course.currency = (pricing.get("price") or {}).get("currency") or course.currency
    exp = (data.get("discount_expiration") or {}).get("data") or {}
    course.expires_text = exp.get("discount_deadline_text") or ""
    return course


COURSE_API_URL = ("https://www.udemy.com/api-2.0/courses/{slug}/?fields[course]=id,title,headline,avg_rating,"
                  "num_reviews,num_subscribers,content_info_short,last_update_date,locale,visible_instructors")


def parse_api_course(data: dict, course: Course) -> Course:
    """Course details from Udemy's public course API (looked up by slug)."""
    course.course_id = data.get("id") or course.course_id
    course.title = data.get("title") or course.title
    course.headline = data.get("headline") or course.headline
    course.rating = float(data.get("avg_rating") or course.rating or 0)
    course.num_reviews = int(data.get("num_reviews") or course.num_reviews or 0)
    course.students = int(data.get("num_subscribers") or course.students or 0)
    m = re.match(r"([\d.]+)", data.get("content_info_short") or "")
    if m and "hour" in data.get("content_info_short", ""):
        course.hours = float(m.group(1))
    locale = data.get("locale") or {}
    lang = locale.get("simple_english_title") or locale.get("english_title") or ""
    course.language = lang.lower() or course.language
    course.last_updated = (data.get("last_update_date") or course.last_updated or "")[:10]
    instructors = data.get("visible_instructors") or []
    if instructors:
        course.instructor = instructors[0].get("title") or instructors[0].get("display_name") or ""
    return course


def slug_of(url: str) -> str:
    m = re.search(r"/course/([\w-]+)", url)
    return m.group(1) if m else ""


def verify(course: Course, trace: list | None = None) -> Course:
    """Fill in details and the coupon price. Errors leave price None (= not free).
    trace, if given, collects one line per request for diagnostics."""
    note = trace.append if trace is not None else (lambda line: None)
    course.price = None
    if not course.course_id:
        try:
            resp = get(COURSE_API_URL.format(slug=slug_of(course.url)))
            parse_api_course(resp.json(), course)
            note(f"course API: HTTP {resp.status_code}, id={course.course_id}")
        except Exception as e:
            note(f"course API failed: {str(e)[:150]}")
    if not course.course_id or not course.students:
        try:
            resp = get(course.url)
            parse_course_page(resp.text, course)
            note(f"course page: HTTP {resp.status_code}, {len(resp.text)} bytes, id={course.course_id}")
        except Exception as e:
            note(f"course page failed: {str(e)[:150]}")
    if not course.course_id:
        log.info("no course id for %s", course.url)
        return course
    try:
        resp = get(COMPONENTS_URL.format(id=course.course_id, coupon=course.coupon))
        note(f"price check: HTTP {resp.status_code}, starts {resp.text[:200]!r}")
        parse_components(resp.json(), course)
    except Exception as e:
        note(f"price check failed: {str(e)[:150]}")
        log.warning("verify failed for %s: %s", course.url, e)
        course.price = None
    return course


def hours_left(expires_text: str) -> float | None:
    """'2 days left at this price!' -> 48. None when unknown."""
    m = re.search(r"(\d+)\s*(minute|hour|day)", expires_text or "", re.I)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return n / 60 if unit == "minute" else n if unit == "hour" else n * 24
