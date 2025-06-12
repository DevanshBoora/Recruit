from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for, flash
from flask_cors import CORS
import os
import json
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_
import google.generativeai as genai
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from sqlalchemy import text
from datetime import datetime, timedelta
import threading
import time
import schedule
from datetime import datetime
from routes import register_blueprints
from models import db, Job, Application, Interviewer, InterviewSlot, InterviewSchedule, Feedback, AcceptedCandidate
import logging
from functools import wraps
from db_tools import get_applicant_info, get_job_details, get_jobs_by_type, get_applications_by_status
from email_utils import (
    send_initial_rejection_email,
    send_reminder_email,
    send_schedule_email,
    send_rejection_email
)
from flask_moment import Moment
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)
moment=Moment(app)
register_blueprints(app)

UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/JobApplications'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_super_secret_key_change_this_in_production'
app.config['SESSION_TYPE'] = 'filesystem'

# Admin credentials (in production, use environment variables)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

db.init_app(app)
with app.app_context():
    db.create_all()

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")
genai.configure(api_key=GEMINI_API_KEY)

# Decorators for authentication
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def interviewer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'interviewer_id' not in session:
            return redirect(url_for('interviewer_login'))
        return f(*args, **kwargs)
    return decorated_function

# ------------------ Admin Routes ------------------ #

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            flash('Successfully logged in as admin!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials!', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('Successfully logged out!', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Get statistics
    total_jobs = Job.query.count()
    total_applications = Application.query.count()
    pending_applications = Application.query.filter_by(status='Pending').count()
    accepted_applications = Application.query.filter_by(status='Accepted').count()
    rejected_applications = Application.query.filter_by(status='Rejected').count()
    total_interviewers = Interviewer.query.count()
    scheduled_interviews = InterviewSchedule.query.count()
    
    # Recent applications
    recent_applications = Application.query.order_by(Application.applied_at.desc()).limit(10).all()
    
    # Upcoming interviews
    upcoming_interviews = InterviewSchedule.query.filter(
        InterviewSchedule.interview_date > datetime.utcnow()
    ).order_by(InterviewSchedule.interview_date).limit(10).all()
    
    stats = {
        'total_jobs': total_jobs,
        'total_applications': total_applications,
        'pending_applications': pending_applications,
        'accepted_applications': accepted_applications,
        'rejected_applications': rejected_applications,
        'total_interviewers': total_interviewers,
        'scheduled_interviews': scheduled_interviews
    }
    
    return render_template('admin_dashboard.html', 
                         stats=stats, 
                         recent_applications=recent_applications,
                         upcoming_interviews=upcoming_interviews)

@app.route('/admin/jobs')
@admin_required
def admin_jobs():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    jobs = Job.query.order_by(Job.posted_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin_jobs.html', jobs=jobs)

@app.route('/admin/jobs/create', methods=['GET', 'POST'])
@admin_required
def admin_create_job():
    if request.method == 'POST':
        try:
            job = Job(
                title=request.form['title'],
                description=request.form['description'],
                qualifications=request.form['qualifications'],
                responsibilities=request.form['responsibilities'],
                job_type=request.form['job_type'],
                location=request.form['location'],
                required_experience=request.form['required_experience'],
                assessment_timer=int(request.form['assessment_timer']),
                assessment_questions=request.form['assessment_questions'],
                min_assesment_score=int(request.form['min_assessment_score'])
            )
            db.session.add(job)
            db.session.commit()
            flash('Job created successfully!', 'success')
            return redirect(url_for('admin_jobs'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating job: {str(e)}', 'error')
    
    return render_template('admin_create_job.html')

@app.route('/admin/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_job(job_id):
    job = Job.query.get_or_404(job_id)
    
    if request.method == 'POST':
        try:
            job.title = request.form['title']
            job.description = request.form['description']
            job.qualifications = request.form['qualifications']
            job.responsibilities = request.form['responsibilities']
            job.job_type = request.form['job_type']
            job.location = request.form['location']
            job.required_experience = request.form['required_experience']
            job.assessment_timer = int(request.form['assessment_timer'])
            job.assessment_questions = request.form['assessment_questions']
            job.min_assesment_score = int(request.form['min_assessment_score'])
            
            db.session.commit()
            flash('Job updated successfully!', 'success')
            return redirect(url_for('admin_jobs'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating job: {str(e)}', 'error')
    
    return render_template('admin_edit_job.html', job=job)

@app.route('/admin/jobs/<int:job_id>/delete', methods=['POST'])
@admin_required
def admin_delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    try:
        # Check if there are applications for this job
        application_count = Application.query.filter_by(job_id=job_id).count()
        if application_count > 0:
            flash(f'Cannot delete job. It has {application_count} applications.', 'error')
        else:
            db.session.delete(job)
            db.session.commit()
            flash('Job deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting job: {str(e)}', 'error')
    
    return redirect(url_for('admin_jobs'))

@app.route('/admin/applications')
@admin_required
def admin_applications():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    per_page = 15
    
    query = Application.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    applications = query.order_by(Application.applied_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin_applications.html', 
                         applications=applications, 
                         status_filter=status_filter)

@app.route('/admin/applications/<int:app_id>')
@admin_required
def admin_application_detail(app_id):
    application = Application.query.get_or_404(app_id)
    job = Job.query.get(application.job_id)
    feedback = Feedback.query.filter_by(candidate_id=app_id).first()
    interview_schedule = InterviewSchedule.query.filter_by(candidate_id=app_id).first()
    
    return render_template('admin_application_detail.html', 
                         application=application, 
                         job=job, 
                         feedback=feedback,
                         interview_schedule=interview_schedule)

@app.route('/admin/interviewers')
@admin_required
def admin_interviewers():
    interviewers = Interviewer.query.order_by(Interviewer.name).all()
    return render_template('admin_interviewers.html', interviewers=interviewers)

@app.route('/admin/interviews')
@admin_required
def admin_interviews():
    page = request.args.get('page', 1, type=int)
    per_page = 15
    
    interviews = InterviewSchedule.query.order_by(
        InterviewSchedule.interview_date.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin_interviews.html', interviews=interviews)

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    # Application statistics by status
    status_stats = db.session.query(
        Application.status, db.func.count(Application.id)
    ).group_by(Application.status).all()
    
    # Application statistics by job type
    job_type_stats = db.session.query(
        Job.job_type, db.func.count(Application.id)
    ).join(Application, Job.id == Application.job_id).group_by(Job.job_type).all()
    
    # Monthly application trends
    monthly_stats = db.session.query(
        db.func.date_format(Application.applied_at, '%Y-%m').label('month'),
        db.func.count(Application.id).label('count')
    ).group_by('month').order_by('month').all()
    
    # Average scores
    avg_scores = db.session.query(
        db.func.avg(Application.eligibility_score).label('avg_eligibility'),
        db.func.avg(Application.assessment_score).label('avg_assessment'),
        db.func.avg(Feedback.communication_score).label('avg_communication'),
        db.func.avg(Feedback.technical_score).label('avg_technical'),
        db.func.avg(Feedback.problem_solving_score).label('avg_problem_solving')
    ).outerjoin(Feedback, Application.id == Feedback.candidate_id).first()
    
    return render_template('admin_analytics.html',
                         status_stats=status_stats,
                         job_type_stats=job_type_stats,
                         monthly_stats=monthly_stats,
                         avg_scores=avg_scores)

@app.route('/admin/settings')
@admin_required
def admin_settings():
    return render_template('admin_settings.html')

# ------------------ Existing Routes (Corrected) ------------------ #

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/assessment/<int:job_id>/<int:application_id>', methods=['GET'])
def assessment_page_route(job_id, application_id):
    job = db.session.get(Job, job_id)
    application = db.session.get(Application, application_id)
    if not job or not application or application.job_id != job.id:
        return render_template('main_page.html', message="Assessment Error."), 400
    return render_template('assessment_page.html', job=job, application=application)

@app.route('/applications', methods=['GET'])
def get_applications():
    applications = Application.query.all()
    result = []
    for a in applications:
        job = db.session.get(Job, a.job_id)
        result.append({
            'id': a.id,
            'job_id': a.job_id,
            'job_title': job.title if job else "N/A",
            'applicant_name': a.applicant_name,
            'applicant_email': a.applicant_email,
            'applicant_age': a.applicant_age,
            'applicant_experience': a.applicant_experience,
            'education': a.education,
            'applied_at': a.applied_at.isoformat(),
            'resume_path': a.resume_path,
            'eligibility_score': a.eligibility_score,
            'assessment_score': a.assessment_score,
            'status': a.status
        })
    return jsonify(result), 200

@app.route('/applications/<int:app_id>/status', methods=['PUT'])
def update_application_status(app_id):
    application = db.session.get(Application, app_id)
    if not application:
        return jsonify({"message": "Application not found"}), 404
    
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['Accepted', 'Rejected', 'Pending']:
        return jsonify({"message": "Invalid status"}), 400
    
    if new_status == 'Rejected' and not application.rejection_email_sent:
        try:
            send_initial_rejection_email(application.applicant_email, application.applicant_name)
            application.rejection_email_sent = True
        except Exception as e:
            return jsonify({"message": f"Error sending email: {str(e)}"}), 500
    
    application.status = new_status
    try:
        db.session.commit()
        return jsonify({"message": "Status updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500

@app.route('/resumes/<filename>', methods=['GET'])
def serve_resume(filename):
    safe_filename = secure_filename(filename)
    if not safe_filename:
        return "Invalid filename", 400
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    if not os.path.exists(file_path):
        return "File not found", 404
    
    return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename)

@app.route("/schedule", methods=["GET", "POST"])
def schedule_interview():
    if request.method == "POST":
        try:
            data = request.form
            slot_id = int(data["slot_id"])
            candidate_id = int(data["candidate_id"])

            slot = InterviewSlot.query.filter_by(id=slot_id, is_booked=False).first()
            if not slot:
                flash("Slot already booked or not found.", "error")
                return redirect(url_for("schedule_interview"))

            # Check if candidate already has a scheduled interview
            existing_candidate = InterviewSchedule.query.filter_by(candidate_id=candidate_id).first()
            if existing_candidate:
                flash("Candidate already has a scheduled interview.", "error")
                return redirect(url_for("schedule_interview"))

            # Check if interviewer has another interview at the same time
            conflict = InterviewSchedule.query.filter(
                and_(
                    InterviewSchedule.interview_date == slot.slot_datetime,
                    InterviewSchedule.interviewer_email == slot.interviewer.email
                )
            ).first()
            if conflict:
                flash("Interviewer already has an interview at this time.", "error")
                return redirect(url_for("schedule_interview"))

            # Create interview schedule
            interview = InterviewSchedule(
                candidate_id=candidate_id,
                mode=slot.mode,
                interview_date=slot.slot_datetime,
                interviewer_name=slot.interviewer.name,
                interviewer_email=slot.interviewer.email,
                meeting_link=slot.meeting_link,
                address=slot.address
            )

            slot.is_booked = True
            db.session.add(interview)
            db.session.commit()
            
            # Send schedule confirmation emails
            try:
                application = Application.query.get(candidate_id)
                if application:
                    send_schedule_email(application.applicant_email, interview.interview_date, 
                                      application.applicant_name, interview.mode, 
                                      interview.meeting_link, interview.address)
            except Exception as email_error:
                logging.error(f"Failed to send schedule email: {email_error}")
            
            flash("Interview scheduled successfully!", "success")
            return redirect(url_for("schedule_interview"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error scheduling interview: {str(e)}", "error")
            return redirect(url_for("schedule_interview"))

    # GET request
    candidates = db.session.query(Application.id, Application.applicant_name, Application.applicant_email)\
        .filter(Application.status == 'Accepted')\
        .filter(~Application.id.in_(
            db.session.query(InterviewSchedule.candidate_id)
            .filter(InterviewSchedule.candidate_id.isnot(None))
        ))\
        .order_by(Application.applied_at.desc()).all()

    available_slots = InterviewSlot.query.filter_by(is_booked=False)\
        .filter(InterviewSlot.slot_datetime > datetime.utcnow())\
        .order_by(InterviewSlot.slot_datetime).all()

    return render_template("schedule.html", candidates=candidates, slots=available_slots)

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        try:
            data = request.form
            candidate_id = int(data["candidate_id"])

            # Check for existing feedback
            existing = Feedback.query.filter_by(candidate_id=candidate_id).first()
            if existing:
                flash("Feedback already submitted for this candidate.", "error")
                return redirect(url_for("feedback"))

            # Create new feedback
            new_feedback = Feedback(
                candidate_id=candidate_id,
                comments=data["comments"],
                decision=data["decision"],
                communication_score=float(data["communication_score"]),
                technical_score=float(data["technical_score"]),
                problem_solving_score=float(data["problem_solving_score"])
            )
            
            db.session.add(new_feedback)
            
            # If accepted, add to accepted candidates
            if data['decision'] == "Accepted":
                application = Application.query.get(candidate_id)
                if application:
                    accepted_candidate = AcceptedCandidate(
                        candidate_id=application.id,
                        applicant_name=application.applicant_name,
                        applicant_email=application.applicant_email
                    )
                    db.session.add(accepted_candidate)
                    
            db.session.commit()
            flash("Feedback submitted successfully!", "success")
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error submitting feedback: {str(e)}", "error")
            
        return redirect(url_for("feedback"))

    # GET request - candidates with scheduled interviews but no feedback
    candidates = db.session.query(
        Application.id, 
        Application.applicant_name, 
        Application.applicant_email,
        InterviewSchedule.interview_date
    ).join(InterviewSchedule, Application.id == InterviewSchedule.candidate_id)\
    .filter(~Application.id.in_(
        db.session.query(Feedback.candidate_id)
        .filter(Feedback.candidate_id.isnot(None))
    ))\
    .order_by(InterviewSchedule.interview_date.desc()).all()
    
    return render_template("feedback.html", candidates=candidates)

@app.route("/dashboard")
def dashboard():
    feedback_data = db.session.query(
        Application.applicant_name,
        Application.applicant_email,
        Feedback.decision,
        Feedback.comments,
        Feedback.communication_score,
        Feedback.technical_score,
        Feedback.problem_solving_score,
        Feedback.rejection_email_sent,
        InterviewSchedule.interview_date
    ).join(Feedback, Application.id == Feedback.candidate_id)\
    .outerjoin(InterviewSchedule, Application.id == InterviewSchedule.candidate_id)\
    .order_by(InterviewSchedule.interview_date.desc()).all()
    
    return render_template("dashboard.html", feedback=feedback_data)

# ------------------ Interviewer Routes (Corrected) ------------------ #

@app.route('/interviewer/login', methods=['GET', 'POST'])
def interviewer_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        interviewer = Interviewer.query.filter_by(email=email).first()
        if interviewer and interviewer.check_password(password):
            session['interviewer_id'] = interviewer.id
            session['interviewer_name'] = interviewer.name
            session['interviewer_email'] = interviewer.email
            flash("Successfully logged in!", "success")
            return redirect(url_for('interviewer_dashboard'))
        else:
            flash("Invalid credentials", "error")

    return render_template('interviewer_login.html')

@app.route('/interviewer/register', methods=['GET', 'POST'])
def register_interviewer():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        # Validate input
        if not all([name, email, password]):
            flash("All fields are required.", "error")
            return render_template('interviewer_register.html')

        existing = Interviewer.query.filter_by(email=email).first()
        if existing:
            flash("Interviewer with this email already exists.", "error")
            return render_template('interviewer_register.html')

        try:
            new_interviewer = Interviewer(name=name, email=email)
            new_interviewer.set_password(password)
            db.session.add(new_interviewer)
            db.session.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for('interviewer_login'))
        except Exception as e:
            db.session.rollback()
            flash(f"Registration failed: {str(e)}", "error")

    return render_template('interviewer_register.html')

@app.route("/interviewer/slots", methods=["GET", "POST"])
@interviewer_required
def add_slot():
    if request.method == "POST":
        try:
            slot_datetime = request.form["slot_datetime"]
            mode = request.form["mode"]
            meeting_link = request.form.get("meeting_link", "").strip()
            address = request.form.get("address", "").strip()

            # Validate inputs
            if mode not in ['Online', 'Offline']:
                flash("Invalid mode selected", "error")
                return redirect(url_for('add_slot'))

            if mode == 'Online' and not meeting_link:
                flash("Meeting link is required for online interviews", "error")
                return redirect(url_for('add_slot'))
            
            if mode == 'Offline' and not address:
                flash("Address is required for offline interviews", "error")
                return redirect(url_for('add_slot'))

            # Convert string to datetime
            slot_datetime = datetime.strptime(slot_datetime, '%Y-%m-%dT%H:%M')
            
            # Check if slot is in the future
            if slot_datetime <= datetime.utcnow():
                flash("Slot must be in the future", "error")
                return redirect(url_for('add_slot'))

            # Check for existing slot
            existing_slot = InterviewSlot.query.filter_by(
                interviewer_id=session['interviewer_id'],
                slot_datetime=slot_datetime
            ).first()
            
            if existing_slot:
                flash("You already have a slot at this time", "error")
                return redirect(url_for('add_slot'))

            new_slot = InterviewSlot(
                interviewer_id=session['interviewer_id'],
                slot_datetime=slot_datetime,
                mode=mode,
                meeting_link=meeting_link if mode == 'Online' else None,
                address=address if mode == 'Offline' else None
            )

            db.session.add(new_slot)
            db.session.commit()
            flash("Slot added successfully!", "success")
            
        except ValueError:
            flash("Invalid date format", "error")
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding slot: {str(e)}", "error")
            
        return redirect(url_for('add_slot'))

    # GET request - show existing slots
    interviewer_slots = InterviewSlot.query.filter_by(
        interviewer_id=session['interviewer_id']
    ).order_by(InterviewSlot.slot_datetime.desc()).all()

    return render_template("add_slot.html", slots=interviewer_slots)

@app.route('/interviewer/slots/<int:slot_id>/delete', methods=['POST'])
@interviewer_required
def delete_slot(slot_id):
    slot = InterviewSlot.query.filter_by(
        id=slot_id, 
        interviewer_id=session['interviewer_id']
    ).first()
    
    if not slot:
        flash("Slot not found", "error")
        return redirect(url_for('add_slot'))
    
    if slot.is_booked:
        flash("Cannot delete booked slot", "error")
        return redirect(url_for('add_slot'))
    
    try:
        db.session.delete(slot)
        db.session.commit()
        flash("Slot deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting slot: {str(e)}", "error")
    
    return redirect(url_for('add_slot'))

@app.route('/interviewer/logout')
def logout_interviewer():
    session.pop('interviewer_id', None)
    session.pop('interviewer_email', None)
    session.pop('interviewer_name', None)
    flash("Successfully logged out!", "info")
    return redirect(url_for('interviewer_login'))

@app.route('/interviewer/dashboard')
@interviewer_required
def interviewer_dashboard():
    interviewer = Interviewer.query.get(session['interviewer_id'])

    # Get upcoming slots
    upcoming_slots = InterviewSlot.query.filter_by(
        interviewer_id=interviewer.id
    ).filter(InterviewSlot.slot_datetime > datetime.utcnow())\
    .order_by(InterviewSlot.slot_datetime).all()

    # Get past slots
    past_slots = InterviewSlot.query.filter_by(
        interviewer_id=interviewer.id
    ).filter(InterviewSlot.slot_datetime <= datetime.utcnow())\
    .order_by(InterviewSlot.slot_datetime.desc()).limit(10).all()

    # Get scheduled interviews
    scheduled_interviews = InterviewSchedule.query.filter_by(
        interviewer_email=interviewer.email
    ).order_by(InterviewSchedule.interview_date).all()

    return render_template(
        'interviewer_dashboard.html',
        interviewer=interviewer,
        upcoming_slots=upcoming_slots,
        past_slots=past_slots,
        interviews=scheduled_interviews
    )

# ------------------ Background Tasks (Corrected) ------------------ #

def send_feedback_rejections():
    """Send rejection emails for candidates rejected after interview"""
    with app.app_context():
        try:
            rejected_feedback = db.session.query(
                Feedback.feedback_id,
                Feedback.comments,
                Application.applicant_email,
                Application.applicant_name
            ).join(Application, Feedback.candidate_id == Application.id)\
            .filter(Feedback.decision == 'Rejected')\
            .filter(or_(Feedback.rejection_email_sent.is_(None), Feedback.rejection_email_sent == False)).all()
            
            for feedback in rejected_feedback:
                try:
                    feedback_obj = Feedback.query.get(feedback.feedback_id)
                    if feedback_obj and not feedback_obj.rejection_email_sent:
                        send_rejection_email(feedback.applicant_email, feedback.applicant_name, feedback.comments)
                        feedback_obj.rejection_email_sent = True
                        db.session.commit()
                        logging.info(f"Sent rejection email to {feedback.applicant_name}")
                        
                except Exception as e:
                    logging.error(f"Error sending feedback rejection to {feedback.applicant_name}: {e}")
                    db.session.rollback()
                    
        except Exception as e:
            logging.error(f"Error in send_feedback_rejections: {e}")

def send_reminders():
    """Send interview reminders"""
    with app.app_context():
        try:
            now = datetime.utcnow()
            interviews = db.session.query(
                InterviewSchedule.id,
                InterviewSchedule.interview_date,
                InterviewSchedule.candidate_id,
                InterviewSchedule.mode,
                InterviewSchedule.interviewer_name,
                InterviewSchedule.interviewer_email,
                InterviewSchedule.meeting_link,
                InterviewSchedule.address,
                InterviewSchedule.reminder_1day_sent,
                InterviewSchedule.reminder_1hour_sent,
                Application.applicant_email,
                Application.applicant_name
            ).join(Application, InterviewSchedule.candidate_id == Application.id)\
            .filter(InterviewSchedule.interview_date > now).all()
            
            for interview in interviews:
                interview_time = interview.interview_date
                time_diff = interview_time - now
                
                try:
                    interview_obj = InterviewSchedule.query.get(interview.id)
                    
                    # 1 day reminder
                    if timedelta(hours=23) < time_diff <= timedelta(days=1):
                        if not interview_obj.reminder_1day_sent:
                            # Send to candidate
                            send_reminder_email(
                                interview.applicant_email, 
                                interview_time, 
                                interview.applicant_name,
                                interview.mode, 
                                interview.meeting_link, 
                                interview.address
                            )
                            
                            # Send to interviewer
                            send_reminder_email(
                                interview.interviewer_email, 
                                interview_time, 
                                interview.interviewer_name,
                                interview.mode, 
                                interview.meeting_link, 
                                interview.address, 
                                is_interviewer=True
                            )

                            interview_obj.reminder_1day_sent = True
                            db.session.commit()
                            logging.info(f"Sent 1-day reminder for {interview.applicant_name}")

                    # 1 hour reminder
                    elif timedelta(minutes=30) < time_diff <= timedelta(hours=1):
                        if not interview_obj.reminder_1hour_sent:
                            # Send to candidate
                            send_reminder_email(
                                interview.applicant_email, 
                                interview_time, 
                                interview.applicant_name,
                                interview.mode, 
                                interview.meeting_link, 
                                interview.address
                            )
                            
                            # Send to interviewer
                            send_reminder_email(
                                interview.interviewer_email, 
                                interview_time, 
                                interview.interviewer_name,
                                interview.mode, 
                                interview.meeting_link, 
                                interview.address, 
                                is_interviewer=True
                            )

                            interview_obj.reminder_1hour_sent = True
                            db.session.commit()
                            logging.info(f"Sent 1-hour reminder for {interview.applicant_name}")

                except Exception as e:
                    logging.error(f"Reminder error for {interview.applicant_name}: {e}")
                    db.session.rollback()
                    
        except Exception as e:
            logging.error(f"Error in send_reminders: {e}")

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

# Schedule background tasks
schedule.every(5).minutes.do(send_feedback_rejections)
schedule.every(5).minutes.do(send_reminders)

def run_scheduler():
    """Background scheduler for email tasks"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except Exception as e:
            logging.error(f"Scheduler error: {e}")
            time.sleep(60)

# Start background scheduler
threading.Thread(target=run_scheduler, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=True, port=5000)