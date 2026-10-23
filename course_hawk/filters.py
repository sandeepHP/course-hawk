import math

from . import config
from .models import Course
from .udemy import hours_left


def topics_for(course: Course) -> list[str]:
    text = f" {course.title} {course.headline} ".lower()
    return [t for t, words in config.TOPICS.items() if any(w in text for w in words)]


def reject_reason(course: Course, f: dict | None = None) -> str | None:
    """None if the course passes every filter, else a short reason (shown in logs)."""
    f = f or config.FILTERS
    if not course.is_free:
        return "not free"
    if course.kind == "free":
        text = f"{course.title} {course.headline}".lower()
        if any(w in text for w in f["blocked_words"]):
            return "blocked word"
        course.topics = course.topics or topics_for(course)
        return None if course.topics else "off topic"
    popular = course.rating >= f["min_rating"] and course.students >= f["min_students"]
    rated_new = course.rating >= f["alt_min_rating"] and course.num_reviews >= f["alt_min_reviews"]
    if not (popular or rated_new):
        return f"rating {course.rating} / {course.students} students"
    if course.last_updated and int(course.last_updated[:4]) < f["min_year"]:
        return f"last updated {course.last_updated}"
    if course.hours and course.hours < f["min_hours"]:
        return f"{course.hours}h long"
    if course.language and not any(l in course.language for l in f["languages"]):
        return f"language {course.language}"
    text = f"{course.title} {course.headline}".lower()
    if any(w in text for w in f["blocked_words"]):
        return "blocked word"
    if course.instructor and course.instructor.lower() in [i.lower() for i in f["blocked_instructors"]]:
        return "blocked instructor"
    left = hours_left(course.expires_text)
    if left is not None and left < 6:
        return f"{left:.0f}h left"
    course.topics = topics_for(course)
    if not course.topics:
        return "off topic"
    return None


def score(course: Course) -> float:
    if course.kind == "free":
        return 0.0
    return course.rating * math.log10(max(course.students, 10))
