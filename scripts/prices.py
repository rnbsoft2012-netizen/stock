#!/usr/bin/env python3
"""
포트폴리오 시세/손익 조회 스크립트.

국내 주식은 pykrx, 해외 주식은 yfinance로 시세를 가져오고,
portfolio.yaml의 보유수량/평단가와 합쳐서 평가금액과 손익을 계산한다.
해외 종목은 yfinance가 제공하는 뉴스 헤드라인도 함께 담는다
(국내 종목 뉴스는 이 스크립트가 아니라 PlayMCP 네이버뉴스 검색으로 별도 조회한다).

사용법: python scripts/prices.py [portfolio.yaml 경로]
출력: JSON (stdout)
"""
import sys
import json
import datetime
from pathlib import Path

import yaml
from pykrx import stock
import yfinance as yf


def load_portfolio(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_domestic(item: dict) -> dict:
    code = item["code"]
    today = datetime.date.today()
    start = today - datetime.timedelta(days=10)
    df = stock.get_market_ohlcv_by_date(
        start.strftime("%Y%m%d"), today.strftime("%Y%m%d"), code
    )
    df = df[df["종가"] > 0]
    if df.empty:
        current_price = None
        day_change_pct = None
    else:
        current_price = int(df["종가"].iloc[-1])
        if len(df) >= 2:
            prev_close = int(df["종가"].iloc[-2])
            day_change_pct = round((current_price - prev_close) / prev_close * 100, 2)
        else:
            day_change_pct = None

    result = {
        "name": item["name"],
        "code": code,
        "quantity": item["quantity"],
        "avg_price": item["avg_price"],
        "current_price": current_price,
        "day_change_pct": day_change_pct,
    }
    if current_price is not None:
        valuation = current_price * item["quantity"]
        cost = item["avg_price"] * item["quantity"]
        result["valuation"] = valuation
        result["profit_loss"] = valuation - cost
        result["profit_loss_pct"] = round((valuation - cost) / cost * 100, 2) if cost else None
    return result


def fetch_overseas(item: dict) -> dict:
    ticker = item["ticker"]
    t = yf.Ticker(ticker)
    hist = t.history(period="5d")
    current_price = None
    day_change_pct = None
    if not hist.empty:
        closes = hist["Close"].dropna()
        if len(closes) >= 1:
            current_price = round(float(closes.iloc[-1]), 2)
        if len(closes) >= 2:
            prev_close = float(closes.iloc[-2])
            day_change_pct = round((current_price - prev_close) / prev_close * 100, 2)

    news_items = []
    try:
        for n in (t.news or [])[:3]:
            content = n.get("content", n)  # yfinance news schema varies by version
            title = content.get("title") or n.get("title")
            link = (content.get("canonicalUrl") or {}).get("url") or n.get("link")
            if title:
                news_items.append({"title": title, "link": link})
    except Exception:
        pass

    result = {
        "name": item["name"],
        "ticker": ticker,
        "quantity": item["quantity"],
        "avg_price": item["avg_price"],
        "current_price": current_price,
        "day_change_pct": day_change_pct,
        "news": news_items,
    }
    if current_price is not None:
        valuation = current_price * item["quantity"]
        cost = item["avg_price"] * item["quantity"]
        result["valuation"] = valuation
        result["profit_loss"] = valuation - cost
        result["profit_loss_pct"] = round((valuation - cost) / cost * 100, 2) if cost else None
    return result


def main():
    portfolio_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).resolve().parent.parent / "portfolio.yaml"
    )
    portfolio = load_portfolio(portfolio_path)

    domestic = [fetch_domestic(item) for item in portfolio.get("domestic", [])]
    overseas = [fetch_overseas(item) for item in portfolio.get("overseas", [])]

    output = {
        "date": datetime.date.today().isoformat(),
        "domestic": domestic,
        "overseas": overseas,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
