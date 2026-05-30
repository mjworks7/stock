"""데이터 계층: 시세/재무/거시 데이터 조회. 인터페이스로 추상화하여 교체 가능."""
from .provider import MarketDataProvider, detect_market, resolve_ticker

__all__ = ["MarketDataProvider", "detect_market", "resolve_ticker"]
