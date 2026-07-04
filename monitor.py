"""
lgtwins.com 모니터링 체크 로직.

각 페이지를 병렬로 요청해서 아래 3단계를 판정한다.
  1) 접속       : HTTP 상태코드 정상 여부
  2) 화면 렌더  : 필수 HTML 구조 마커 + 최소 본문 크기
  3) 실제 데이터: 페이지별 데이터 요소(선수/경기/뉴스/상품 등) 건수가 기대치 이상인지
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# 한국 표준시(UTC+9). 서버가 UTC(예: GitHub Actions)여도 항상 KST로 표기.
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)

import requests
import urllib3
from bs4 import BeautifulSoup

# 사내 프록시가 self-signed 인증서를 물고 있어 검증을 끈다.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.lgtwins.com"

# 모니터링 대상 페이지 정의.
#   name         : 화면에 표시할 한글 이름
#   path         : BASE_URL 기준 경로
#   category     : 그룹핑용 분류
#   must_contain : 응답 본문(bytes)에 반드시 있어야 하는 ASCII 마커 (렌더 검증)
#   data_selector: 실제 데이터 요소를 세기 위한 CSS 선택자
#   data_min     : data_selector 로 센 개수가 이 값 이상이어야 '데이터 정상'
#   data_label   : 무엇을 세는지 사람이 읽을 이름
TARGETS: list[dict] = [
    {"name": "홈(루트)",   "path": "/",                      "category": "핵심",   "must_contain": ["<html", "/css/style.css"], "data_selector": "img",                             "data_min": 5,  "data_label": "이미지/배너"},
    {"name": "메인",       "path": "/main",                  "category": "핵심",   "must_contain": ["<html"],                   "data_selector": "img",                             "data_min": 5,  "data_label": "이미지/배너"},
    {"name": "경기일정",   "path": "/game/schedule",         "category": "경기",   "must_contain": ["<html"],                   "data_selector": "table td",                        "data_min": 10, "data_label": "일정 셀"},
    {"name": "퓨처스일정", "path": "/game/futures-schedule", "category": "경기",   "must_contain": ["<html"],                   "data_selector": "table td",                        "data_min": 10, "data_label": "일정 셀"},
    {"name": "선수단",     "path": "/team/player-list",      "category": "팀",     "must_contain": ["<html"],                   "data_selector": "a[href*='player']",               "data_min": 20, "data_label": "선수"},
    {"name": "코칭스태프", "path": "/team/coach-list",       "category": "팀",     "must_contain": ["<html"],                   "data_selector": "a[href*='coach']",                "data_min": 10, "data_label": "코칭스태프"},
    {"name": "뉴스",       "path": "/twins/feed/news",       "category": "미디어", "must_contain": ["<html"],                   "data_selector": "a[href*='news']",                 "data_min": 5,  "data_label": "뉴스 기사"},
    {"name": "공지사항",   "path": "/twins/feed/notices",    "category": "미디어", "must_contain": ["<html"],                   "data_selector": "a[href*='notice']",               "data_min": 5,  "data_label": "공지"},
    {"name": "이벤트",     "path": "/twins/feed/events",     "category": "미디어", "must_contain": ["<html"],                   "data_selector": "a[href*='event']",                "data_min": 5,  "data_label": "이벤트"},
    {"name": "구단소개",   "path": "/twins/about/ceo",       "category": "구단",   "must_contain": ["<html"],                   "data_selector": "img",                             "data_min": 3,  "data_label": "이미지"},
    {"name": "구단역사",   "path": "/twins/history/main",    "category": "구단",   "must_contain": ["<html"],                   "data_selector": "[class*='history']",              "data_min": 3,  "data_label": "연혁 항목"},
    {"name": "예매(일반)", "path": "/ticket/general",        "category": "티켓",   "must_contain": ["<html"],                   "data_selector": "[class*='ticket'], a[href*='ticket']", "data_min": 3, "data_label": "예매 요소"},
    {"name": "시즌권안내", "path": "/ticket/seasonGuide",    "category": "티켓",   "must_contain": ["<html"],                   "data_selector": "img",                             "data_min": 3,  "data_label": "안내 이미지"},
    {"name": "제휴예매",   "path": "/ticket/affiliate",      "category": "티켓",   "must_contain": ["<html"],                   "data_selector": "img",                             "data_min": 3,  "data_label": "이미지"},
    {"name": "MVP투표",    "path": "/fan/mvp",               "category": "팬",     "must_contain": ["<html"],                   "data_selector": "[class*='vote']",                 "data_min": 3,  "data_label": "투표 항목"},
    {"name": "응원",       "path": "/fan/cheers",            "category": "팬",     "must_contain": ["<html"],                   "data_selector": "[class*='cheer']",                "data_min": 5,  "data_label": "응원 콘텐츠"},
    {"name": "팬서비스",   "path": "/fan/services",          "category": "팬",     "must_contain": ["<html"],                   "data_selector": "li",                              "data_min": 10, "data_label": "서비스 항목"},
    {"name": "SHOP",       "path": "/shop",                  "category": "커머스", "must_contain": ["<html"],                   "data_selector": "img",                             "data_min": 5,  "data_label": "상품 이미지"},
    {"name": "로그인",     "path": "/member/login",          "category": "회원",   "must_contain": ["<html"],                   "data_selector": "input",                           "data_min": 2,  "data_label": "입력 필드"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
}

# 판정 임계값
MIN_CONTENT_BYTES = 500          # 이보다 작으면 콘텐츠 비정상 의심
SLOW_THRESHOLD_MS = 2000         # 이보다 느리면 '느림' 경고


@dataclass
class CheckResult:
    name: str
    path: str
    category: str
    url: str
    status_code: int | None = None
    ok: bool = False                 # 최종 정상 여부(가용률 집계 기준)
    elapsed_ms: float | None = None
    content_bytes: int | None = None
    content_ok: bool = False         # 화면 렌더 검증 통과 여부
    data_count: int | None = None    # 실제 데이터 요소 개수
    data_min: int | None = None      # 기대 최소 개수
    data_label: str = ""             # 무엇을 세는지
    data_ok: bool = False            # 실제 데이터 정상 여부
    slow: bool = False
    level: str = "DOWN"              # UP / SLOW / WARN / DOWN
    message: str = ""
    checked_at: str = field(default_factory=lambda: now_kst().strftime("%H:%M:%S"))


def _count_data(html: str, selector: str) -> int | None:
    """CSS 선택자로 데이터 요소 개수를 센다. 실패 시 None."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        return len(soup.select(selector))
    except Exception:  # noqa: BLE001
        return None


