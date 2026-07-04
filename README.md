# ⚾ LG 트윈스 홈페이지 모니터링 대시보드

[www.lgtwins.com](https://www.lgtwins.com) 주요 페이지의 **접속 · 화면 렌더 · 실제 데이터 출력**을
실시간으로 점검하는 Streamlit 대시보드.

## 기능
- 19개 주요 페이지(메인·경기일정·선수단·뉴스·공지·티켓·샵·로그인 등) 병렬 점검
- 3단계 검증
  1. **접속** — HTTP 상태코드
  2. **화면 렌더** — 필수 HTML 구조 + 본문 크기
  3. **실제 데이터** — 페이지별 데이터 요소 건수(선수/경기/뉴스/상품 등)가 기대치 이상인지
- 요약 배너 + 가용률(%), 응답시간 막대/도넛 차트, 가용률·응답시간 추이
- 색상 코딩 상세 테이블, 자동 새로고침(5~120초)

## 로컬 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```
Windows 에서는 `run.bat` 더블클릭.

## Streamlit Community Cloud 배포
1. 이 폴더를 **GitHub 공개 저장소**에 push
2. [share.streamlit.io](https://share.streamlit.io) 접속 → Google 계정으로 로그인
3. **New app** → 저장소 / 브랜치 / `app.py` 선택 → Deploy
4. 몇 분 뒤 `https://<앱이름>.streamlit.app` 주소로 공개됨

## 📧 이메일 알림 설정

상태 리포트(요약표 + 응답시간 차트 이미지)를 메일로 받습니다.

### 1) Gmail 앱 비밀번호 발급
1. Google 계정 → **보안** → **2단계 인증** 켜기(필수)
2. [앱 비밀번호](https://myaccount.google.com/apppasswords) 페이지에서 앱 비밀번호 생성
3. 나오는 **16자리**를 복사(공백 없이 사용)

### 2) 발송 방식 — GitHub Actions (권장, 앱이 꺼져 있어도 동작)
`.github/workflows/monitor.yml` 이 자동 실행됩니다.
- **30분마다** → 장애/경고가 있을 때만 메일(`alert`)
- **매일 08:00 KST** → 정기 상태 리포트(`scheduled`)

GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에 등록:

| 이름 | 값(예시) |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | `sungyoul81@gmail.com` |
| `SMTP_PASSWORD` | (16자리 앱 비밀번호) |
| `MAIL_TO` | `sungyoul81@gmail.com` (여러 명은 콤마) |
| `MAIL_FROM` | `sungyoul81@gmail.com` (선택) |

등록 후 **Actions 탭 → 워크플로우 → Run workflow** 로 즉시 테스트 발송 가능.

### 3) 대시보드에서 직접 발송(선택)
`.streamlit/secrets.toml.example` 을 `secrets.toml` 로 복사해 값을 채우면
사이드바 **"✉️ 현재 상태 메일 발송"** 버튼이 활성화됩니다.
(Streamlit Cloud 는 앱 **Settings → Secrets** 에 `[smtp]` 블록 붙여넣기)

### 로컬에서 수동 발송 테스트
```bash
set SMTP_USER=sungyoul81@gmail.com
set SMTP_PASSWORD=앱비밀번호
set MAIL_TO=sungyoul81@gmail.com
python send_report.py --mode scheduled
```

## 참고
- 사내망에서는 프록시 self-signed 인증서 때문에 SSL 검증을 꺼야 정상 동작합니다
  (사이드바 `SSL 인증서 검증` 옵션, 기본 꺼짐). 공개 클라우드/GitHub Actions 에서는 켜도 무방합니다.
- 모니터링 대상/기대 데이터 건수는 `monitor.py` 의 `TARGETS` 리스트에서 조정합니다.
- ⚠️ `alert` 모드는 문제가 지속되면 30분마다 재발송됩니다. 빈도를 줄이려면 workflow 의 cron 을 조정하세요.
- ⚠️ 앱 내 자동 발송이 아니라 **GitHub Actions** 가 알림을 담당합니다
  (Streamlit Cloud 앱은 유휴 시 잠들기 때문).
