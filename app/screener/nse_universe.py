"""
app/screener/nse_universe.py

Loads the REAL, official list of every NSE-listed stock (~2,000 symbols)
from NSE's own master CSV - the same source Groww/Angel One-style
screeners use. Download it yourself from:
    https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv
Save it as data/EQUITY_L.csv in the project root.
"""
import csv
import os

DEFAULT_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "EQUITY_L.csv")


def load_full_nse_universe(csv_path: str = None, series_filter: str = "EQ") -> list:
    """
    Returns a list of "SYMBOL.NS" tickers ready for yfinance.
    series_filter defaults to EQ only (normal, freely tradable stocks) -
    pass None to include everything (BE/BZ trade-for-trade restricted too).
    """
    path = csv_path or DEFAULT_CSV_PATH
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"NSE master list not found at {path}. Download it from "
            f"https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv "
            f"and save it as data/EQUITY_L.csv in your project root."
        )

    symbols = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row.get("SYMBOL", "").strip()
            series = row.get(" SERIES", row.get("SERIES", "")).strip()
            if not symbol:
                continue
            if series_filter and series != series_filter:
                continue
            symbols.append(f"{symbol}.NS")

    return symbols


def get_universe_batch(offset: int = 0, batch_size: int = 50, csv_path: str = None) -> dict:
    """
    Returns one page of the full universe - scanning ~2000 stocks in a
    single request would take many minutes and likely trigger Yahoo
    Finance rate limiting. Page through it instead: offset=0,50,100...
    """
    full_list = load_full_nse_universe(csv_path=csv_path)
    total = len(full_list)
    batch = full_list[offset:offset + batch_size]
    return {
        "total_symbols_in_universe": total,
        "offset": offset,
        "batch_size": batch_size,
        "returned": len(batch),
        "has_more": (offset + batch_size) < total,
        "next_offset": offset + batch_size if (offset + batch_size) < total else None,
        "symbols": batch,
    }