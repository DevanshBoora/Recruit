from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import os
import PyPDF2
import google.generativeai as genai # Import Google Generative AI library
import io
import re
from datetime import datetime
import uuid # Import for unique filenames
from werkzeug.utils import secure_filename # For sanitizing filenames
import json # Import for handling JSON questions
from dotenv import load_dotenv


app = Flask(__name__)

# --- Configuration for Upload Folder ---
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER) # Create the uploads directory if it doesn't exist

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Max upload size: 16 MB

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/JobApplications'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

load_dotenv()  # Load environment variables from .env file
# Configure Gemini API with your API key
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")
genai.configure(api_key=GEMINI_API_KEY)

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
}



# Define the model for the 'jobs' table
class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    qualifications = db.Column(db.Text, nullable=False)
    responsibilities = db.Column(db.Text, nullable=False)
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    job_type = db.Column(db.String(50), nullable=False) # e.g., On-site, Remote, Hybrid
    location = db.Column(db.String(255), nullable=False) # e.g., City, State, Country
    required_experience = db.Column(db.String(50), nullable=False) # e.g., 2+ years, 5-7 years
    assessment_timer = db.Column(db.Integer, nullable=True, default=0) # Timer in minutes
    assessment_questions = db.Column(db.Text, nullable=True) # JSON string for questions

    def __repr__(self):
        return f'<Job {self.title}>'

# Define the model for the 'applications' table
class Application(db.Model):
    __tablename__ = 'applications'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    applicant_name = db.Column(db.String(255), nullable=False)
    applicant_age = db.Column(db.Integer, nullable=True)
    applicant_email = db.Column(db.String(255), nullable=False)
    applicant_experience = db.Column(db.Text, nullable=True)
    education = db.Column(db.Text, nullable=True)
    resume_path = db.Column(db.String(255), nullable=False)
    resume_plain_text = db.Column(db.Text, nullable=True)
    eligibility_score = db.Column(db.Float, default=0.0)
    assessment_score = db.Column(db.Float, nullable=True, default=0.0) # Score from the assessment
    status = db.Column(db.String(50), default='Pending')
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)

    job = db.relationship('Job', backref=db.backref('applications', lazy=True))

    def __repr__(self):
        return f'<Application {self.applicant_name} for Job {self.job_id}>'

# Create database tables if they don't exist
with app.app_context():
    db.create_all()

# Helper function to extract text from PDF (takes file-like object directly)
def extract_text_from_pdf(pdf_file_object):
    text = ""
    try:
        reader = PyPDF2.PdfReader(pdf_file_object)
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text() or ""
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        text = "Error extracting resume text."
    return text

# Helper function for allowed file types
ALLOWED_EXTENSIONS = {'pdf'}
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---


@app.route('/')
def home():
    return render_template('main_page.html')

@app.route('/post_job.html')
def post_job_page():
    return render_template('job_form.html')

@app.route('/job_post.html')
def job_postings_page():
    return render_template('job_post.html')

@app.route('/view_applications.html')
def view_applications_page():
    return render_template('view_applications.html')

@app.route('/apply.html')
def apply_page():
    return render_template('apply.html')

@app.route('/edit_job.html')
def edit_job_page():
    return render_template('edit_job.html')

# Assessment Page route - renders the HTML template
@app.route('/assessment/<int:job_id>/<int:application_id>')
def assessment_page(job_id, application_id):
    job = db.session.get(Job, job_id)
    application = db.session.get(Application, application_id)
    if not job or not application:
        # Fallback to home page or show a generic error
        return render_template('main_page.html', message="Job or Application not found."), 404
    # Ensure application belongs to this job
    if application.job_id != job.id:
        return render_template('main_page.html', message="Application does not belong to this job."), 400
    assessment_timer_duration = 3600 
    return render_template('assessment_page.html', job_id=job.id, application_id=application.id ,assessment_timer=assessment_timer_duration )


