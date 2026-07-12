import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
STEPAN_ID = int(os.getenv("STEPAN_ID", "0"))
SERGEY_ID = int(os.getenv("SERGEY_ID", "0"))
INITIAL_DEBT = int(os.getenv("INITIAL_DEBT", "4000"))
INTEREST_RATE = float(os.getenv("INTEREST_RATE", "0.02"))
INTEREST_START_DATE = os.getenv("INTEREST_START_DATE", "2026-08-01")
REMINDER_INTERVAL = int(os.getenv("REMINDER_INTERVAL", str(4 * 60 * 60)))
DEBTOR_NAME = os.getenv("DEBTOR_NAME", "Степан")
OWNER_NAME = os.getenv("OWNER_NAME", "Сергей")
BANK_NAME = os.getenv("BANK_NAME", "СергоБанк")
PROXY_URL = os.getenv("PROXY_URL", "")

NEURAL_ENABLED = os.getenv("NEURAL_ENABLED", "True").lower() == "true"
NEURAL_PROVIDER = os.getenv("NEURAL_PROVIDER", "gemini")
NEURAL_API_KEY = os.getenv("NEURAL_API_KEY", "")
NEURAL_MODEL = os.getenv("NEURAL_MODEL", "gemini-3.1-flash-lite")
