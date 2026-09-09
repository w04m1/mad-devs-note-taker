from __future__ import annotations

import smtplib
import threading
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


@dataclass(frozen=True)
class Email:
    recipient: str
    subject: str
    body: str
    message_id: str


class EmailSender(Protocol):
    def send(self, email: Email) -> None: ...


class SMTPEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str = "",
        password: str = "",
        starttls: bool = False,
        timeout: float = 10,
    ) -> None:
        self.host, self.port, self.sender = host, port, sender
        self.username, self.password = username, password
        self.starttls, self.timeout = starttls, timeout

    def send(self, email: Email) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = email.recipient
        message["Subject"] = email.subject
        message["Message-ID"] = email.message_id
        message.set_content(email.body)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


class FakeEmailSender:
    """Deterministic, thread-safe test adapter."""

    def __init__(self, error: Exception | None = None) -> None:
        self.messages: list[Email] = []
        self.error = error
        self._lock = threading.Lock()

    def send(self, email: Email) -> None:
        with self._lock:
            self.messages.append(email)
        if self.error:
            raise self.error
