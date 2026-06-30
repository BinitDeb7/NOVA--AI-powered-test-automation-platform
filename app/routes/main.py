"""
UI routes — page rendering only. No business logic here.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from app import db
from app.models import TestRun, TestCase

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    from app.models import TestRun
    total_runs = TestRun.query.count()
    return render_template('index.html', total_runs=total_runs)


@main_bp.route('/about')
def about():
    return render_template('about.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    test_case_id   = request.args.get('test_case_id')
    is_visual_test = request.args.get('visual_test', 'false') == 'true'
    commands       = ''

    if test_case_id:
        tc = TestCase.query.get(test_case_id)
        if tc and tc.user_id == current_user.id:
            commands = tc.commands_json
        else:
            test_case_id = None

    return render_template('dashboard.html',
                           name=current_user.name,
                           test_case_id=test_case_id,
                           is_visual_test=is_visual_test,
                           commands=commands)


@main_bp.route('/code-analysis')
@login_required
def code_analysis():
    return render_template('code_analysis.html')


@main_bp.route('/test-suites')
@login_required
def test_suites():
    cases = TestCase.query.filter_by(user_id=current_user.id)\
                          .order_by(TestCase.timestamp.desc()).all()
    return render_template('test_suites.html', cases=cases)


@main_bp.route('/history')
@login_required
def history():
    runs = TestRun.query.filter_by(user_id=current_user.id)\
                        .order_by(TestRun.timestamp.desc()).all()
    return render_template('history.html', history=runs)


@main_bp.route('/profile')
@login_required
def profile():
    runs   = TestRun.query.filter_by(user_id=current_user.id).all()
    suites = TestCase.query.filter_by(user_id=current_user.id).count()
    total  = len(runs)
    passed = sum(1 for r in runs if r.status == 'Success')
    failed = total - passed
    rate   = int((passed / total * 100)) if total else 0
    stats  = dict(total=total, passed=passed, failed=failed, suites=suites, rate=rate)
    return render_template('profile.html', stats=stats)


@main_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    new_pw  = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()
    if not new_pw or len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('main.profile'))
    if new_pw != confirm:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('main.profile'))
    current_user.password = generate_password_hash(new_pw, method='pbkdf2:sha256')
    db.session.commit()
    flash('Password updated successfully!', 'success')
    return redirect(url_for('main.profile'))


@main_bp.route('/clear-history', methods=['POST'])
@login_required
def clear_all_history():
    TestRun.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash('All test history cleared.', 'success')
    return redirect(url_for('main.profile'))


@main_bp.route('/delete-test-case/<int:test_case_id>', methods=['POST'])
@login_required
def delete_test_case(test_case_id):
    tc = TestCase.query.get_or_404(test_case_id)
    if tc.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('main.test_suites'))
    db.session.delete(tc)
    db.session.commit()
    flash('Test suite deleted successfully.', 'success')
    return redirect(url_for('main.test_suites'))


@main_bp.route('/delete-history/<int:test_run_id>', methods=['POST'])
@login_required
def delete_history(test_run_id):
    tr = TestRun.query.get_or_404(test_run_id)
    if tr.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('main.history'))
    db.session.delete(tr)
    db.session.commit()
    flash('Test history item deleted.', 'success')
    return redirect(url_for('main.history'))


@main_bp.route('/api/stats')
@login_required
def api_stats():
    from sqlalchemy import func
    runs = TestRun.query.filter_by(user_id=current_user.id)
    total = runs.count()
    passed = runs.filter_by(status='Success').count()
    failed = total - passed
    suites = TestCase.query.filter_by(user_id=current_user.id).count()
    rate = int((passed / total * 100)) if total else 0
    return jsonify(total=total, passed=passed, failed=failed, suites=suites, rate=rate)
