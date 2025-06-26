from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, flash, url_for,g
from flask_cors import CORS
from flask_bcrypt import Bcrypt
import os
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import google.generativeai as genai
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from sqlalchemy import text
from datetime import datetime, timedelta
import threading
import time,schedule , smtplib,imaplib,unicodedata,re ,email
import pandas as pd
from email.mime.text import MIMEText
from routes import register_blueprints
from models import db, Job, Application, InterviewSchedule, Feedback, AcceptedCandidate, User, JobOffer, Slot
import logging
from email_utils import (
    send_initial_rejection_email,
    send_reminder_email,
    send_schedule_email,
    send_rejection_email
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)
register_blueprints(app)
bcrypt = Bcrypt(app)

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/JobApplications32'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_super_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'

# Email configuration (add to your config file)
EMAIL_CONFIG = {
    "email_address": "your_email@gmail.com",
    "email_password": "your_app_password"
}
SMTP_SERVER = "smtp.gmail.com"
IMAP_SERVER = "imap.gmail.com"
TIMEOUT_HOURS = 24  # Hours to wait for offer response

db.init_app(app)
with app.app_context():
    db.create_all()

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")
genai.configure(api_key=GEMINI_API_KEY)
# ==================== EXISTING ROUTES (PRESERVED) ====================
@app.route('/signup' , methods=['POST',"GET"])
def signup():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        company_name = "User"
        role = "u"
        position = "user"
        if not name or not password:
            return jsonify({"message": "Name and password are required"}), 400

        existing_user = User.query.filter_by(name=name).first()
        if existing_user:
            return jsonify({"message": "Username already exists"}), 409

        new_user = User(name=name, email=email ,password=password, company_name=company_name, role=role,position=position)
        db.session.add(new_user)
        session['candidate_name'] = name
        session['candidate_email'] = email
        session['who'] ='user'
        return jsonify({"message": "Username signup"}), 200
    return render_template('signUp.html')


@app.route('/auth/google', methods=['POST'])
def google_auth():
    token = request.json.get('token')

    if not token:
        return jsonify({"message": "No Google token provided"}), 400

    try:
        # Verify the Google ID Token
        # It verifies the token's signature, issuer, and audience (your client ID)
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID"))

        # Extract user information from the token
        google_id = idinfo['sub'] # Unique Google User ID
        email = idinfo.get('email')
        name = idinfo.get('name', email.split('@')[0] if email else 'User') # Default name if not provided
        password = "thub123"
        role = "u"
        position = "user"
        if not email:
            return jsonify({"message": "Google account did not provide an email address."}), 400

        # Check if user already exists in your database by Google ID
        user = User.query.filter_by(company_name=google_id).first()

        if user:
            # User exists via Google, log them in
            message = "Login"
        else:
            # Check if an account with this email already exists (e.g., from manual signup)
            existing_user_by_email = User.query.filter_by(email=email).first()
            if existing_user_by_email:
                # If email exists but google_id is null, link the Google ID to the existing account
                if not existing_user_by_email.google_id:
                    existing_user_by_email.google_id = google_id
                    db.session.commit()
                    user = existing_user_by_email
                    message = "Google account linked and logged in successfully!"
                else:
                    return jsonify({"message": "An account with this email already exists. Please log in normally or try linking your account."}), 409
            else:
                user = User(company_name=google_id, email=email, name=name,password=password,role=role,position=position)
                
                db.session.add(user)
                db.session.commit()
                message = "Signed up with Google successfully and logged in!"

        session['candidate_name'] = name
        session['candidate_email'] = email
        session['who'] ='user'
        return jsonify({"message": message, "user": user.to_dict()}), 200

    except ValueError as e:
        # Invalid token or other verification issues
        app.logger.error(f"Google token verification failed: {e}")
        return jsonify({"message": f"Authentication failed: Invalid token or client mismatch: {e}"}), 401
    except Exception as e:
        app.logger.error(f"An unexpected error occurred during Google auth: {e}", exc_info=True)
        return jsonify({"message": "An internal server error occurred during Google authentication."}), 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        password = data.get('password')

        if not name or not password:
            return jsonify({"message": "Name and password are required"}), 400

        user = User.query.filter_by(name=name).first()
        if not user or not user.check_password(password):
            return jsonify({"message": "Invalid username or password"}), 401

        
        if ( user.position == "interviewer"):
            session['role'] ='i'
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['name'] = user.company_name
            session['response'] = user.role
            session['email'] = user.email
            return jsonify({
            "message": "Login successful!",
            "name": user.name,
            "company_name": user.company_name,
            "email": user.email,
            "role": user.role,
            "position":user.position
        }), 200
        elif user.position == "manager": 
            session['role'] ='a'
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['name'] = user.company_name
            session['response'] = user.role
            session['email'] = user.email
            return jsonify({
            "message": "Login successful!",
            "name": user.name,
            "company_name": user.company_name,
            "email": user.email,
            "role": user.role,
            "position":user.position
        }), 200


        session['candidate_name'] = user.name
        session['candidate_email'] = user.email
        session['who'] ='user'
        return jsonify({
            "message": "Login successful!",
            "name": user.name,
            "company_name": user.company_name,
            "email": user.email,
            "role": user.role,
            "position":user.position
        }), 200
    return render_template('login.html')

