"""
Service layer: Selenium test execution + async job store.
The route layer submits jobs here and polls for results.
"""
import json
import os
from flask import current_app
from app import db, celery_ext
from app.models import TestRun
from app.services.ai_service import analyze_code_for_bugs

# ── Background worker ──────────────────────────────────────────

@celery_ext.task(bind=True)
def run_test_job(self, url: str, commands_text: str,
                 test_case_id, is_visual_test: bool, user_id: int) -> dict:
        try:
            results_array = _execute_selenium_test(url, commands_text, test_case_id, is_visual_test)

            failed_steps   = [r for r in results_array
                              if str(r.get("status", "")).lower() in ("failed", "visual mismatch")]
            total_steps    = len(results_array)
            summary        = (f"Executed {total_steps} step(s) on {url}. " +
                              (f"{len(failed_steps)} step(s) failed." if failed_steps else "All steps succeeded."))
            logs           = "\n".join(
                f"Step {r.get('step')}: [{r.get('status')}] {r.get('command')} - {r.get('details', '')}"
                for r in results_array
            )
            probable_cause, suggested_fix = _extract_ai_suggestion(failed_steps)
            overall_status = "Success" if not failed_steps else "Failed"

            _persist_test_run(url, overall_status, results_array, user_id)

            return {
                "success":        True,
                "summary":        summary,
                "logs":           logs,
                "results":        results_array,
                "probable_cause": probable_cause,
                "suggested_fix":  suggested_fix,
                "result_text":    f"{summary}\n\n{logs}",
                "results_html":   f"{summary}\n\n{logs}".replace("\n", "<br>"),
                "test_results":   f"{summary}\n\n{logs}",
            }
        except Exception as e:
            # Raise so Celery captures the failure
            raise e


# ── Selenium execution ─────────────────────────────────────────

def _execute_selenium_test(url: str, commands_text: str,
                            test_case_id=None, is_visual_test: bool = False) -> list:
    import base64, io, json as _json
    from PIL import Image, ImageChops
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import WebDriverException, TimeoutException
    from app.models import TestCase

    baseline_images = {}
    if is_visual_test and test_case_id:
        tc = TestCase.query.get(test_case_id)
        if tc and tc.baseline_images_json:
            baseline_images = _json.loads(tc.baseline_images_json)

    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = webdriver.ChromeOptions()
    for arg in (
        "--headless=new",
        "--window-size=1280,800",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-blink-features=AutomationControlled",
        "--remote-debugging-port=0",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ):
        options.add_argument(arg)

    # In Docker (Linux) use the system-installed ChromeDriver to avoid
    # webdriver-manager downloading a mismatched or unavailable binary.
    import platform, shutil
    driver = None

    # Prefer an explicit path set by the Dockerfile, then fall back to PATH lookup
    chromedriver_path = (
        os.environ.get("CHROMEDRIVER_PATH")
        or shutil.which("chromedriver")
    )

    if chromedriver_path and platform.system() != "Windows":
        # Docker / Linux path — use system ChromeDriver directly
        try:
            service = Service(chromedriver_path)
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            return [{"step": "Setup", "command": "Initialize WebDriver",
                     "status": "Failed",
                     "details": f"System ChromeDriver error: {str(e)}"}]
    else:
        # Local dev path — let webdriver-manager download the right version
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            try:
                driver = webdriver.Chrome(options=options)
            except Exception as inner_e:
                return [{"step": "Setup", "command": "Initialize WebDriver",
                         "status": "Failed",
                         "details": f"DriverManager error: {str(e)} | Local fallback error: {str(inner_e)}"}]

    driver.get(url)
    results  = []
    commands = [c.strip() for c in commands_text.split("\n") if c.strip()]

    BY_MAP = {
        'id': By.ID,
        'name': By.NAME,
        'xpath': By.XPATH,
        'class_name': By.CLASS_NAME,
        'css_selector': By.CSS_SELECTOR,
        'link_text': By.LINK_TEXT,
        'partial_link_text': By.PARTIAL_LINK_TEXT,
        'tag_name': By.TAG_NAME,
    }

    def _resolve_by(selector_str):
        if '=' not in selector_str:
            raise ValueError(f"Invalid selector format '{selector_str}'. Use: type=value (e.g. id=username)")
        by_key, val = selector_str.split('=', 1)
        by = BY_MAP.get(by_key.strip().lower())
        if not by:
            raise ValueError(f"Unknown selector type '{by_key}'. Use: id, name, xpath, class_name, css_selector, link_text")
        return by, val.strip()

    for i, command in enumerate(commands):
        step = {"step": i + 1, "command": command, "status": "Failed", "details": ""}
        try:
            wait   = WebDriverWait(driver, 20)
            action = command.lower().split()[0]

            if action == "type":
                text     = command.split('"')[1]
                selector = command.split('into')[1].strip().replace('"', '')
                by, val = _resolve_by(selector)
                el = wait.until(EC.presence_of_element_located((by, val)))
                el.clear(); el.send_keys(text)
                step.update(status="Success", details=f"Typed '{text}'")

            elif action == "click":
                selector = command.split('click')[1].strip().replace('"', '')
                by, val = _resolve_by(selector)
                el = wait.until(EC.element_to_be_clickable((by, val)))
                el.click()
                step.update(status="Success", details="Clicked element")

            elif action == "verify":
                text     = command.split('"')[1]
                selector = command.split('in ')[1].strip().replace('"', '')
                by, val = _resolve_by(selector)
                wait.until(EC.text_to_be_present_in_element((by, val), text))
                step.update(status="Success", details=f"Verified text '{text}'")

            elif action == "navigate":
                import time as _navtime
                parts = command.split('"')
                nav_url = parts[1] if len(parts) > 1 else command.split()[-1]
                driver.get(nav_url)
                # Wait for full DOM ready (handles cold-start / slow sites like Heroku)
                try:
                    WebDriverWait(driver, 20).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                except Exception:
                    _navtime.sleep(2)  # fallback if JS execution fails
                step.update(status="Success", details=f"Navigated to {nav_url}")

            elif action == "wait":
                import time
                try:
                    seconds = float(command.split()[-1])
                    time.sleep(seconds)
                    step.update(status="Success", details=f"Waited for {seconds} seconds")
                except Exception as e:
                    raise ValueError(f"Invalid wait duration: {str(e)}")

            else:
                step["details"] = "Unsupported command"

            if is_visual_test:
                screenshot = driver.get_screenshot_as_base64()
                baseline   = baseline_images.get(str(i + 1))
                if baseline:
                    diff_pct, diff_img = _compare_images(baseline, screenshot)
                    if diff_pct > 0.1:
                        step.update(status="Visual Mismatch",
                                    details=f"{diff_pct:.2f}% difference",
                                    screenshot=diff_img,
                                    baseline=baseline,
                                    current_screenshot=screenshot)
                    else:
                        step.update(status="Visuals Match",
                                    details="Visual comparison matched baseline",
                                    screenshot=screenshot,
                                    baseline=baseline)
                else:
                    step.update(status="New Baseline", screenshot=screenshot)

        except TimeoutException:
            step["details"]       = "Element not found"
            step["ai_suggestion"] = _get_ai_bug_suggestion(step["details"], url, command)
        except WebDriverException as e:
            step["details"]       = str(e)
            step["ai_suggestion"] = _get_ai_bug_suggestion(str(e), url, command)
        except Exception as e:
            step["details"]       = f"Syntax Error: {str(e)}"

        results.append(step)
        if step["status"] in ("Failed", "Visual Mismatch"):
            break

    driver.quit()
    return results


