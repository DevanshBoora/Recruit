# my_app_with_models/models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize SQLAlchemy here, but DO NOT pass the app instance yet.
# The 'db' object will be bound to the app in app.py using db.init_app(app).
db = SQLAlchemy()



class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    qualifications = db.Column(db.Text, nullable=False)
    responsibilities = db.Column(db.Text, nullable=False)
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    job_type = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    required_experience = db.Column(db.String(50), nullable=False)
    assessment_timer = db.Column(db.Integer, nullable=True, default=0)
    assessment_questions = db.Column(db.Text, nullable=True)
    min_assesment_score = db.Column(db.Integer, nullable=True, default=0)

    def __repr__(self):
        return f'<Job {self.title}>'

class Application(db.Model):
    __tablename__ = 'applications'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False) # ADD ondelete='CASCADE'
    applicant_name = db.Column(db.String(255), nullable=False)
    applicant_age = db.Column(db.Integer, nullable=True)
    applicant_email = db.Column(db.String(255), nullable=False)
    applicant_experience = db.Column(db.Text, nullable=True)
    education = db.Column(db.Text, nullable=True)
    resume_path = db.Column(db.String(255), nullable=False)
    resume_plain_text = db.Column(db.Text, nullable=True)
    eligibility_score = db.Column(db.Float, default=0.0)
    assessment_score = db.Column(db.Float, nullable=True, default=0.0)
    status = db.Column(db.String(50), default='Pending')
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)

    job = db.relationship('Job', backref=db.backref('applications', lazy=True, cascade='all, delete-orphan'))
    def __repr__(self):
        return f'<Application {self.applicant_name} for Job {self.job_id}>'
