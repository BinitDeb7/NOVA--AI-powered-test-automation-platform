import os
import time
import requests
from dotenv import load_dotenv

load_dotenv(override=False)  # Docker env vars must take precedence over .env

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")

_MAX_RETRIES   = 2
_RETRY_DELAY   = 1.5   # seconds between retries
_DEFAULT_TIMEOUT = 120  # seconds per attempt


def _is_ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def ask_ollama(prompt: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    if not _is_ollama_running():
        return (
            f"⚠️ Ollama is not running. Start it with: ollama serve\n"
            f"Then make sure the model is available: ollama pull {OLLAMA_MODEL}"
        )

    last_error = ""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model":  OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json().get("response", "").strip()
            if result:
                return result
            last_error = "Ollama returned an empty response."

        except requests.exceptions.ConnectionError:
            last_error = (
                f"⚠️ Cannot reach Ollama at {OLLAMA_BASE_URL}. "
                f"Run: ollama serve  (and: ollama pull {OLLAMA_MODEL})"
            )
            break  # No point retrying a connection error

        except requests.exceptions.Timeout:
            last_error = (
                f"⏱️ Ollama timed out after {timeout}s "
                f"(attempt {attempt}/{_MAX_RETRIES}). "
                "The model may be loading — try again in a moment."
            )

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            if status == 404:
                last_error = (
                    f"⚠️ Model '{OLLAMA_MODEL}' not found. "
                    f"Pull it with: ollama pull {OLLAMA_MODEL}"
                )
                break  # No point retrying a missing model
            last_error = f"Ollama HTTP {status}: {e}"

        except Exception as e:
            last_error = f"Ollama error: {e}"

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_DELAY)

    return last_error
