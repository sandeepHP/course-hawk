"""One scheduled run: read your bot replies, post a due slot, mark expired posts, scan for new courses.

Runs every 15 minutes on GitHub Actions. Each step is safe to skip or repeat."""

import argparse
import logging
import random
from collections import Counter
from html import escape
from datetime import datetime, timedelta, timezone

from . import config, free_sources, telegram, udemy
from .filters import reject_reason, score
from .formatter import format_post
from .models import Course
from .sources import scan_feeds
from .state import State, now

log = logging.getLogger("course_hawk")
IST = timezone(timedelta(hours=5, minutes=30))
PREVIEW_SLOTS = ["07:30", "12:00", "17:00", "21:00"]
RECHECK_EVERY = timedelta(hours=3)


def preview_buttons(key: str) -> list[list[dict]]:
    return [
        [{"text": "✅ Approve", "callback_data": f"a:{key}"}, {"text": "⚡ Post now", "callback_data": f"p:{key}"}],
        [{"text": "⏭ Skip", "callback_data": f"s:{key}"}, {"text": "🚫 Ban instructor", "callback_data": f"b:{key}"}],
    ]


def due_slot(slots, state: State, at: datetime, prefix: str) -> str | None:
    """Return the slot ("HH:MM") that is due now and not yet done, marking it done."""
    local = at.astimezone(IST)
    for hhmm in slots:
        h, m = map(int, hhmm.split(":"))
        start = local.replace(hour=h, minute=m, second=0, microsecond=0)
        mark = f"{local:%Y-%m-%d} {prefix}{hhmm}"
        if start <= local < start + timedelta(minutes=config.SLOT_WINDOW_MIN + 1) and mark not in state.data["slots_done"]:
            state.data["slots_done"][mark] = True
            return hhmm
    return None


def post_to_channel(state: State, course: Course) -> bool:
    """Check the price one last time, then post. Returns False if the coupon died."""
    if course.kind == "free":
        if not free_sources.link_alive(course.url):
            telegram.send(config.ADMIN_CHAT_ID, f"⚠️ Link is down, not posted: {course.title}")
            return False
    else:
        udemy.verify(course)
        if not course.is_free:
            telegram.send(config.ADMIN_CHAT_ID, f"⚠️ Coupon ended before posting: {course.title}")
            return False
    try:
        message_id = telegram.send(config.CHANNEL, format_post(course))
    except RuntimeError as e:
        telegram.send(config.ADMIN_CHAT_ID, f"⚠️ Could not post to the channel <code>{escape(config.CHANNEL)}</code>: {escape(str(e))}\n\n"
                      "Check the TELEGRAM_CHANNEL secret is the channel's @username and that this bot is an "
                      "admin of the channel with permission to post.")
        raise
    state.data["posted"].append({"course": course.to_dict(), "message_id": message_id,
                                 "posted_at": now().isoformat(), "checked_at": now().isoformat(),
                                 "expired": False})
    log.info("posted %s", course.title)
    return True


def handle_updates(state: State) -> None:
    for upd in telegram.updates(state.data["update_offset"]):
        state.data["update_offset"] = upd["update_id"] + 1
        if "callback_query" in upd:
            handle_button(state, upd["callback_query"])
        elif "message" in upd:
            handle_message(state, upd["message"])


def _from_admin(chat: dict) -> bool:
    return str(chat.get("id")) == str(config.ADMIN_CHAT_ID)


def handle_button(state: State, cb: dict) -> None:
    msg = cb.get("message") or {}
    if not _from_admin(msg.get("chat") or {}):
        return
    action, _, key = cb.get("data", "").partition(":")
    entry = state.data["pending"].pop(key, None)
    if not entry:
        telegram.answer(cb["id"], "Already handled")
        return
    course = State.course(entry)
    preview = format_post(course)
    if action == "a":
        urgent = (udemy.hours_left(course.expires_text) or 99) < config.URGENT_HOURS
        if urgent:
            ok = post_to_channel(state, course)
            note = "⚡ Posted now (expires soon)" if ok else "❌ Coupon ended"
        else:
            state.data["queue"].append({"course": course.to_dict(), "preview_id": msg.get("message_id")})
            note = "✅ Approved, queued for the next slot"
    elif action == "p":
        note = "⚡ Posted" if post_to_channel(state, course) else "❌ Coupon ended"
    elif action == "b":
        state.data.setdefault("banned", []).append(course.instructor)
        note = f"🚫 Skipped, banned {course.instructor or 'instructor'}"
    else:
        note = "⏭ Skipped"
    telegram.answer(cb["id"], note)
    telegram.edit(config.ADMIN_CHAT_ID, msg["message_id"], f"{note}\n\n{preview}", buttons=[])


def handle_message(state: State, msg: dict) -> None:
    if not _from_admin(msg.get("chat") or {}):
        return
    text = (msg.get("text") or "").strip()
    reply_to = (msg.get("reply_to_message") or {}).get("message_id")
    if reply_to and text and not text.startswith("/"):
        # A reply to a preview replaces its one-line description.
        for key, entry in state.data["pending"].items():
            if entry.get("preview_id") == reply_to:
                entry["course"]["headline"] = text
                telegram.edit(config.ADMIN_CHAT_ID, reply_to, format_post(State.course(entry)),
                              buttons=preview_buttons(key))
                return
    if text.startswith("/queue"):
        lines = [f"{i + 1}. {e['course']['title']}" for i, e in enumerate(state.data["queue"])]
        telegram.send(config.ADMIN_CHAT_ID,
                      f"Queue ({len(lines)}):\n" + "\n".join(lines) if lines else "Queue is empty.")
    elif text.startswith("/status"):
        d = state.data
        telegram.send(config.ADMIN_CHAT_ID, f"Waiting for you: {len(d['pending'])}\nQueued: {len(d['queue'])}\n"
                                            f"Posted (last {config.RECHECK_DAYS + 1} days): {len(d['posted'])}")


