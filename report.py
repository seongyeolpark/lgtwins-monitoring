"""
점검 결과 -> 이메일용 HTML 본문 + 차트 PNG 생성.
Streamlit 대시보드와 동일한 구성(다크 테마):
  배너 → 6지표 카드 → 페이지별 응답시간(막대) → 상태 분포(도넛) → 페이지별 상세표
matplotlib 는 헤드리스(Agg) 백엔드로 GitHub Actions / 클라우드에서 안전하게 동작.
"""
from __future__ import annotations

import io
import matplotlib
matplotlib.use("Agg")  # 반드시 pyplot import 전에
import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams
from matplotlib.colors import LinearSegmentedColormap, Normalize

from monitor import APP_URL, now_kst

LEVEL_COLOR = {"UP": "#2ecc71", "SLOW": "#f1c40f", "WARN": "#e67e22", "DOWN": "#e74c3c"}
LEVEL_LABEL = {"UP": "정상", "SLOW": "느림", "WARN": "경고", "DOWN": "장애"}

# 대시보드와 맞춘 다크 팔레트
BG = "#0e1117"       # 전체 배경
PANEL = "#1a1d24"    # 카드/표 배경
GRID = "#2a2e37"     # 경계선
TXT = "#e6e8eb"      # 기본 텍스트
MUTED = "#8b93a1"    # 보조 텍스트

# 응답시간 그라데이션(밝은 핑크 → 진한 크림슨): 느릴수록 진하게 강조 (대시보드 RESP_SCALE 와 동일)
RESP_CMAP = LinearSegmentedColormap.from_list(
    "resp", ["#fde4ee", "#f7a8c4", "#e0457e", "#c30452", "#7a0138"])
NODATA_COLOR = "#555a63"  # 응답시간 없음(접속 실패)


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
    data_targets = [r for r in results if r.data_min is not None]
    data_ok = sum(1 for r in data_targets if r.data_ok)
    return {
        "total": total, "up": up, "slow": slow, "warn": warn, "down": down,
        "healthy": healthy,
        "ratio": (healthy / total * 100) if total else 0,
        "avg_ms": (sum(valid_ms) / len(valid_ms)) if valid_ms else 0,
        "data_total": len(data_targets), "data_ok": data_ok,
        "data_fail": len(data_targets) - data_ok,
        "has_problem": (down + warn) > 0,
    }


def build_chart_png(results) -> bytes:
    """페이지별 응답시간 가로 막대 차트 PNG(bytes) — 다크 테마."""
    _apply_korean_font()
    return build_charts_png(results)


def _resp_colors(results):
    """응답시간 기반 그라데이션 색상 리스트. 응답 없음은 회색."""
    valid = [r.elapsed_ms for r in results if r.elapsed_ms is not None]
    vmin, vmax = (min(valid), max(valid)) if valid else (0.0, 1.0)
    norm = Normalize(vmin=vmin, vmax=vmax if vmax > vmin else vmin + 1)
    colors = []
    for r in results:
        if r.elapsed_ms is None:
            colors.append(NODATA_COLOR)
        else:
            colors.append(RESP_CMAP(norm(r.elapsed_ms)))
    return colors


