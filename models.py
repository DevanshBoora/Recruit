from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
from werkzeug.security import generate_password_hash, check_password_hash
import bcrypt

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
    number_of_positions = db.Column(db.Integer,default=3)
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
            'posted_at': self.posted_at.isoformat(),
            'number_of_positions':self.number_of_positions
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
    resume_plain_text = db.Column(db.Text)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    eligibility_score = db.Column(db.Float)
    assessment_score = db.Column(db.Float)
    status = db.Column(db.String(50), default="Pending")
    rejection_email_sent = db.Column(db.Boolean, default=False)

    job = db.relationship('Job', backref=db.backref('application', lazy=True))

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
            'rejection_email_sent': self.rejection_email_sent,
            'applied_at': self.applied_at.isoformat() if self.applied_at else None
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

    def to_dict(self):
        return {
            'id': self.id,
            'candidate_id': self.candidate_id,
            'mode': self.mode,
            'interview_date': self.interview_date.isoformat() if self.interview_date else None,
            'interviewer_name': self.interviewer_name,
            'interviewer_email': self.interviewer_email,
            'meeting_link': self.meeting_link,
            'address': self.address
        }

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

    def to_dict(self):
        return {
            'feedback_id': self.feedback_id,
            'candidate_id': self.candidate_id,
            'comments': self.comments,
            'decision': self.decision,
            'communication_score': self.communication_score,
            'technical_score': self.technical_score,
            'problem_solving_score': self.problem_solving_score
        }

class AcceptedCandidate(db.Model):
    __tablename__ = 'accepted_candidates'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    applicant_name = db.Column(db.String(255), nullable=False)
    applicant_email = db.Column(db.String(255), nullable=False)
    company_name = db.Column(db.String(255), nullable=False)
    company_role = db.Column(db.String(255), nullable=False)
    candidate = db.relationship('Application', backref=db.backref('accepted_entry', lazy=True))

class JobOffer(db.Model):
    __tablename__ = 'job_offers'
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=False)
    status = db.Column(db.String(50), default='pending')
    offer_sent = db.Column(db.Boolean, default=False)
    offer_sent_time = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    company_name = db.Column(db.String(255), nullable=False)
    company_role = db.Column(db.String(255), nullable=False)
    application = db.relationship('Application', backref=db.backref('job_offer', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'application_id': self.application_id,
            'status': self.status,
            'offer_sent': self.offer_sent,
            'offer_sent_time': self.offer_sent_time.isoformat() if self.offer_sent_time else None
        }

class Conversation(db.Model):
    __tablename__ = 'conversations'
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    conversation_info = db.Column(db.Text, nullable=True)

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
    sender = db.Column(db.String(50), nullable=False)
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

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=False, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    company_name = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(50), nullable=False, default='u')
    position = db.Column(db.String(100), nullable=True)  # Optional field for user's position

    def __init__(self, name, email,password, company_name=None, role='u',position=None):
        self.name = name
        self.email = email.lower()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        self.company_name = company_name
        self.role = role
        self.position = position

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email':self.email,
            'company_name': self.company_name,
            'role': self.role
        }

    def __repr__(self):
        return f'<User {self.name} ({self.role}) at {self.company_name}>'

# models.py (continued)

class Slot(db.Model):
    __tablename__ = 'slots'
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(255), nullable=False) # This refers to the Job role/title
    interview_time = db.Column(db.DateTime, nullable=False)
    interviewer_name = db.Column(db.String(255), nullable=False)
    interviewer_email = db.Column(db.String(255), nullable=False)
    mode = db.Column(db.String(50), nullable=False) # 'online' or 'offline'
    meeting_link = db.Column(db.String(1000), nullable=True) # For online
    address = db.Column(db.String(1000), nullable=True) # For offline
    is_booked = db.Column(db.Boolean, default=False)
    booked_by_application_id = db.Column(db.Integer, db.ForeignKey('application.id'), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to Application (optional, but good for direct lookup)
    booked_application = db.relationship('Application', backref=db.backref('booked_slot', uselist=False))

    def to_dict(self):
        return {
            'id': self.id,
            'company_name': self.company_name,
            'role': self.role,
            'interview_time': self.interview_time.isoformat(),
            'interviewer_name': self.interviewer_name,
            'interviewer_email': self.interviewer_email,
            'mode': self.mode,
            'meeting_link': self.meeting_link,
            'address': self.address,
            'is_booked': self.is_booked,
            'booked_by_application_id': self.booked_by_application_id,
            'created_at': self.created_at.isoformat()
        }

    def __repr__(self):
        return f'<Slot {self.id} for {self.role} at {self.interview_time}>'



class Company(db.Model):
    __tablename__ = 'companies' # It's good practice to pluralize table names

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False) # Store hashed password

    # Optional: Add other company-specific fields if needed later, e.g.,
    # website = db.Column(db.String(255))
    # contact_email = db.Column(db.String(255))

    def __init__(self, company_name, password):
        self.company_name = company_name
        # Hash the password using bcrypt for security
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        """Checks the provided password against the stored hash."""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def to_dict(self):
        return {
            'id': self.id,
            'company_name': self.company_name
        }

    def __repr__(self):
        return f'<Company {self.company_name}>'