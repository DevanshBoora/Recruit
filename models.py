from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

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
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'location': self.location,
            'job_type': self.job_type,
            'required_experience': self.required_experience,
            'responsibilities': self.responsibilities,
            'qualifications': self.qualifications
        }    applications = db.relationship('Application', backref='job', lazy=True, cascade='all, delete-orphan')

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

    job = db.relationship('Job', backref=db.backref('applications', lazy=True, cascade='all, delete-orphan'))

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


class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Renamed 'metadata' to 'conversation_info' to avoid conflict
    conversation_info = db.Column(db.Text, nullable=True) # Storing JSON string

    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Conversation {self.id} started at {self.started_at}>'

    def to_dict(self):
        return {
            'id': self.id,
            'started_at': self.started_at.isoformat(),
            'conversation_info': json.loads(self.conversation_info) if self.conversation_info else None, # Use new name here
            'messages': [msg.to_dict() for msg in self.messages]
        }

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    sender = db.Column(db.String(50), nullable=False) # 'user' or 'bot'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Message {self.id} from {self.sender} in convo {self.conversation_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender': self.sender,
            'content': self.content,
            'timestamp': self.timestamp.isoformat()
        }

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