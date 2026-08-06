#!/usr/bin/env python3
"""
보유 종목의 1년 일봉을 받아 추세·상대강도·위치·변동성을 계산한다.

**예측이 아니라 분류다.** 차트 패턴으로 방향을 맞히려 하지 않는다. 대신 "이
종목이 지금 어떤 상태인가"를 네 축으로 재고, 그 상태에서 합리적인 대응을
고르는 데 쓴다. 판단은 사람이 한다.

네 축:
  추세    종가 vs MA60/MA120, MA60 기울기 → up / side / down
  상대강도 3·6개월 수익률에서 지수 수익률을 뺀 값 → 시장 탓인지 종목 탓인지
  위치    52주 범위 내 백분위, 최근 20·60일 스윙 고저 → 지지·저항 참고선
  변동성  20일 일간수익률 표준편차 연율화, 1년 최대낙폭 → 비중 상한 근거

지수는 종목이 상장된 시장을 따라간다(.KS → KOSPI, .KQ → KOSDAQ). 오늘처럼
지수가 4% 빠지는 날 개별 종목의 하락 대부분은 시장 요인이므로, 상대강도를
보지 않으면 모든 종목이 똑같이 나빠 보인다.

사용법:
    python scripts/technical.py [portfolio.yaml 경로]
출력: JSON {ticker: {...지표...}}
"""
import sys
import json
import time
import math
import statistics
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prices import CHART_URL, make_session  # noqa: E402

BENCHMARKS = {"KS": "^KS11", "KQ": "^KQ11"}  # 코스피 / 코스닥 지수
TRADING_DAYS = 252


def fetch_closes(session, ticker: str, rng: str = "1y") -> list:
    """일봉 종가 리스트. Yahoo가 429를 주는 경우가 있어 지수 백오프로 재시도."""
    delay = 1.0
    for attempt in range(4):
        resp = session.get(
            CHART_URL.format(ticker=ticker),
            params={"range": rng, "interval": "1d"},
            timeout=25,
        )
        if resp.status_code == 429:
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        closes = result["indicators"]["quote"][0].get("close") or []
        volumes = result["indicators"]["quote"][0].get("volume") or []
        pairs = [
            (c, v)
            for c, v in zip(closes, volumes or [None] * len(closes))
            if c is not None
        ]
        return pairs
    raise RuntimeError(f"{ticker}: 429가 계속되어 시세를 못 받았다")


def ma(values: list, n: int):
    return sum(values[-n:]) / n if len(values) >= n else None


def pct(a, b):
    """b 대비 a의 변화율(%)."""
    if not b:
        return None
    return round((a - b) / b * 100, 1)


def rsi(closes: list, n: int = 14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(-n, 0):
        diff = closes[i] - closes[i - 1]
        (gains if diff >= 0 else losses).append(abs(diff))
    avg_gain = sum(gains) / n
    avg_loss = sum(losses) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def max_drawdown(closes: list):
    """1년 최대낙폭(%). 고점에서 저점까지 얼마나 빠졌었나."""
    peak = closes[0]
    worst = 0.0
    for c in closes:
        peak = max(peak, c)
        worst = min(worst, (c - peak) / peak)
    return round(worst * 100, 1)


def annual_vol(closes: list, n: int = 20):
    if len(closes) < n + 1:
        return None
    rets = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(-n, 0)
        if closes[i - 1]
    ]
    if len(rets) < 2:
        return None
    return round(statistics.stdev(rets) * math.sqrt(TRADING_DAYS) * 100, 1)


def trend_of(closes: list) -> tuple:
    """추세 판정. 이동평균 배열과 MA60 기울기를 함께 본다.

    종가가 MA60 위에 있어도 MA60 자체가 내려가고 있으면 하락 추세 속 반등일
    뿐이다. 그래서 기울기를 반드시 같이 본다.
    """
    price = closes[-1]
    ma60, ma120 = ma(closes, 60), ma(closes, 120)
    slope = None
    if len(closes) >= 80:
        prev60 = sum(closes[-80:-20]) / 60
        slope = pct(ma60, prev60)  # 20거래일 전 MA60 대비

    if ma60 is None:
        return "unknown", slope
    above60 = price > ma60
    above120 = price > ma120 if ma120 else above60
    rising = (slope or 0) > 1.5
    falling = (slope or 0) < -1.5

    if above60 and above120 and not falling:
        return "up", slope
    if not above60 and not above120 and falling:
        return "down", slope
    return "side", slope


