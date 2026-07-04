"""
LG 트윈스 (www.lgtwins.com) 실시간 모니터링 대시보드.

실행:
    streamlit run app.py
"""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from monitor import BASE_URL, TARGETS, check_all
from mailer import send_report, validate_config
from report import build_chart_png, build_html

st.set_page_config(
    page_title="LG트윈스 모니터링",
    page_icon="⚾",
    layout="wide",
)

# ---------------------------------------------------------------- 상태 스타일
LEVEL_COLOR = {"UP": "#2ecc71", "SLOW": "#f1c40f", "WARN": "#e67e22", "DOWN": "#e74c3c"}
LEVEL_EMOJI = {"UP": "🟢", "SLOW": "🟡", "WARN": "🟠", "DOWN": "🔴"}
LEVEL_LABEL = {"UP": "정상", "SLOW": "느림", "WARN": "경고", "DOWN": "장애"}

HISTORY_MAXLEN = 120  # 페이지별 최근 이력 보관 개수


# ---------------------------------------------------------------- 세션 초기화
def init_state():
    st.session_state.setdefault("history", {})      # name -> deque[(ts, ms, level)]
    st.session_state.setdefault("uptime_log", deque(maxlen=500))  # (ts, up_ratio)
    st.session_state.setdefault("last_results", None)
    st.session_state.setdefault("run_count", 0)


def record_history(results):
    hist = st.session_state["history"]
    now = datetime.now()
    for r in results:
        dq = hist.setdefault(r.name, deque(maxlen=HISTORY_MAXLEN))
        dq.append((now, r.elapsed_ms if r.elapsed_ms is not None else None, r.level))
    up = sum(1 for r in results if r.ok)
    ratio = up / len(results) * 100 if results else 0
    st.session_state["uptime_log"].append((now, ratio))


# ---------------------------------------------------------------- 사이드바
def sidebar_controls():
    st.sidebar.header("⚙️ 설정")

    auto = st.sidebar.toggle("자동 새로고침", value=True)
    interval = st.sidebar.select_slider(
        "새로고침 간격(초)", options=[5, 10, 15, 30, 60, 120], value=30,
        disabled=not auto,
    )
    timeout = st.sidebar.slider("요청 타임아웃(초)", 3, 30, 10)

    st.sidebar.divider()
    st.sidebar.subheader("모니터링 대상")
    categories = sorted({t["category"] for t in TARGETS})
    picked_cats = st.sidebar.multiselect("분류 필터", categories, default=categories)
    targets = [t for t in TARGETS if t["category"] in picked_cats]
    st.sidebar.caption(f"선택된 페이지: {len(targets)}개 / 전체 {len(TARGETS)}개")

    verify = st.sidebar.checkbox(
        "SSL 인증서 검증", value=False,
        help="사내 프록시 환경에서는 self-signed 인증서 때문에 꺼야 정상 동작합니다.",
    )

    if st.sidebar.button("🔄 지금 새로고침", use_container_width=True):
        st.rerun()

    st.sidebar.divider()
    sidebar_mail_section(targets, timeout, verify)

    st.sidebar.divider()
    if st.sidebar.button("🗑️ 이력 초기화", use_container_width=True):
        for k in ("history", "uptime_log", "last_results", "run_count"):
            st.session_state.pop(k, None)
        init_state()
        st.rerun()

    return {"auto": auto, "interval": interval, "timeout": timeout,
            "targets": targets, "verify": verify}


def mail_config_from_secrets() -> dict | None:
    """st.secrets 의 [smtp] 블록을 config 딕셔너리로 변환. 없으면 None."""
    try:
        smtp = st.secrets.get("smtp")
    except Exception:  # secrets.toml 자체가 없을 때
        return None
    if not smtp:
        return None
    return {
        "host": smtp.get("host", "smtp.gmail.com"),
        "port": smtp.get("port", 465),
        "user": smtp.get("user", ""),
        "password": smtp.get("password", ""),
        "sender": smtp.get("sender") or smtp.get("user", ""),
        "recipients": smtp.get("recipients", ""),
    }


