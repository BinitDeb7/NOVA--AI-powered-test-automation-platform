from .router import route
from .mini_llm import generate
from .ollama_client import ask_ollama

_MIN_RESPONSE_WORDS = 6


def _is_good_response(text: str) -> bool:
    words = text.lower().split()
    if len(words) < _MIN_RESPONSE_WORDS:
        return False
    from collections import Counter
    counts = Counter(words)
    most_common_count = counts.most_common(1)[0][1]
    if most_common_count > 3:
        return False
    if most_common_count / len(words) > 0.35:
        return False
    return True


def ask(prompt: str) -> str:
    source = route(prompt)

    if source == "mini":
        mini_response = generate(prompt)

        if _is_good_response(mini_response):
            print(f"[Hybrid AI] Mini LLM responded ({len(mini_response.split())} words)")
            return mini_response
        else:
            print(
                f"[Hybrid AI] Mini LLM response rejected (low quality) "
                "-- falling back to Ollama"
            )
            return ask_ollama(prompt)

    print("[Hybrid AI] Routing to Ollama (general query)")
    return ask_ollama(prompt)
