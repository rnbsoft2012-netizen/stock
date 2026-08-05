# 매일 아침 7시 카톡 브리핑 - 실행 절차

매일 아침 7시(KST)에 깨어나는 Claude Routine이 그대로 따라야 할 절차입니다.

## ⚠️ 먼저: PlayMCP 커넥터를 켠 상태로 세션을 시작해야 한다

커넥터 도구 목록은 **세션이 시작될 때** 로드된다. 대화 중간에 커넥터 토글을
켜도 이미 떠 있는 세션에는 반영되지 않는다 (`enabledInChat: false`로 남는다).
게다가 세션은 자기가 가진 커넥터 집합을 **좁힐 수만 있고 넓힐 수는 없어서**,
PlayMCP 없이 시작한 세션에서 예약을 만들면 그 예약도 PlayMCP를 쓸 수 없다.

따라서 카톡 발송과 아침 7시 예약 생성은 **PlayMCP를 미리 켜둔 새 대화**에서
해야 한다. 새 대화를 열고 아래 프롬프트를 붙여넣으면 이어받을 수 있다:

> 이 저장소의 `docs/morning_routine.md` 절차대로 오늘자 주식 브리핑을 만들어
> 카톡으로 테스트 발송해줘. 형식 확인하고 나면 매일 아침 7시(KST) 예약도
> 걸어줘. 브랜치는 `claude/stock-portfolio-kakao-alerts-c7lqtv`.

### 예약(Routine)은 claude.ai Routines UI에서 만들어야 한다

2026-08-06 확인: PlayMCP가 켜진 세션 안에서 예약 생성 도구(`create_trigger`)를
호출해도 **이 조직에서는 커넥터 파라미터 자체가 차단된다**
("the connectors parameter is not available for this organization"). 파라미터를
빼고 만들면 예약은 생성되지만 `stores no MCP connectors` 경고가 붙고, 그
예약이 깨우는 세션에는 `mcp__*` 도구가 아예 없어 카톡 전송이 불가능하다.

2026-08-06 재확인: PlayMCP 커넥터를 연결 해제 후 재연결하고 같은 호출을 다시
해도 **에러 문구가 동일하다.** 재연결 자체는 정상이었다(같은 세션에서 네이버
뉴스 검색이 성공했다). 즉 커넥터 상태의 문제가 아니라 조직 정책이므로,
껐다 켜는 것으로는 해결되지 않는다.

따라서 아침 7시 예약은 **claude.ai의 Routines UI에서 직접 만들어야 한다.**
거기서 PlayMCP 커넥터를 붙인 뒤, 아래 "절차"를 그대로 수행하라는 프롬프트를
넣으면 된다. 세션 안에서 만든 예약은 카톡을 못 보낸다.

#### Routines UI에 넣을 설정값

| 항목 | 값 |
| --- | --- |
| 스케줄 | 매일 오전 7:00 (KST) |
| 커넥터 | **PlayMCP** (하위 `KakaotalkChat`, `NaverSearch` 둘 다) |
| 저장소 | `rnbsoft2012-netizen/stock` |
| 브랜치 | `claude/stock-portfolio-kakao-alerts-c7lqtv` |
| 환경 | 이 저장소가 연결된 환경 (`env_01L3SqK1aj3j8e5ZheKZ4kXt`) |

#### Routines UI에 붙여넣을 프롬프트 (그대로 복사)

```text
저장소 rnbsoft2012-netizen/stock, 브랜치 claude/stock-portfolio-kakao-alerts-c7lqtv
에서 오늘자 주식 모닝 브리핑을 만들어 카카오톡으로 보내주세요.

절차는 저장소의 docs/morning_routine.md에 전부 적혀 있습니다. 먼저 그 문서를
읽고 거기 적힌 절차를 그대로 따르세요. 요약하면:

1. python scripts/brief.py 실행 (필요하면 pip install -r requirements.txt).
   요약 메시지와 주목 종목 5개가 JSON으로 나옵니다.
2. 주목 종목 5개 각각에 대해 PlayMCP 네이버뉴스 검색(NaverSearch-search_news)을
   news_query로 sort=date, display=3 호출합니다.
3. 요약 1건 + 종목 5건 = 총 6건의 메시지를 작성합니다. 각 메시지 앞에 [n/6]을
   붙이고, 종목 메시지는 stat_line + "뉴스:" 헤드라인 한 줄 + "코멘트:" 한 줄
   구성입니다. 추측에 근거한 목표가나 매수·매도 지시는 쓰지 마세요. 마지막
   메시지 끝에 "* 투자 참고용이며 투자 권유가 아닙니다."를 붙입니다.
4. 메시지 6개를 JSON 배열 파일로 저장하고 python scripts/brief.py --check <파일>
   로 200자 이내인지 검증합니다. 초과분은 줄여서 다시 검증하세요.
5. PlayMCP 카카오톡 나에게 보내기(KakaotalkChat-MemoChat)로 [1/6]부터 순서대로
   6건 전송합니다.

저장소 코드는 수정하지 말고, 커밋이나 푸시도 하지 마세요. 전송에 실패하면
원인을 파악해 재시도하고, 그래도 안 되면 무엇이 왜 실패했는지 남기세요.
```

만든 뒤에는 루틴을 **한 번 수동 실행(Run now)** 해서 카톡 6건이 실제로 오는지
확인한다. 안 오면 그 루틴에도 커넥터가 안 붙은 것이므로, 조직 관리자 설정에서
루틴·커넥터 정책을 확인해야 한다.

