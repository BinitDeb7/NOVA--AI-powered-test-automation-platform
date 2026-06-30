from app import db
from datetime import datetime


class TestCase(db.Model):
    __tablename__ = 'test_case'

    id                   = db.Column(db.Integer, primary_key=True)
    name                 = db.Column(db.String(150), nullable=False)
    commands_json        = db.Column(db.Text, nullable=False)
    timestamp            = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    user_id              = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    baseline_images_json = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<TestCase {self.id} {self.name}>'
