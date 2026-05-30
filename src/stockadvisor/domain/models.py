"""도메인 모델 — 순수 dataclass.

분석 파이프라인 전반에서 주고받는 자료구조를 정의한다.
프레임워크/네트워크 의존이 없어 단독 테스트가 쉽다.
"""
from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


class Market(str, enum.Enum):
    KR = "KR"  # 한국거래소 (KOSPI/KOSDAQ)
    US = "US"  # 미국 (NYSE/NASDAQ)

    @property
    def currency(self) -> str:
        return "KRW" if self is Market.KR else "USD"

    @property
    def symbol(self) -> str:
        return "₩" if self is Market.KR else "$"


@dataclass(frozen=True)
class Ticker:
    """입력 종목 식별자.

    raw: 사용자가 입력한 원본 문자열 (예: "005930", "AAPL")
    market: 추정된 시장
    yf_symbol: yfinance 조회용 심볼 (KR은 "005930.KS" 등)
    name: 종목명 (조회 후 채워짐)
    """

    raw: str
    market: Market
    yf_symbol: str
    name: str = ""

    def display(self) -> str:
        return f"{self.name or self.raw} ({self.raw})"


@dataclass
class MacroSnapshot:
    """거시/시장 국면 데이터 스냅샷 (시장당 1회 산출)."""

    as_of: str = ""
    market: Optional[Market] = None
    indicators: dict[str, Any] = field(default_factory=dict)  # 지표명 -> 값
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["market"] = self.market.value if self.market else None
        return d


@dataclass
class StockData:
    """단일 종목의 정량 데이터 번들 (데이터 계층이 채운다)."""

    ticker: Ticker
    currency: str = "USD"
    price: Optional[float] = None
    market_cap: Optional[float] = None

    # 밸류에이션 멀티플
    per: Optional[float] = None          # P/E
    forward_per: Optional[float] = None
    pbr: Optional[float] = None          # P/B
    psr: Optional[float] = None          # P/S
    ev_ebitda: Optional[float] = None
    dividend_yield: Optional[float] = None  # %

    # 성장성
    revenue_growth: Optional[float] = None  # YoY %
    earnings_growth: Optional[float] = None  # YoY %

    # 수익성/건전성
    operating_margin: Optional[float] = None  # %
    profit_margin: Optional[float] = None     # %
    roe: Optional[float] = None               # %
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    free_cashflow: Optional[float] = None

    # 가격/모멘텀
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    ma50: Optional[float] = None
    ma200: Optional[float] = None
    ret_1m: Optional[float] = None   # %
    ret_3m: Optional[float] = None
    ret_6m: Optional[float] = None
    ret_1y: Optional[float] = None
    beta: Optional[float] = None

    # 분류
    sector: str = ""
    industry: str = ""

    # 진단/경고 (데이터 누락 등)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ticker"] = {
            "raw": self.ticker.raw,
            "market": self.ticker.market.value,
            "name": self.ticker.name,
            "yf_symbol": self.ticker.yf_symbol,
        }
        return d


@dataclass
class AnalystOpinion:
    """개별 전문가 에이전트의 의견."""

    analyst: str                 # 에이전트 이름 (예: fundamental-analyst)
    role: str                    # 한국어 역할명 (예: 펀더멘털 분석가)
    stance: str = "neutral"      # bullish / neutral / bearish (또는 도메인별 라벨)
    score: float = 50.0          # 0~100 (해당 관점에서의 매력도)
    confidence: float = 0.5      # 0~1
    summary: str = ""            # 1~3문장 핵심 요약
    key_points: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    raw: str = ""                # 모델 원문(디버그용, 리포트엔 미포함 가능)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TargetBand:
    """특정 기간의 목표가 밴드."""

    horizon: str = ""        # 예: "1-3개월"
    low: Optional[float] = None
    base: Optional[float] = None
    high: Optional[float] = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TargetPrices:
    short_term: TargetBand = field(default_factory=TargetBand)
    mid_term: TargetBand = field(default_factory=TargetBand)
    long_term: TargetBand = field(default_factory=TargetBand)

    def bands(self) -> list[TargetBand]:
        return [self.short_term, self.mid_term, self.long_term]

    def to_dict(self) -> dict[str, Any]:
        return {
            "short_term": self.short_term.to_dict(),
            "mid_term": self.mid_term.to_dict(),
            "long_term": self.long_term.to_dict(),
        }


@dataclass
class StockVerdict:
    """단일 종목 종합 판단 (리스크 매니저 + 종합 단계 산출)."""

    ticker: Ticker
    currency: str = "USD"
    current_price: Optional[float] = None

    valuation_judgment: str = "적정"   # 저평가 / 적정 / 고평가
    action: str = "관망"               # 적극매수 / 분할매수 / 관망 / 비중축소 / 매도
    conviction: float = 50.0           # 0~100 종합 확신도/점수
    total_score: float = 50.0          # 가중 종합 점수 (순위 산출용)

    target_prices: TargetPrices = field(default_factory=TargetPrices)
    stop_loss: Optional[float] = None
    suggested_position_pct: Optional[float] = None  # 권고 비중 상한(%)

    thesis: str = ""                   # 투자 논리 요약
    key_risks: list[str] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)

    opinions: list[AnalystOpinion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": {
                "raw": self.ticker.raw,
                "market": self.ticker.market.value,
                "name": self.ticker.name,
            },
            "currency": self.currency,
            "current_price": self.current_price,
            "valuation_judgment": self.valuation_judgment,
            "action": self.action,
            "conviction": self.conviction,
            "total_score": self.total_score,
            "target_prices": self.target_prices.to_dict(),
            "stop_loss": self.stop_loss,
            "suggested_position_pct": self.suggested_position_pct,
            "thesis": self.thesis,
            "key_risks": self.key_risks,
            "catalysts": self.catalysts,
            "opinions": [o.to_dict() for o in self.opinions],
        }


@dataclass
class RankingEntry:
    rank: int
    ticker: Ticker
    total_score: float
    action: str
    one_liner: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "ticker": self.ticker.display(),
            "total_score": self.total_score,
            "action": self.action,
            "one_liner": self.one_liner,
        }
