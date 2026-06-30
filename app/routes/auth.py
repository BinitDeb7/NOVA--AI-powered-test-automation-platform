"""
Auth routes — login, register, logout, password reset.
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, limiter
from app.models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login')
def login():
    return render_template('auth/login.html')


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute; 3 per 10 seconds")
def login_post():
    email    = request.form.get('email')
    password = request.form.get('password')
    user     = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login'))
    login_user(user)
    return redirect(url_for('main.dashboard'))


@auth_bp.route('/register')
def register():
    return render_template('auth/register.html')


@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register_post():
    email            = request.form.get('email')
    name             = request.form.get('name')
    password         = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    if password != confirm_password:
        flash('Passwords do not match.')
        return redirect(url_for('auth.register'))
    if User.query.filter_by(email=email).first():
        flash('Email address already exists.')
        return redirect(url_for('auth.register'))
    db.session.add(User(
        email=email, name=name,
        password=generate_password_hash(password, method='pbkdf2:sha256')
    ))
    db.session.commit()
    flash('Registration successful! Please login.')
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def forgot_password():
    if request.method == 'POST':
        user = User.query.filter_by(
            email=request.form.get('email'),
            name=request.form.get('name')
        ).first()
        if user:
            return redirect(url_for('auth.reset_password', user_id=user.id))
        flash('No account found with that name and email address.')
        return redirect(url_for('auth.forgot_password'))
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<int:user_id>', methods=['GET', 'POST'])
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        password = request.form.get('password')
        if password != request.form.get('confirm_password'):
            flash('Passwords do not match.')
            return redirect(url_for('auth.reset_password', user_id=user.id))
        user.password = generate_password_hash(password, method='pbkdf2:sha256')
        db.session.commit()
        flash('Password reset successfully! Please login.')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', user_id=user.id)
