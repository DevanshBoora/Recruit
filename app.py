from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, flash, url_for
from flask_cors import CORS
from flask_bcrypt import Bcrypt
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
import pandas as pd
import smtplib
import imaplib
import email
import re
import traceback
import unicodedata
import requests
from email.mime.text import MIMEText
import mysql.connector
from mysql.connector import Error
from routes import register_blueprints
from models import db, Job, Application, InterviewSchedule, Feedback, AcceptedCandidate, User, JobOffer, Slot,Company
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
bcrypt = Bcrypt(app)

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/JobApplications'
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

# ==================== INTEGRATED EMAIL OFFER SYSTEM ====================

def normalize_unicode(text):
    """Normalize unicode characters in text"""
    normalized = unicodedata.normalize('NFKD', text)
    replacements = {
        ''': "'", ''': "'", '"': '"', '"': '"',
        '…': '...', '–': '-', '—': '--', 'ʼ': "'"
    }
    for k, v in replacements.items():
        normalized = normalized.replace(k, v)
    return normalized

def clean_email_body(raw_body):
    """Clean email body by removing signatures and quoted text"""
    text = normalize_unicode(raw_body)
    separators = [
        r"On.wrote:", r"From:\s.", r"Sent:\s.", r"To:\s.", r"Subject:\s.*",
        r"-----Original Message-----", r"^\s*>", r"^\s*--\s*$", r"Best regards",
        r"Kind regards", r"Regards", r"Cheers", r"Sincerely"
    ]
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in separators):
            break
        if line and not line.startswith('>'):
            clean_lines.append(line)
    clean_text = ' '.join(clean_lines)
    return re.sub(r'\s+', ' ', clean_text).strip()

def classify_with_gemini(text):
    """Classify email response as accepted or rejected using Gemini AI"""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""Classify this email response to a job offer as 'accepted' or 'rejected'. 
    Look for clear acceptance or rejection language. Be strict in classification.
    Text: "{text}" 
    Respond with only 'accepted' or 'rejected'."""
    try:
        response = model.generate_content(prompt)
        result = response.text.strip().lower()
        return "accepted" if "accept" in result and "reject" not in result else "rejected"
    except Exception as e:
        logging.error(f"Gemini classification error: {e}")
        return "rejected"

def send_job_offer_email(to_email, name, job_position, company_name="Our Company"):
    """Send job offer email to candidate"""
    msg = MIMEText(f"""Dear {name},

We are delighted to offer you the position of {job_position} at {company_name}.

We were impressed by your qualifications and believe you would be a valuable addition to our team.

Please reply to this email within 24 hours to confirm your acceptance of this offer.

If you have any questions, please don't hesitate to contact us.