def check_one(target: dict, timeout: float = 10.0, verify: bool = False) -> CheckResult:
    url = BASE_URL + target["path"]
    res = CheckResult(
        name=target["name"], path=target["path"],
        category=target["category"], url=url,
        data_min=target.get("data_min"), data_label=target.get("data_label", ""),
    )
    start = time.perf_counter()
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout,
                         verify=verify, allow_redirects=True)
        res.elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        res.status_code = r.status_code
        body = r.content or b""
        res.content_bytes = len(body)

        # 2) 화면 렌더 검증: 필수 마커 존재 + 최소 크기
        lower = body.lower()
        markers_ok = all(m.lower().encode() in lower for m in target.get("must_contain", []))
        size_ok = res.content_bytes >= MIN_CONTENT_BYTES
        res.content_ok = markers_ok and size_ok
        res.slow = res.elapsed_ms is not None and res.elapsed_ms > SLOW_THRESHOLD_MS

        # 3) 실제 데이터 검증: 200 이면서 렌더 정상일 때만 의미가 있음
        selector = target.get("data_selector")
        if selector and 200 <= r.status_code < 300 and res.content_ok:
            html = body.decode("utf-8", errors="replace")
            res.data_count = _count_data(html, selector)
            if res.data_count is not None and res.data_min is not None:
                res.data_ok = res.data_count >= res.data_min

        # ---- 레벨 판정 (심각도 높은 순) ----
        if r.status_code >= 500:
            res.level, res.ok = "DOWN", False
            res.message = f"서버오류 {r.status_code}"
        elif r.status_code >= 400:
            res.level, res.ok = "DOWN", False
            res.message = f"클라이언트오류 {r.status_code}"
        elif not res.content_ok:
            res.level, res.ok = "WARN", False
            res.message = (f"본문 과소 ({res.content_bytes}B)"
                           if not size_ok else "필수 콘텐츠 누락")
        elif not res.data_ok:
            res.level, res.ok = "WARN", False
            cnt = res.data_count if res.data_count is not None else "?"
            res.message = f"데이터 부족 ({res.data_label} {cnt}/{res.data_min})"
        elif res.slow:
            res.level, res.ok = "SLOW", True
            res.message = f"응답 느림 ({res.elapsed_ms:.0f}ms)"
        else:
            res.level, res.ok = "UP", True
            res.message = f"정상 ({res.data_label} {res.data_count}건)"

    except requests.exceptions.Timeout:
        res.elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        res.level, res.ok, res.message = "DOWN", False, f"타임아웃 (>{timeout:.0f}s)"
    except requests.exceptions.SSLError as e:
        res.level, res.ok, res.message = "DOWN", False, f"SSL 오류: {str(e)[:60]}"
    except requests.exceptions.ConnectionError:
        res.level, res.ok, res.message = "DOWN", False, "연결 실패"
    except Exception as e:  # noqa: BLE001
        res.level, res.ok, res.message = "DOWN", False, f"오류: {str(e)[:60]}"
    return res


def check_all(targets: list[dict] | None = None, timeout: float = 10.0,
              verify: bool = False, max_workers: int = 10) -> list[CheckResult]:
    targets = targets if targets is not None else TARGETS
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(lambda t: check_one(t, timeout, verify), targets))
    # 정의 순서 유지
    order = {t["path"]: i for i, t in enumerate(targets)}
    results.sort(key=lambda r: order.get(r.path, 999))
    return results
