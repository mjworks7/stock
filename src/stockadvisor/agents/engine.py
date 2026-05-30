"""분석 엔진 인터페이스 + 팩토리.

동일한 인터페이스를 LLM 엔진(Claude API)과 휴리스틱 엔진(오프라인)이
구현한다. 오케스트레이션 계층은 엔진 종류를 몰라도 된다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import Config
from ..domain import (
    AnalystOpinion,
    MacroSnapshot,
    PortfolioReview,
    RankingEntry,
    StockData,
    StockVerdict,
)


class AnalysisEngine(ABC):
    """전문가 에이전트 구동 엔진."""

    @abstractmethod
    def analyze_macro(self, macro: MacroSnapshot) -> AnalystOpinion:
        ...

    @abstractmethod
    def analyze_sector(self, data: StockData, macro: MacroSnapshot) -> AnalystOpinion:
        ...

    @abstractmethod
    def analyze_fundamental(self, data: StockData) -> AnalystOpinion:
        ...

    @abstractmethod
    def analyze_valuation(self, data: StockData) -> AnalystOpinion:
        ...

    @abstractmethod
    def synthesize(
        self,
        data: StockData,
        macro_op: AnalystOpinion,
        opinions: list[AnalystOpinion],
    ) -> StockVerdict:
        """리스크 매니저 관점에서 종합 판단(적정성/대응/목표가/손절)을 산출."""
        ...

    @abstractmethod
    def rank(self, verdicts: list[StockVerdict]) -> tuple[list[RankingEntry], str]:
        """여러 종목 종합 판단을 비교하여 추천 순위 + 총평을 산출."""
        ...

    @abstractmethod
    def review_portfolio(self, review: PortfolioReview) -> PortfolioReview:
        """정량 지표가 채워진 보유 포트폴리오에 리스크 매니저 관점의
        정성 가이드(종목별 조치/경고/리밸런싱/총평)를 추가해 반환."""
        ...


def build_engine(cfg: Config, offline: bool = False) -> AnalysisEngine:
    """API 키 유무/오프라인 플래그에 따라 적절한 엔진을 선택."""
    use_llm = cfg.has_api_key and not offline
    if use_llm:
        try:
            from .llm import LLMEngine

            return LLMEngine(cfg)
        except Exception as e:  # anthropic 미설치 등
            print(f"[경고] LLM 엔진 초기화 실패 ({e}). 휴리스틱 엔진으로 대체합니다.")
    from .heuristic import HeuristicEngine

    return HeuristicEngine(cfg)
