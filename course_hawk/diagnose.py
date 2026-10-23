"""Check which coupon sources and Udemy checks work from this machine. Sends nothing to Telegram.

    python -m course_hawk.diagnose
"""

import logging

from . import udemy
from .filters import reject_reason
from .http import get
from .models import Course
from .sources import find_udemy_link, parse_feed

# Known free-coupon sites to try. The ones that work here can go into config.FEEDS.
CANDIDATES = {
    "tutorialbar": "https://www.tutorialbar.com/feed/",
    "coursevania": "https://coursevania.com/feed/",
    "couponscorpion": "https://couponscorpion.com/feed/",
    "idownloadcoupon": "https://idownloadcoupon.com/feed/",
    "onlinecourses_ooo": "https://www.onlinecourses.ooo/feed/",
    "freewebcart": "https://freewebcart.com/feed/",
    "discudemy": "https://www.discudemy.com/feed/",
}


def check_feed(name: str, url: str):
    try:
        resp = get(url)
    except Exception as e:
        print(f"{name}: FAILED {e.__class__.__name__}: {str(e)[:120]}")
        return None
    head = resp.text[:150].replace("\n", " ")
    try:
        items = parse_feed(resp.text, name)
    except Exception as e:
        print(f"{name}: HTTP {resp.status_code}, not a feed ({e}); starts with: {head!r}")
        return None
    in_feed = [c for c, _ in items if c.url]
    print(f"{name}: HTTP {resp.status_code}, {len(items)} items, {len(in_feed)} with a Udemy coupon link in the feed")
    if not items:
        print(f"   starts with: {head!r}")
    if in_feed:
        return in_feed[0]
    page = next((p for _, p in items if p), "")
    if page:
        try:
            found = find_udemy_link(get(page).text)
            print(f"   first item page: {'coupon link found' if found else 'no Udemy coupon link'} ({page})")
            if found:
                return Course(url=found[0], coupon=found[1], title=items[0][0].title, source=name)
        except Exception as e:
            print(f"   first item page FAILED: {e.__class__.__name__}: {str(e)[:120]}")
    return None


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    print("== Coupon sources")
    samples = [c for c in (check_feed(n, u) for n, u in CANDIDATES.items()) if c]
    print("\n== Udemy price check")
    if not samples:
        print("No coupon link found to test with.")
    for course in samples[:3]:
        udemy.verify(course)
        print(f"{course.url}?couponCode={course.coupon}")
        print(f"   id={course.course_id} price={course.price} list={course.list_price} {course.currency} "
              f"expires={course.expires_text!r}")
        print(f"   rating={course.rating} reviews={course.num_reviews} students={course.students} "
              f"hours={course.hours} lang={course.language!r} updated={course.last_updated!r}")
        print(f"   filter: {reject_reason(course) or 'PASS'}")


if __name__ == "__main__":
    main()
