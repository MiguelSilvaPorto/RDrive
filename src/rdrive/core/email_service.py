"""SMTP email delivery for recovery OTP codes."""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from rdrive.core.app_logger import get_app_logger
from rdrive.core.project_paths import resolve_project_root
from rdrive.core.recovery_profile import load_recovery_profile


@dataclass(slots=True)
class EmailSendResult:
    ok: bool
    message: str
    dev_mode: bool = False
    dev_log_path: Path | None = None


def _smtp_configured(profile: dict[str, Any]) -> bool:
    host = str(profile.get("smtp_host", "")).strip()
    user = str(profile.get("smtp_user", "")).strip()
    password = str(profile.get("smtp_password", ""))
    return bool(host and user and password)


def _dev_log_path() -> Path:
    return resolve_project_root() / "logs" / "password_reset_otp.log"


def _write_dev_log(email: str, code: str) -> Path:
    path = _dev_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    line = (
        f"{datetime.now().astimezone().isoformat()} "
        f"to={email} code={code}\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return path


def build_otp_email_pt(code: str) -> tuple[str, str]:
    subject = "Código de recuperação RDrive"
    body = (
        "Olá,\n\n"
        f"O seu código RDrive: {code}\n\n"
        "Este código expira em 10 minutos. Se não pediu esta recuperação, ignore este email.\n\n"
        "— RDrive"
    )
    return subject, body


def send_otp_email(
    to_email: str,
    code: str,
    *,
    profile: dict[str, Any] | None = None,
) -> EmailSendResult:
    to_email = to_email.strip()
    profile = profile or load_recovery_profile()

    if not _smtp_configured(profile):
        log_path = _write_dev_log(to_email, code)
        get_app_logger().info(
            f"[recovery] SMTP not configured — OTP logged to {log_path}",
            module="email_service",
        )
        return EmailSendResult(
            ok=True,
            message=(
                "SMTP não configurado. O código foi gravado em logs/password_reset_otp.log "
                "para testes locais."
            ),
            dev_mode=True,
            dev_log_path=log_path,
        )

    host = str(profile["smtp_host"]).strip()
    port = int(profile.get("smtp_port", 465) or 465)
    user = str(profile["smtp_user"]).strip()
    password = str(profile["smtp_password"])
    sender = str(profile.get("smtp_from", "")).strip() or user

    subject, body = build_otp_email_pt(code)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_email
    message.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001
        get_app_logger().log_exception("send_otp_email", exc, module="email_service")
        return EmailSendResult(False, f"Falha ao enviar email: {exc}")

    return EmailSendResult(ok=True, message="Código enviado por email.")