def _compare_images(base64_img1: str, base64_img2: str):
    import base64, io
    from PIL import Image, ImageChops
    img1 = Image.open(io.BytesIO(base64.b64decode(base64_img1)))
    img2 = Image.open(io.BytesIO(base64.b64decode(base64_img2)))
    if img1.size != img2.size:
        return 100.0, None
    diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
    if not diff.getbbox():
        return 0.0, None
    diff_pixels  = sum(1 for p in diff.getdata() if any(v > 32 for v in p))
    diff_percent = (diff_pixels / (img1.size[0] * img1.size[1])) * 100
    buf = io.BytesIO()
    diff.save(buf, format="PNG")
    return diff_percent, base64.b64encode(buf.getvalue()).decode()


def _get_ai_bug_suggestion(error: str, url: str, command: str) -> str:
    try:
        from app.ai.ollama_client import ask_ollama
        prompt = (f"Selenium test failed.\nURL: {url}\nCommand: {command}\nError: {error}\n\n"
                  "Provide a brief cause and suggest a correct test command using ONLY one of the exact formats:\n"
                  "- type \"text\" into \"selector=value\"\n"
                  "- click \"selector=value\"\n"
                  "- verify text \"text\" in \"selector=value\"\n"
                  "(Where selector is: id, name, class_name, xpath, css_selector, or link_text).\n\n"
                  "EXAMPLES:\n"
                  "Example 1:\n"
                  "URL: https://facebook.com\n"
                  "Command: type \"myemail@domain.com\" into \"id=login_form_email\"\n"
                  "Error: Element not found\n"
                  "Output:\n"
                  "Probable Cause: The Facebook email input element ID is 'email', not 'login_form_email'.\n"
                  "Suggested Fix: type \"myemail@domain.com\" into \"id=email\"\n\n"
                  "Example 2:\n"
                  "URL: https://example.com\n"
                  "Command: click \"id=submit_btn\"\n"
                  "Error: Element not found\n"
                  "Output:\n"
                  "Probable Cause: The submit button uses the class name 'btn-submit' or ID 'btn-submit-action' instead of 'submit_btn'.\n"
                  "Suggested Fix: click \"id=btn-submit-action\"\n\n"
                  "DO NOT use Java, Python, or raw Selenium code. DO NOT explain standard selenium waits or troubleshooting steps. Respond exactly in the format above.")
        return ask_ollama(prompt)
    except Exception:
        return "AI unavailable. Please inspect selectors manually."


def _extract_ai_suggestion(failed_steps: list) -> tuple[str, str]:
    import re
    if not failed_steps:
        return "", ""
    ai_suggestion = failed_steps[0].get("ai_suggestion", "") or ""
    
    match = re.search(r'(?i)\*?probable cause:\*?\s*(.*?)\s*\*?suggested fix:\*?\s*(.*)', ai_suggestion, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
        
    if "Suggested Fix:" in ai_suggestion and "Probable Cause:" in ai_suggestion:
        try:
            pc_part = ai_suggestion.split("Probable Cause:", 1)[1]
            if "Suggested Fix:" in pc_part:
                pc, sf = pc_part.split("Suggested Fix:", 1)
                return pc.strip(), sf.strip()
            return pc_part.strip(), ""
        except Exception:
            pass
    return ai_suggestion, ""


def _persist_test_run(url: str, status: str, results: list, user_id: int):
    try:
        stripped = [{k: v for k, v in r.items() if k != 'screenshot'} for r in results]
        db.session.add(TestRun(url_tested=url, status=status,
                               results_json=json.dumps(stripped), user_id=user_id))
        db.session.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not persist test run: {e}")
