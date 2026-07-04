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

## 참고
- 사내망에서는 프록시 self-signed 인증서 때문에 SSL 검증을 꺼야 정상 동작합니다
  (사이드바 `SSL 인증서 검증` 옵션, 기본 꺼짐). 공개 클라우드에서는 켜도 무방합니다.
- 모니터링 대상/기대 데이터 건수는 `monitor.py` 의 `TARGETS` 리스트에서 조정합니다.
