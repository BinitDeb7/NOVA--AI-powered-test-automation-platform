"""
Service layer: AI-powered test operations.
Wraps the AI layer so routes never import from app.ai directly.
"""
import os
import re
from app.ai.ollama_client import ask_ollama as _ask


def generate_script_from_goal(url: str, goal: str) -> str:
    import requests as _req

    html = _fetch_page_html(url)

    prompt = f"""Generate Selenium test commands for the following goal.
Use ONLY these three command formats (one per line, no numbering or bullet points):
  type "text" into "selector=value"
  click "selector=value"
  verify text "text" in "selector=value"

Where selector is one of: id, name, class_name, xpath, css_selector, link_text

USER GOAL:
{goal}

URL: {url}

{f"PAGE HTML (use element IDs/names/classes from this):{chr(10)}{html}" if html else ""}

Return ONLY the commands, nothing else."""

    result = _ask(prompt)
    if result.startswith("⚠️") or result.startswith("AI Error:"):
        raise RuntimeError(result)

    # Strip markdown and filter out conversational fluff
    result = re.sub(r'```[a-z]*\n?', '', result).strip()
    valid_lines = [
        line.strip() for line in result.split('\n')
        if line.strip().startswith(("type ", "click ", "verify "))
    ]
    return "\n".join(valid_lines)


def _fetch_page_html(url: str) -> str:
    """Fetch page HTML for context. Uses a plain HTTP request first (fast, no
    timeout risk). Falls back to a headless Chrome fetch only when the plain
    request returns an empty or script-only body (SPA / JS-rendered sites)."""
    import requests as _req

    # ── Fast path: plain HTTP request ────────────────────────────────────
    try:
        resp = _req.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NOVABot/1.0)"},
        )
        raw = resp.text
        # Strip tags we don't need
        raw = re.sub(r'<(script|style|svg|img|video|audio|noscript|iframe)[^>]*>.*?</\1>',
                     '', raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r'<[^>]+>', ' ', raw)           # strip remaining tags
        cleaned = re.sub(r'\s+', ' ', raw).strip()[:4000]
        if len(cleaned) > 200:                        # got real content
            return cleaned
    except Exception as e:
        print(f"[AI Service] HTTP fetch failed: {e}")

    # ── Slow path: headless Chrome (only for JS-heavy SPAs) ──────────────
    try:
        import platform, shutil
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.service import Service as _Svc

        options = webdriver.ChromeOptions()
        for arg in (
            "--headless=new", "--window-size=1280,800", "--no-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu", "--disable-extensions",
            "--remote-debugging-port=0",
        ):
            options.add_argument(arg)

        chromedriver_path = (
            os.environ.get("CHROMEDRIVER_PATH") or shutil.which("chromedriver")
        )
        if chromedriver_path and platform.system() != "Windows":
            driver = webdriver.Chrome(service=_Svc(chromedriver_path), options=options)
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            driver = webdriver.Chrome(service=_Svc(ChromeDriverManager().install()), options=options)

        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        js = """
        let c = document.body.cloneNode(true);
        ['script','style','svg','img','video','audio','noscript','iframe']
          .forEach(t => c.querySelectorAll(t).forEach(el => el.remove()));
        return c.innerHTML;
        """
        raw_html = driver.execute_script(js) or ""
        driver.quit()
        return re.sub(r'\s+', ' ', raw_html).strip()[:4000]
    except Exception as e:
        print(f"[AI Service] Chrome fetch failed: {e}")
        return ""


def translate_natural_language_to_command(natural_command: str) -> str:
    prompt = f"""Convert the following plain English instruction into Selenium test commands.

Use ONLY these exact formats (one per line):
  type "text" into "selector=value"
  click "selector=value"
  verify text "text" in "selector=value"

Where selector must be one of: id, name, class_name, xpath, css_selector, link_text

Instruction: {natural_command}

Return ONLY the command lines. No explanation, no numbering, no markdown."""
    try:
        result = _ask(prompt).strip()
        if not result or result.startswith("Ollama") or result.startswith("AI Error"):
            raise RuntimeError(result or "AI returned empty response")
            
        # Strip markdown and filter out conversational fluff
        result = re.sub(r'```[a-z]*\n?', '', result).strip()
        valid_lines = [
            line.strip() for line in result.split('\n')
            if line.strip().startswith(("type ", "click ", "verify "))
        ]
        return "\n".join(valid_lines)
    except Exception:
        return _fallback_script()


def _fallback_script() -> str:
    return (
        'type "test@example.com" into "id=email"\n'
        'type "wrongpassword" into "id=pass"\n'
        'click "name=login"\n'
        'verify text "incorrect" in "xpath=//*[contains(text(),\'incorrect\')]"'
    )


def analyze_code_for_bugs(code: str) -> str:
    prompt = f"""You are an expert Python code reviewer. Analyze the following code for:
1. **Bugs** — logic errors, off-by-one errors, null/None issues
2. **Security vulnerabilities** — injection, unsafe operations
3. **Performance issues** — inefficient loops, memory leaks
4. **Best practice violations** — naming, structure, PEP 8

Format your response in Markdown with clear sections and code examples.

```python
{code}
```"""
    return _ask(prompt)


def generate_unit_tests(code: str) -> str:
    prompt = f"""You are an expert Python test engineer. Generate a complete pytest unit test suite for the following code.

Include:
- Tests for normal/expected inputs
- Edge cases (empty, None, boundary values)
- Error/exception handling tests
- Use descriptive test names

Return ONLY the complete test file content in a Python code block.

```python
{code}
```"""
    return _ask(prompt)


def refactor_code(code: str) -> str:
    prompt = f"""You are an expert Python developer. Refactor the following code to improve:
1. **Readability** — clear naming, proper structure
2. **Performance** — optimize algorithms, reduce complexity
3. **Maintainability** — modular design, DRY principle
4. **Best practices** — type hints, docstrings, PEP 8

Show the refactored code and explain what you changed and why.

```python
{code}
```"""
    return _ask(prompt)
