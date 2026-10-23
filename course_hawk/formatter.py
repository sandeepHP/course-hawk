"""Telegram post text (HTML parse mode)."""

from html import escape
from urllib.parse import quote

from . import config
from .models import Course


def course_link(course: Course) -> str:
    url = f"{course.url}?couponCode={course.coupon}" if course.coupon else course.url
    if config.CUELINKS_TEMPLATE:
        return config.CUELINKS_TEMPLATE.replace("{url}", quote(url, safe=""))
    return url


def _count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    return f"{n:,}"


def _money(amount: float, currency: str) -> str:
    symbol = "₹" if currency == "INR" else f"{currency} "
    return f"{symbol}{amount:,.0f}"


def format_post(course: Course, expired: bool = False) -> str:
    stats = [f"⭐ {course.rating:.1f} ({_count(course.num_reviews)} ratings)" if course.num_reviews
             else f"⭐ {course.rating:.1f}"]
    if course.students:
        stats.append(f"👥 {_count(course.students)} students")
    if course.hours:
        stats.append(f"⏱ {course.hours:g}h")
    # Udemy prices by the visitor's country; GitHub's servers are not in India, so only show a
    # rupee list price when Udemy actually returned one.
    if course.list_price and course.currency == "INR":
        price = f"💰 {_money(course.list_price, course.currency)} → FREE"
    else:
        price = "💰 Paid course → FREE"
    if course.expires_text:
        price += f" · ⏳ {escape(course.expires_text.replace(' at this price!', '').strip())}"
    lines = []
    if expired:
        lines.append("❌ <b>EXPIRED</b> — this coupon has ended\n")
    lines += [
        f"🎓 <b>{escape(course.title)}</b>",
        " · ".join(stats),
        price,
    ]
    if course.headline:
        lines += ["", escape(course.headline)]
    lines += ["", f'👉 <a href="{escape(course_link(course))}">Enroll free</a>']
    tags = " ".join(f"#{t}" for t in course.topics) + " #udemy"
    lines += ["", tags.strip()]
    return "\n".join(lines)
