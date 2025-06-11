from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

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
            'assessment_timer': self.assessment_timer, # Added these from previous fix
            'min_assesment_score': self.min_assesment_score, # Added these from previous fix
            'posted_at': self.posted_at.isoformat() # Convert datetime to string
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

    job = db.relationship('Job', backref=db.backref('applications', lazy=True)) # This is correct for Application

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
    conversation_info = db.Column(db.Text, nullable=True) # Storing JSON string

    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Conversation {self.id} started at {self.started_at}>'

    def to_dict(self):
        return {
            'id': self.id,
            'started_at': self.started_at.isoformat(),
            'conversation_info': json.loads(self.conversation_info) if self.conversation_info else None,
            'messages': [msg.to_dict() for msg in self.messages]
        }

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False)
    sender = db.Column(db.String(50), nullable=False) # 'user' or 'bot'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # REMOVED: messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')
    # This line is redundant and incorrect here. The backref on Conversation already handles it.
    # If you intended a self-referencing relationship for Message, it needs proper primaryjoin and remote_side.
    # But based on typical use, Conversation.messages is what you want.

    def __repr__(self: 'Message') -> str: # Added type hint for clarity
        return f'<Message {self.id} from {self.sender} in convo {self.conversation_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender': self.sender,
            'content': self.content,
            'timestamp': self.timestamp.isoformat()
        }

# REMOVED: These lines were misplaced and caused the error
# eligibility_score = db.Column(db.Float)
# assessment_score = db.Column(db.Float)
# status = db.Column(db.String(50), default="Pending")
# rejection_email_sent = db.Column(db.Boolean, default=False)
# job = db.relationship('Job', backref=db.backref('applications', lazy=True))


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