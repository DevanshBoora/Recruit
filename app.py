from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect
from flask_cors import CORS
import os
import json
import google.generativeai as genai
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from sqlalchemy import text
from datetime import datetime, timedelta
import threading
import time
import schedule

from routes import register_blueprints
from models import db, Job, Application
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

        # Prevent scheduling more than once
        existing = db.session.execute(text("""
            SELECT 1 FROM interview_schedule WHERE candidate_id = :candidate_id
        """), {"candidate_id": data["candidate_id"]}).fetchone()

        if existing:
            return redirect("/schedule?message=Interview%20already%20scheduled%20for%20this%20candidate.&type=error")

        try:
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

            result = db.session.execute(text("SELECT applicant_email FROM application WHERE id = :id"),
                                        {"id": data["candidate_id"]}).mappings().first()
            if result:
                send_schedule_email(result['applicant_email'], data["interview_datetime"], data["mode"],
                                    data["interviewer_name"], data.get("meeting_link"), data.get("address"))
                send_schedule_email(data["interviewer_email"], data["interview_datetime"], data["mode"],
                                    data["interviewer_name"], data.get("meeting_link"), data.get("address"), True)
            db.session.commit()
            return redirect("/schedule?message=Interview%20scheduled%20successfully!&type=success")
        except Exception as e:
            db.session.rollback()
            return redirect(f"/schedule?message=Error%20scheduling%20interview:%20{str(e)}&type=error")

    # GET request - fetch only candidates who don't have interviews scheduled
    candidates = db.session.execute(text("""
        SELECT a.id, a.applicant_name
        FROM application a 
        WHERE a.status = 'Accepted' 
        AND a.id NOT IN (
            SELECT DISTINCT candidate_id 
            FROM interview_schedule 
            WHERE candidate_id IS NOT NULL
        )
        ORDER BY a.applied_at DESC
    """)).mappings().all()
    
    return render_template("schedule.html", candidates=candidates)

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        data = request.form

        # Prevent duplicate feedback
        existing = db.session.execute(text("""
            SELECT 1 FROM feedback WHERE candidate_id = :candidate_id
        """), {"candidate_id": data["candidate_id"]}).fetchone()

        if existing:
            return "Feedback already submitted for this candidate.", 400

        try:
            db.session.execute(text("""
                INSERT INTO feedback (candidate_id, comments, decision, communication_score, technical_score, problem_solving_score)
                VALUES (:candidate_id, :comments, :decision, :communication_score, :technical_score, :problem_solving_score)
            """), data)
            if data['decision'] == "Accepted":
                result = db.session.execute(text("""
                    SELECT applicant_name, applicant_email 
                    FROM application 
                    WHERE id = :id
                """), {"id": data['candidate_id']}).mappings().first()
                if result:
                    db.session.execute(text("""
                        INSERT INTO accepted_candidates (candidate_id, applicant_name, applicant_email)
                        VALUES (:id, :name, :email)
                    """), {
                        "id": data['candidate_id'],
                        "name": result['applicant_name'],
                        "email": result['applicant_email']
                    })
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return f"Error: {e}", 500
        return redirect("/feedback")

    # GET request - fetch only candidates who don't have feedback submitted
    candidates = db.session.execute(text("""
        SELECT a.id, a.applicant_name 
        FROM application a 
        WHERE a.status = 'Accepted' 
        AND a.id NOT IN (
            SELECT DISTINCT candidate_id 
            FROM feedback 
            WHERE candidate_id IS NOT NULL
        )
        ORDER BY a.applied_at DESC
    """)).mappings().all()
    
    return render_template("feedback.html", candidates=candidates)

@app.route("/dashboard")
def dashboard():
    result = db.session.execute(text("""
        SELECT a.applicant_name, f.decision, f.comments, f.communication_score,
               f.technical_score, f.problem_solving_score, f.rejection_email_sent
        FROM feedback f
        JOIN application a ON f.candidate_id = a.id
    """)).mappings().all()
    return render_template("dashboard.html", feedback=result)
# ------------------ Background Tasks ------------------ #

