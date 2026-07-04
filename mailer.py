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


def clean_password(pw) -> str:
    """앱 비밀번호에서 모든 공백/개행/탭 제거 (붙여넣기 실수 방지)."""
    return "".join(str(pw).split())


def clean_addr(addr) -> str:
    """주소 앞뒤 공백·따옴표·개행 제거."""
    return str(addr).strip().strip('"').strip("'").strip()


def validate_config(config: dict) -> list[str]:
    """누락된 필수 키 목록 반환(비어 있으면 정상)."""
    missing = []
    for key in ("host", "port", "user", "password", "recipients"):
        v = config.get(key)
        if v is None or (isinstance(v, str) and not v.strip()) or \
           (key == "recipients" and not _as_list(v)):
            missing.append(key)
    return missing


# cid -> 다운로드 첨부 파일명
_ATTACH_NAME = {"charts": "charts_overview.png",
                "chart": "response_times.png", "donut": "status_distribution.png"}


def send_report(config: dict, subject: str, html: str,
                images: dict | None = None,
                chart_png: bytes | None = None, chart_cid: str = "chart",
                attach_downloadable: bool = True) -> None:
    """리포트 메일 발송. 실패 시 예외 발생.

    images: {cid: png_bytes} 형태의 인라인 이미지 모음 (HTML 의 cid:xxx 와 연결).
            하위호환용으로 chart_png/chart_cid 단일 인자도 지원.
    구조(multipart/mixed):
      - multipart/related : HTML 본문 + 인라인 이미지(cid) → 본문에 이미지가 보임
      - image/png(attachment) : 동일 이미지를 다운로드 첨부파일로도 제공
    """
    missing = validate_config(config)
    if missing:
        raise ValueError(f"메일 설정 누락: {', '.join(missing)}")

    # 이미지 인자 정규화
    imgs: dict = dict(images) if images else {}
    if chart_png and chart_cid not in imgs:
        imgs[chart_cid] = chart_png

    user = clean_addr(config["user"])
    password = clean_password(config["password"])
    sender = clean_addr(config.get("sender") or config["user"])
    recipients = _as_list(config["recipients"])

    root = MIMEMultipart("mixed")
    root["Subject"] = subject
    root["From"] = formataddr(("LG트윈스 모니터링", sender))
    root["To"] = ", ".join(recipients)

    # 1) HTML 본문 + 인라인 이미지
    related = MIMEMultipart("related")
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("HTML 메일입니다. HTML 보기를 지원하는 클라이언트에서 확인하세요.", "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    related.attach(alt)
    for cid, png in imgs.items():
        img = MIMEImage(png, _subtype="png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline",
                       filename=_ATTACH_NAME.get(cid, f"{cid}.png"))
        related.attach(img)
    root.attach(related)

    # 2) 다운로드용 PNG 첨부
    if attach_downloadable:
        for cid, png in imgs.items():
            att = MIMEImage(png, _subtype="png")
            att.add_header("Content-Disposition", "attachment",
                           filename=_ATTACH_NAME.get(cid, f"{cid}.png"))
            root.attach(att)

    port = int(config["port"])
    host = config["host"]
    if port == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
            server.login(user, password)
            server.sendmail(sender, recipients, root.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.sendmail(sender, recipients, root.as_string())