새 대화 시작 전 확인할 것:
- 커넥터 메뉴에서 **PlayMCP 토글이 켜져 있는지** (하위 서버 `KakaotalkChat`,
  `NaverSearch` 둘 다)
- 환경의 네트워크 정책이 `query1.finance.yahoo.com`,
  `query2.finance.yahoo.com`을 허용하는지 (2026-08-06 기준 허용 완료)

## 브리핑 형식 (확정)

카카오톡 메시지 1건은 **최대 200자**입니다. 보유 종목이 23개라 종목당 1건씩
보내면 매일 24건이 되므로, **요약 1건 + 주목 종목 5건 = 총 6건**으로 보냅니다.

- **요약(1건)**: 전체 평가금액·당일 등락·평가손익 + 계좌 A/B별 평가·손익.
  계좌는 요약에서만 나누고, 종목 설명은 두 계좌를 합산해 중복 없이 다룹니다.
- **주목 종목(5건)**: `scripts/brief.py`가 골라줍니다. 등락률 상위 3개 +
  거기 안 뽑힌 종목 중 하루 평가액 변동액 상위 2개. 작은 종목의 -18%와
  비중 큰 종목의 +5%를 둘 다 놓치지 않기 위한 조합입니다.
- 두 계좌에 걸친 종목(SK하이닉스, 현대모비스)은 평단가 차이가 크므로
  계좌별 평단·수익률을 함께 적습니다. `brief.py`의 `held_in`에 들어 있습니다.

## 절차

1. `python scripts/brief.py` 실행. 다음이 나온다:
   - `summary_message`: 그대로 보낼 수 있는 요약 메시지 (길이도 함께 출력)
   - `notable`: 주목 종목 5개 — 종목명, `news_query`, `stat_line`, `held_in`
   - `all_holdings`: 전 종목 수치 (참고용, 브리핑에는 안 넣음)
2. `notable` 5개 각각에 대해 PlayMCP 네이버뉴스 검색(`NaverSearch-search_news`)을
   `news_query`로 `sort=date`, `display=3` 호출.
3. 종목별 메시지를 작성한다. `stat_line`을 그대로 쓰고 뒤에 붙인다:
   - `뉴스:` 헤드라인 한 줄 (기사 제목의 HTML 태그 `<b>` 제거)
   - `코멘트:` 그 뉴스와 수치에 근거한 관전 포인트 한 줄.
     추측으로 목표가나 매수·매도 지시를 쓰지 않는다. 근거가 뉴스에 없으면
     "관련 뉴스 없음, 수급/지수 영향으로 보임" 처럼 솔직하게 적는다.
4. 각 메시지 맨 앞에 `[n/6]` 순번을 붙인다. 마지막 메시지 끝에
   `* 투자 참고용이며 투자 권유가 아닙니다.` 를 덧붙인다.
5. **보내기 전에 길이를 검증한다.** 메시지 6개를 JSON 배열 파일로 저장하고
   `python scripts/brief.py --check <파일>` 실행. 200자 초과가 있으면
   해당 메시지를 줄여서 다시 검증한다.
6. PlayMCP 카카오톡 나에게 보내기(`KakaotalkChat-MemoChat`)로 [1/6]부터
   순서대로 6건 전송한다.
7. 전송 실패 시 원인을 파악해 재시도한다. PlayMCP가 이 세션에서 꺼져 있으면
   (`enabledInChat: false`) 전송이 불가능하므로, 그 사실을 세션에 남긴다.

## 데이터 소스에 대한 메모

- **시세**: 국내·해외 모두 Yahoo Finance chart API를 `requests`로 직접 호출.
  - `yfinance` 라이브러리는 쓰지 않는다. 내부적으로 curl_cffi로 브라우저 TLS
    지문을 위장하는데, 클라우드 세션의 보안 프록시가 그 연결을 리셋한다.
  - `pykrx`도 쓰지 않는다. 최신 pykrx(1.2.8)는 KRX 계정(KRX_ID/KRX_PW)
    로그인을 요구하는데, 클라우드 환경변수에는 안전한 비밀 저장소가 없어
    계정 비밀번호를 두기 적절하지 않다. Yahoo가 국내 종목도 원화로 제공한다.
  - **코스닥 종목의 `.KQ` 접미사를 짐작하지 말 것.** 코스닥 코드에 `.KS`를
    붙여도 Yahoo가 200을 주지만 전혀 다른 종목 데이터가 온다 (로보티즈는
    `.KS`로 22,400원 / `.KQ`로 242,000원). 종목 추가 시
    `python scripts/resolve_tickers.py --check-portfolio` 로 검증한다.
- **뉴스**: PlayMCP 네이버뉴스 검색. 해외 종목도 네이버를 쓴다 — Yahoo 뉴스
  검색은 티커와 무관한 기사를 섞어 내보낸다 (NVDA 검색에 SolarEdge 기사).
- **시간대**: 컨테이너는 UTC다. 아침 7시 KST는 UTC로 전날 22시이므로
  날짜 표기는 반드시 KST 기준(`today_kst()`)으로 한다.

## 전제 조건

- PlayMCP 커넥터가 **이 세션에서 활성화**되어 있어야 함
  (claude.ai 커넥터 설정에서 조직 연결 + 해당 대화의 도구 토글 둘 다)
- 환경 네트워크 정책이 `query1.finance.yahoo.com`,
  `query2.finance.yahoo.com` 허용 (확인 완료)
- `portfolio.yaml`이 최신 보유내역을 반영 (2026-08-06 기준 반영 완료)
