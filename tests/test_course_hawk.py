"""Offline tests. The Udemy fixtures are hand-made in the shapes the parsers expect; the first live
run on GitHub Actions is what confirms Udemy still answers in these shapes."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from course_hawk import config, filters, formatter, run, sources, udemy
from course_hawk.models import Course
from course_hawk.state import State

FIX = Path(__file__).parent / "fixtures"


def good_course(**kw) -> Course:
    base = dict(url="https://www.udemy.com/course/python-ds/", coupon="FREE24", title="Python for Data Science",
                headline="Learn NumPy and Pandas", rating=4.5, num_reviews=1200, students=85000, hours=22,
                language="english", last_updated="2025-06-01", list_price=3199, price=0.0,
                expires_text="2 days left at this price!", course_id=123)
    base.update(kw)
    return Course(**base)


def test_find_udemy_link_handles_extra_params_and_amp():
    text = 'href="https://www.udemy.com/course/aws-basics/?ranMID=1&amp;couponCode=OCT-FREE"'
    assert sources.find_udemy_link(text) == ("https://www.udemy.com/course/aws-basics/", "OCT-FREE")
    assert sources.find_udemy_link("https://www.udemy.com/course/aws-basics/") is None


def test_parse_feed():
    items = sources.parse_feed((FIX / "feed.xml").read_text(), "tutorialbar")
    assert len(items) == 2
    first, page = items[0]
    assert first.url == "https://www.udemy.com/course/python-bootcamp-x/" and first.coupon == "PYFREE"
    second, page2 = items[1]
    assert second.url == "" and page2 == "https://example.org/post-2"


def test_parse_feed_not_well_formed():
    bad = (FIX / "feed.xml").read_text().replace("Excel Basics", "Excel & VBA") + "\n"
    items = sources.parse_feed("\ufeff\n" + bad, "x")
    assert len(items) == 2 and items[0][0].coupon == "PYFREE" and items[1][0].title == "Excel & VBA"


def test_parse_course_page():
    c = udemy.parse_course_page((FIX / "course_page.html").read_text(), Course(url="u"))
    assert c.course_id == 567828
    assert c.title == "Complete Python Bootcamp"
    assert c.rating == 4.6 and c.num_reviews == 520000 and c.students == 1900000
    assert c.hours == 22.0 and c.language == "english" and c.last_updated == "2025-03-01"
    assert c.instructor == "Jose Portilla"


def test_parse_components_free_and_rejected():
    data = json.loads((FIX / "components_free.json").read_text())
    c = udemy.parse_components(data, Course(url="u", coupon="PYFREE"))
    assert c.is_free and c.list_price == 3199 and c.expires_text.startswith("4 days")
    c2 = udemy.parse_components(data, Course(url="u", coupon="OTHER"))
    assert c2.price is None and not c2.is_free


def test_parse_components_unknown_shape_is_not_free():
    c = udemy.parse_components({"something": {}}, Course(url="u", coupon="X"))
    assert c.price is None and not c.is_free


@pytest.mark.parametrize("text,hours", [("2 days left at this price!", 48), ("5 hours left", 5),
                                        ("30 minutes left", 0.5), ("", None)])
def test_hours_left(text, hours):
    assert udemy.hours_left(text) == hours


def test_filters_pass_and_tag():
    c = good_course()
    assert filters.reject_reason(c) is None
    assert "python" in c.topics and "data" in c.topics


@pytest.mark.parametrize("change,reason", [
    (dict(price=449.0), "not free"),
    (dict(rating=3.9), "rating"),
    (dict(students=200, num_reviews=10), "rating"),
    (dict(last_updated="2021-01-01"), "last updated"),
    (dict(hours=0.5), "h long"),
    (dict(language="spanish"), "language"),
    (dict(title="Make money with ChatGPT"), "blocked"),
    (dict(expires_text="3 hours left"), "left"),
    (dict(title="Gardening basics", headline="Grow tomatoes"), "off topic"),
])
def test_filters_reject(change, reason):
    assert reason in filters.reject_reason(good_course(**change))


def test_new_course_with_good_reviews_passes():
    assert filters.reject_reason(good_course(students=300, rating=4.4, num_reviews=60)) is None


def test_format_post(monkeypatch):
    monkeypatch.setattr(config, "CUELINKS_TEMPLATE", "")
    c = good_course(title="Python & <Data>")
    c.topics = ["python"]
    text = formatter.format_post(c)
    assert "Python &amp; &lt;Data&gt;" in text
    assert "₹3,199 → FREE" in text and "2 days left" in text
    assert "couponCode=FREE24" in text and "#python #udemy" in text
    assert formatter.format_post(c, expired=True).startswith("❌ <b>EXPIRED</b>")


def test_cuelinks_wrap(monkeypatch):
    monkeypatch.setattr(config, "CUELINKS_TEMPLATE", "https://links.example/?id=1&url={url}")
    link = formatter.course_link(good_course())
    assert link.startswith("https://links.example/?id=1&url=https%3A%2F%2Fwww.udemy.com")
    assert "couponCode%3DFREE24" in link


def test_due_slot_once(tmp_path):
    state = State(str(tmp_path / "s.json"))
    at = datetime.fromisoformat("2026-10-23T08:10:00+05:30")
    assert run.due_slot(["08:00"], state, at, "post ") == "08:00"
    assert run.due_slot(["08:00"], state, at, "post ") is None
    late = datetime.fromisoformat("2026-10-23T08:45:00+05:30")
    assert run.due_slot(["08:00"], State(str(tmp_path / "t.json")), late, "post ") is None


class FakeTelegram:
    def __init__(self, updates=()):
        self._updates, self.sent, self.edited, self.next_id = list(updates), [], [], 100

    def updates(self, offset):
        return [u for u in self._updates if u["update_id"] >= offset]

    def send(self, chat, text, buttons=None):
        self.next_id += 1
        self.sent.append((chat, text))
        return self.next_id

    def edit(self, chat, mid, text, buttons=None):
        self.edited.append((chat, mid, text))

    def answer(self, *a, **k):
        pass


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CHANNEL", "@chan")
    monkeypatch.setattr(config, "ADMIN_CHAT_ID", "42")
    monkeypatch.setattr(config, "CUELINKS_TEMPLATE", "")
    return State(str(tmp_path / "state.json"))


def button(key, action, update_id=1):
    return {"update_id": update_id, "callback_query": {"id": "cb", "data": f"{action}:{key}",
                                                        "message": {"message_id": 7, "chat": {"id": 42}}}}


def test_scan_sends_previews_and_dedupes(env, monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(run, "telegram", fake)
    monkeypatch.setattr(run, "scan_feeds", lambda: [good_course(price=None, course_id=None)])
    def verify(c):
        for k, v in good_course().to_dict().items():
            setattr(c, k, v)
        return c
    monkeypatch.setattr(run.udemy, "verify", verify)
    run.scan(env, datetime.now(), force=True)
    assert list(env.data["pending"]) == ["123"] and fake.sent[0][0] == "42"
    run.scan(env, datetime.now(), force=True)
    assert len(fake.sent) == 1


def test_approve_then_slot_posts(env, monkeypatch):
    env.data["pending"]["123"] = {"course": good_course().to_dict(), "preview_id": 7}
    fake = FakeTelegram([button("123", "a")])
    monkeypatch.setattr(run, "telegram", fake)
    monkeypatch.setattr(run.udemy, "verify", lambda c: c)
    run.handle_updates(env)
    assert env.data["update_offset"] == 2 and len(env.data["queue"]) == 1 and not env.data["pending"]
    run.post_slot(env, datetime.fromisoformat("2026-10-23T08:05:00+05:30"))
    assert fake.sent[-1][0] == "@chan" and not env.data["queue"] and len(env.data["posted"]) == 1


def test_urgent_approve_posts_at_once(env, monkeypatch):
    env.data["pending"]["123"] = {"course": good_course(expires_text="8 hours left").to_dict(), "preview_id": 7}
    fake = FakeTelegram([button("123", "a")])
    monkeypatch.setattr(run, "telegram", fake)
    monkeypatch.setattr(run.udemy, "verify", lambda c: c)
    run.handle_updates(env)
    assert fake.sent[-1][0] == "@chan" and not env.data["queue"]


def test_dead_coupon_not_posted(env, monkeypatch):
    env.data["pending"]["123"] = {"course": good_course().to_dict(), "preview_id": 7}
    fake = FakeTelegram([button("123", "p")])
    monkeypatch.setattr(run, "telegram", fake)
    def dead(c):
        c.price = 449.0
        return c
    monkeypatch.setattr(run.udemy, "verify", dead)
    run.handle_updates(env)
    assert all(chat != "@chan" for chat, _ in fake.sent) and not env.data["posted"]


def test_buttons_from_strangers_ignored(env, monkeypatch):
    env.data["pending"]["123"] = {"course": good_course().to_dict(), "preview_id": 7}
    upd = button("123", "p")
    upd["callback_query"]["message"]["chat"]["id"] = 999
    monkeypatch.setattr(run, "telegram", FakeTelegram([upd]))
    run.handle_updates(env)
    assert "123" in env.data["pending"]


def test_recheck_marks_expired(env, monkeypatch):
    old = (datetime.now().astimezone() - timedelta(hours=4)).isoformat()
    env.data["posted"].append({"course": good_course().to_dict(), "message_id": 55, "posted_at": old,
                               "checked_at": old, "expired": False})
    fake = FakeTelegram()
    monkeypatch.setattr(run, "telegram", fake)
    def ended(c):
        c.price = 449.0
        return c
    monkeypatch.setattr(run.udemy, "verify", ended)
    run.recheck_posted(env)
    assert env.data["posted"][0]["expired"] and "EXPIRED" in fake.edited[0][2]


def test_recheck_unknown_price_is_not_expiry(env, monkeypatch):
    old = (datetime.now().astimezone() - timedelta(hours=4)).isoformat()
    env.data["posted"].append({"course": good_course().to_dict(), "message_id": 55, "posted_at": old,
                               "checked_at": old, "expired": False})
    monkeypatch.setattr(run, "telegram", FakeTelegram())
    def unknown(c):
        c.price = None
        return c
    monkeypatch.setattr(run.udemy, "verify", unknown)
    run.recheck_posted(env)
    assert not env.data["posted"][0]["expired"]


def test_reply_edits_description(env, monkeypatch):
    env.data["pending"]["123"] = {"course": good_course().to_dict(), "preview_id": 7}
    fake = FakeTelegram([{"update_id": 1, "message": {"chat": {"id": 42}, "text": "Best NumPy intro",
                                                      "reply_to_message": {"message_id": 7}}}])
    monkeypatch.setattr(run, "telegram", fake)
    run.handle_updates(env)
    assert env.data["pending"]["123"]["course"]["headline"] == "Best NumPy intro"
    assert "Best NumPy intro" in fake.edited[0][2]
