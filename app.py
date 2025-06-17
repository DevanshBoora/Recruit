from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, flash
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
import subprocess
import signal
import atexit
from datetime import datetime
from routes import register_blueprints
from models import db, Job, Application, InterviewSchedule, Feedback, AcceptedCandidate
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

# Global variables for Streamlit process management
streamlit_process = None
streamlit_port = 8501

UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:12345678@localhost/jobapplications'
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

# ==================== STREAMLIT PROCESS MANAGEMENT ====================

def start_streamlit_process():
    """Start the Streamlit email automation dashboard as a subprocess."""
    global streamlit_process
    
    if streamlit_process and streamlit_process.poll() is None:
        logging.info("Streamlit process is already running")
        return True
    
    try:
        # Path to your streamlit app file
        streamlit_app_path = os.path.join(os.path.dirname(__file__), 'streamlit_app.py')
        
        if not os.path.exists(streamlit_app_path):
            logging.error(f"Streamlit app file not found: {streamlit_app_path}")
            return False
        
        # Command to run Streamlit
        cmd = [
            'streamlit', 'run', streamlit_app_path,
            '--server.port', str(streamlit_port),
            '--server.address', 'localhost',
            '--server.headless', 'true',
            '--browser.gatherUsageStats', 'false'
        ]
        
        # Start the process
        streamlit_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )
        
        logging.info(f"Streamlit process started with PID: {streamlit_process.pid}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to start Streamlit process: {e}")
        return False

def stop_streamlit_process():
    """Stop the Streamlit process."""
    global streamlit_process
    
    if streamlit_process and streamlit_process.poll() is None:
        try:
            if os.name == 'nt':  # Windows
                streamlit_process.terminate()
            else:  # Unix/Linux
                os.killpg(os.getpgid(streamlit_process.pid), signal.SIGTERM)
            
            streamlit_process.wait(timeout=10)
            logging.info("Streamlit process stopped successfully")
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                streamlit_process.kill()
            else:
                os.killpg(os.getpgid(streamlit_process.pid), signal.SIGKILL)
            logging.warning("Streamlit process force killed")
        except Exception as e:
            logging.error(f"Error stopping Streamlit process: {e}")
    
    streamlit_process = None

def is_streamlit_running():
    """Check if Streamlit process is running."""
    global streamlit_process
    return streamlit_process and streamlit_process.poll() is None

def cleanup_processes():
    """Clean up processes when the application shuts down."""
    stop_streamlit_process()

atexit.register(cleanup_processes)

# ==================== STREAMLIT INTEGRATION ROUTES ====================

@app.route('/email-dashboard')
def email_dashboard():
    """Route to access the Streamlit email automation dashboard."""
    if not is_streamlit_running():
        if start_streamlit_process():
            # Wait a moment for Streamlit to start
            time.sleep(3)
        else:
            flash("Failed to start email automation dashboard", "error")
            return redirect('/')
    
    # Redirect to the Streamlit app
    streamlit_url = f"http://localhost:{streamlit_port}"
    return render_template('streamlit_redirect.html', streamlit_url=streamlit_url)

@app.route('/email-dashboard/start', methods=['POST'])
def start_email_dashboard():
    """API endpoint to start the Streamlit dashboard."""
    success = start_streamlit_process()
    return jsonify({
        "success": success,
        "message": "Email dashboard started successfully" if success else "Failed to start email dashboard",
        "url": f"http://localhost:{streamlit_port}" if success else None
    })

@app.route('/email-dashboard/stop', methods=['POST'])
def stop_email_dashboard():
    """API endpoint to stop the Streamlit dashboard."""
    stop_streamlit_process()
    return jsonify({
        "success": True,
        "message": "Email dashboard stopped successfully"
    })

@app.route('/email-dashboard/status')
def email_dashboard_status():
    """Check the status of the Streamlit dashboard."""
    is_running = is_streamlit_running()
    return jsonify({
        "running": is_running,
        "url": f"http://localhost:{streamlit_port}" if is_running else None
    })

# ==================== EXISTING ROUTES (KEEP ALL YOUR ORIGINAL ROUTES) ====================

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
                    result["applicant_email"],
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
                application = Application.query.get(int(data['candidate_id']))
                if application:
                    accepted_candidate = AcceptedCandidate(
                        candidate_id=application.id,
                        applicant_name=application.applicant_name,
                        applicant_email=application.applicant_email
                    )
                    db.session.add(accepted_candidate)

            db.session.commit()
            flash("Feedback submitted successfully.", "success")
            return redirect("/view_applications.html")

        except Exception as e:
            db.session.rollback()
            return f"Error: {e}", 500

    try:
        # GET request – only show candidates with interviews and no feedback
        candidates = db.session.query(Application.id, Application.applicant_name).filter(
            Application.status == 'Accepted',
            Application.id.in_(
                db.session.query(InterviewSchedule.candidate_id).filter(InterviewSchedule.candidate_id.isnot(None))
            ),
            ~Application.id.in_(
                db.session.query(Feedback.candidate_id).filter(Feedback.candidate_id.isnot(None))
            )
        ).order_by(Application.applied_at.desc()).all()

        return render_template("feedback.html", candidates=candidates)

    except Exception as e:
        return f"Error loading feedback page: {e}", 500

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

                # 1-day reminder
                if time_diff <= timedelta(days=1) and time_diff > timedelta(hours=23):
                    if not interview_obj.reminder_1day_sent:
                        send_reminder_email(interview.applicant_email, interview_time, interview.applicant_name,
                                            interview.mode, interview.meeting_link, interview.address)

                        send_reminder_email(interview.interviewer_email, interview_time, interview.interviewer_name,
                                            interview.mode, interview.meeting_link, interview.address, True)

                        interview_obj.reminder_1day_sent = True
                        db.session.commit()
                        print(f"✅ Sent 1-day reminder for {interview.applicant_name}")

                # 1-hour reminder
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

threading.Thread(target=run_scheduler, daemon=True).start()

# ==================== MAIN ====================

if __name__ == '__main__':
    app.run(debug=True, port=5000)
