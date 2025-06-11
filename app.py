from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect
from flask_cors import CORS
import os
import json
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_
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
from db_tools import get_applicant_info, get_job_details, get_jobs_by_type, get_applications_by_status
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

UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/JobApplications'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_super_secret_key'
app.config['SESSION_TYPE'] = 'filesystem'

db.init_app(app)
with app.app_context():
    db.create_all()

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")
genai.configure(api_key=GEMINI_API_KEY)

@app.route('/assessment/<int:job_id>/<int:application_id>', methods=['GET'])
def assessment_page_route(job_id, application_id):
    job = db.session.get(Job, job_id)
    application = db.session.get(Application, application_id)
    if not job or not application or application.job_id != job.id:
        return render_template('main_page.html', message="Assessment Error."), 400
    return render_template('assessment_page.html')

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
        slot_id = int(data["slot_id"])
        candidate_id = int(data["candidate_id"])
        mode = data["mode"]
        meeting_link = data.get("meeting_link")
        address = data.get("address")

        slot = InterviewSlot.query.filter_by(id=slot_id, is_booked=False).first()

        if not slot:
            return redirect("/schedule?message=Slot%20already%20booked.&type=error")

        # Check if candidate already has a scheduled interview
        existing_candidate = InterviewSchedule.query.filter_by(candidate_id=candidate_id).first()
        if existing_candidate:
            return redirect("/schedule?message=Candidate%20already%20scheduled.&type=error")

        # Check if interviewer has another interview at the same time
        conflict = InterviewSchedule.query.filter(
            and_(
                InterviewSchedule.interview_date == slot.slot_datetime,
                InterviewSchedule.interviewer_email == slot.interviewer.email
            )
        ).first()
        if conflict:
            return redirect("/schedule?message=Interviewer%20already%20has%20a%20slot%20at%20this%20time.&type=error")

        try:
            # Create interview schedule using slot's details
            interview = InterviewSchedule(
                candidate_id=candidate_id,
                mode=slot.mode,
                interview_date=slot.slot_datetime,
                interviewer_name=slot.interviewer.name,
                interviewer_email=slot.interviewer.email,
                meeting_link=slot.meeting_link if slot.mode == 'Online' else meeting_link,
                address=slot.address if slot.mode == 'Offline' else address
            )

            slot.is_booked = True
            db.session.add(interview)
            db.session.commit()
            return redirect("/schedule?message=Interview%20scheduled%20successfully!&type=success")

        except IntegrityError as e:
            db.session.rollback()
            return redirect(f"/schedule?message=Integrity%20error.&type=error")
        except Exception as e:
            db.session.rollback()
            return redirect(f"/schedule?message=Error:%20{str(e)}&type=error")

    # GET request
    # Use ORM queries instead of raw SQL
    candidates = db.session.query(Application.id, Application.applicant_name)\
        .filter(Application.status == 'Accepted')\
        .filter(~Application.id.in_(
            db.session.query(InterviewSchedule.candidate_id)
            .filter(InterviewSchedule.candidate_id.isnot(None))
        ))\
        .order_by(Application.applied_at.desc()).all()

    available_slots = InterviewSlot.query.filter_by(is_booked=False).order_by(InterviewSlot.slot_datetime).all()

    return render_template("schedule.html", candidates=candidates, slots=available_slots)

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        data = request.form

        # Prevent duplicate feedback using ORM
        existing = Feedback.query.filter_by(candidate_id=data["candidate_id"]).first()

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
            
            if data['decision'] == "Accepted":
                application = Application.query.get(data['candidate_id'])
                if application:
                    accepted_candidate = AcceptedCandidate(
                        candidate_id=application.id,
                        applicant_name=application.applicant_name,
                        applicant_email=application.applicant_email
                    )
                    db.session.add(accepted_candidate)
                    
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Error: {e}", 500
        return redirect("/feedback")

    # GET request - fetch only candidates who don't have feedback submitted using ORM
    candidates = db.session.query(Application.id, Application.applicant_name)\
        .filter(Application.status == 'Accepted')\
        .filter(~Application.id.in_(
            db.session.query(Feedback.candidate_id)
            .filter(Feedback.candidate_id.isnot(None))
        ))\
        .order_by(Application.applied_at.desc()).all()
    
    return render_template("feedback.html", candidates=candidates)

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

@app.route('/interviewer/login', methods=['GET', 'POST'])
def interviewer_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        interviewer = Interviewer.query.filter_by(email=email).first()
        if interviewer and interviewer.check_password(password):
            session['interviewer_id'] = interviewer.id
            session['interviewer_name'] = interviewer.name
            return redirect('/interviewer/slots')  # or dashboard
        else:
            return "Invalid credentials", 401

    return render_template('interviewer_login.html')

@app.route('/interviewer/register', methods=['GET', 'POST'])
def register_interviewer():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        existing = Interviewer.query.filter_by(email=email).first()
        if existing:
            return "Interviewer with this email already exists.", 400

        new_interviewer = Interviewer(name=name, email=email)
        new_interviewer.set_password(password)

        try:
            db.session.add(new_interviewer)
            db.session.commit()
            return redirect('/interviewer/login')  # or show success
        except Exception as e:
            db.session.rollback()
            return f"Error: {e}", 500

    return render_template('interviewer_register.html')