def post_slot(state: State, at: datetime, now_all: bool = False) -> None:
    if not state.data["queue"]:
        return  # leave the slot open, so courses approved later in its window still post
    slot = None if now_all else due_slot(config.SLOTS, state, at, "post ")
    if not slot and not now_all:
        return
    queue = sorted(state.data["queue"], key=lambda e: -score(State.course(e)))
    posted = 0
    try:
        while queue and (now_all or posted < config.SLOTS[slot]):
            entry = queue.pop(0)
            if post_to_channel(state, State.course(entry)):
                posted += 1
    except Exception:
        queue.insert(0, entry)  # not posted: keep it for the next try
        if not posted and slot:  # e.g. the channel is misconfigured: keep the slot open too
            state.data["slots_done"].pop(f"{at.astimezone(IST):%Y-%m-%d} post {slot}", None)
        raise
    finally:
        state.data["queue"] = queue


def recheck_posted(state: State) -> None:
    cutoff = now() - timedelta(days=config.RECHECK_DAYS)
    for entry in state.data["posted"]:
        posted_at = datetime.fromisoformat(entry["posted_at"])
        checked = datetime.fromisoformat(entry.get("checked_at") or entry["posted_at"])
        if entry["course"].get("kind") == "free":
            continue
        if entry["expired"] or posted_at < cutoff or now() - checked < RECHECK_EVERY:
            continue
        course = State.course(entry)
        udemy.verify(course)
        entry["checked_at"] = now().isoformat()
        if course.price is not None and not course.is_free:  # unknown price is not proof of expiry
            entry["expired"] = True
            telegram.edit(config.CHANNEL, entry["message_id"], format_post(State.course(entry), expired=True))
            log.info("marked expired: %s", course.title)


def scan(state: State, at: datetime, force: bool = False) -> None:
    if not force and not due_slot(PREVIEW_SLOTS, state, at, "preview "):
        return
    filters = {**config.FILTERS,
               "blocked_instructors": config.FILTERS["blocked_instructors"] + state.data.get("banned", [])}
    known = set(state.data["pending"]) | {State.course(e).key for e in state.data["queue"]}

    def fresh(course: Course, days: int = config.DEDUPE_DAYS) -> bool:
        return course.key not in known and not state.seen_recently(course.key, days)

    coupons, reasons = [], Counter()
    try:
        found = scan_feeds()
    except Exception:
        log.exception("coupon sources failed")
        found = []
    for course in found:
        if not fresh(course):
            continue
        udemy.verify(course)
        if not fresh(course):
            continue  # same course found under its slug and its id
        reason = reject_reason(course, filters)
        if reason:
            log.info("rejected %s: %s", course.title, reason)
            reasons[reason.split(" ")[0]] += 1
            continue
        coupons.append(course)
        known.add(course.key)
    coupons = sorted(coupons, key=score, reverse=True)[:config.COUPON_PREVIEWS]

    free = []
    for name, fetch in (("microsoft_learn", free_sources.microsoft_learn), ("youtube", free_sources.youtube)):
        try:
            found = fetch()
        except Exception as e:
            log.warning("%s failed: %s", name, e)
            continue
        taken = 0
        for course in found:
            if taken < config.FREE_PER_SOURCE and fresh(course) and not reject_reason(course, filters):
                free.append(course)
                known.add(course.key)
                taken += 1
    free = free[:config.FREE_PREVIEWS]
    catalog = free_sources.catalog()
    today = now().date().isoformat()
    offered_today = sum(1 for c in catalog if state.data["seen"].get(c.key, "")[:10] == today)
    picks = [c for c in catalog if fresh(c, config.CATALOG_REPEAT_DAYS)]
    random.shuffle(picks)
    free += picks[:max(0, min(config.CATALOG_PER_DAY - offered_today, config.FREE_PREVIEWS - len(free)))]

    for course in coupons + free:
        preview_id = telegram.send(config.ADMIN_CHAT_ID, format_post(course), buttons=preview_buttons(course.key))
        state.data["pending"][course.key] = {"course": course.to_dict(), "preview_id": preview_id}
        state.mark_seen(course.key)
    log.info("scan: %d coupon and %d free previews; coupons rejected: %s", len(coupons), len(free), dict(reasons))


def main() -> None:
    parser = argparse.ArgumentParser(description="Course Hawk scheduled run")
    parser.add_argument("--scan-now", action="store_true", help="scan even if no preview slot is due")
    parser.add_argument("--post-queue", action="store_true", help="post every approved course now")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    missing = [n for n in ("BOT_TOKEN", "CHANNEL", "ADMIN_CHAT_ID") if not getattr(config, n)]
    if missing and not config.DRY_RUN:
        # Not set up yet: exit quietly so the schedule doesn't fail every 15 minutes.
        log.warning("not configured, skipping run; missing: %s", ", ".join(missing))
        return
    state = State(config.STATE_FILE)
    at = now()
    steps = [("updates", lambda: handle_updates(state)), ("post", lambda: post_slot(state, at, args.post_queue)),
             ("recheck", lambda: recheck_posted(state)), ("scan", lambda: scan(state, at, args.scan_now))]
    try:
        for name, step in steps:
            try:
                step()
            except Exception:
                log.exception("step %s failed", name)
            state.save()  # save after each step so a later failure loses nothing
    finally:
        state.prune(config.DEDUPE_DAYS, config.RECHECK_DAYS)
        state.save()


if __name__ == "__main__":
    main()
