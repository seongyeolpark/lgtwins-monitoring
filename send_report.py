"""
독립 실행 점검+메일 스크립트. GitHub Actions cron / 로컬 예약작업에서 호출.

사용:
    python send_report.py --mode scheduled   # 항상 리포트 발송(정기)
    python send_report.py --mode alert       # 문제(장애/경고)가 있을 때만 발송

SMTP 설정은 환경변수에서 읽는다:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_TO, [MAIL_FROM]
"""
from __future__ import annotations

import argparse
import os
import sys

from mailer import send_report, validate_config
from monitor import BASE_URL, check_all
from report import build_chart_png, build_html, summarize


def config_from_env() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": os.environ.get("SMTP_PORT", "465"),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "sender": os.environ.get("MAIL_FROM", "") or os.environ.get("SMTP_USER", ""),
        "recipients": os.environ.get("MAIL_TO", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["scheduled", "alert"], default="scheduled")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--verify", action="store_true", help="SSL 인증서 검증 활성화")
    args = parser.parse_args()

    config = config_from_env()
    missing = validate_config(config)
    if missing:
        print(f"[ERROR] SMTP 환경변수 누락: {', '.join(missing)}", file=sys.stderr)
        return 2

    print(f"[INFO] 점검 시작 (mode={args.mode}, verify={args.verify})")
    results = check_all(timeout=args.timeout, verify=args.verify)
    s = summarize(results)
    print(f"[INFO] 전체 {s['total']} · 정상 {s['healthy']} · 경고 {s['warn']} · "
          f"장애 {s['down']} · 가용률 {s['ratio']:.1f}%")

    # alert 모드는 문제가 없으면 메일 생략
    if args.mode == "alert" and not s["has_problem"]:
        print("[INFO] 이상 없음 → alert 메일 생략")
        return 0

    subject, html = build_html(results, BASE_URL)
    chart = build_chart_png(results)
    send_report(config, subject, html, chart_png=chart)
    print(f"[INFO] 메일 발송 완료 → {config['recipients']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
