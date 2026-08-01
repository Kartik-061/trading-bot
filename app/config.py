"""
app/config.py
Central config, loaded from environment variables. Never hardcode secrets here -
that's what made BookIQ safe to push to GitHub, same rule applies here.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Mode
    MODE = os.getenv("BOT_MODE", "paper").lower()  # "paper" or "live"

    # Angel One
    ANGEL_API_KEY = os.getenv("ANGEL_API_KEY", "")
    ANGEL_CLIENT_ID = os.getenv("ANGEL_CLIENT_ID", "")
    ANGEL_PASSWORD = os.getenv("ANGEL_PASSWORD", "")
    ANGEL_TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET", "")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tradebot.db")

    # Trading defaults
    PAPER_STARTING_CAPITAL = float(os.getenv("PAPER_STARTING_CAPITAL", "100000"))
    DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "SBIFUNDS")
    DEFAULT_QTY = int(os.getenv("DEFAULT_QTY", "1"))

    @classmethod
    def validate_for_live(cls):
        missing = [
            name for name, val in [
                ("ANGEL_API_KEY", cls.ANGEL_API_KEY),
                ("ANGEL_CLIENT_ID", cls.ANGEL_CLIENT_ID),
                ("ANGEL_PASSWORD", cls.ANGEL_PASSWORD),
                ("ANGEL_TOTP_SECRET", cls.ANGEL_TOTP_SECRET),
            ] if not val
        ]
        if missing:
            raise RuntimeError(f"Missing credentials for LIVE mode: {missing}")


settings = Settings()
