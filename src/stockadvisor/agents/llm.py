"""Claude API 기반 분석 엔진.

각 전문가 페르소나를 system 프롬프트로, 정량 데이터를 user 메시지로 주고
tool-use 로 구조화된 결과를 강제 수집한다. 긴 페르소나 프롬프트는
prompt caching 으로 비용을 절감한다.
"""
from __future__ import annotations

from ..config import Config
from ..domain import (
    AnalystOpinion,
    MacroSnapshot,
    RankingEntry,
    StockData,
    StockVerdict,
    TargetBand,
    TargetPrices,
    Ticker,
)
from .context import format_macro, format_stock
from .loader import AGENT_ROLES, load_persona
from .schemas import OPINION_SCHEMA, RANKING_SCHEMA, VERDICT_SCHEMA


class _Client:
    """Anthropic 메시지 API 얇은 래퍼 (구조화 출력 + 캐싱)."""

    def __init__(self, cfg: Config) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=cfg.api_key)
        self.cfg = cfg

    def structured(
        self, persona: str, user_text: str, tool_name: str, schema: dict
    ) -> dict:
        resp = self._client.messages.create(
            model=self.cfg.model,
            max_tokens=self.cfg.max_tokens,
            temperature=self.cfg.temperature,
            system=[
                {
                    "type": "text",
                    "text": persona,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[
                {
                    "name": tool_name,
                    "description": "분석 결과를 이 스키마에 맞춰 반환한다.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user_text}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == tool_name:
                return dict(block.input)
        raise RuntimeError("모델이 구조화된 결과를 반환하지 않았습니다.")


def _opinion_from(d: dict, agent: str, role: str) -> AnalystOpinion:
    return AnalystOpinion(
        analyst=agent,
        role=role,
        stance=str(d.get("stance", "neutral")),
        score=float(d.get("score", 50)),
        confidence=float(d.get("confidence", 0.5)),
        summary=str(d.get("summary", "")),
        key_points=list(d.get("key_points", [])),
        risks=list(d.get("risks", [])),
    )


class LLMEngine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client = _Client(cfg)
        self._agents_dir = str(cfg.agents_dir)

    def _persona(self, agent: str) -> str:
        return load_persona(self._agents_dir, agent)

    def _opinion(self, agent: str, user_text: str) -> AnalystOpinion:
        role = AGENT_ROLES.get(agent, (agent, ""))[0]
        d = self.client.structured(
            self._persona(agent), user_text, "submit_opinion", OPINION_SCHEMA
        )
        return _opinion_from(d, agent, role)

    # ----------------------------------------------------------- 개별 분석
    def analyze_macro(self, macro: MacroSnapshot) -> AnalystOpinion:
        user = (
            format_macro(macro)
            + "\n\n위 거시 지표를 바탕으로 '지금이 주식 비중을 늘리기 좋은 환경인가?'를"
            " 판단해 submit_opinion 으로 제출하라. score 는 주식 익스포저 매력도(0~100)."
        )
        return self._opinion("macro-regime-analyst", user)

    def analyze_sector(self, data: StockData, macro: MacroSnapshot) -> AnalystOpinion:
        user = (
            format_stock(data)
            + "\n\n[시장 국면]\n"
            + format_macro(macro)
            + "\n\n이 종목이 속한 산업/섹터의 성장성·경쟁구도·사이클 위치를 평가해"
            " submit_opinion 으로 제출하라. score 는 섹터 매력도(0~100)."
        )
        return self._opinion("industry-sector-analyst", user)

    def analyze_fundamental(self, data: StockData) -> AnalystOpinion:
        user = (
            format_stock(data)
            + "\n\n매출·영업이익·재무건전성·비즈니스 모델 관점에서 펀더멘털을 평가해"
            " submit_opinion 으로 제출하라. score 는 기업 질(0~100)."
        )
        return self._opinion("fundamental-analyst", user)

    def analyze_valuation(self, data: StockData) -> AnalystOpinion:
        user = (
            format_stock(data)
            + "\n\n'지금 주가가 싼가 비싼가?' 한 가지에 집중해 상대/절대 밸류에이션을"
            " 평가해 submit_opinion 으로 제출하라. score 는 가격 매력도(쌀수록 높음, 0~100)."
        )
        return self._opinion("valuation-quant-analyst", user)

    # --------------------------------------------------------------- 종합
    def synthesize(
        self, data: StockData, macro_op: AnalystOpinion, opinions: list[AnalystOpinion]
    ) -> StockVerdict:
        h = self.cfg.horizons
        op_text = "\n".join(
            f"- [{o.role}] 입장={o.stance}, 점수={o.score:.0f}, 확신={o.confidence:.2f}: {o.summary}"
            for o in [macro_op, *opinions]
        )
        user = (
            format_stock(data)
            + "\n\n[전문가 의견 종합]\n"
            + op_text
            + f"\n\n위 의견을 종합해 리스크 관점에서 최종 판단을 submit_verdict 로 제출하라."
            + f"\n목표가 기간 정의: 단기={h.get('short_term','1-3개월')},"
            + f" 중기={h.get('mid_term','6-12개월')}, 장기={h.get('long_term','1-3년')}."
            + f"\n목표가는 현재가({data.price})와 같은 통화({data.currency}) 절대금액으로 제시."
            + "\nvaluation_judgment 는 밸류에이션 분석가 의견을 우선 반영하라."
        )
        d = self.client.structured(
            self._persona("portfolio-risk-manager"), user, "submit_verdict", VERDICT_SCHEMA
        )
        return self._verdict_from(d, data, [macro_op, *opinions])

    def _verdict_from(
        self, d: dict, data: StockData, opinions: list[AnalystOpinion]
    ) -> StockVerdict:
        h = self.cfg.horizons

        def band(key: str, label: str) -> TargetBand:
            b = d.get(key, {}) or {}
            return TargetBand(
                horizon=label,
                low=_num(b.get("low")),
                base=_num(b.get("base")),
                high=_num(b.get("high")),
                rationale=str(b.get("rationale", "")),
            )

        return StockVerdict(
            ticker=data.ticker,
            currency=data.currency,
            current_price=data.price,
            valuation_judgment=str(d.get("valuation_judgment", "적정")),
            action=str(d.get("action", "관망")),
            conviction=float(d.get("conviction", 50)),
            total_score=float(d.get("total_score", 50)),
            target_prices=TargetPrices(
                short_term=band("target_short", h.get("short_term", "1-3개월")),
                mid_term=band("target_mid", h.get("mid_term", "6-12개월")),
                long_term=band("target_long", h.get("long_term", "1-3년")),
            ),
            stop_loss=_num(d.get("stop_loss")),
            suggested_position_pct=_num(d.get("suggested_position_pct")),
            thesis=str(d.get("thesis", "")),
            key_risks=list(d.get("key_risks", [])),
            catalysts=list(d.get("catalysts", [])),
            opinions=opinions,
        )

    # --------------------------------------------------------------- 순위
    def rank(self, verdicts: list[StockVerdict]) -> tuple[list[RankingEntry], str]:
        if len(verdicts) == 1:
            v = verdicts[0]
            return (
                [RankingEntry(1, v.ticker, v.total_score, v.action, v.thesis[:80])],
                "단일 종목이므로 비교 순위는 생략합니다.",
            )
        rows = "\n".join(
            f"- {v.ticker.raw} ({v.ticker.name}): 종합점수={v.total_score:.0f},"
            f" 적정성={v.valuation_judgment}, 대응={v.action}, 확신={v.conviction:.0f}."
            f" 논리: {v.thesis}"
            for v in verdicts
        )
        user = (
            "다음은 여러 종목의 종합 판단이다. 매수 매력도 기준으로 추천 순위를 매기고"
            " submit_ranking 으로 제출하라. ticker 는 각 항목의 코드를 그대로 사용.\n\n"
            + rows
        )
        d = self.client.structured(
            self._persona("portfolio-risk-manager"), user, "submit_ranking", RANKING_SCHEMA
        )
        by_raw: dict[str, Ticker] = {v.ticker.raw: v.ticker for v in verdicts}
        entries: list[RankingEntry] = []
        for item in d.get("ranking", []):
            raw = str(item.get("ticker", ""))
            tk = by_raw.get(raw) or by_raw.get(raw.split(".")[0])
            if tk is None:
                continue
            entries.append(
                RankingEntry(
                    rank=int(item.get("rank", len(entries) + 1)),
                    ticker=tk,
                    total_score=float(item.get("total_score", 0)),
                    action=next((v.action for v in verdicts if v.ticker is tk), ""),
                    one_liner=str(item.get("one_liner", "")),
                )
            )
        entries.sort(key=lambda e: e.rank)
        return entries, str(d.get("summary", ""))


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None
