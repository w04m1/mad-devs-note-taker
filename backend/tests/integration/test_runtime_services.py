from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import websockets
from redis import Redis
from sqlalchemy import select, text

from app.api.router import delete_note
from app.db.models import DeliveryState, OutboxEvent, ReminderDelivery, ReminderRule
from app.db.session import async_session_factory, sync_session_factory
from app.email.senders import SMTPEmailSender
from app.jobs.celery_app import publish_outbox
from app.jobs.reminders import authorize_delivery, claim_due, deliver
from tests.integration.test_background_jobs import make_delivery

pytestmark = [
    pytest.mark.skipif(
        "TEST_DATABASE_URL" not in os.environ, reason="isolated PostgreSQL required"
    ),
    pytest.mark.runtime,
]


@pytest.fixture(autouse=True)
def clean_database() -> None:
    with sync_session_factory() as session, session.begin():
        session.execute(
            text(
                "TRUNCATE outbox_events, notifications, reminder_deliveries, reminder_rules, occurrence_exceptions, series_reminder_templates, series_tags, note_tags, notes, recurrence_series, tags, user_settings CASCADE"
            )
        )


def _redis() -> Redis:
    return Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def _free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_port(port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise AssertionError(f"uvicorn did not listen on {port}")


async def test_redis_fans_one_event_to_two_uvicorn_processes() -> None:
    """Each process owns a subscriber; Redis must reach clients connected to both."""
    ports = [_free_port(), _free_port()]
    processes = [
        subprocess.Popen(  # noqa: ASYNC220
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        for port in ports
    ]
    try:
        await asyncio.gather(*(_wait_port(port) for port in ports))
        async with (
            websockets.connect(f"ws://127.0.0.1:{ports[0]}/ws") as first,
            websockets.connect(f"ws://127.0.0.1:{ports[1]}/ws") as second,
        ):
            # Give both independent Redis subscriptions time to become active.
            await asyncio.sleep(0.25)
            event_id = str(uuid.uuid4())
            payload = json.dumps({"event_id": event_id, "type": "qa.fanout", "version": 1})
            assert _redis().publish("notetaker.events", payload) >= 2
            received = await asyncio.gather(
                asyncio.wait_for(first.recv(), 3), asyncio.wait_for(second.recv(), 3)
            )
            assert {json.loads(item)["event_id"] for item in received} == {event_id}
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def test_real_mailpit_smtp_records_exactly_one_message() -> None:
    api = os.getenv("MAILPIT_API_URL", "http://mailpit:8025")
    with httpx.Client(base_url=api, timeout=5) as client:
        client.delete("/api/v1/messages")
    now = datetime.now(UTC)
    delivery_id = make_delivery(due_at=now - timedelta(seconds=1))
    with sync_session_factory() as session, session.begin():
        [(_, token)] = claim_due(session, now=now, grace_seconds=60, lease_seconds=30)
    sender = SMTPEmailSender(
        host=os.environ["SMTP_HOST"],
        port=int(os.environ.get("SMTP_PORT", "1025")),
        sender="qa@example.test",
        timeout=5,
    )
    assert deliver(str(delivery_id), str(token), sender) is True
    assert deliver(str(delivery_id), str(token), sender) is False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        messages = httpx.get(f"{api}/api/v1/messages", timeout=5).json()["messages"]
        if messages:
            break
        time.sleep(0.05)
    assert len(messages) == 1
    assert messages[0]["To"][0]["Address"] == "demo@example.test"
    with sync_session_factory() as session:
        assert session.get(ReminderDelivery, delivery_id).state == DeliveryState.sent


@pytest.mark.celery
def test_real_celery_worker_publishes_outbox_through_redis() -> None:
    if os.getenv("RUN_CELERY_INTEGRATION") != "1":
        pytest.skip("qa-services starts a worker and sets RUN_CELERY_INTEGRATION=1")
    event_id = uuid.uuid4()
    with sync_session_factory() as session, session.begin():
        session.add(
            OutboxEvent(
                id=event_id,
                event_type="qa.celery",
                payload={
                    "event_id": str(event_id),
                    "type": "qa.celery",
                    "version": 1,
                },
            )
        )
    result = publish_outbox.delay()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with sync_session_factory() as session:
            row = session.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id))
            if row is not None and row.published_at is not None:
                break
        time.sleep(0.1)
    assert row is not None and row.published_at is not None
    assert result.id


def test_concurrent_authorization_has_one_winner() -> None:
    """The row lock is the final race boundary before irreversible SMTP."""

    now = datetime.now(UTC)
    delivery_id = make_delivery(due_at=now - timedelta(seconds=1))
    with sync_session_factory() as session, session.begin():
        [(_, token)] = claim_due(session, now=now, grace_seconds=60, lease_seconds=30)

    def authorize() -> bool:
        with sync_session_factory() as session, session.begin():
            return (
                authorize_delivery(session, delivery_id, token, now=now, grace_seconds=60)
                is not None
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: authorize(), range(2))) == [False, True]
    with sync_session_factory() as session:
        assert session.execute(text("SELECT count(*) FROM notifications")).scalar_one() == 1


async def test_authorization_and_delete_race_serializes_across_sessions() -> None:
    """Deletion and final SMTP authorization share the note row lock."""
    now = datetime.now(UTC)
    delivery_id = make_delivery(due_at=now - timedelta(seconds=1))
    with sync_session_factory() as session, session.begin():
        [(_, token)] = claim_due(session, now=now, grace_seconds=60, lease_seconds=30)
        delivery = session.get(ReminderDelivery, delivery_id)
        note_id = session.get(ReminderRule, delivery.reminder_rule_id).note_id

    def authorize():
        with sync_session_factory() as session, session.begin():
            return authorize_delivery(
                session, delivery_id, token, now=now, grace_seconds=60
            )

    async def delete() -> None:
        async with async_session_factory() as session:
            response = await delete_note(
                note_id, session, expected_version=1, expected_series_version=None
            )
            assert response.status_code == 204

    email, _ = await asyncio.gather(asyncio.to_thread(authorize), delete())
    with sync_session_factory() as session:
        delivery = session.get(ReminderDelivery, delivery_id)
        notification_count = session.execute(
            text("SELECT count(*) FROM notifications")
        ).scalar_one()
        if email is None:
            assert delivery.state == DeliveryState.cancelled
            assert notification_count == 0
        else:
            assert delivery.state == DeliveryState.attempt_started
            assert notification_count == 1