def sidebar_mail_section(targets, timeout, verify):
    st.sidebar.subheader("📧 메일 알림")
    cfg = mail_config_from_secrets()
    if cfg is None or validate_config(cfg):
        st.sidebar.caption("메일 설정이 없습니다. `.streamlit/secrets.toml`(또는 "
                           "클라우드 Secrets)에 `[smtp]` 블록을 넣으면 활성화됩니다.")
        return
    st.sidebar.caption(f"수신: {cfg['recipients']}")
    if st.sidebar.button("✉️ 현재 상태 메일 발송", use_container_width=True):
        with st.spinner("점검 후 메일 발송 중…"):
            results = st.session_state.get("last_results")
            if not results:
                results = check_all(targets, timeout=timeout, verify=verify)
            try:
                subject, html = build_html(results, BASE_URL)
                png = build_chart_png(results)
                send_report(cfg, subject, html, chart_png=png)
                st.sidebar.success(f"발송 완료 → {cfg['recipients']}")
            except Exception as e:  # noqa: BLE001
                st.sidebar.error(f"발송 실패: {e}")


# ---------------------------------------------------------------- 요약 지표
def render_summary(results):
    total = len(results)
    up = sum(1 for r in results if r.level == "UP")
    slow = sum(1 for r in results if r.level == "SLOW")
    warn = sum(1 for r in results if r.level == "WARN")
    down = sum(1 for r in results if r.level == "DOWN")
    healthy = up + slow  # ok=True 기준
    ratio = healthy / total * 100 if total else 0
    valid_ms = [r.elapsed_ms for r in results if r.elapsed_ms is not None]
    avg_ms = sum(valid_ms) / len(valid_ms) if valid_ms else 0

    # 실제 데이터 검증 대상(데이터 기대치가 있는 페이지) 중 통과 개수
    data_targets = [r for r in results if r.data_min is not None]
    data_ok_cnt = sum(1 for r in data_targets if r.data_ok)
    data_fail = len(data_targets) - data_ok_cnt

    # 전체 상태 배너
    if down > 0:
        st.error(f"🔴 장애 감지: {down}개 페이지 다운  ·  가용률 {ratio:.1f}%", icon="🚨")
    elif warn > 0:
        st.warning(f"🟠 경고: {warn}개 페이지 이상"
                   + (f" (데이터 미출력 {data_fail}개 포함)" if data_fail else "")
                   + f"  ·  가용률 {ratio:.1f}%", icon="⚠️")
    elif slow > 0:
        st.info(f"🟡 {slow}개 페이지 응답 지연  ·  데이터·화면 모두 정상", icon="ℹ️")
    else:
        st.success(f"🟢 모든 페이지 정상  ·  화면·데이터 이상 없음  ·  가용률 {ratio:.1f}%", icon="✅")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("전체 페이지", f"{total}개")
    c2.metric("정상 가동", f"{healthy}개", delta=f"{ratio:.0f}%")
    c3.metric("데이터 정상", f"{data_ok_cnt}/{len(data_targets)}",
              delta=(f"-{data_fail} 미출력" if data_fail else "이상 없음"),
              delta_color="inverse" if data_fail else "normal")
    c4.metric("평균 응답시간", f"{avg_ms:.0f} ms")
    c5.metric("느림/경고", f"{slow + warn}개")
    c6.metric("장애", f"{down}개", delta=f"-{down}" if down else "0",
              delta_color="inverse")


# ---------------------------------------------------------------- 상세 테이블
def render_table(results):
    rows = []
    for r in results:
        # 데이터 컬럼: 실제 데이터 건수 / 기대 최소치
        if r.data_count is not None:
            data_cell = f"{'✔' if r.data_ok else '✖'} {r.data_count}건"
        elif r.data_min is not None:
            data_cell = "✖ -"
        else:
            data_cell = "-"
        rows.append({
            "상태": f"{LEVEL_EMOJI[r.level]} {LEVEL_LABEL[r.level]}",
            "페이지": r.name,
            "분류": r.category,
            "HTTP": r.status_code if r.status_code is not None else "-",
            "응답(ms)": r.elapsed_ms if r.elapsed_ms is not None else None,
            "크기(KB)": round(r.content_bytes / 1024, 1) if r.content_bytes else None,
            "렌더": "✔" if r.content_ok else "✖",
            "데이터": data_cell,
            "데이터항목": f"{r.data_label} (≥{r.data_min})" if r.data_min else "-",
            "메시지": r.message,
            "경로": r.path,
        })
    df = pd.DataFrame(rows)

    def _row_style(row):
        lvl = row["상태"].split()[0]
        color_map = {v: k for k, v in LEVEL_EMOJI.items()}
        level = color_map.get(lvl, "UP")
        bg = {"UP": "", "SLOW": "background-color:#4d4416",
              "WARN": "background-color:#5c3a17", "DOWN": "background-color:#5c1f1f"}[level]
        return [bg] * len(row)

    styled = df.style.apply(_row_style, axis=1).format(
        {"응답(ms)": "{:.0f}", "크기(KB)": "{:.1f}"}, na_rep="-")
    st.dataframe(
        styled, use_container_width=True, hide_index=True,
        column_config={
            "경로": st.column_config.TextColumn("경로", width="medium"),
            "메시지": st.column_config.TextColumn("메시지", width="medium"),
        },
    )


