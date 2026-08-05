# 주식 포트폴리오 카톡 모닝 브리핑

매일 아침 7시(KST)에 내 주식 포트폴리오 현황 + 관련 뉴스 + 투자 아이디어를
카카오톡("나에게 보내기")으로 받기 위한 저장소입니다.

## 구조

- `portfolio.yaml` — 보유 종목, 수량, 평단가, 뉴스 검색 키워드.
  **실제 키움증권 보유내역으로 채워야 합니다.**
- `scripts/prices.py` — Yahoo Finance chart API로 국내·해외 시세와 평가손익을
  계산. `python scripts/prices.py` 로 실행, JSON 출력.
- `docs/morning_routine.md` — 매일 아침 Claude Routine이 따라야 할 절차
  (시세 조회 → 네이버뉴스 검색 → 메시지 작성 → 카톡 전송).

실제 "매일 7시 자동 실행"은 저장소 코드가 아니라 **Claude Routine(예약)** 이
담당합니다. PlayMCP 같은 MCP 도구는 Claude 대화 턴 안에서만 호출 가능하기
때문에, 무인 cron 스크립트가 아니라 매일 7시에 Claude 세션을 깨워서
`docs/morning_routine.md` 절차를 수행시키는 방식입니다.

## 시작하기

카톡 발송과 아침 7시 예약은 **PlayMCP 커넥터를 미리 켜둔 새 대화**에서 해야
합니다 — 커넥터 도구는 세션 시작 시점에 로드되고, 커넥터 없이 시작한 세션은
예약에 커넥터 권한을 넘겨줄 수 없습니다. 자세한 이유와 인수인계 프롬프트는
`docs/morning_routine.md` 맨 위에 있습니다.

## 동작 확인 상태 (2026-08-06)

| 항목 | 상태 |
| --- | --- |
| 카톡 나에게 보내기 (PlayMCP `KakaotalkChat-MemoChat`) | 확인됨 — 단 **1건당 200자 제한** |
| 네이버뉴스 검색 (PlayMCP `NaverSearch-search_news`) | 확인됨 |
| 시세 조회 (`scripts/prices.py`) | 확인됨 — 국내·해외 모두 |
| 네트워크 정책 (Yahoo Finance 허용) | 확인됨 |
| 브리핑 6건 실제 전송 | 확인됨 (2026-08-06, 요약 1 + 종목 5) |
| 아침 7시 예약 | ⚠️ **claude.ai 예약 UI에서 만들어야 함** — 대화 안에서 도구로 만든 예약에는 PlayMCP가 붙지 않아 카톡 전송이 안 된다. [자세히](docs/morning_routine.md) |

## 데이터 소스 선택 이유

- **시세는 Yahoo Finance 하나로 통일** (국내 `.KS`/`.KQ` 포함). `yfinance`
  라이브러리 대신 `requests`로 직접 호출하는데, yfinance는 curl_cffi로 브라우저
  TLS 지문을 위장해서 클라우드 세션의 보안 프록시가 연결을 리셋하기 때문입니다.
- **`pykrx`는 쓰지 않습니다.** 최신 pykrx(1.2.8)가 KRX 계정 로그인(`KRX_ID`/
  `KRX_PW`)을 요구하는데, 클라우드 환경변수에는 안전한 비밀 저장소가 없어
  계정 비밀번호를 두기에 적절하지 않습니다.
- **뉴스는 네이버뉴스**를 국내·해외 모두에 사용합니다. 해외 종목도 한국어
  기사가 나오고, Yahoo 뉴스 검색보다 관련도가 눈에 띄게 높았습니다.

## 참고

키움증권 보유내역을 실시간 자동 연동하는 기능은 없습니다. 보유내역이 바뀌면
`portfolio.yaml`을 업데이트해주세요.