@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return jsonify({"message": "Successfully logged out"}), 200



# ==================== EXISTING ROUTES (KEEP ALL YOUR ORIGINAL ROUTES) ====================


@app.route('/applications/<int:app_id>/status', methods=['PUT'])
def update_application_status(app_id):
    application = db.session.get(Application, app_id)
    if not application:
        return jsonify({"message": "Application not found"}), 404
    data = request.get_json()
    new_status = data.get('status')
    if new_status == 'Rejected' and not application.rejection_email_sent:
        try:
            send_initial_rejection_email(application.applicant_email, application.applicant_name)
            application.rejection_email_sent = True
        except Exception as e:
            return jsonify({"message": str(e)}), 500
    application.status = new_status
    try:
        db.session.commit()
        return jsonify({"message": "Status updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": str(e)}), 500

@app.route('/resumes/<filename>', methods=['GET'])
def serve_resume(filename):
    safe_filename = secure_filename(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename)

@app.route("/schedule", methods=["GET", "POST"])
def schedule_interview():
    if request.method == "POST":
        data = request.form
        try:
            # Step 1: Check if candidate already has an interview scheduled
            existing = db.session.execute(text("""
                SELECT 1 FROM interview_schedule WHERE candidate_id = :candidate_id
            """), {"candidate_id": data["candidate_id"]}).first()
            
            if existing:
                return "Interview already scheduled for this candidate.", 400

            # Step 2: Insert new interview schedule
            db.session.execute(text("""
                INSERT INTO interview_schedule 
                (candidate_id, mode, interview_date, interviewer_name, interviewer_email, meeting_link, address)
                VALUES (:candidate_id, :mode, :interview_date, :interviewer_name, :interviewer_email, :meeting_link, :address)
            """), {
                "candidate_id": data["candidate_id"],
                "mode": data["mode"],
                "interview_date": data["interview_datetime"],
                "interviewer_name": data["interviewer_name"],
                "interviewer_email": data["interviewer_email"],
                "meeting_link": data.get("meeting_link"),
                "address": data.get("address")
            })

            # Fetch candidate email
            result = db.session.execute(text("""
                SELECT applicant_email FROM application WHERE id = :candidate_id
            """), {"candidate_id": data["candidate_id"]}).mappings().first()

            if result:
                send_schedule_email(
                    result["applicant_email"],#fksdhgsufsdiugsdiugisdgdgisdgiusd
                    data["interview_datetime"],
                    data["mode"],
                    data["interviewer_name"],
                    data.get("meeting_link"),
                    data.get("address")
                )

            send_schedule_email(
                data["interviewer_email"],
                data["interview_datetime"],
                data["mode"],
                data["interviewer_name"],
                data.get("meeting_link"),
                data.get("address"),
                is_interviewer=True
            )

            db.session.commit()
            flash("Interview scheduled successfully and email sent.", "success")
        except Exception as e:
            db.session.rollback()
            return f"Error: {e}", 500

        return redirect("/view_applications.html")

    # Fetch candidates who have not been scheduled yet
    candidates = db.session.execute(text("""
        SELECT a.id, a.applicant_name
        FROM application a
        WHERE a.status = 'Accepted'
        AND a.id NOT IN (SELECT candidate_id FROM interview_schedule)
    """)).mappings().all()

    return render_template("schedule.html", candidates=candidates)

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        data = request.form

        # Prevent duplicate feedback using ORM
        existing = Feedback.query.filter_by(candidate_id=data["candidate_id"]).first()
        name = session.get('name')
        role = session.get('response')
        if existing:
            return "Feedback already submitted for this candidate.", 400

        try:
            # Create new feedback using ORM
            new_feedback = Feedback(
                candidate_id=int(data["candidate_id"]),
                comments=data["comments"],
                decision=data["decision"],
                communication_score=float(data["communication_score"]),
                technical_score=float(data["technical_score"]),
                problem_solving_score=float(data["problem_solving_score"])
            )
            db.session.add(new_feedback)
            application = Application.query.get(int(data['candidate_id']))
            if data['decision'] == "Accepted":
                if application:
                    accepted_candidate = AcceptedCandidate(
                        candidate_id=application.id,
                        applicant_name=application.applicant_name,
                        applicant_email=application.applicant_email,
                        company_name = name,
                        company_role =role
                    )
                    db.session.add(accepted_candidate)
                    application.status='Interview Completed'
            else:
                application.status = 'Rejected'
            slot = Slot.query.filter_by(
                booked_by_application_id=application.id,
                company_name=name,
                is_booked = 1,
                role=role
                ).first()

            slot.is_booked = 2
            db.session.commit()
            flash("Feedback submitted successfully.", "success")
            return redirect("/dashboard")

        except Exception as e:
            db.session.rollback()
            return f"Error: {e}", 500
