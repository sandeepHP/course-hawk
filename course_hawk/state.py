"""State kept in one JSON file. GitHub Actions commits it back after each run, so no database
or server is needed."""

import json
import os
from datetime import datetime, timedelta, timezone

from .models import Course

EMPTY = {
    "update_offset": 0,
    "seen": {},      # course key -> ISO time last offered or skipped (for dedupe)
    "pending": {},   # course key -> {"course": {...}, "preview_id": int}
    "queue": [],     # approved: [{"course": {...}, "preview_id": int, "urgent": bool}]
    "posted": [],    # [{"course": {...}, "message_id": int, "posted_at": iso, "expired": bool}]
    "slots_done": {},  # "YYYY-MM-DD HH:MM" -> true
}


def now() -> datetime:
    return datetime.now(timezone.utc)


class State:
    def __init__(self, path: str):
        self.path = path
        data = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.data = {**json.loads(json.dumps(EMPTY)), **data}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    def seen_recently(self, key: str, days: int) -> bool:
        when = self.data["seen"].get(key)
        return bool(when) and now() - datetime.fromisoformat(when) < timedelta(days=days)

    def mark_seen(self, key: str) -> None:
        self.data["seen"][key] = now().isoformat()

    def prune(self, dedupe_days: int, recheck_days: int) -> None:
        cutoff = now() - timedelta(days=max(dedupe_days, recheck_days) + 1)
        self.data["seen"] = {k: v for k, v in self.data["seen"].items() if datetime.fromisoformat(v) > cutoff}
        self.data["posted"] = [p for p in self.data["posted"] if datetime.fromisoformat(p["posted_at"]) > cutoff]
        day_cut = (now() - timedelta(days=3)).strftime("%Y-%m-%d")
        self.data["slots_done"] = {k: v for k, v in self.data["slots_done"].items() if k[:10] >= day_cut}

    @staticmethod
    def course(entry: dict) -> Course:
        return Course.from_dict(entry["course"])