# API to handle job postings (POST, GET all)
@app.route('/jobs', methods=['POST', 'GET'])
def handle_jobs():
    if request.method == 'POST':
        title = request.form.get('jobTitle')
        description = request.form.get('jobDescription')
        qualifications = request.form.get('qualifications')
        responsibilities = request.form.get('responsibilities')
        job_type = request.form.get('jobType')
        location = request.form.get('jobLocation')
        required_experience = request.form.get('requiredExperience')
        assessment_timer_str = request.form.get('assessmentTimer')
        assessment_questions = request.form.get('assessmentQuestions') # This is the JSON string

        if not all([title, description, qualifications, responsibilities, job_type, location, required_experience]):
            return jsonify({"message": "Missing required fields."}), 400

        assessment_timer = int(assessment_timer_str) if assessment_timer_str and assessment_timer_str.isdigit() else 0

        new_job = Job(
            title=title,
            description=description,
            qualifications=qualifications,
            responsibilities=responsibilities,
            job_type=job_type,
            location=location,
            required_experience=required_experience,
            assessment_timer=assessment_timer,
            assessment_questions=assessment_questions # Store the JSON string
        )
        db.session.add(new_job)
        try:
            db.session.commit()
            return jsonify({"message": "Job posted successfully!", "job_id": new_job.id}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Error posting job: {str(e)}"}), 500

    elif request.method == 'GET':
        jobs = Job.query.all()
        jobs_list = []
        for job in jobs:
            jobs_list.append({
                'id': job.id,
                'title': job.title,
                'description': job.description,
                'qualifications': job.qualifications,
                'responsibilities': job.responsibilities,
                'posted_at': job.posted_at.isoformat(),
                'job_type': job.job_type,
                'location': job.location,
                'required_experience': job.required_experience,
                'assessment_timer': job.assessment_timer,
                'assessment_questions': job.assessment_questions # Return the JSON string
            })
        return jsonify(jobs_list), 200

# API to handle specific job (GET, PUT, DELETE)
@app.route('/jobs/<int:job_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_job(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"message": "Job not found"}), 404

    if request.method == 'GET':
        return jsonify({
            'id': job.id,
            'title': job.title,
            'description': job.description,
            'qualifications': job.qualifications,
            'responsibilities': job.responsibilities,
            'posted_at': job.posted_at.isoformat(),
            'job_type': job.job_type,
            'location': job.location,
            'required_experience': job.required_experience,
            'assessment_timer': job.assessment_timer,
            'assessment_questions': job.assessment_questions # Return the JSON string
        }), 200

    elif request.method == 'PUT':
        job_title = request.form.get('jobTitle')
        job_description = request.form.get('jobDescription')
        qualifications = request.form.get('qualifications')
        responsibilities = request.form.get('responsibilities')
        job_type = request.form.get('jobType')
        job_location = request.form.get('jobLocation')
        required_experience = request.form.get('requiredExperience')
        assessment_timer_str = request.form.get('assessmentTimer')
        assessment_questions = request.form.get('assessmentQuestions')

        if not all([job_title, job_description, qualifications, responsibilities, job_type, job_location, required_experience]):
            return jsonify({"message": "Missing required fields for update."}), 400

        assessment_timer = int(assessment_timer_str) if assessment_timer_str and assessment_timer_str.isdigit() else 0

        job.title = job_title
        job.description = job_description
        job.qualifications = qualifications
        job.responsibilities = responsibilities
        job.job_type = job_type
        job.location = job_location
        job.required_experience = required_experience
        job.assessment_timer = assessment_timer
        job.assessment_questions = assessment_questions

        try:
            db.session.commit()
            return jsonify({"message": "Job updated successfully!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Error updating job: {str(e)}"}), 500

    elif request.method == 'DELETE':
        try:
            db.session.delete(job)
            db.session.commit()
            return jsonify({"message": "Job deleted successfully!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Error deleting job: {str(e)}"}), 500

# NEW: API to get job assessment details for the assessment page
@app.route('/jobs/<int:job_id>/assessment_questions', methods=['GET'])
def get_job_assessment_questions(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"message": "Job not found."}), 404

    questions = []

    if job.assessment_questions:
        try:
            questions = json.loads(job.assessment_questions)
            print("hello")
            print(questions)
        except json.JSONDecodeError:
            print(f"Warning: Assessment questions for job ID {job.id} are not valid JSON.")
            questions = [] # Return empty list if malformed

    return jsonify({
        'job_title': job.title,
        'assessment_timer': job.assessment_timer,
        'assessment_questions': questions # Return as parsed JSON array
    }), 200


# API to submit job applications (initial application)
@app.route('/submit_application', methods=['POST'])
def submit_application():
    job_id = request.form.get('jobId')
    applicant_name = request.form.get('name')
    applicant_age_str = request.form.get('age')
    applicant_email = request.form.get('email')
    applicant_experience = request.form.get('applicantExperience')
    education = request.form.get('education')

    if not all([job_id, applicant_name, applicant_email]):
        return jsonify({"message": "Missing required text fields for application."}), 400

    applicant_age = None
    if applicant_age_str and applicant_age_str.isdigit():
        applicant_age = int(applicant_age_str)

    if 'resume' not in request.files:
        return jsonify({"message": "No resume file part"}), 400

    resume_file = request.files['resume']
    if resume_file.filename == '':
        return jsonify({"message": "No selected resume file"}), 400

    if not allowed_file(resume_file.filename):
        return jsonify({"message": "Invalid file type. Only PDFs are allowed."}), 400

    try:
        file_content = resume_file.read()
        if not file_content:
            return jsonify({"message": "Error processing resume: Cannot read an empty file"}), 400

        resume_plain_text = extract_text_from_pdf(io.BytesIO(file_content))

        original_filename = secure_filename(resume_file.filename)
        unique_filename = f"{uuid.uuid4()}_{original_filename}"
        resume_path_on_disk = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        with open(resume_path_on_disk, 'wb') as f:
            f.write(file_content)

    except Exception as e:
        return jsonify({"message": f"Error processing resume: {str(e)}"}), 500

    job = db.session.get(Job, int(job_id))
    resume_eligibility_score = 0.0 # Renamed for clarity
    if job:
        job_keywords = [
            job.title, job.description, job.qualifications,
            job.responsibilities, job.job_type, job.location,
            job.required_experience
        ]
        combined_job_text = " ".join(job_keywords).lower()
        
        resume_text_lower = resume_plain_text.lower()
        
        score_count = 0
        for keyword in combined_job_text.split():
            if re.search(r'\b' + re.escape(keyword) + r'\b', resume_text_lower):
                score_count += 1
        
        if len(combined_job_text.split()) > 0:
            resume_eligibility_score = (score_count / len(combined_job_text.split())) * 100
        
        resume_eligibility_score = round(resume_eligibility_score, 2)

    new_application = Application(
        job_id=job_id,
        applicant_name=applicant_name,
        applicant_age=applicant_age,
        applicant_email=applicant_email,
        applicant_experience=applicant_experience,
        education=education,
        resume_path=unique_filename,
        resume_plain_text=resume_plain_text,
        eligibility_score=resume_eligibility_score, # Initial resume-based score
        assessment_score=0.0, # Initialize assessment score
        status='Pending' # Status remains pending until assessment is complete
    )
    db.session.add(new_application)
    try:
        db.session.commit()
        # Redirect to the assessment page after successful initial application submission
        return jsonify({"message": "Application submitted successfully! Redirecting to assessment.", 
                        "application_id": new_application.id, 
                        "job_id": job_id,
                        "redirect_url": f"/assessment/{job_id}/{new_application.id}"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Error submitting application: {str(e)}"}), 500


# NEW: API to submit assessment answers and calculate score
@app.route('/submit_assessment/<int:job_id>/<int:application_id>', methods=['POST'])
def submit_assessment_answers(job_id, application_id):
    # Ensure Content-Type is application/json for request.get_json()
    if not request.is_json:
        return jsonify({"message": "Request must be JSON"}), 400

    data = request.get_json()
    submitted_answers_list = data.get('answers', []) # Get list of {question_index, answer}
    # time_taken_seconds = data.get('timeTaken') # Not currently used for score, but available

    application = db.session.get(Application, application_id)
    job = db.session.get(Job, job_id)

    if not application or not job:
        return jsonify({"message": "Application or Job not found."}), 404
    
    if application.job_id != job.id:
        return jsonify({"message": "Application does not belong to this job."}), 400

    assessment_score = 0.0
    try:
        job_questions = json.loads(job.assessment_questions) if job.assessment_questions else []
        
        correct_mcq_count = 0
        total_mcq_questions = 0

        # Map job questions by their 'id' for easier lookup if needed, though index is used by frontend
        # For this setup, we'll rely on matching by index.
        
        for submitted_answer_obj in submitted_answers_list:
            q_index = submitted_answer_obj.get('question_index')
            applicant_answer = submitted_answer_obj.get('answer', '').strip() # Clean answer string

            if q_index is not None and 0 <= q_index < len(job_questions):
                job_q_data = job_questions[q_index]
                
                if job_q_data.get('type') == 'mcq':
                    total_mcq_questions += 1
                    correct_option_value = job_q_data.get('correct_option', '').strip()

                    if applicant_answer.lower() == correct_option_value.lower(): # Case-insensitive comparison
                        correct_mcq_count += 1
                # For 'text' and 'coding' questions, no automated scoring here.
                # Their answers are captured and can be viewed by a human reviewer.
            
        if total_mcq_questions > 0:
            assessment_score = (correct_mcq_count / total_mcq_questions) * 100
        
    except json.JSONDecodeError:
        print(f"Warning: Assessment questions for Job ID {job.id} are not valid JSON.")
        assessment_score = 0.0
    except Exception as e:
        print(f"Error during assessment scoring for Application ID {application.id}: {e}")
        assessment_score = 0.0

    application.assessment_score = round(assessment_score, 2)

    # Recalculate eligibility_score: Average initial resume score and assessment score
    # Ensure both scores are not None before averaging
    if application.eligibility_score is not None and application.assessment_score is not None:
        application.eligibility_score = round((application.eligibility_score + application.assessment_score) / 2, 2)
    elif application.assessment_score is not None: # If only assessment_score is available
        application.eligibility_score = application.assessment_score
    # If both are None, eligibility_score remains its initial (default 0.0) state.
    
    # Optional: Update status to 'Assessed' or 'Review' after assessment completion
    # application.status = 'Assessed'

    try:
        db.session.commit()
        return jsonify({
            "message": "Assessment submitted and scored successfully!", 
            "assessment_score": application.assessment_score, 
            "new_eligibility_score": application.eligibility_score
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Error saving assessment score: {str(e)}"}), 500


# API to get all applications
@app.route('/applications', methods=['GET'])
def get_applications():
    applications = Application.query.all()
    applications_list = []
    for app_obj in applications:
        job = db.session.get(Job, app_obj.job_id)
        
        resume_plain_text_from_db = app_obj.resume_plain_text if app_obj.resume_plain_text else "No plain text available."

        applications_list.append({
            'id': app_obj.id,
            'applicant_name': app_obj.applicant_name,
            'applicant_age': app_obj.applicant_age,
            'applicant_email': app_obj.applicant_email,
            'applicant_experience': app_obj.applicant_experience,
            'education': app_obj.education,
            'job_title': job.title if job else "N/A",
            'applied_at': app_obj.applied_at.isoformat(),
            'resume_path': app_obj.resume_path,
            'resume_plain_text': resume_plain_text_from_db,
            'eligibility_score': app_obj.eligibility_score,
            'assessment_score': app_obj.assessment_score, # Include assessment score
            'status': app_obj.status
        })
    return jsonify(applications_list), 200

# API endpoint to update application status
@app.route('/applications/<int:app_id>/status', methods=['PUT'])
def update_application_status(app_id):
    application = db.session.get(Application, app_id)
    if not application:
        return jsonify({"message": "Application not found"}), 404

    data = request.get_json()
    new_status = data.get('status')

    if new_status not in ['Accepted', 'Rejected', 'Pending']:
        return jsonify({"message": "Invalid status provided."}), 400

    application.status = new_status
    try:
        db.session.commit()
        return jsonify({"message": f"Application status updated to '{new_status}' successfully!"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Error updating status: {str(e)}"}), 500

# API endpoint to serve uploaded resume files
@app.route('/resumes/<filename>', methods=['GET'])
def serve_resume(filename):
    safe_filename = secure_filename(filename)
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename)
    except Exception as e:
        return jsonify({"message": f"Resume file not found or access denied: {str(e)}"}), 404


if __name__ == '__main__':
    app.run(debug=True)