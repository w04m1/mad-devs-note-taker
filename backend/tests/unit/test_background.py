from __future__ import annotations

import asyncio
import json

from app.email.senders import Email, FakeEmailSender, SMTPEmailSender
from app.jobs.celery_app import celery_app
from app.realtime.broker import ConnectionManager


def test_beat_schedule_and_registered_tasks() -> None:
    schedule = celery_app.conf.beat_schedule
    assert set(schedule) == {
        "discover-due-reminders",
        "publish-outbox",
        "delivery-maintenance",
        "trash-cleanup",
    }
    assert schedule["delivery-maintenance"]["schedule"] == 60
    assert "app.jobs.deliver_reminder" in celery_app.tasks


def test_fake_sender_records_one_attempt_even_on_failure() -> None:
    sender = FakeEmailSender(RuntimeError("no smtp"))
    email = Email("to@example.test", "subject", "body", "<stable@example.test>")
    try:
        sender.send(email)
    except RuntimeError:
        pass
    assert sender.messages == [email]


def test_smtp_adapter_builds_message_and_uses_config(monkeypatch) -> None:
    calls: list[object] = []

    class SMTP:
        def __init__(self, host, port, timeout):
            calls.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self):
            calls.append("tls")

        def login(self, username, password):
            calls.append((username, password))

        def send_message(self, message):
            calls.append(message)

    monkeypatch.setattr("app.email.senders.smtplib.SMTP", SMTP)
    SMTPEmailSender(
        host="smtp",
        port=25,
        sender="from@example.test",
        username="u",
        password="p",
        starttls=True,
        timeout=3,
    ).send(Email("to@example.test", "Reminder", "hello", "<id@example.test>"))
    assert calls[:3] == [("smtp", 25, 3), "tls", ("u", "p")]
    message = calls[3]
    assert message["Message-ID"] == "<id@example.test>"
    assert message["To"] == "to@example.test"


class Socket:
    def __init__(self, broken: bool = False):
        self.messages, self.broken = [], broken

    async def accept(self):
        pass

    async def send_text(self, message):
        if self.broken:
            raise RuntimeError("closed")
        self.messages.append(json.loads(message))


def test_connection_manager_fanout_and_recovery_event() -> None:
    async def scenario():
        manager, first, second, broken = ConnectionManager(), Socket(), Socket(), Socket(True)
        await manager.connect(first)  # type: ignore[arg-type]
        await manager.connect(second)  # type: ignore[arg-type]
        await manager.connect(broken)  # type: ignore[arg-type]
        await manager.broadcast('{"event_id":"one","type":"note.updated"}')
        await manager.resync_required()
        assert [m["type"] for m in first.messages] == ["note.updated", "resync_required"]
        assert second.messages == first.messages
        assert len(manager._connections) == 2

    asyncio.run(scenario())