@app.route("/interviewer/slots", methods=["GET", "POST"])
def add_slot():
    if 'interviewer_id' not in session:
        return redirect("/interviewer/login")

    if request.method == "POST":
        slot_datetime = request.form["slot_datetime"]
        mode = request.form["mode"]
        meeting_link = request.form.get("meeting_link", "").strip()
        address = request.form.get("address", "").strip()

        # Validate mode selection
        if mode not in ['Online', 'Offline']:
            return "Invalid mode selected", 400

        # Validate required fields based on mode
        if mode == 'Online' and not meeting_link:
            return "Meeting link is required for online interviews", 400
        
        if mode == 'Offline' and not address:
            return "Address is required for offline interviews", 400

        # Convert string to datetime object
        try:
            slot_datetime = datetime.strptime(slot_datetime, '%Y-%m-%dT%H:%M')
        except ValueError:
            return "Invalid date format", 400

        new_slot = InterviewSlot(
            interviewer_id=session['interviewer_id'],
            slot_datetime=slot_datetime,
            mode=mode,
            meeting_link=meeting_link if mode == 'Online' else None,
            address=address if mode == 'Offline' else None
        )

        try:
            db.session.add(new_slot)
            db.session.commit()
            return redirect("/interviewer/slots?message=Slot%20added%20successfully!&type=success")
        except IntegrityError:
            db.session.rollback()
            return "Slot already exists for this time", 400
        except Exception as e:
            db.session.rollback()
            return f"Error: {e}", 500

    # GET request - show existing slots
    interviewer_slots = InterviewSlot.query.filter_by(
        interviewer_id=session['interviewer_id']
    ).order_by(InterviewSlot.slot_datetime.desc()).all()

    return render_template("add_slot.html", slots=interviewer_slots)

@app.route('/logout_interviewer')
def logout_interviewer():
    # Remove interviewer-specific session keys
    session.pop('interviewer_id', None)
    session.pop('interviewer_email', None)
    session.pop('interviewer_name', None)
    
    # Redirect to a login or home page
    return redirect('/interviewer/login')  # Fixed redirect

@app.route('/interviewer/dashboard')
def interviewer_dashboard():
    if 'interviewer_id' not in session:
        return redirect('/interviewer/login')

    interviewer = Interviewer.query.get(session['interviewer_id'])

    # Get upcoming slots
    upcoming_slots = InterviewSlot.query.filter_by(
        interviewer_id=interviewer.id
    ).order_by(InterviewSlot.slot_datetime).all()

    # Get interviews scheduled with this interviewer
    scheduled_interviews = InterviewSchedule.query.filter_by(
        interviewer_email=interviewer.email
    ).order_by(InterviewSchedule.interview_date).all()

    return render_template(
        'interviewer_dashboard.html',
        interviewer=interviewer,
        slots=upcoming_slots,
        interviews=scheduled_interviews
    )

# ------------------ Background Tasks ------------------ #

def send_feedback_rejections():
    with app.app_context():
        # Use ORM instead of raw SQL
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
                # Double-check before sending to prevent race conditions
                feedback_obj = Feedback.query.get(feedback.feedback_id)
                if feedback_obj.rejection_email_sent:
                    continue
                    
                send_rejection_email(feedback.applicant_email, feedback.applicant_name, feedback.comments)
                
                # Mark as sent immediately after sending
                feedback_obj.rejection_email_sent = True
                db.session.commit()
                print(f"Sent rejection email to {feedback.applicant_name} ({feedback.applicant_email})")
                
            except Exception as e:
                print(f"Error sending feedback rejection to {feedback.applicant_name}: {e}")
                db.session.rollback()

def send_reminders():
    with app.app_context():
        now = datetime.now()
        # Use ORM instead of raw SQL
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
                
                # --- 1 day reminder ---
                if time_diff <= timedelta(days=1) and time_diff > timedelta(hours=23):
                    if not interview_obj.reminder_1day_sent:
                        send_reminder_email(interview.applicant_email, interview_time, interview.applicant_name,
                                            interview.mode, interview.meeting_link, interview.address)

                        send_reminder_email(interview.interviewer_email, interview_time, interview.interviewer_name,
                                            interview.mode, interview.meeting_link, interview.address, True)

                        interview_obj.reminder_1day_sent = True
                        db.session.commit()
                        print(f"✅ Sent 1-day reminder for {interview.applicant_name}")

                # --- 1 hour reminder ---
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

# Reduce frequency to prevent excessive checking
schedule.every(2).minutes.do(send_feedback_rejections)
schedule.every(2).minutes.do(send_reminders)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute instead of every 10 seconds

threading.Thread(target=run_scheduler, daemon=True).start()

# ------------------ Main ------------------ #

if __name__ == '__main__':
    app.run(debug=True)