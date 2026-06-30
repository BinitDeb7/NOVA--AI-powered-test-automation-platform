from flask_login import UserMixin
from app import db
from datetime import datetime


class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id       = db.Column(db.Integer, primary_key=True)
    email    = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    name     = db.Column(db.String(100), nullable=False)

    test_runs  = db.relationship('TestRun',  backref='user', lazy=True, cascade='all, delete-orphan')
    test_cases = db.relationship('TestCase', backref='user', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.email}>'