@app.route('/fetch/feedback' ,methods=['POST','GET'])
def fetch():
    if request.method == "POST":
        try:
            data = request.get_json()
            id = data.get('app_id')
            if not id:
                return jsonify({'status':'Error','message':'Id is missign in the post request'}) ,500
            candidates = Application.query.get(id)
            return jsonify({'candidate_name':candidates.applicant_name, 'candidate_id':id}) ,200

        except Exception as e:
            print(f"Error fetching candidates: {e}")
            return render_template("error.html", message=f"An error occurred while fetching candidates: {e}")
    return render_template('feedback.html')

@app.route("/dashboard")
def dashboard():
    # Use ORM join instead of raw SQL
    feedback_data = db.session.query(
        Application.applicant_name,
        Feedback.decision,
        Feedback.comments,
        Feedback.communication_score,
        Feedback.technical_score,
        Feedback.problem_solving_score,
        Feedback.rejection_email_sent
    ).join(Application, Feedback.candidate_id == Application.id).all()
    
    return render_template("dashboard.html", feedback=feedback_data)



# [Include all other existing routes from the second file...]
# (Assessment, applications, schedule, feedback, dashboard routes remain the same)

@app.route('/assessment/<int:job_id>/<int:application_id>', methods=['GET'])
def assessment_page_route(job_id, application_id):
    job = db.session.get(Job, job_id)
    application = db.session.get(Application, application_id)
    if not job or not application or application.job_id != job.id:
        return render_template('main_page.html', message="Assessment Error."), 400
    return render_template('assessment_page.html')

