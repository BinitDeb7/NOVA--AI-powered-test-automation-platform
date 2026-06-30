MINI_LLM_KEYWORDS = {
    "selenium",
    "test",
    "testing",
    "automation",
    "click",
    "verify",
    "locator",
    "xpath",
    "webdriver",
    "driver",
    "element",
    "selector",
    "css",
    "assert",
    "pytest",
    "browser",
    "headless",
    "wait",
    "screenshot",
    "regression",
    "smoke",
    "unit",
    "integration",
    "framework",
    "script",
    "bug",
    "defect",
    "testcase",
    "suite",
}


def route(prompt: str) -> str:
    prompt_lower = prompt.lower()
    words = set(prompt_lower.split())

    for keyword in MINI_LLM_KEYWORDS:
        if keyword in words or keyword in prompt_lower:
            return "mini"

    return "ollama"
