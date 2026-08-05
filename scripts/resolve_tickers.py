#!/usr/bin/env python3
"""
종목코드에 붙일 Yahoo 접미사(.KS / .KQ)를 실제 시세로 대조해 확인하는 도구.

왜 필요한가: 코스닥 종목에 .KS 를 붙여도 Yahoo가 200 응답을 준다. 그런데
돌아오는 건 전혀 다른 종목의 데이터고, shortName이 "032500.KS,0P0000BFTW,48062"
같은 코드 나열로 나온다. 접미사를 눈으로 짐작해 넣으면 조용히 틀린 종목을
브리핑하게 되므로, 새 종목을 portfolio.yaml에 넣기 전 이 스크립트로 확인한다.

사용법:
    python scripts/resolve_tickers.py 005930 000660 ...
    python scripts/resolve_tickers.py 005930=242000 032500=16890
        - "코드=현재가" 형태로 주면 증권사 화면의 현재가와 대조해
          가장 가까운 접미사를 골라준다 (권장).
    python scripts/resolve_tickers.py --check-portfolio
        - portfolio.yaml에 이미 적힌 티커들이 맞는지 검증한다.
"""
import sys
from pathlib import Path

import yaml
import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
SUFFIXES = (".KS", ".KQ")


def probe(session: requests.Session, ticker: str):
    try:
        resp = session.get(
            CHART_URL.format(ticker=ticker),
            params={"range": "5d", "interval": "1d"},
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        results = resp.json().get("chart", {}).get("result")
        if not results:
            return None
        meta = results[0]["meta"]
        if not meta.get("regularMarketPrice"):
            return None
        return {
            "ticker": ticker,
            "price": meta["regularMarketPrice"],
            "name": meta.get("shortName") or meta.get("longName") or "",
            "exchange": meta.get("fullExchangeName") or "",
        }
    except Exception:
        return None


def looks_bogus(candidate: dict) -> bool:
    """shortName이 코드 나열이면 Yahoo가 엉뚱한 걸 물어온 것이다."""
    return candidate["ticker"].split(".")[0] in candidate["name"].replace(" ", "")


def resolve(session: requests.Session, code: str, reference_price: float | None):
    candidates = [c for c in (probe(session, code + s) for s in SUFFIXES) if c]
    if not candidates:
        return None, []
    sane = [c for c in candidates if not looks_bogus(c)] or candidates
    if reference_price:
        best = min(sane, key=lambda c: abs(c["price"] - reference_price) / reference_price)
    else:
        best = sane[0]
    return best, candidates


def main():
    args = sys.argv[1:]
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    if not args:
        print(__doc__)
        return 1

    if args[0] == "--check-portfolio":
        path = Path(__file__).resolve().parent.parent / "portfolio.yaml"
        portfolio = yaml.safe_load(path.read_text(encoding="utf-8"))
        seen = set()
        problems = 0
        for account in portfolio.get("accounts", []):
            for holding in account.get("holdings", []):
                if holding["ticker"] in seen:
                    continue
                seen.add(holding["ticker"])
                got = probe(session, holding["ticker"])
                if got is None:
                    print(f"!!  {holding['name']:16} {holding['ticker']:12} 시세 없음")
                    problems += 1
                elif looks_bogus(got):
                    print(f"!!  {holding['name']:16} {holding['ticker']:12} 이름이 코드 나열 → 접미사 의심 ({got['name']})")
                    problems += 1
                else:
                    print(f"ok  {holding['name']:16} {holding['ticker']:12} {got['price']:>12,.0f}  {got['exchange']:8} [{got['name']}]")
        print(f"\n{len(seen)}개 종목 확인, 문제 {problems}건")
        return 1 if problems else 0

    for arg in args:
        code, _, ref = arg.partition("=")
        best, candidates = resolve(session, code, float(ref) if ref else None)
        alt = " | ".join(f"{c['ticker']}={c['price']:,.0f}" for c in candidates)
        if best is None:
            print(f"!!  {code} 해석 실패")
        else:
            print(f"ok  {code} -> {best['ticker']:12} {best['price']:>12,.0f}  {best['exchange']:8} [{best['name']}]   후보: {alt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
