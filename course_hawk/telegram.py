"""Minimal Telegram Bot API client."""

import json
import logging

import requests

from . import config

log = logging.getLogger(__name__)


def _call(method: str, **params) -> dict:
    if config.DRY_RUN and (method != "getUpdates" or not config.BOT_TOKEN):
        if method == "getUpdates":
            return []
        log.info("[dry run] %s %s", method, json.dumps(params, ensure_ascii=False)[:300])
        return {"message_id": 0}
    resp = requests.post(f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}", json=params, timeout=30)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram {method}: {data.get('description')}")
    return data["result"]


def send(chat_id: str, text: str, buttons: list[list[dict]] | None = None) -> int:
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    return _call("sendMessage", **params)["message_id"]


def edit(chat_id: str, message_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
    params = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True}
    if buttons is not None:
        params["reply_markup"] = {"inline_keyboard": buttons}
    try:
        _call("editMessageText", **params)
    except RuntimeError as e:
        if "message is not modified" not in str(e):
            raise


def updates(offset: int) -> list[dict]:
    return _call("getUpdates", offset=offset, timeout=0, allowed_updates=["message", "callback_query"])


def answer(callback_id: str, text: str = "") -> None:
    try:
        _call("answerCallbackQuery", callback_query_id=callback_id, text=text)
    except RuntimeError as e:  # old callbacks expire; harmless
        log.info("answerCallbackQuery: %s", e)
