"""
app/data_feed/feeds.py
SimulatedFeed: random-walk generator, zero dependencies, for dev/testing.
AngelLiveFeed: real LTP pulls from Angel One, used when BOT_MODE=live.
"""
import random


class SimulatedFeed:
    def __init__(self, symbols: dict, volatility: float = 0.003):
        """symbols: {"SBIFUNDS": 598.0}"""
        self.prices = dict(symbols)
        self.volatility = volatility

    def get_price(self, symbol: str) -> float:
        move = random.uniform(-self.volatility, self.volatility)
        self.prices[symbol] = round(self.prices[symbol] * (1 + move), 2)
        return self.prices[symbol]


class AngelLiveFeed:
    def __init__(self, broker, token_map: dict):
        """token_map: {"SBIFUNDS": {"exchange": "NSE", "token": "..."}}"""
        self.broker = broker
        self.token_map = token_map

    def get_price(self, symbol: str) -> float:
        meta = self.token_map[symbol]
        return self.broker.get_ltp(meta["exchange"], symbol, meta["token"])
