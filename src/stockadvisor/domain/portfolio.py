"""보유 포트폴리오 도메인 모델 — 순수 dataclass."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .models import Ticker


@dataclass
class Holding:
    """사용자 입력 보유 내역."""

    raw_ticker: str
    shares: float
    avg_price: float  # 평균 매수단가(해당 종목 통화 기준)


@dataclass
class Position:
    """현재가가 반영된 보유 종목 평가."""

    ticker: Ticker
    currency: str
    shares: float
    avg_price: float
    current_price: Optional[float] = None

    cost_basis: float = 0.0       # 매입금액(종목 통화)
    market_value: float = 0.0     # 평가금액(종목 통화)
    pnl: float = 0.0              # 평가손익(종목 통화)
    pnl_pct: float = 0.0          # 수익률(%)
    weight_pct: float = 0.0       # 포트폴리오 내 비중(기준통화 환산)
    value_base: float = 0.0       # 기준통화 환산 평가금액
    sector: str = ""

    # 리스크 매니저 가이드
    flags: list[str] = field(default_factory=list)   # 집중/손절 등 경고
    action: str = "보유"          # 추가매수 / 보유 / 일부익절 / 비중축소 / 손절
    stop_loss: Optional[float] = None
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ticker"] = self.ticker.display()
        return d


@dataclass
class PortfolioReview:
    base_currency: str = "KRW"
    fx_usdkrw: float = 1350.0
    positions: list[Position] = field(default_factory=list)

    total_cost_base: float = 0.0
    total_value_base: float = 0.0
    total_pnl_base: float = 0.0
    total_pnl_pct: float = 0.0
    cash_base: float = 0.0

    sector_weights: dict[str, float] = field(default_factory=dict)
    market_weights: dict[str, float] = field(default_factory=dict)

    risk_alerts: list[str] = field(default_factory=list)
    rebalancing: list[str] = field(default_factory=list)
    summary: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_currency": self.base_currency,
            "fx_usdkrw": self.fx_usdkrw,
            "total_cost_base": self.total_cost_base,
            "total_value_base": self.total_value_base,
            "total_pnl_base": self.total_pnl_base,
            "total_pnl_pct": self.total_pnl_pct,
            "cash_base": self.cash_base,
            "sector_weights": self.sector_weights,
            "market_weights": self.market_weights,
            "risk_alerts": self.risk_alerts,
            "rebalancing": self.rebalancing,
            "summary": self.summary,
            "positions": [p.to_dict() for p in self.positions],
            "errors": self.errors,
        }