def build_charts_png(results) -> bytes:
    """대시보드처럼 좌:응답시간 막대(그라데이션) + 우:상태 분포 도넛 을
    하나의 이미지에 가로로 나란히 렌더 — 다크 테마."""
    _apply_korean_font()
    names = [r.name for r in results]
    vals = [r.elapsed_ms if r.elapsed_ms is not None else 0 for r in results]
    colors = _resp_colors(results)

    fig = plt.figure(figsize=(11, max(4.5, len(results) * 0.34)), dpi=130)
    fig.patch.set_facecolor(BG)
    gs = fig.add_gridspec(1, 2, width_ratios=[3, 2], wspace=0.28)

    # 좌: 응답시간 막대 (그라데이션)
    ax = fig.add_subplot(gs[0, 0])
    ax.set_facecolor(BG)
    y = range(len(names))
    ax.barh(list(y), vals, color=colors)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=9, color=TXT)
    ax.invert_yaxis()
    ax.set_xlabel("응답시간 (ms)", fontsize=9, color=MUTED)
    ax.tick_params(axis="x", colors=MUTED)
    ax.set_title("페이지별 응답시간", fontsize=12, fontweight="bold", color=TXT, loc="left")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:.0f}", va="center", fontsize=7.5, color=TXT)
    ax.grid(axis="x", alpha=0.15, color=GRID)
    for spine in ax.spines.values():
        spine.set_color(GRID)

    # 우: 상태 분포 도넛
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor(BG)
    counts = {}
    for r in results:
        counts[r.level] = counts.get(r.level, 0) + 1
    labels, values, dcolors = [], [], []
    for lv in ("UP", "SLOW", "WARN", "DOWN"):
        if counts.get(lv):
            labels.append(f"{LEVEL_LABEL[lv]} {counts[lv]}")
            values.append(counts[lv])
            dcolors.append(LEVEL_COLOR[lv])
    ax2.pie(
        values, labels=labels, colors=dcolors, startangle=90,
        wedgeprops=dict(width=0.42, edgecolor=BG, linewidth=2),
        textprops=dict(color=TXT, fontsize=10),
    )
    ax2.text(0, 0, f"{sum(values)}\n페이지", ha="center", va="center",
             color=TXT, fontsize=13, fontweight="bold")
    ax2.set_aspect("equal")
    ax2.set_title("상태 분포", fontsize=12, fontweight="bold", color=TXT)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()


def _metric_card(label: str, value: str, color: str = TXT) -> str:
    return f"""<td style="padding:12px 10px;background:{PANEL};border-radius:10px;
      text-align:center;">
      <div style="font-size:12px;color:{MUTED};margin-bottom:4px;">{label}</div>
      <div style="font-size:22px;font-weight:bold;color:{color};">{value}</div></td>"""