Best regards,
HR Team
{company_name}""")
    
    msg["Subject"] = f"Job Offer - {job_position} Position"
    msg["From"] = EMAIL_CONFIG["email_address"]
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_SERVER, 587) as server:
            server.starttls()
            server.login(EMAIL_CONFIG["email_address"], EMAIL_CONFIG["email_password"])
            server.send_message(msg)
        logging.info(f"Job offer email sent to {to_email}")
        return True
    except Exception as e:
        logging.error(f"Email send error: {e}")
        return False

def get_email_responses():
    """Check for email responses to job offers"""
    responses = {}
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
        mail.login(EMAIL_CONFIG["email_address"], EMAIL_CONFIG["email_password"])
        mail.select("inbox")
        
        # Search for replies to job offers
        status, data = mail.search(None, '(UNSEEN SUBJECT "Re: Job Offer")')
        
        for num in data[0].split():
            _, msg_data = mail.fetch(num, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            sender = email.utils.parseaddr(msg["From"])[1]

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                        body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")

            clean_body = clean_email_body(body)
            responses[sender] = classify_with_gemini(clean_body)
            
            # Mark email as read
            mail.store(num, "+FLAGS", "\\Seen")
            
        mail.close()
        mail.logout()
    except Exception as e:
        logging.error(f"IMAP error: {e}")
    
    return responses

def process_job_offers():
    """Process job offers and handle responses"""
    try:
        # Get email responses
        email_responses = get_email_responses()
        
        # Check for pending offers that need to be sent
        pending_offers = JobOffer.query.filter_by(status='pending', offer_sent=False).all()
        
        for offer in pending_offers:
            application = Application.query.get(offer.application_id)
            if application:
                job = Job.query.get(application.job_id)
                if send_job_offer_email(application.applicant_email, application.applicant_name, job.title):
                    offer.offer_sent = True
                    offer.offer_sent_time = datetime.now()
                    db.session.commit()
                    logging.info(f"Offer sent to {application.applicant_name}")
                    break  # Send one offer at a time
        
        # Process email responses
        for email_addr, response in email_responses.items():
            application = Application.query.filter_by(applicant_email=email_addr).first()
            if application:
                offer = JobOffer.query.filter_by(application_id=application.id, status='pending').first()
                if offer:
                    if response == 'accepted':
                        offer.status = 'accepted'
                        application.status = 'Hired'
                        # Create accepted candidate record
                        accepted_candidate = AcceptedCandidate(
                            candidate_id=application.id,
                            applicant_name=application.applicant_name,
                            applicant_email=application.applicant_email
                        )
                        db.session.add(accepted_candidate)
                        logging.info(f"Offer accepted by {application.applicant_name}")
                    else:
                        offer.status = 'rejected'
                        application.status = 'Rejected'
                        logging.info(f"Offer rejected by {application.applicant_name}")
                    
                    db.session.commit()
        
        # Check for timed out offers
        timeout_threshold = datetime.now() - timedelta(hours=TIMEOUT_HOURS)
        timed_out_offers = JobOffer.query.filter(
            JobOffer.status == 'pending',
            JobOffer.offer_sent == True,
            JobOffer.offer_sent_time < timeout_threshold
        ).all()
        
        for offer in timed_out_offers:
            offer.status = 'expired'
            application = Application.query.get(offer.application_id)
            if application:
                application.status = 'Offer Expired'
            db.session.commit()
            logging.info(f"Offer expired for application {offer.application_id}")
            
    except Exception as e:
        logging.error(f"Error processing job offers: {e}")
        db.session.rollback()

# ==================== NEW ROUTES FOR OFFER MANAGEMENT ====================

@app.route('/offers', methods=['GET'])
def view_offers():
    """View all job offers"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    offers = db.session.query(
        JobOffer.id,
        JobOffer.status,
        JobOffer.offer_sent,
        JobOffer.offer_sent_time,
        JobOffer.created_at,
        Application.applicant_name,
        Application.applicant_email,
        Job.title.label('job_title')
    ).join(Application, JobOffer.application_id == Application.id)\
     .join(Job, Application.job_id == Job.id)\
     .order_by(JobOffer.created_at.desc()).all()
    
    return render_template('offers.html', offers=offers)

@app.route('/offers/create', methods=['POST'])
def create_offer():
    """Create a new job offer"""
    if 'user_id' not in session:
        return jsonify({"message": "Unauthorized"}), 401
    
    data = request.get_json()
    application_id = data.get('application_id')
    
    if not application_id:
        return jsonify({"message": "Application ID required"}), 400
    
    # Check if application exists and is eligible for offer
    application = Application.query.get(application_id)
    if not application:
        return jsonify({"message": "Application not found"}), 404
    
    if application.status not in ['Accepted']:
        return jsonify({"message": "Application not eligible for offer"}), 400
    
    # Check if offer already exists
    existing_offer = JobOffer.query.filter_by(application_id=application_id).first()
    if existing_offer:
        return jsonify({"message": "Offer already exists for this application"}), 400
    
    # Create new offer
    new_offer = JobOffer(
        application_id=application_id,
        status='pending',
        offer_sent=False
    )
    
    db.session.add(new_offer)
    db.session.commit()
    
    return jsonify({"message": "Offer created successfully", "offer_id": new_offer.id}), 201

@app.route('/offers/process', methods=['POST'])
def manual_process_offers():
    """Manually trigger offer processing"""
    if 'user_id' not in session:
        return jsonify({"message": "Unauthorized"}), 401
    
    process_job_offers()
    return jsonify({"message": "Offers processed successfully"}), 200

