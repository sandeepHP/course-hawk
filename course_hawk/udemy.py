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


def verify(course: Course) -> Course:
    """Fill in details and the coupon price. Network errors leave price None (= not free)."""
    try:
        if not course.course_id:
            parse_course_page(get(course.url).text, course)
        if not course.course_id:
            log.info("no course id for %s", course.url)
            course.price = None
            return course
        resp = get(COMPONENTS_URL.format(id=course.course_id, coupon=course.coupon))
        parse_components(resp.json(), course)
    except Exception as e:
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