def build_report(results, base_url: str):
    """대시보드와 동일한 형태의 메일을 구성한다.
    반환: (subject, html, images)  images = {cid: png_bytes}
    """
    s = summarize(results)
    now = now_kst().strftime("%Y-%m-%d %H:%M:%S") + " KST"

    if s["down"] > 0:
        banner_bg = "#e74c3c"
        banner_txt = f"🔴 장애 감지 {s['down']}건 · 가용률 {s['ratio']:.1f}%"
        subject = f"[LG트윈스 모니터링] 🔴 장애 {s['down']}건 발생 ({now})"
    elif s["warn"] > 0:
        banner_bg = "#e67e22"
        extra = f" (데이터 미출력 {s['data_fail']}건 포함)" if s["data_fail"] else ""
        banner_txt = f"🟠 경고 {s['warn']}건{extra} · 가용률 {s['ratio']:.1f}%"
        subject = f"[LG트윈스 모니터링] 🟠 경고 {s['warn']}건 ({now})"
    elif s["slow"] > 0:
        banner_bg = "#b7950b"
        banner_txt = f"🟡 응답 지연 {s['slow']}건 · 화면·데이터 모두 정상"
        subject = f"[LG트윈스 모니터링] 🟡 지연 {s['slow']}건 ({now})"
    else:
        banner_bg = "#2ecc71"
        banner_txt = f"🟢 모든 페이지 정상 · 화면·데이터 이상 없음 · 가용률 {s['ratio']:.1f}%"
        subject = f"[LG트윈스 모니터링] 🟢 전체 정상 ({now})"

    # 지표 카드 6개 (대시보드와 동일)
    cards = "".join([
        _metric_card("전체 페이지", f"{s['total']}개"),
        '<td style="width:8px;"></td>',
        _metric_card("정상 가동", f"{s['healthy']}개", "#2ecc71"),
        '<td style="width:8px;"></td>',
        _metric_card("데이터 정상", f"{s['data_ok']}/{s['data_total']}",
                     "#e74c3c" if s["data_fail"] else TXT),
        '<td style="width:8px;"></td>',
        _metric_card("평균 응답시간", f"{s['avg_ms']:.0f}ms"),
        '<td style="width:8px;"></td>',
        _metric_card("느림/경고", f"{s['slow'] + s['warn']}개",
                     "#e67e22" if (s["slow"] + s["warn"]) else TXT),
        '<td style="width:8px;"></td>',
        _metric_card("장애", f"{s['down']}개", "#e74c3c" if s["down"] else TXT),
    ])

    # 페이지별 상세표 (대시보드 컬럼 구성)
    rows = []
    for i, r in enumerate(results):
        c = LEVEL_COLOR.get(r.level, "#888")
        rowbg = PANEL if i % 2 == 0 else "#161920"
        size_kb = f"{r.content_bytes / 1024:.1f}" if r.content_bytes else "-"
        render_ok = "✔" if r.content_ok else "✖"
        data_cell = f"{'✔' if r.data_ok else '✖'} {r.data_count}건" if r.data_count is not None else "-"
        rows.append(f"""
        <tr style="background:{rowbg};">
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};white-space:nowrap;">
            <span style="display:inline-block;width:9px;height:9px;border-radius:50%;
              background:{c};margin-right:6px;"></span>{LEVEL_LABEL.get(r.level, r.level)}</td>
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};">{r.name}</td>
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};color:{MUTED};">{r.category}</td>
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};text-align:center;">{r.status_code or '-'}</td>
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};text-align:right;">{(f'{r.elapsed_ms:.0f}' if r.elapsed_ms is not None else '-')}</td>
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};text-align:right;color:{MUTED};">{size_kb}</td>
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};text-align:center;">{render_ok}</td>
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};text-align:center;">{data_cell}</td>
          <td style="padding:7px 9px;border-bottom:1px solid {GRID};color:{MUTED};">{r.message}</td>
        </tr>""")

    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="margin:0;background:{BG};
      font-family:'Malgun Gothic','Apple SD Gothic Neo',AppleGothic,sans-serif;color:{TXT};">
    <div style="max-width:820px;margin:0 auto;padding:22px;">
      <h2 style="margin:0 0 4px;color:{TXT};">⚾ LG 트윈스 홈페이지 모니터링</h2>
      <div style="margin:2px 0 6px;font-size:13px;">
        🔗 <a href="{APP_URL}" style="color:#6db3ff;text-decoration:none;">{APP_URL}</a></div>
      <div style="color:{MUTED};font-size:12px;margin-bottom:16px;">
        마지막 점검 {now} · 대상 {base_url}</div>

      <div style="background:{banner_bg};color:#fff;padding:13px 16px;border-radius:10px;
        font-weight:bold;font-size:15px;">{banner_txt}</div>

      <table style="width:100%;margin:16px 0;border-collapse:separate;">
        <tr>{cards}</tr>
      </table>

      <img src="cid:charts" style="width:100%;border-radius:10px;background:{BG};margin-top:18px;" alt="응답시간·상태분포 차트"/>

      <div style="font-size:16px;font-weight:bold;margin:22px 0 8px;color:{TXT};">페이지별 상세</div>
      <table style="width:100%;border-collapse:collapse;background:{PANEL};
        border-radius:10px;overflow:hidden;font-size:13px;color:{TXT};">
        <thead>
          <tr style="background:#12141a;color:{TXT};text-align:left;">
            <th style="padding:8px 9px;">상태</th><th style="padding:8px 9px;">페이지</th>
            <th style="padding:8px 9px;">분류</th>
            <th style="padding:8px 9px;text-align:center;">HTTP</th>
            <th style="padding:8px 9px;text-align:right;">응답(ms)</th>
            <th style="padding:8px 9px;text-align:right;">크기(KB)</th>
            <th style="padding:8px 9px;text-align:center;">렌더</th>
            <th style="padding:8px 9px;text-align:center;">데이터</th>
            <th style="padding:8px 9px;">메시지</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>

      <div style="color:{MUTED};font-size:11px;margin-top:16px;">
        본 메일은 LG트윈스 모니터링 대시보드에서 자동 발송되었습니다.</div>
    </div></body></html>"""

    images = {"charts": build_charts_png(results)}
    return subject, html, images
