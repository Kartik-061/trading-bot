from app.strategies.ema_rsi import EmaRsiStrategy
from app.strategies.mean_reversion import MeanReversionStrategy

STRATEGY_REGISTRY = {
    "ema_rsi": EmaRsiStrategy,
    "mean_reversion": MeanReversionStrategy,
}