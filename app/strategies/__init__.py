from app.strategies.ema_rsi import EmaRsiStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.volume_confirmed import VolumeConfirmedStrategy
from app.strategies.trend_following import TrendFollowingStrategy

STRATEGY_REGISTRY = {
    "ema_rsi": EmaRsiStrategy,
    "mean_reversion": MeanReversionStrategy,
    "volume_confirmed": VolumeConfirmedStrategy,
    "trend_following": TrendFollowingStrategy,
}