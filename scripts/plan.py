#!/usr/bin/env python3
"""
"언제 더 사고 언제 줄이나"를 관측된 가격 수준으로만 답한다.

`technical.py`가 종목의 **상태**를 네 축으로 분류했다면, 이 스크립트는 그 상태에
대응하는 **행동 기준선**을 만든다. 예측은 하지 않는다. 여기 나오는 숫자는 전부
이미 시장에 찍힌 값에서 나온다:

    60일 지지·저항   실제로 최근 60거래일 안에서 눌린/막힌 가격
    MA60            60일 평균 매입단가, 추세의 기준선
    ×0.7 매수선     증권사 목표가 × 0.7 (사용자의 기존 매수 검토 기준)
    평단             내가 실제로 산 가격
    52주 위치        1년 범위 안에서 지금 어디쯤인지

**왜 목표가만으로는 부족한가**: 목표가 × 0.7은 "이 값이면 싸다"는 밸류에이션
기준이지, "지금 사도 되는가"에는 답하지 않는다. 하락 추세에서 매수선에 닿는 건
싸져서가 아니라 계속 밀리고 있어서다. 그래서 매수 구간은 밸류에이션(매수선)과
추세(MA60·지지선)가 **둘 다** 허락할 때만 제시하고, 추세·상대강도가 모두 약한
종목에는 아예 제시하지 않는다 — 그 구간에서 필요한 건 물타기가 아니라 비중 관리다.

사용법:
    python scripts/plan.py BRIEFING_JSON TECH_JSON [NOTES_JSON]
출력: JSON {ticker: {"stance", "badge", "lines": [...], "kakao": str|None}}

`lines`는 메일 카드의 "▶ 대응"에 그대로 들어갈 문장들이다.
`kakao`가 채워진 종목은 **오늘 사람이 봐야 하는 종목**이다(아래 "카톡에 올릴
기준" 참조).
"""
import sys
import json
from pathlib import Path

# 비중 상한: 변동성이 큰 종목일수록 같은 비중이라도 포트폴리오를 더 흔든다.
# 연변동성 구간별로 "이 종목 하나가 차지해도 되는 최대 비중"을 다르게 잡는다.
WEIGHT_CAP = [(150, 8.0), (100, 12.0), (60, 18.0), (0, 25.0)]

RSI_HOT = 70          # 과열 — 신규 매수 보류
RSI_COLD = 30         # 침체 — 지지선 확인 시 분할매수 후보
NEAR_LOW_PCT = 25     # 52주 위치가 이 아래면 저점권
NEAR_HIGH_PCT = 80    # 이 위면 고점권
BUY_LINE_RATIO = 0.7
DEEP_LOSS_PCT = -25   # 이 아래로 깨진 종목의 물타기는 따로 경고한다


def weight_cap(vol_annual) -> float:
    v = vol_annual or 0
    for threshold, cap in WEIGHT_CAP:
        if v >= threshold:
            return cap
    return 25.0


def won(n) -> str:
    return "-" if n is None else f"{n:,.0f}원"


def man(n) -> str:
    return "-" if n is None else f"{n/10000:,.1f}만원"


def money(n) -> str:
    """10만원 넘어가면 만원 단위가 읽기 쉽다."""
    if n is None:
        return "-"
    return man(n) if n >= 100000 else won(n)


def ma60_price(price, vs_ma60_pct):
    if price is None or vs_ma60_pct is None:
        return None
    return price / (1 + vs_ma60_pct / 100)


ETF_PREFIXES = ("KODEX", "TIGER", "PLUS", "ACE", "RISE", "SOL", "KBSTAR", "ARIRANG")


def is_etf(name: str) -> bool:
    return any(name.upper().startswith(p) for p in ETF_PREFIXES)