# ---------------------------------------------------------------- 차트
def render_charts(results):
    col1, col2 = st.columns([3, 2])

    # 페이지별 응답시간 바 차트
    with col1:
        st.subheader("페이지별 응답시간")
        df = pd.DataFrame([{
            "페이지": r.name,
            "응답(ms)": r.elapsed_ms if r.elapsed_ms is not None else 0,
            "상태": r.level,
        } for r in results])
        fig = px.bar(
            df, x="응답(ms)", y="페이지", orientation="h",
            color="상태", color_discrete_map=LEVEL_COLOR,
            category_orders={"상태": ["UP", "SLOW", "WARN", "DOWN"]},
        )
        fig.update_layout(
            height=max(400, len(results) * 26), margin=dict(l=10, r=10, t=10, b=10),
            yaxis=dict(autorange="reversed"), legend_title_text="",
        )
        st.plotly_chart(fig, use_container_width=True)

    # 상태 분포 도넛
    with col2:
        st.subheader("상태 분포")
        counts = {}
        for r in results:
            counts[r.level] = counts.get(r.level, 0) + 1
        labels = [LEVEL_LABEL[k] for k in counts]
        fig2 = go.Figure(go.Pie(
            labels=labels, values=list(counts.values()), hole=0.55,
            marker=dict(colors=[LEVEL_COLOR[k] for k in counts]),
            textinfo="label+value",
        ))
        fig2.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10),
                          showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

        # 가용률 추이
        ulog = list(st.session_state["uptime_log"])
        if len(ulog) >= 2:
            udf = pd.DataFrame(ulog, columns=["시각", "가용률"])
            fig3 = px.line(udf, x="시각", y="가용률", markers=True)
            fig3.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10),
                              yaxis=dict(range=[0, 105]), title="가용률 추이(%)")
            fig3.update_traces(line_color="#2ecc71")
            st.plotly_chart(fig3, use_container_width=True)


def render_response_trend():
    """페이지별 응답시간 이력 추이 (선택)."""
    hist = st.session_state["history"]
    if not hist:
        return
    st.subheader("응답시간 추이")
    names = list(hist.keys())
    picked = st.multiselect("페이지 선택", names,
                            default=names[: min(5, len(names))])
    if not picked:
        return
    frames = []
    for name in picked:
        for ts, ms, level in hist[name]:
            if ms is not None:
                frames.append({"시각": ts, "응답(ms)": ms, "페이지": name})
    if not frames:
        st.caption("아직 표시할 이력이 없습니다.")
        return
    tdf = pd.DataFrame(frames)
    fig = px.line(tdf, x="시각", y="응답(ms)", color="페이지", markers=True)
    fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------- 메인 렌더
def render_dashboard(cfg):
    st.session_state["run_count"] += 1
    with st.spinner("페이지 상태 점검 중…"):
        results = check_all(cfg["targets"], timeout=cfg["timeout"], verify=cfg["verify"])
    record_history(results)
    st.session_state["last_results"] = results

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.caption(f"마지막 점검: **{now}**  ·  대상 {BASE_URL}  ·  "
               f"누적 점검 {st.session_state['run_count']}회"
               + (f"  ·  {cfg['interval']}초마다 자동 갱신" if cfg["auto"] else "  ·  자동 갱신 꺼짐"))

    render_summary(results)
    st.divider()
    render_charts(results)
    st.divider()
    st.subheader("페이지별 상세")
    render_table(results)
    st.divider()
    render_response_trend()


# ---------------------------------------------------------------- 엔트리
def main():
    init_state()
    st.title("⚾ LG 트윈스 홈페이지 모니터링")
    cfg = sidebar_controls()

    if not cfg["targets"]:
        st.warning("사이드바에서 모니터링할 분류를 하나 이상 선택하세요.")
        return

    # 자동 새로고침이면 fragment 를 run_every 로 감싸 해당 영역만 주기 실행
    if cfg["auto"]:
        frag = st.fragment(run_every=cfg["interval"])(render_dashboard)
        frag(cfg)
    else:
        render_dashboard(cfg)


if __name__ == "__main__":
    main()
