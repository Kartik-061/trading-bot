export const STRATEGIES = [
  "mean_reversion",
  "ema_rsi",
  "trend_following",
  "volume_confirmed",
] as const;

export type Strategy = (typeof STRATEGIES)[number];

export const INTERVALS = ["5m", "15m", "1h", "1d"] as const;
export const PERIODS = ["60d", "1y", "2y", "5y"] as const;
