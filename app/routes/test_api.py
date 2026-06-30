"""
Test API routes — async test execution, job polling, script generation,
NL translation, code analysis, test suite management.
"""
import json
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app import db, limiter
from app.models import TestCase
from app.services.test_service import run_test_job
from app.services.ai_service import (
    generate_script_from_goal,
    translate_natural_language_to_command,
    analyze_code_for_bugs,
    generate_unit_tests,
    refactor_code,
)

test_api_bp = Blueprint('test_api', __name__)


# ── Async test execution ───────────────────────────────────────

@test_api_bp.route('/run-test', methods=['POST'])
@login_required
@limiter.limit("4 per minute")
def run_test():
    data           = request.get_json() or {}
    url            = data.get('url')
    commands_text  = data.get('commands')
    test_case_id   = data.get('test_case_id')
    is_visual_test = bool(data.get('is_visual_test', False))

    if not url or not commands_text:
        return jsonify({"success": False, "error": "Missing URL or test commands"}), 400

    task = run_test_job.delay(url, commands_text, test_case_id, is_visual_test, current_user.id)
    return jsonify({"job_id": task.id, "status": "running"})


@test_api_bp.route('/job/<job_id>', methods=['GET'])
@login_required
def job_status(job_id: str):
    task = run_test_job.AsyncResult(job_id)
    if task.state == 'PENDING':
        return jsonify({"status": "running"})
    elif task.state == 'PROGRESS':
        return jsonify({"status": "running"})
    elif task.state == 'SUCCESS':
        return jsonify({"status": "done", **task.result})
    elif task.state == 'FAILURE':
        return jsonify({"success": False, "status": "error", "error": str(task.info)}), 500
    return jsonify({"status": "error", "error": "Unknown Task State"}), 500


# ── AI script generation ───────────────────────────────────────

@test_api_bp.route('/generate-script', methods=['POST'])
@login_required
@limiter.limit("6 per minute")
def generate_script():
    data = request.get_json() or {}
    url  = data.get('url')
    goal = data.get('goal')
    if not url or not goal:
        return jsonify({"error": "Missing URL or goal"}), 400
    try:
        script = generate_script_from_goal(url, goal)
    except Exception as e:
        current_app.logger.exception("Script generation error")
        return jsonify({"error": str(e)}), 500
    if not script:
        return jsonify({"error": "AI did not return a script"}), 500
    return jsonify({"script": script})


# ── NL translation ─────────────────────────────────────────────

@test_api_bp.route('/translate', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def translate():
    text = (request.get_json() or {}).get('text', '').strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        result = translate_natural_language_to_command(text)
        if not result or result.startswith("Ollama") or result.startswith("AI Error"):
            return jsonify({"error": "AI unavailable — make sure Ollama is running"}), 503
        return jsonify({"translated": result})
    except Exception as e:
        current_app.logger.exception("Translation error")
        return jsonify({"error": str(e)}), 500


# ── Code analysis ──────────────────────────────────────────────

@test_api_bp.route('/analyze-code', methods=['POST'])
@login_required
def analyze_code():
    code = (request.get_json() or {}).get('code', '').strip()
    if not code:
        return jsonify({"error": "No code provided"}), 400
    try:
        return jsonify({"result": analyze_code_for_bugs(code)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@test_api_bp.route('/generate-tests', methods=['POST'])
@login_required
def generate_tests():
    code = (request.get_json() or {}).get('code', '').strip()
    if not code:
        return jsonify({"error": "No code provided"}), 400
    try:
        return jsonify({"result": generate_unit_tests(code)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@test_api_bp.route('/refactor-code', methods=['POST'])
@login_required
def refactor_code_route():
    code = (request.get_json() or {}).get('code', '').strip()
    if not code:
        return jsonify({"error": "No code provided"}), 400
    try:
        return jsonify({"result": refactor_code(code)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Test suite management ──────────────────────────────────────

@test_api_bp.route('/save-test-case', methods=['POST'])
@login_required
def save_test_case():
    data     = request.get_json() or {}
    name     = data.get('name', '').strip()
    commands = data.get('commands', '').strip()
    if not name or not commands:
        return jsonify({"error": "Name and commands are required"}), 400
    try:
        db.session.add(TestCase(name=name, commands_json=commands, user_id=current_user.id))
        db.session.commit()
        return jsonify({"success": True, "message": f"Test suite '{name}' saved!"})
    except Exception as e:
        current_app.logger.exception("Save test case error")
        return jsonify({"error": str(e)}), 500


@test_api_bp.route('/approve-baseline', methods=['POST'])
@login_required
def approve_baseline():
    data         = request.get_json() or {}
    test_case_id = data.get('test_case_id')
    results      = data.get('results', [])
    if not test_case_id:
        return jsonify({"error": "No test case ID provided"}), 400
    tc = TestCase.query.get(test_case_id)
    if not tc or tc.user_id != current_user.id:
        return jsonify({"error": "Test case not found"}), 404
    baselines = json.loads(tc.baseline_images_json) if tc.baseline_images_json else {}
    for r in results:
        if r.get('status') == 'New Baseline' and r.get('screenshot'):
            baselines[str(r['step'])] = r['screenshot']
    tc.baseline_images_json = json.dumps(baselines)
    db.session.commit()
    return jsonify({"success": True, "message": "Baseline images approved and saved!"})
