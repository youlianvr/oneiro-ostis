"""Telegram translates messages, not agent logic. One poller owns this bot."""
from __future__ import annotations

import json
import urllib.request


class Telegram:
    def __init__(self, service, token: str, owner_id: int, transport=None):
        self.service = service
        self.token = token
        self.owner_id = int(owner_id)
        self.transport = transport or self._call

    def _call(self, method, payload):
        request = urllib.request.Request(f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                answer = json.loads(response.read(2_000_000))
        except Exception as exc:
            # urllib's exception can contain the full URL and therefore bot token.
            raise RuntimeError("Telegram transport failed") from None
        if not answer.get("ok"):
            raise RuntimeError("Telegram refused " + method)
        return answer.get("result")

    def offset(self):
        rows = [e for e in self.service.memory.events() if e["kind"] == "telegram_offset"]
        return rows[-1]["data"]["offset"] if rows else 0

    def poll(self):
        rows = self.transport("getUpdates", {"offset": self.offset(), "timeout": 0,
            "limit": 50, "allowed_updates": ["message", "callback_query"]}) or []
        for update in rows:
            callback = update.get("callback_query")
            message = update.get("message")
            if callback and callback.get("from", {}).get("id") == self.owner_id:
                if callback.get("message", {}).get("chat", {}).get("id") == self.owner_id:
                    data = callback.get("data", "")
                    if data.startswith(("yes:", "no:")):
                        identifier = data.split(":", 1)[1]
                        try:
                            self.service.decide(identifier, data.startswith("yes:"))
                        except ValueError:
                            pass  # stale press, no second effect
                    self.transport("answerCallbackQuery", {"callback_query_id": callback["id"]})
            if message and message.get("from", {}).get("id") == self.owner_id and message.get("chat", {}).get("id") == self.owner_id:
                text = message.get("text") or message.get("caption") or ""
                if text.strip():
                    reply = message.get("reply_to_message") or {}
                    if reply:
                        text = "Reply to: " + str(reply.get("text") or reply.get("caption") or "")[:6000] + "\n\n" + text
                    # Media is not claimed to have been analysed by this text adapter.
                    if message.get("video") or message.get("photo") or message.get("document"):
                        text += "\n[Attachment received; native media inspection is not connected.]"
                    self.service.message(text, channel="telegram", external_id=str(update["update_id"]),
                                         reply_to=str(reply.get("message_id") or ""))
            # Acknowledge only after persistence. No prime/drop of queued owner work.
            self.service.emit("telegram_offset", "runtime", {"offset": int(update["update_id"]) + 1})

    def flush(self):
        delivered = self.service.memory.latest("telegram_delivery")
        messages = [row for row in self.service.messages("owner") if row["side"] == "manager"]
        for row in messages:
            if "message:" + row["id"] in delivered:
                continue
            # Chunk by unicode characters well below Telegram's UTF-16 limit.
            parts = [row["text"][i:i+1800] for i in range(0, len(row["text"]), 1800)]
            for index, text in enumerate(parts):
                key = f"part:{row['id']}:{index}"
                if key in delivered:
                    continue
                self.transport("sendMessage", {"chat_id": self.owner_id, "text": text})
                self.service.emit("telegram_delivery", "runtime", {"id": key})
            self.service.emit("telegram_delivery", "runtime", {"id": "message:" + row["id"]})
        for row in self.service.memory.latest("approval").values():
            key = "approval:" + row["id"]
            if row["status"] != "pending" or key in delivered:
                continue
            self.transport("sendMessage", {"chat_id": self.owner_id,
                "text": (row["reason"] + "\n" + row["tool"] + "\n" + json.dumps(row["args"], ensure_ascii=False))[:1800],
                "reply_markup": {"inline_keyboard": [[
                    {"text": "Approve exact action", "callback_data": "yes:" + row["id"]},
                    {"text": "Reject", "callback_data": "no:" + row["id"]}]]}})
            self.service.emit("telegram_delivery", "runtime", {"id": key})
        for row in self.service.memory.latest("question").values():
            key = "question:" + row["id"]
            if row["status"] == "open" and key not in delivered:
                sent = self.transport("sendMessage", {"chat_id": self.owner_id,
                    "text": row["question"][:1800]})
                self.service.emit("telegram_delivery", "runtime", {"id": key,
                    "question_id": row["id"], "message_id": (sent or {}).get("message_id")})