def build(row: dict, tech: dict, note: dict) -> dict:
    """종목 하나의 대응 기준선. 규칙은 전부 위 docstring에 적힌 관측값에서 나온다."""
    price = row.get("current_price")
    if price is None or not tech or tech.get("error"):
        return {
            "stance": "판정 보류",
            "badge": "확인 필요",
            "lines": ["시세 또는 지표를 받지 못해 기준선을 만들지 못했다."],
            "kakao": None,
        }

    trend = tech.get("trend", "unknown")
    rs6 = tech.get("rs_6m_pct") or 0
    rsi = tech.get("rsi14")
    pos52 = tech.get("pos_52w_pct")
    vol = tech.get("vol_annual_pct")
    sup = tech.get("swing_low_60d")
    res = tech.get("swing_high_60d")
    ma60 = ma60_price(price, tech.get("vs_ma60_pct"))
    weight = row.get("weight_pct") or 0
    pl = row.get("profit_loss_pct")

    lo, hi = note.get("target_low"), note.get("target_high")
    buy_line = lo * BUY_LINE_RATIO if lo else None

    etf = is_etf(row.get("name", ""))
    weak = trend == "down" and rs6 < 0
    strong = trend == "up" and rs6 >= 0
    cap = weight_cap(vol)
    over_cap = weight > cap

    lines: list[str] = []
    kakao = None

    # ── 1. 지금 위치 ────────────────────────────────────────────────
    where = [f"현재가 {money(price)}"]
    if buy_line:
        rel = "아래" if price < buy_line else "위"
        where.append(f"×0.7 매수선 {money(buy_line)} {rel}")
    if sup:
        gap = (price / sup - 1) * 100
        where.append(f"60일 지지 {money(sup)} 대비 +{gap:.0f}%" if gap >= 0
                     else f"60일 지지 {money(sup)} 이탈 상태")
    lines.append(" · ".join(where))

    # ── 2. 추가매수 ─────────────────────────────────────────────────
    if over_cap:
        lines.append(
            f"<b>추가매수 ✕</b> 비중이 이미 상한을 넘었다({weight}% &gt; {cap}%). "
            f"종목을 어떻게 보든, 여기서 더 사는 건 한 종목에 걸린 위험만 키운다."
        )
    elif weak:
        extra = " 평단 대비 손실이 커도 마찬가지다." if (pl or 0) < DEEP_LOSS_PCT else ""
        # ETF는 지수 그 자체라 "종목 쪽 문제"라는 말이 성립하지 않는다.
        # 같은 숫자라도 해석은 "어느 지수에 돈을 둘 것인가"의 문제가 된다.
        why = (
            f"추세 하락 + 비교지수 대비 {rs6:+.1f}%p로, 이 지수가 시장 평균보다 "
            f"뒤처지고 있다. 지수를 더 담는 대신 어느 지수에 둘지를 먼저 정한다."
            if etf else
            f"추세 하락 + 지수 대비 {rs6:+.1f}%p로 약세가 시장 탓이 아니라 종목 쪽이다. "
            f"여기서 사면 약한 종목의 비중만 커진다."
        )
        lines.append(
            f"<b>추가매수 ✕</b> {why}{extra} MA60 {money(ma60)} 회복 전까지 신규 자금 보류."
        )
    elif rsi and rsi >= RSI_HOT:
        lines.append(
            f"<b>추가매수 보류</b> RSI {rsi}로 단기 과열. MA60 {money(ma60)} 부근까지 "
            f"밀리면 재검토."
        )
    else:
        # 매수 구간 = 밸류에이션(매수선)과 추세(MA60·지지선)가 둘 다 허락하는 곳
        cands = [c for c in (buy_line, ma60) if c and c < price]
        zone_hi = max(cands) if cands else None
        zone_lo = sup if sup and (zone_hi is None or sup < zone_hi) else None
        if zone_hi and zone_lo:
            drop = (1 - zone_hi / price) * 100
            lines.append(
                f"<b>추가매수 ○ {money(zone_lo)}~{money(zone_hi)}</b> — 현재가에서 "
                f"{drop:.0f}% 더 밀려야 진입 구간. 비중 {weight}%/상한 {cap}%."
            )
        elif zone_lo:
            # 현재가가 이미 매수선 아래면 그 사실이 지지선보다 먼저 나와야 한다 —
            # 밸류에이션은 이미 통과했고 남은 건 추세 확인뿐이라는 뜻이기 때문이다.
            under = (
                f"현재가가 이미 ×0.7 매수선 {money(buy_line)} 아래다. "
                if buy_line and price < buy_line else ""
            )
            lines.append(
                f"<b>추가매수 △ {money(zone_lo)} 지지 확인 후</b> — {under}"
                f"지지선을 지켜내는 걸 보고 들어간다. 비중 {weight}%/상한 {cap}%."
            )
        else:
            lines.append(
                "<b>추가매수 △</b> 매수선·MA60·지지선 중 현재가 아래에 있는 참고선이 "
                "없다 — 서두를 자리가 아니다."
            )

    # 목표가 편차가 2배를 넘으면 ×0.7 매수선은 기준선 노릇을 못 한다.
    # (한미반도체 10만~50만처럼 시장이 적정가에 합의하지 못한 경우)
    if lo and hi and hi / lo >= 2:
        lines.append(
            f"※ 목표가가 {money(lo)}~{money(hi)}으로 {hi/lo:.1f}배 벌어져 있다. "
            f"매수선을 기계적으로 쓰지 말고 지지선·추세를 우선한다."
        )

    # 같은 종목이라도 계좌별 평단이 2배 넘게 벌어지면 '한 종목'으로 다룰 수 없다.
    # 파는 순서가 계좌에 따라 정반대가 되기 때문이다.
    accs = row.get("accounts") or []
    if len(accs) > 1:
        avgs = [a["avg_price"] for a in accs]
        if max(avgs) / min(avgs) >= 1.5:
            worst = max(accs, key=lambda a: a["avg_price"])
            best = min(accs, key=lambda a: a["avg_price"])
            lines.append(
                f"※ 계좌별로 상황이 반대다 — {best['account']} 평단 {money(best['avg_price'])}"
                f"({best.get('profit_loss_pct'):+.1f}%) / {worst['account']} 평단 "
                f"{money(worst['avg_price'])}({worst.get('profit_loss_pct'):+.1f}%). "
                f"줄인다면 <b>{worst['account']}부터</b>다."
            )

    # ── 3. 비중 축소 / 매도 ─────────────────────────────────────────
    sells = []
    if sup:
        sells.append(f"<b>{money(sup)} 종가 이탈 시 비중 축소</b>(60일 지지 붕괴)")
    if over_cap:
        # 36%를 8%로 한 번에 줄이라는 말은 실행 가능한 조언이 아니다.
        # 중간 목표를 먼저 두고, 상한은 최종 지향점으로 남긴다.
        step = round((weight + cap) / 2, 1)
        sells.append(
            f"<b>비중 {weight}%가 상한 {cap}% 초과</b> — 연변동성 {vol}% 종목이라 "
            f"이 비중이면 포트폴리오 등락이 사실상 이 한 종목에서 결정된다. "
            f"반등 구간에서 <b>1차로 {step}%</b>까지 줄이고, {cap}%는 최종 지향점으로 "
            f"둔다(한 번에 정리하라는 뜻이 아니다)"
        )
    if hi and price >= hi:
        sells.append(f"목표가 상단 {money(hi)} 도달 — 일부 차익 실현 검토")
    elif lo and price >= lo:
        sells.append(f"목표가 하단 {money(lo)} 도달 — 신규 매수는 멈추고 보유만")
    if pos52 is not None and pos52 >= NEAR_HIGH_PCT:
        sells.append(f"52주 위치 {pos52}%로 고점권 — 추격 매수 금지")
    if weak and pos52 is not None and pos52 <= NEAR_LOW_PCT:
        sells.append("52주 저점권 + 약세 — 반등할 때 정리할 후보")
    lines.append("<b>줄일 때</b> " + (" / ".join(sells) if sells
                 else "당장의 매도 트리거 없음 — 지지선만 지켜보면 된다"))

    # ── 4. 스탠스 한 줄 ─────────────────────────────────────────────
    if over_cap:
        # 비중 초과는 추세가 좋든 나쁘든 가장 먼저 손봐야 할 사유다.
        stance, badge = "비중 축소가 먼저", "축소 검토"
    elif strong:
        stance, badge = "보유 유지", "보유"
    elif weak:
        stance, badge = "비중 관리", "축소 검토"
    elif trend == "up":
        stance, badge = "보유, 확대는 보류", "보유"
    elif trend == "down":
        stance, badge = "관찰 — 시장 요인이 큼", "관찰"
    else:
        stance, badge = "관망", "관망"

    # ── 카톡에 올릴 기준 ────────────────────────────────────────────
    # 200자 6건에 23종목을 다 넣을 수 없다. "오늘 사람이 실제로 결정할 게
    # 생긴 종목"만 올린다: 비중 상한 초과, 지지선 이탈, 목표가 도달, 매수 구간 진입.
    if over_cap:
        kakao = f"비중 {weight}%>상한 {cap}% 축소 검토"
    elif sup and price < sup:
        kakao = f"60일 지지 {money(sup)} 이탈"
    elif hi and price >= hi:
        kakao = f"목표가 상단 {money(hi)} 도달, 차익 검토"
    elif not weak and buy_line and price < buy_line:
        kakao = f"×0.7 매수선 {money(buy_line)} 아래, 분할매수 구간"

    return {"stance": stance, "badge": badge, "lines": lines, "kakao": kakao}


def build_all(briefing: dict, tech: dict, notes: dict) -> dict:
    return {
        row["ticker"]: build(row, tech.get(row["ticker"]) or {},
                             notes.get(row["ticker"]) or {})
        for row in briefing["all_holdings"]
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    briefing = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    tech = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    notes = {}
    if len(sys.argv) > 3:
        notes = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    print(json.dumps(build_all(briefing, tech, notes), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
