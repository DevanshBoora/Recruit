from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
from werkzeug.security import generate_password_hash, check_password_hash
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

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'location': self.location,
            'job_type': self.job_type,
            'required_experience': self.required_experience,
            'responsibilities': self.responsibilities,
            'qualifications': self.qualifications,
            'assessment_timer': self.assessment_timer,
            'min_assesment_score': self.min_assesment_score,
            'posted_at': self.posted_at.isoformat()
        }
    def __repr__(self):
        return f'<Job {self.title}>'

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
    
    # These belong here (moved from Message class)
    eligibility_score = db.Column(db.Float)
    assessment_score = db.Column(db.Float)
    status = db.Column(db.String(50), default="Pending")
    rejection_email_sent = db.Column(db.Boolean, default=False)

    job = db.relationship('Job', backref=db.backref('applications', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'applicant_name': self.applicant_name,
            'applicant_age': self.applicant_age,
            'applicant_email': self.applicant_email,
            'applicant_experience': self.applicant_experience,
            'education': self.education,
            'resume_path': self.resume_path,
            'resume_plain_text': self.resume_plain_text,
            'eligibility_score': self.eligibility_score,
            'assessment_score': self.assessment_score,
            'status': self.status,
        }
    def __repr__(self):
        return f'<Application {self.applicant_name} for Job {self.job_id}>'

class InterviewSchedule(db.Model):
    __tablename__ = 'interview_schedule'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    mode = db.Column(db.String(50), nullable=False)
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
    decision = db.Column(db.String(50))
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


class Interviewer(db.Model):
    __tablename__ = 'interviewer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class InterviewSlot(db.Model):
    __tablename__ = 'interviewer_slot'
    id = db.Column(db.Integer, primary_key=True)
    interviewer_id = db.Column(db.Integer, db.ForeignKey('interviewer.id'), nullable=False)
    slot_datetime = db.Column(db.DateTime, nullable=False)
    is_booked = db.Column(db.Boolean, default=False)
    mode = db.Column(db.String(20), nullable=False)  # 'Online' or 'Offline'
    meeting_link = db.Column(db.String(1000))  # For online interviews
    address = db.Column(db.String(1000))  # For offline interviews

    interviewer = db.relationship('Interviewer', backref='slots')

    def __repr__(self):
        return f'<InterviewSlot {self.slot_datetime} - {self.mode}>'

class Admin(db.Model):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Admin {self.username}>'