"""
SMTP 이메일 발송 (Gmail 등). HTML 본문 + 인라인 차트 이미지.

설정(config) 딕셔너리 키:
  host      : SMTP 서버 (Gmail: smtp.gmail.com)
  port      : 465(SSL) 또는 587(STARTTLS)
  user      : 발신 계정 (Gmail 주소)
  password  : 앱 비밀번호 (16자리)
  sender    : 보내는 사람 주소 (기본 = user)
  recipients: 받는 사람 주소 리스트 또는 콤마 문자열
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr


def _as_list(recipients) -> list[str]:
    if isinstance(recipients, str):
        return [x.strip() for x in recipients.split(",") if x.strip()]
    return [x for x in recipients if x]


def validate_config(config: dict) -> list[str]:
    """누락된 필수 키 목록 반환(비어 있으면 정상)."""
    missing = []
    for key in ("host", "port", "user", "password", "recipients"):
        v = config.get(key)
        if v is None or (isinstance(v, str) and not v.strip()) or \
           (key == "recipients" and not _as_list(v)):
            missing.append(key)
    return missing


def send_report(config: dict, subject: str, html: str,
                chart_png: bytes | None = None, chart_cid: str = "chart") -> None:
    """리포트 메일 발송. 실패 시 예외 발생."""
    missing = validate_config(config)
    if missing:
        raise ValueError(f"메일 설정 누락: {', '.join(missing)}")

    sender = config.get("sender") or config["user"]
    recipients = _as_list(config["recipients"])

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = formataddr(("LG트윈스 모니터링", sender))
    msg["To"] = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("HTML 메일입니다. HTML 보기를 지원하는 클라이언트에서 확인하세요.", "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)

    if chart_png:
        img = MIMEImage(chart_png, _subtype="png")
        img.add_header("Content-ID", f"<{chart_cid}>")
        img.add_header("Content-Disposition", "inline", filename="response_times.png")
        msg.attach(img)

    port = int(config["port"])
    host = config["host"]
    if port == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
            server.login(config["user"], config["password"])
            server.sendmail(sender, recipients, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.login(config["user"], config["password"])
            server.sendmail(sender, recipients, msg.as_string())
