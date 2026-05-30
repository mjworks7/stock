"""Claude tool-use 강제 출력을 위한 JSON 스키마 정의.

각 분석가는 자유 서술 대신 아래 스키마에 맞춰 구조화된 결과를 반환한다.
파싱 안정성을 위해 tool_choice 로 강제한다.
"""
from __future__ import annotations

# 개별 분석가 의견 스키마
OPINION_SCHEMA = {
    "type": "object",
    "properties": {
        "stance": {
            "type": "string",
            "enum": ["bullish", "neutral", "bearish"],
            "description": "해당 관점에서의 종합 입장",
        },
        "score": {
            "type": "number",
            "description": "0~100. 이 관점에서 본 매력도(높을수록 긍정적).",
        },
        "confidence": {"type": "number", "description": "0~1. 데이터 충분성/확신도."},
        "summary": {"type": "string", "description": "1~3문장 한국어 핵심 요약."},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "근거가 되는 핵심 포인트 2~5개.",
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "이 관점에서 주의할 리스크 1~4개.",
        },
    },
    "required": ["stance", "score", "confidence", "summary", "key_points", "risks"],
}

_TARGET_BAND = {
    "type": "object",
    "properties": {
        "low": {"type": "number", "description": "보수적 목표가"},
        "base": {"type": "number", "description": "기준 목표가"},
        "high": {"type": "number", "description": "낙관적 목표가"},
        "rationale": {"type": "string", "description": "산출 근거 한 문장"},
    },
    "required": ["low", "base", "high", "rationale"],
}

# 종합 판단(리스크 매니저) 스키마
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "valuation_judgment": {
            "type": "string",
            "enum": ["저평가", "적정", "고평가"],
            "description": "현재 주가의 적정성 판단.",
        },
        "action": {
            "type": "string",
            "enum": ["적극매수", "분할매수", "관망", "비중축소", "매도"],
            "description": "현재 시점 권고 대응.",
        },
        "conviction": {"type": "number", "description": "0~100 종합 확신도."},
        "total_score": {"type": "number", "description": "0~100 종합 점수(순위 산출 기준)."},
        "target_short": _TARGET_BAND,
        "target_mid": _TARGET_BAND,
        "target_long": _TARGET_BAND,
        "stop_loss": {"type": "number", "description": "손절 권고가."},
        "suggested_position_pct": {
            "type": "number",
            "description": "포트폴리오 내 권고 비중 상한(%).",
        },
        "thesis": {"type": "string", "description": "투자 논리 2~4문장 한국어 요약."},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "catalysts": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "valuation_judgment",
        "action",
        "conviction",
        "total_score",
        "target_short",
        "target_mid",
        "target_long",
        "stop_loss",
        "suggested_position_pct",
        "thesis",
        "key_risks",
        "catalysts",
    ],
}

# 순위 산출 스키마
RANKING_SCHEMA = {
    "type": "object",
    "properties": {
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "종목 코드/심볼(raw)."},
                    "rank": {"type": "integer"},
                    "total_score": {"type": "number"},
                    "one_liner": {"type": "string", "description": "추천/비추천 한 줄 이유."},
                },
                "required": ["ticker", "rank", "total_score", "one_liner"],
            },
        },
        "summary": {"type": "string", "description": "전체 비교 총평 2~4문장."},
    },
    "required": ["ranking", "summary"],
}
