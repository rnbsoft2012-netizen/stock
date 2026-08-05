# 주식 포트폴리오 카톡 모닝 브리핑

매일 아침 7시(KST)에 내 주식 포트폴리오 현황 + 관련 뉴스 + 투자 아이디어를
카카오톡("나에게 보내기")으로 받기 위한 저장소입니다.

## 구조

- `portfolio.yaml` — 보유 종목(국내: KRX 종목코드, 해외: yfinance 티커),
  수량, 평단가. **실제 키움증권 보유내역으로 채워야 합니다.**
- `scripts/prices.py` — pykrx(국내)/yfinance(해외)로 시세·평가손익 계산 +
  해외 종목 뉴스(yfinance) 조회. `python scripts/prices.py` 로 실행, JSON 출력.
- `docs/morning_routine.md` — 매일 아침 Claude Routine이 따라야 할 절차
  (시세 조회 → PlayMCP 네이버뉴스 검색 → 메시지 작성 → PlayMCP 카톡 나에게 보내기).
- 실제 "매일 7시 자동 실행"은 저장소 코드가 아니라 **Claude Routine(예약)** 이
  담당합니다. PlayMCP 같은 MCP 도구는 Claude 대화 턴 안에서만 호출 가능하기
  때문에, 무인 cron 스크립트가 아니라 매일 7시에 Claude 세션을 깨워서
  `docs/morning_routine.md` 절차를 그대로 수행시키는 방식입니다.

## 시작하기 전에 필요한 것 (사용자 준비사항)

1. **PlayMCP 연결**: claude.ai → 설정 → 커넥터에서 PlayMCP 연결 (네이버뉴스
   검색 + 카카오톡 나에게 보내기 권한 승인).
2. **네트워크 정책 확인**: 이 실행 환경(environment)이 `data.krx.co.kr`,
   `query1.finance.yahoo.com`, `query2.finance.yahoo.com` 아웃바운드 접속을
   허용하는지 확인 — 기본값은 차단되어 있을 수 있습니다. 실제 테스트 결과
   두 도메인 모두 현재 환경 정책에서 403으로 막혀 있는 것을 확인했습니다.
   환경 설정(Environment settings)에서 허용 도메인을 추가하거나 네트워크
   정책을 완화해야 시세 조회 스크립트가 동작합니다.
3. **포트폴리오 정보**: `portfolio.yaml`의 예시 데이터를 실제 보유 종목·수량·
   평단가로 교체 (직접 수정하거나 Claude에게 알려주면 대신 채워줍니다).

## 참고

- 키움증권 보유내역을 실시간 자동 연동하는 기능은 아직 없습니다 (키움 Open
  API는 이 클라우드 환경에서 바로 붙이기 어려움). 보유내역이 바뀌면
  `portfolio.yaml`을 업데이트해주세요.