@app.route('/applications', methods=['POST'])
def get_filtered_applications():
    if 'user_id' not in session:
        return jsonify({"message": "Unauthorized access. Please log in."}), 403

    data = request.get_json()
    name_filter = data.get('name')
    role_filter = data.get('role')
    print(name_filter)
    print(role_filter)
    
    if not name_filter and not role_filter:
        return jsonify({"error": "Missing 'name' or 'role' in request body."}), 400

    # Initialize applications_query with the base Application query
    applications_query =  Application.query # Assuming 'session' is your SQLAlchemy session

    if name_filter or role_filter:
    # Join the Job table only once if any filter requires it
        applications_query = applications_query.filter(Job.is_open == 1)

    if name_filter:
        applications_query = applications_query.filter(
        Job.title.ilike(f'%{name_filter}%')
        )

    if role_filter:
    # No need to join again, Job is already joined
        applications_query = applications_query.filter(
        Job.responsibilities.ilike(f'%{role_filter}%')
        )

    applications = applications_query.all()

    filtered_applications_list = []
    
    for app_obj in applications:
        job = db.session.get(Job, app_obj.job_id)
        if not job:
            continue

        filtered_applications_list.append({
            'id': app_obj.id,
            'job_id': app_obj.job_id,
            'job_title': job.title,
            'applicant_name': app_obj.applicant_name,
            'applicant_email': app_obj.applicant_email,
            'applicant_age': app_obj.applicant_age,
            'applicant_experience': app_obj.applicant_experience,
            'education': app_obj.education,
            'applied_at': app_obj.applied_at.isoformat(),
            'resume_path': app_obj.resume_path,
            'eligibility_score': app_obj.eligibility_score,
            'assessment_score': app_obj.assessment_score,
            'status': app_obj.status
        })

    print(filtered_applications_list)

    return jsonify(filtered_applications_list), 200

# ==================== BACKGROUND TASKS ====================

def send_feedback_rejections():
    with app.app_context():
        rejected_feedback = db.session.query(
            Feedback.feedback_id,
            Feedback.comments,
            Application.applicant_email,
            Application.applicant_name
        ).join(Application, Feedback.candidate_id == Application.id)\
        .filter(Feedback.decision == 'Rejected')\
        .filter((Feedback.rejection_email_sent.is_(None)) | (Feedback.rejection_email_sent == False)).all()
        
        for feedback in rejected_feedback:
            try:
                feedback_obj = db.session.get(Feedback, feedback.feedback_id)
                if feedback_obj.rejection_email_sent:
                    continue
                    
                send_rejection_email(feedback.applicant_email, feedback.applicant_name, feedback.comments)
                
                feedback_obj.rejection_email_sent = True
                db.session.commit()
                print(f"✅ Sent rejection email to {feedback.applicant_name} ({feedback.applicant_email})")
                
            except Exception as e:
                print(f"❌ Error sending feedback rejection to {feedback.applicant_name}: {e}")
                db.session.rollback()

def send_reminders():
    with app.app_context():
        now = datetime.now()

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
                interview_obj = db.session.get(InterviewSchedule, interview.id)

                if time_diff <= timedelta(days=1) and time_diff > timedelta(hours=23):
                    if not interview_obj.reminder_1day_sent:
                        send_reminder_email(interview.applicant_email, interview_time, interview.applicant_name,
                                            interview.mode, interview.meeting_link, interview.address)

                        send_reminder_email(interview.interviewer_email, interview_time, interview.interviewer_name,
                                            interview.mode, interview.meeting_link, interview.address, True)

                        interview_obj.reminder_1day_sent = True
                        db.session.commit()
                        print(f"✅ Sent 1-day reminder for {interview.applicant_name}")

                elif time_diff <= timedelta(hours=1) and time_diff > timedelta(minutes=30):
                    if not interview_obj.reminder_1hour_sent:
                        send_reminder_email(interview.applicant_email, interview_time, interview.applicant_name,
                                            interview.mode, interview.meeting_link, interview.address)

                        send_reminder_email(interview.interviewer_email, interview_time, interview.interviewer_name,
                                            interview.mode, interview.meeting_link, interview.address, True)

                        interview_obj.reminder_1hour_sent = True
                        db.session.commit()
                        print(f"✅ Sent 1-hour reminder for {interview.applicant_name}")

            except Exception as e:
                print(f"❌ Reminder error for {interview.applicant_name}: {e}")
                db.session.rollback()

# Schedule background tasks
schedule.every(2).minutes.do(send_feedback_rejections)
schedule.every(2).minutes.do(send_reminders)


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Start background scheduler
threading.Thread(target=run_scheduler, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=True, port=5000)