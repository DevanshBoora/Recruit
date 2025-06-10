from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Job(db.Model):
    __tablename__ = 'job'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    qualifications = db.Column(db.Text)
    responsibilities = db.Column(db.Text)
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    job_type = db.Column(db.String(50))
    location = db.Column(db.String(255))
    required_experience = db.Column(db.String(50))
    assessment_timer = db.Column(db.Integer)
    assessment_questions = db.Column(db.Text)
    min_assesment_score = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
class Application(db.Model):
    __tablename__ = 'application'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    applicant_name = db.Column(db.String(255), nullable=False)
    applicant_email = db.Column(db.String(255), nullable=False)
    applicant_age = db.Column(db.Integer)
    applicant_experience = db.Column(db.Float)
    education = db.Column(db.String(255))
    resume_path = db.Column(db.String(500))
    resume_plain_text=db.Column(db.String(1024))
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    eligibility_score = db.Column(db.Float)
    assessment_score = db.Column(db.Float)
    status = db.Column(db.String(50), default="Pending")
    rejection_email_sent = db.Column(db.Boolean, default=False)

    job = db.relationship('Job', backref=db.backref('applications', lazy=True))


class InterviewSchedule(db.Model):
    __tablename__ = 'interview_schedule'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    mode = db.Column(db.String(50), nullable=False)  # e.g., "Online", "Offline"
    interview_date = db.Column(db.DateTime, nullable=False)
    interviewer_name = db.Column(db.String(255), nullable=False)
    interviewer_email = db.Column(db.String(255), nullable=False)
    meeting_link = db.Column(db.String(1000))
    address = db.Column(db.String(1000))
    reminder_1day_sent = db.Column(db.Boolean, default=False)
    reminder_1hour_sent = db.Column(db.Boolean, default=False)

    candidate = db.relationship('Application', backref=db.backref('interview_schedule', lazy=True))


class Feedback(db.Model):
    __tablename__ = 'feedback'

    feedback_id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    comments = db.Column(db.Text)
    decision = db.Column(db.String(50))  # e.g., "Accepted", "Rejected"
    communication_score = db.Column(db.Float)
    technical_score = db.Column(db.Float)
    problem_solving_score = db.Column(db.Float)
    rejection_email_sent = db.Column(db.Boolean, default=False)

    candidate = db.relationship('Application', backref=db.backref('feedback', lazy=True))


class AcceptedCandidate(db.Model):
    __tablename__ = 'accepted_candidates'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    applicant_name = db.Column(db.String(255), nullable=False)
    applicant_email = db.Column(db.String(255), nullable=False)

    candidate = db.relationship('Application', backref=db.backref('accepted_entry', lazy=True))
