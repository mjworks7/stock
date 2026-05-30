"""KRX 종목명 ↔ 코드 변환 (FinanceDataReader 기반, 지연/캐시).

사용자가 종목 코드 대신 한글 종목명("영원무역")을 입력해도 코드(111770)로
변환할 수 있게 한다. FDR 미설치/네트워크 실패 시 None 을 반환하고 호출측이
방어적으로 처리한다.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

_HANGUL_RE = re.compile(r"[가-힣]")
_CODE_RE = re.compile(r"^\d{6}$")


def has_hangul(s: str) -> bool:
    return bool(_HANGUL_RE.search(s or ""))


def is_kr_code(s: str) -> bool:
    return bool(_CODE_RE.match((s or "").strip().split(".")[0]))


@lru_cache(maxsize=1)
def _listing():
    """KRX 전체 종목 리스트(코드/이름). 프로세스당 1회 로드."""
    import FinanceDataReader as fdr  # 지연 import

    df = fdr.StockListing("KRX")
    return df


def _cols(df):
    name_col = "Name" if "Name" in df.columns else None
    code_col = "Code" if "Code" in df.columns else ("Symbol" if "Symbol" in df.columns else None)
    return name_col, code_col


def name_to_code(name: str) -> Optional[str]:
    """한글 종목명 → 6자리 코드. 정확 일치 우선, 실패 시 공백제거 비교."""
    try:
        df = _listing()
        name_col, code_col = _cols(df)
        if not name_col or not code_col:
            return None
        target = (name or "").strip()
        hit = df[df[name_col] == target]
        if hit.empty:
            compact = target.replace(" ", "")
            hit = df[df[name_col].astype(str).str.replace(" ", "", regex=False) == compact]
        if hit.empty:
            return None
        return str(hit.iloc[0][code_col]).zfill(6)
    except Exception:
        return None


def code_to_name(code: str) -> Optional[str]:
    """6자리 코드 → 종목명."""
    try:
        df = _listing()
        name_col, code_col = _cols(df)
        if not name_col or not code_col:
            return None
        c = str(code).zfill(6)
        hit = df[df[code_col].astype(str).str.zfill(6) == c]
        if hit.empty:
            return None
        return str(hit.iloc[0][name_col])
    except Exception:
        return None
