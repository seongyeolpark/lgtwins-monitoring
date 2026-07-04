"""
점검 결과 -> 이메일용 HTML 본문 + 차트 PNG 생성.
matplotlib 는 헤드리스(Agg) 백엔드로 GitHub Actions / 클라우드에서 안전하게 동작.
"""
from __future__ import annotations

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # 반드시 pyplot import 전에
import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams

LEVEL_COLOR = {"UP": "#2ecc71", "SLOW": "#f1c40f", "WARN": "#e67e22", "DOWN": "#e74c3c"}
LEVEL_LABEL = {"UP": "정상", "SLOW": "느림", "WARN": "경고", "DOWN": "장애"}


def _apply_korean_font():
    """한글 깨짐 방지: 시스템에 있는 한글 폰트를 찾아 지정.

    1) 잘 알려진 한글 폰트 패밀리명이 등록돼 있으면 사용
    2) 없으면 폰트 파일 경로를 직접 찾아 addfont 로 등록 (리눅스/클라우드 대비)
    """
    candidates = ["Malgun Gothic", "NanumGothic", "NanumGothicCoding",
                  "NanumBarunGothic", "AppleGothic",
                  "Noto Sans CJK KR", "Noto Sans KR", "Noto Sans CJK JP"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((n for n in candidates if n in available), None)

    if chosen is None:
        import glob
        patterns = [
            "/usr/share/fonts/**/Nanum*.ttf",
            "/usr/share/fonts/**/NotoSansCJK*.*",
            "/usr/share/fonts/**/NotoSansKR*.*",
            "/usr/share/fonts/truetype/nanum/*.ttf",
        ]
        for pat in patterns:
            for path in glob.glob(pat, recursive=True):
                try:
                    font_manager.fontManager.addfont(path)
                    chosen = font_manager.FontProperties(fname=path).get_name()
                    break
                except Exception:  # noqa: BLE001
                    continue
            if chosen:
                break

    if chosen:
        rcParams["font.family"] = chosen
    rcParams["axes.unicode_minus"] = False
    return chosen


def summarize(results) -> dict:
    total = len(results)
    up = sum(1 for r in results if r.level == "UP")
    slow = sum(1 for r in results if r.level == "SLOW")
    warn = sum(1 for r in results if r.level == "WARN")
    down = sum(1 for r in results if r.level == "DOWN")
    healthy = up + slow
    valid_ms = [r.elapsed_ms for r in results if r.elapsed_ms is not None]
    return {
        "total": total, "up": up, "slow": slow, "warn": warn, "down": down,
        "healthy": healthy,
        "ratio": (healthy / total * 100) if total else 0,
        "avg_ms": (sum(valid_ms) / len(valid_ms)) if valid_ms else 0,
        "has_problem": (down + warn) > 0,
    }


def build_chart_png(results) -> bytes:
    """페이지별 응답시간 가로 막대 차트 PNG(bytes)."""
    _apply_korean_font()
    names = [r.name for r in results]
    vals = [r.elapsed_ms if r.elapsed_ms is not None else 0 for r in results]
    colors = [LEVEL_COLOR.get(r.level, "#888") for r in results]

    fig, ax = plt.subplots(figsize=(8, max(3, len(results) * 0.34)), dpi=130)
    y = range(len(names))
    ax.barh(list(y), vals, color=colors)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("응답시간 (ms)", fontsize=9)
    ax.set_title("페이지별 응답시간", fontsize=11, fontweight="bold")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:.0f}", va="center", fontsize=7.5)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def build_html(results, base_url: str, chart_cid: str = "chart") -> tuple[str, str]:
    """HTML 본문과 제목을 만든다. chart_cid 는 인라인 이미지 참조용."""
    s = summarize(results)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if s["down"] > 0:
        banner_bg, banner_txt = "#e74c3c", f"🔴 장애 감지 {s['down']}건 · 가용률 {s['ratio']:.1f}%"
        subject = f"[LG트윈스 모니터링] 🔴 장애 {s['down']}건 발생 ({now})"
    elif s["warn"] > 0:
        banner_bg, banner_txt = "#e67e22", f"🟠 경고 {s['warn']}건(데이터/화면 이상) · 가용률 {s['ratio']:.1f}%"
        subject = f"[LG트윈스 모니터링] 🟠 경고 {s['warn']}건 ({now})"
    elif s["slow"] > 0:
        banner_bg, banner_txt = "#b7950b", f"🟡 응답 지연 {s['slow']}건 · 그 외 정상"
        subject = f"[LG트윈스 모니터링] 🟡 지연 {s['slow']}건 ({now})"
    else:
        banner_bg, banner_txt = "#2ecc71", f"🟢 모든 페이지 정상 · 가용률 {s['ratio']:.1f}%"
        subject = f"[LG트윈스 모니터링] 🟢 전체 정상 ({now})"

    rows = []
    for r in results:
        c = LEVEL_COLOR.get(r.level, "#888")
        data_cell = (f"{r.data_count}건" if r.data_count is not None else "-")
        rows.append(f"""
        <tr>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;">
            <span style="display:inline-block;width:9px;height:9px;border-radius:50%;
              background:{c};margin-right:6px;"></span>{LEVEL_LABEL.get(r.level, r.level)}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;">{r.name}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:center;">{r.status_code or '-'}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{(f'{r.elapsed_ms:.0f}' if r.elapsed_ms is not None else '-')}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">{data_cell}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #eee;color:#555;">{r.message}</td>
        </tr>""")

    html = f"""<!DOCTYPE html><html><body style="margin:0;background:#f4f5f7;
      font-family:'Malgun Gothic',AppleGothic,sans-serif;">
    <div style="max-width:760px;margin:0 auto;padding:20px;">
      <h2 style="margin:0 0 4px;color:#111;">⚾ LG 트윈스 홈페이지 모니터링</h2>
      <div style="color:#888;font-size:12px;margin-bottom:14px;">
        점검 시각 {now} · 대상 {base_url}</div>

      <div style="background:{banner_bg};color:#fff;padding:12px 16px;border-radius:8px;
        font-weight:bold;font-size:15px;">{banner_txt}</div>

      <table style="width:100%;margin:16px 0;border-collapse:collapse;text-align:center;">
        <tr>
          <td style="padding:10px;background:#fff;border-radius:8px;">
            <div style="font-size:12px;color:#888;">전체</div>
            <div style="font-size:22px;font-weight:bold;">{s['total']}</div></td>
          <td style="width:8px;"></td>
          <td style="padding:10px;background:#fff;border-radius:8px;">
            <div style="font-size:12px;color:#888;">정상 가동</div>
            <div style="font-size:22px;font-weight:bold;color:#2ecc71;">{s['healthy']}</div></td>
          <td style="width:8px;"></td>
          <td style="padding:10px;background:#fff;border-radius:8px;">
            <div style="font-size:12px;color:#888;">평균 응답</div>
            <div style="font-size:22px;font-weight:bold;">{s['avg_ms']:.0f}ms</div></td>
          <td style="width:8px;"></td>
          <td style="padding:10px;background:#fff;border-radius:8px;">
            <div style="font-size:12px;color:#888;">장애</div>
            <div style="font-size:22px;font-weight:bold;color:#e74c3c;">{s['down']}</div></td>
        </tr>
      </table>

      <img src="cid:{chart_cid}" style="width:100%;border-radius:8px;background:#fff;" alt="응답시간 차트"/>

      <table style="width:100%;margin-top:16px;border-collapse:collapse;background:#fff;
        border-radius:8px;overflow:hidden;font-size:13px;">
        <thead>
          <tr style="background:#1a1d24;color:#fff;text-align:left;">
            <th style="padding:8px;">상태</th><th style="padding:8px;">페이지</th>
            <th style="padding:8px;text-align:center;">HTTP</th>
            <th style="padding:8px;text-align:right;">응답(ms)</th>
            <th style="padding:8px;text-align:right;">데이터</th>
            <th style="padding:8px;">메시지</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>

      <div style="color:#aaa;font-size:11px;margin-top:14px;">
        본 메일은 LG트윈스 모니터링 대시보드에서 자동 발송되었습니다.</div>
    </div></body></html>"""
    return subject, html