@app.route('/offers/dashboard')
def offers_dashboard():
    """Dashboard for job offers"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get statistics
    total_offers = JobOffer.query.count()
    pending_offers = JobOffer.query.filter_by(status='pending').count()
    accepted_offers = JobOffer.query.filter_by(status='accepted').count()
    rejected_offers = JobOffer.query.filter_by(status='rejected').count()
    expired_offers = JobOffer.query.filter_by(status='expired').count()
    
    stats = {
        'total': total_offers,
        'pending': pending_offers,
        'accepted': accepted_offers,
        'rejected': rejected_offers,
        'expired': expired_offers
    }
    
    return render_template('offers_dashboard.html', stats=stats)
# ==================== Adding the slots ====================
@app.route('/slots/add', methods=['GET', 'POST'])
def add_slots():
    # Only allow certain roles (e.g., admin, HR) to add slots
    # if session.get('user_role') not in ['admin', 'hr']:
    #     flash('You do not have permission to add slots.', 'error')
    #     return redirect(url_for('dashboard')) # Or appropriate page
   
    if request.method == 'POST':
        data = request.get_json() 
        company_name = data.get('company_name')
        role = data.get('role')
        interview_time_str = data.get('interview_time')
        interviewer_name = data.get('interviewer_name')
        interviewer_email = data.get('interviewer_email')
        mode = data.get('mode')
        meeting_link = data.get('meeting_link')
        address = data.get('address')
        

        if not all([company_name, role, interview_time_str, interviewer_name, interviewer_email, mode]):
            print(company_name)
            return jsonify({"message": "Missing required fields"}), 400

        try:
            # Parse datetime string from HTML form (example: 2025-06-19T14:30)
            interview_time = datetime.fromisoformat(interview_time_str)
        except ValueError:
            return jsonify({"message": "Invalid date/time format"}), 400

        # Basic validation for mode-specific fields
        if mode == 'online' and not meeting_link:
            return jsonify({"message": "Meeting link is required for online interviews"}), 400
        if mode == 'offline' and not address:
            return jsonify({"message": "Address is required for in-person interviews"}), 400
        
        # Ensure meeting_link/address is None if not applicable, for cleaner data
        if mode != 'online': meeting_link = None
        if mode != 'offline': address = None

        new_slot = Slot(
            company_name=company_name,
            role=role,
            interview_time=interview_time,
            interviewer_name=interviewer_name,
            interviewer_email=interviewer_email,
            mode=mode,
            meeting_link=meeting_link,
            address=address,
            is_booked=False # Initially not booked
        )
        db.session.add(new_slot)
        db.session.commit()
        return jsonify({"message": "Slot added successfully", "slot_id": new_slot.id}), 201
    
    # GET request for adding slots
    return render_template('add_slot.html') # You'll create this HTML template


# --- New Route to View Available Slots ---
@app.route('/slots', methods=['GET'])
def view_slots():
    # Fetch all unbooked slots or filter by company/role if needed
    # You might want to filter by user's company if 'company_name' in Slot matches User's company
    current_user_id = session.get('user_id')
    user = User.query.get(current_user_id)
    
    if not user:
        return jsonify({"message": "User not found"}), 404

    slots_query = Slot.query.filter_by(is_booked=False).order_by(Slot.interview_time)

    # Filter slots based on the logged-in user's company (if they have one)
    if user.company_name:
        slots_query = slots_query.filter_by(company_name=user.company_name)

    available_slots = slots_query.all()
    
    # You might want to filter by job title/role as well if the user has a specific job they are hiring for
    # Example: If `user` has an associated job they are managing. This would depend on your user-job relationship.
    
    return render_template('view_slots.html', slots=available_slots) # Create this HTML template


@app.route('/applications/<int:application_id>/accept', methods=['POST'])

def accept_application_and_assign_slot(application_id):
    application = db.session.get(Application, application_id)
    if not application:
        return jsonify({"message": "Application not found"}), 404

   
    # if application.status != "Pending":
    #     return jsonify({"message": "Application already processed."}), 400

    
    job = Job.query.get(application.job_id)
    if not job:
        return jsonify({"message": "Associated job not found."}), 404


    current_user_id = session.get('user_id')
    acting_user = db.session.get(User, current_user_id)
    print(current_user_id)
    if not acting_user or not acting_user.company_name:
        return jsonify({"message": "User's company information is missing for slot allocation."}), 400

   
    available_slot = Slot.query.filter(
        Slot.company_name == acting_user.company_name, # Filter by company accepting the application
        Slot.role == job.responsibilities, # Match the job title/role
        Slot.is_booked == False,
        Slot.interview_time > datetime.utcnow() # Only future slots
    ).order_by(Slot.interview_time.asc()).first() # Get the earliest available slot

    if not available_slot:
        # No slot available, maybe prompt for manual scheduling or offer to create one
        return jsonify({"message": "No available interview slots found for this role and company. Please add new slots."}), 404

    # Book the slot
    available_slot.is_booked = True
    available_slot.booked_by_application_id = application.id

    # Update application status
    application.status = "Interview Scheduled"

    try:
        db.session.commit()

        # Send emails to candidate and interviewer
        print("correct till here")
        send_schedule_email(
            application.applicant_email,
            available_slot.interview_time,
            available_slot.mode,
            available_slot.interviewer_name,
            available_slot.meeting_link,
            available_slot.address
            
        )
        send_schedule_email(
            available_slot.interviewer_email,
            available_slot.interview_time,
            available_slot.mode,
            available_slot.interviewer_name,
            available_slot.meeting_link,
            available_slot.address,
            is_interviewer=True
        )

        message = "Application accepted and interview scheduled."
       

        # Optionally, delete the old InterviewSchedule entry if it exists for this application
        interview_schedule_entry = InterviewSchedule.query.filter_by(candidate_id=application.id).first()
        if interview_schedule_entry:
            db.session.delete(interview_schedule_entry)
            db.session.commit() # Commit again after deleting

        return jsonify({"message": message, "slot_id": available_slot.id}), 200

    except Exception as e:
        db.session.rollback() # Rollback in case of error
        print(f"Error booking slot or sending email: {e}")
        return jsonify({"message": f"Failed to book slot or send emails. Error: {str(e)}"}), 500

# --- You might also want a route to delete a slot if it's no longer needed ---
@app.route('/slots/<int:slot_id>/delete', methods=['POST']) # Or DELETE method
def delete_slot(slot_id):
    slot = Slot.query.get(slot_id)
    if not slot:
        return jsonify({"message": "Slot not found"}), 404
    
    # Add authorization check here: Only owner company/admin can delete
    current_user_id = session.get('user_id')
    user = User.query.get(current_user_id)
    if not user or (user.company_name and user.company_name != slot.company_name) and user.role != 'admin':
        return jsonify({"message": "Unauthorized to delete this slot"}), 403

    if slot.is_booked:
        return jsonify({"message": "Cannot delete a booked slot. Unbook it first if necessary."}), 400

    db.session.delete(slot)
    db.session.commit()
    return jsonify({"message": "Slot deleted successfully"}), 200


# ==================== EXISTING ROUTES (PRESERVED) ====================

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        company_name = data.get('company_name')
        role = data.get('role') 
        company_password = data.get('company_password')
        position = data.get('position')
        company =  Company.query.filter_by(company_name=company_name).first()
        if not name or not password:
            return jsonify({"message": "Name and password are required"}), 400
        
        if not company or not company.check_password(company_password):
            print(company)
            return jsonify({"message": "company password error or company "}), 401
        

        existing_user = User.query.filter_by(name=name).first()
        if existing_user:
            return jsonify({"message": "Username already exists"}), 409

        new_user = User(name=name, email=email ,password=password, company_name=company_name, role=role,position=position)
        db.session.add(new_user)
        try:
            db.session.commit()
            return jsonify({"message": "User registered successfully!", "user": new_user.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Error registering user: {str(e)}"}), 500
    return render_template('signup.html')

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
    return render_template('login.html')

@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return render_template('main_page.html')



# ==================== EXISTING ROUTES (KEEP ALL YOUR ORIGINAL ROUTES) ====================


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
        # Get the current interviewer's name from the session
        current_interviewer_name = session.get('user_name')

        if not current_interviewer_name:
            # Handle case where interviewer name is not in session (e.g., not logged in)
            # You might redirect to login or show an error
            return render_template("error.html", message="Interviewer not identified. Please log in.")

        # GET request – show candidates whose interviews were scheduled by the current interviewer
        # and who do not yet have feedback.
        candidates = db.session.query(Application.id, Application.applicant_name).filter(
            # Candidate application status is 'Accepted' (from your original logic)
            Application.status == 'Accepted',

            # Filter by applications linked to interview schedules booked by the current interviewer
            Application.id.in_(
                db.session.query(Slot.booked_by_application_id).filter(
                    and_(
                        Slot.booked_by_application_id.isnot(None),
                        Slot.interviewer_name == current_interviewer_name # Filter by interviewer's name
                    )
                ).distinct() # Use distinct to avoid duplicate application IDs if one candidate has multiple interviews
            ),

            # Filter out candidates who already have feedback
            ~Application.id.in_(
                db.session.query(Feedback.candidate_id).filter(Feedback.candidate_id.isnot(None)).distinct()
            )
        ).order_by(Application.applied_at.desc()).all()

        return render_template("feedback.html", candidates=candidates)

    except Exception as e:
            # Handle exceptions appropriately, e.g., log the error and return an error page
        print(f"Error fetching candidates: {e}")
            # Consider showing a more user-friendly message or logging full traceback
        return render_template("error.html", message=f"An error occurred while fetching candidates: {e}")

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

    applications_query = Application.query

    if name_filter or role_filter:
        applications_query = applications_query.join(Job)

    if name_filter:
        applications_query = applications_query.filter(Job.title.ilike(f'%{name_filter}%'))

    if role_filter:
        applications_query = applications_query.filter(Job.responsibilities.ilike(f'%{role_filter}%'))

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
schedule.every(5).minutes.do(process_job_offers)  # Process offers every 5 minutes

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Start background scheduler
threading.Thread(target=run_scheduler, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=True, port=5000)