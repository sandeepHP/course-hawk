"""All tunable settings. Secrets come from environment variables (GitHub Actions secrets)."""

import os

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "")  # e.g. "@coursehawk_free"
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")  # your private chat with the bot
# Optional Cuelinks wrapping: your tracking link with {url} where the Udemy link goes, copied from
# the Cuelinks dashboard. Leave empty to post plain Udemy links.
CUELINKS_TEMPLATE = os.environ.get("CUELINKS_TEMPLATE", "")

STATE_FILE = os.environ.get("COURSE_HAWK_STATE", "state/state.json")
DRY_RUN = os.environ.get("COURSE_HAWK_DRY_RUN", "") == "1"

# RSS feeds of public free-coupon listing sites. Each item links to a Udemy course with a coupon,
# either in the feed or on the item's page. A site that fails is skipped; check with
# `python -m course_hawk.diagnose`.
FEEDS = {
    "tutorialbar": "https://www.tutorialbar.com/feed/",
    "coursevania": "https://coursevania.com/feed/",
    "couponscorpion": "https://couponscorpion.com/feed/",
    "idownloadcoupon": "https://idownloadcoupon.com/feed/",
    "onlinecourses_ooo": "https://www.onlinecourses.ooo/feed/",
    "freewebcart": "https://freewebcart.com/feed/",
    "discudemy": "https://www.discudemy.com/feed/",
}

# YouTube channels that publish full free courses (channel name -> channel id).
YOUTUBE_CHANNELS = {
    "freeCodeCamp": "UC8butISFwT-Wl7EV0hUK0BQ",
}
# A video counts as a course only if its title has one of these.
YOUTUBE_TITLE_WORDS = ["full course", "crash course", "course for beginners", "bootcamp", "complete course"]

FILTERS = {
    "min_rating": 4.0,
    "min_students": 1000,
    # A newer course can pass with fewer students if it is rated highly.
    "alt_min_rating": 4.3,
    "alt_min_reviews": 50,
    "min_year": 2024,
    "min_hours": 1.0,
    "languages": ["english"],
    "blocked_words": ["make money", "passive income", "get rich", "side hustle"],
    "blocked_instructors": [],
}

# Topic -> words that place a course in it. A course must match at least one topic.
TOPICS = {
    "python": ["python", "django", "flask", "fastapi", "pandas", "numpy"],
    "ai": ["artificial intelligence", " ai ", "machine learning", "deep learning", "chatgpt", "llm",
           "generative ai", "prompt engineering", "tensorflow", "pytorch"],
    "data": ["data science", "data analysis", "data analytics", "sql", "power bi", "tableau", "statistics"],
    "cloud": ["aws", "azure", "google cloud", "gcp", "cloud"],
    "devops": ["devops", "docker", "kubernetes", "terraform", "jenkins", "ci/cd", "ansible", "git "],
    "linux": ["linux", "bash", "shell scripting"],
    "excel": ["excel", "spreadsheet", "vba"],
    "cybersecurity": ["cyber", "security", "ethical hacking", "penetration testing", "comptia"],
    "webdev": ["javascript", "react", "node", "html", "css", "web development", "typescript", "angular"],
    "java": ["java ", "spring boot"],
    "interview": ["interview", "resume", "placement"],
}

# Post slots in IST (24h "HH:MM") and how many courses each slot posts.
SLOTS = {"08:00": 2, "12:30": 1, "17:30": 2, "20:00": 1, "21:30": 2}
# The scheduled run fires every 15 min (often late), so a slot counts as due for this long after its time.
SLOT_WINDOW_MIN = 29

# Courses with less than this many hours left are posted right after approval.
URGENT_HOURS = 12
DEDUPE_DAYS = 30
RECHECK_DAYS = 5  # how long posted coupons keep being checked for expiry
# Previews per scan: Udemy coupon courses and always-free courses (Microsoft Learn, YouTube, catalog).
COUPON_PREVIEWS = 6
FREE_PREVIEWS = 4
FREE_PER_SOURCE = 2  # so one source (e.g. Microsoft Learn) can't fill every free slot
CATALOG_PER_DAY = 2  # the curated catalog is offered slowly, so it lasts
CATALOG_REPEAT_DAYS = 120