def send_feedback_rejections():
    with app.app_context():
        results = db.session.execute(text("""
            SELECT f.feedback_id, f.comments, a.applicant_email, a.applicant_name
            FROM feedback f
            JOIN application a ON f.candidate_id = a.id
            WHERE f.decision = 'Rejected' AND (f.rejection_email_sent IS NULL OR f.rejection_email_sent = FALSE)
        """)).mappings().all()
        
        for r in results:
            try:
                # Double-check before sending to prevent race conditions
                check_sent = db.session.execute(text("""
                    SELECT rejection_email_sent FROM feedback WHERE feedback_id = :id
                """), {"id": r['feedback_id']}).scalar()
                
                if check_sent:  # If already sent, skip
                    continue
                    
                send_rejection_email(r['applicant_email'], r['applicant_name'], r['comments'])
                
                # Mark as sent immediately after sending
                db.session.execute(text("UPDATE feedback SET rejection_email_sent = TRUE WHERE feedback_id = :id"),
                                   {"id": r['feedback_id']})
                db.session.commit()
                print(f"Sent rejection email to {r['applicant_name']} ({r['applicant_email']})")
                
            except Exception as e:
                print(f"Error sending feedback rejection to {r['applicant_name']}: {e}")
                db.session.rollback()

def send_reminders():
    with app.app_context():
        now = datetime.now()
        interviews = db.session.execute(text("""
            SELECT i.id, i.interview_date, i.candidate_id, i.mode, i.interviewer_name, i.interviewer_email,
                   i.meeting_link, i.address, i.reminder_1day_sent, i.reminder_1hour_sent,
                   a.applicant_email AS candidate_email, a.applicant_name
            FROM interview_schedule i
            JOIN application a ON i.candidate_id = a.id
            WHERE i.interview_date > :now
        """), {"now": now}).mappings().all()
        
        for i in interviews:
            interview_time = i['interview_date']
            time_diff = interview_time - now
            
            try:
                # 1 day reminder
                if time_diff <= timedelta(days=1) and time_diff > timedelta(hours=23) and not i['reminder_1day_sent']:
                    # Double-check before sending
                    check_sent = db.session.execute(text("""
                        SELECT reminder_1day_sent FROM interview_schedule WHERE id = :id
                    """), {"id": i['id']}).scalar()
                    
                    if check_sent:  # Already sent, skip
                        continue
                    
                    # Send to candidate
                    send_reminder_email(i['candidate_email'], interview_time, i['applicant_name'],
                                        i['mode'], i['meeting_link'], i['address'])
                    
                    # Send to interviewer
                    send_reminder_email(i['interviewer_email'], interview_time, i['interviewer_name'],
                                        i['mode'], i['meeting_link'], i['address'], True)
                    
                    # Mark as sent
                    db.session.execute(text("UPDATE interview_schedule SET reminder_1day_sent = TRUE WHERE id = :id"),
                                       {"id": i['id']})
                    db.session.commit()
                    print(f"Sent 1-day reminder for {i['applicant_name']}")
                
                # 1 hour reminder
                elif time_diff <= timedelta(hours=1) and time_diff > timedelta(minutes=30) and not i['reminder_1hour_sent']:
                    # Double-check before sending
                    check_sent = db.session.execute(text("""
                        SELECT reminder_1hour_sent FROM interview_schedule WHERE id = :id
                    """), {"id": i['id']}).scalar()
                    
                    if check_sent:  # Already sent, skip
                        continue
                    
                    # Send to candidate
                    send_reminder_email(i['candidate_email'], interview_time, i['applicant_name'],
                                        i['mode'], i['meeting_link'], i['address'])
                    
                    # Send to interviewer
                    send_reminder_email(i['interviewer_email'], interview_time, i['interviewer_name'],
                                        i['mode'], i['meeting_link'], i['address'], True)
                    
                    # Mark as sent
                    db.session.execute(text("UPDATE interview_schedule SET reminder_1hour_sent = TRUE WHERE id = :id"),
                                       {"id": i['id']})
                    db.session.commit()
                    print(f"Sent 1-hour reminder for {i['applicant_name']}")
                    
            except Exception as e:
                print(f"Reminder error for {i['applicant_name']}: {e}")
                db.session.rollback()

# ------------------ Scheduler ------------------ #

# Reduce frequency to prevent excessive checking
schedule.every(1).minutes.do(send_feedback_rejections)  # Changed from 10 seconds to 1 minute
schedule.every(1).minutes.do(send_reminders)  # Changed from 10 seconds to 1 minute

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute instead of every 10 seconds

threading.Thread(target=run_scheduler, daemon=True).start()

# ------------------ Main ------------------ #

if __name__ == '__main__':
    app.run(debug=True)
