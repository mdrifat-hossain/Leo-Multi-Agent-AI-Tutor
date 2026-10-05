"""Central configuration. No secrets are stored in code - keys come from the
environment, a local .env file, or Kaggle Secrets."""
import os
from pathlib import Path

# Keep CrewAI quiet / offline-friendly (avoids telemetry hangs on Kaggle).
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

_model = os.getenv("LEO_MODEL", "gemini/gemini-3.5-flash-lite").strip()
MODEL_NAME = _model if "/" in _model else f"gemini/{_model}"

N_QUESTIONS = max(1, min(5, int(os.getenv("LEO_N_QUESTIONS", "3"))))
MAX_ROUNDS = max(1, int(os.getenv("LEO_MAX_ROUNDS", "3")))   # quiz rounds (feedback loop)
PASS_SCORE = float(os.getenv("LEO_PASS_SCORE", "0.7"))       # below this -> re-teach
MAX_RETRIES = int(os.getenv("LEO_MAX_RETRIES", "3"))         # Coordinator retry budget
AGENT_TIMEOUT = int(os.getenv("LEO_AGENT_TIMEOUT", "120"))   # seconds before an agent is "stalled"
MAX_ITER = int(os.getenv("LEO_MAX_ITER", "4"))
USE_TOOLS = os.getenv("LEO_USE_TOOLS", "true").lower() == "true"
VERBOSE = os.getenv("LEO_VERBOSE", "false").lower() == "true"
MEMORY_PATH = Path(os.getenv("LEO_MEMORY_PATH", "leo_memory.json"))


def get_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        try:  # Kaggle Secrets (Add-ons -> Secrets -> GEMINI_API_KEY)
            from kaggle_secrets import UserSecretsClient
            key = UserSecretsClient().get_secret("GEMINI_API_KEY")
        except Exception:
            key = None
    if not key:
        raise RuntimeError(
            "No API key found. Set GEMINI_API_KEY (env var, .env file or Kaggle Secret)."
        )
    os.environ["GEMINI_API_KEY"] = key
    return key