def stance(trend: str, rs6, near_low: bool) -> str:
    """4분면 대응. 추세와 상대강도의 조합으로 스탠스를 고른다."""
    strong = (rs6 or 0) > 0
    if trend == "up" and strong:
        return "추세·상대강도 모두 양호 — 보유 유지가 기본"
    if trend == "up" and not strong:
        return "추세는 살아 있으나 지수 대비 부진 — 비중 확대는 보류"
    if trend == "down" and strong:
        return "하락 추세지만 지수보다는 선방 — 시장 요인 비중이 큼, 관찰"
    if trend == "down" and not strong:
        return (
            "추세·상대강도 모두 약함 — 물타기보다 비중 관리 대상"
            + ("(52주 저점권이라 반등 시 정리 검토)" if near_low else "")
        )
    return "방향성 미형성 — 뉴스·실적 확인 전까지 관망"


def analyze(session, ticker: str, bench_cache: dict) -> dict:
    pairs = fetch_closes(session, ticker)
    closes = [p[0] for p in pairs]
    volumes = [p[1] for p in pairs if p[1] is not None]
    if len(closes) < 60:
        return {"error": f"일봉 {len(closes)}개로는 분석 불가"}

    market = "KQ" if ticker.endswith(".KQ") else "KS"
    if market not in bench_cache:
        bench_cache[market] = [p[0] for p in fetch_closes(session, BENCHMARKS[market])]
    bench = bench_cache[market]

    price = closes[-1]
    hi52, lo52 = max(closes), min(closes)
    span = hi52 - lo52
    trend, slope = trend_of(closes)

    def ret(series, days):
        return pct(series[-1], series[-days]) if len(series) > days else None

    r3, r6 = ret(closes, 63), ret(closes, 126)
    b3, b6 = ret(bench, 63), ret(bench, 126)
    rs3 = round(r3 - b3, 1) if r3 is not None and b3 is not None else None
    rs6 = round(r6 - b6, 1) if r6 is not None and b6 is not None else None

    pos52 = round((price - lo52) / span * 100, 1) if span else None
    near_low = pos52 is not None and pos52 < 20

    vol_recent = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else None
    vol_base = sum(volumes[-60:]) / 60 if len(volumes) >= 60 else None

    return {
        "trend": trend,
        "ma60_slope_pct": slope,
        "vs_ma60_pct": pct(price, ma(closes, 60)),
        "vs_ma120_pct": pct(price, ma(closes, 120)),
        "ret_3m_pct": r3,
        "ret_6m_pct": r6,
        "rs_3m_pct": rs3,
        "rs_6m_pct": rs6,
        "pos_52w_pct": pos52,
        "high_52w": round(hi52),
        "low_52w": round(lo52),
        "swing_high_60d": round(max(closes[-60:])),
        "swing_low_60d": round(min(closes[-60:])),
        "rsi14": rsi(closes),
        "vol_annual_pct": annual_vol(closes),
        "max_drawdown_1y_pct": max_drawdown(closes),
        "volume_ratio": round(vol_recent / vol_base, 2) if vol_recent and vol_base else None,
        "stance": stance(trend, rs6, near_low),
    }


def main():
    root = Path(__file__).resolve().parent.parent
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "portfolio.yaml"
    portfolio = yaml.safe_load(path.read_text(encoding="utf-8"))
    session = make_session()

    tickers = []
    for account in portfolio.get("accounts", []):
        for holding in account.get("holdings", []):
            if holding["ticker"] not in tickers:
                tickers.append(holding["ticker"])

    out, bench_cache = {}, {}
    for ticker in tickers:
        try:
            out[ticker] = analyze(session, ticker, bench_cache)
        except Exception as exc:
            out[ticker] = {"error": str(exc)}
        time.sleep(0.4)  # Yahoo 429 회피
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
