from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Job(db.Model):
    __tablename__ = 'job'

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
    applications = db.relationship('Application', backref='job', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Job {self.title}>'


class Application(db.Model):
    __tablename__ = 'application'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    applicant_name = db.Column(db.String(255), nullable=False)
    applicant_email = db.Column(db.String(255), nullable=False)
    applicant_age = db.Column(db.Integer)
    applicant_experience = db.Column(db.Float)  # years of experience
    education = db.Column(db.String(255))
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    resume_path = db.Column(db.String(255))
    resume_plain_text = db.Column(db.Text, nullable=True)

    eligibility_score = db.Column(db.Float)
    assessment_score = db.Column(db.Float)
    status = db.Column(db.String(50), default="Pending")
    rejection_email_sent = db.Column(db.Boolean, default=False, nullable=False)
   

class InterviewSchedule(db.Model):
    __tablename__ = 'interview_schedule'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    mode = db.Column(db.String(50))  # Virtual or Real
    interview_date = db.Column(db.DateTime, nullable=False)
    interviewer_name = db.Column(db.String(255), nullable=False)
    interviewer_email = db.Column(db.String(255), nullable=False)
    meeting_link = db.Column(db.String(500), nullable=True)
    address = db.Column(db.String(500), nullable=True)
    reminder_1day_sent = db.Column(db.Boolean, default=False)
    reminder_1hour_sent = db.Column(db.Boolean, default=False)

    candidate = db.relationship('Application', backref='interviews')


class Feedback(db.Model):
    __tablename__ = 'feedback'
    feedback_id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    comments = db.Column(db.Text)
    decision = db.Column(db.String(50))  # Accepted, Rejected, Pending, etc.
    communication_score = db.Column(db.Integer)
    technical_score = db.Column(db.Integer)
    problem_solving_score = db.Column(db.Integer)
    rejection_email_sent = db.Column(db.Boolean, default=False)

    candidate = db.relationship('Application', backref='feedbacks')


class AcceptedCandidate(db.Model):
    __tablename__ = 'accepted_candidates'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    applicant_name = db.Column(db.String(255))
    applicant_email = db.Column(db.String(255))

    candidate = db.relationship('Application')