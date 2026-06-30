from app import db
from datetime import datetime


class TestRun(db.Model):
    __tablename__ = 'test_run'

    id           = db.Column(db.Integer, primary_key=True)
    url_tested   = db.Column(db.String(500), nullable=False)
    status       = db.Column(db.String(50), nullable=False)
    timestamp    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    results_json = db.Column(db.Text, nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

    def __repr__(self):
        return f'<TestRun {self.id} {self.status}>'
