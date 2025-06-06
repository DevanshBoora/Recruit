from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
import os
import PyPDF2
import google.generativeai as genai
import io
import re
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
import json
from dotenv import load_dotenv


app = Flask(__name__)

# --- Configuration for Upload Folder ---
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/JobApplications'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

load_dotenv()
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


class Job(db.Model):
    __tablename__ = 'jobs'
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

    def __repr__(self):
        return f'<Job {self.title}>'

class Application(db.Model):
    __tablename__ = 'applications'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False) # ADD ondelete='CASCADE'
    applicant_name = db.Column(db.String(255), nullable=False)
    applicant_age = db.Column(db.Integer, nullable=True)
    applicant_email = db.Column(db.String(255), nullable=False)
    applicant_experience = db.Column(db.Text, nullable=True)
    education = db.Column(db.Text, nullable=True)
    resume_path = db.Column(db.String(255), nullable=False)
    resume_plain_text = db.Column(db.Text, nullable=True)
    eligibility_score = db.Column(db.Float, default=0.0)
    assessment_score = db.Column(db.Float, nullable=True, default=0.0)
    status = db.Column(db.String(50), default='Pending')
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)

    job = db.relationship('Job', backref=db.backref('applications', lazy=True, cascade='all, delete-orphan'))
    def __repr__(self):
        return f'<Application {self.applicant_name} for Job {self.job_id}>'

with app.app_context():
    db.create_all()

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

ALLOWED_EXTENSIONS = {'pdf'}
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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

@app.route('/assessment/<int:job_id>/<int:application_id>')
def assessment_page(job_id, application_id):
    job = db.session.get(Job, job_id)
    application = db.session.get(Application, application_id)
    if not job or not application:
        return render_template('main_page.html', message="Job or Application not found."), 404
    if application.job_id != job.id:
        return render_template('main_page.html', message="Application does not belong to this job."), 400
    assessment_timer_duration = 3600
    return render_template('assessment_page.html', job_id=job.id, application_id=application.id ,assessment_timer=assessment_timer_duration )


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
        assessment_questions = request.form.get('assessmentQuestions')

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
            assessment_questions=assessment_questions
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
                'assessment_questions': job.assessment_questions
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
            'assessment_questions': job.assessment_questions
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
            # Check if there are any applications associated with this job
            associated_applications = Application.query.filter_by(job_id=job.id).count()
            if associated_applications > 0:
                return jsonify({"message": f"Cannot delete job: {associated_applications} applications are associated with this job. Please delete applications first or implement cascade delete logic if intended."}), 400

            db.session.delete(job)
            db.session.commit()
            return jsonify({"message": "Job deleted successfully!"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Error deleting job: {str(e)}"}), 500

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
            questions = []
    return jsonify({
        'job_title': job.title,
        'assessment_timer': job.assessment_timer,
        'assessment_questions': questions
    }), 200


@app.route('/submit_application', methods=['POST'])
def submit_application():
    job_id = request.form.get('jobId')
    applicant_name = request.form.get('name')
    applicant_age_str = request.form.get('age')
    applicant_email = request.form.get('email')
    applicant_experience = request.form.get('experience')
    education = request.form.get('education')

    if 'resume' not in request.files:
        return jsonify({"message": "No resume file part"}), 400
    resume_file = request.files['resume']
    if resume_file.filename == '':
        return jsonify({"message": "No selected resume file"}), 400
    if resume_file and allowed_file(resume_file.filename):
        original_filename = secure_filename(resume_file.filename)
        unique_filename = str(uuid.uuid4()) + "_" + original_filename
        resume_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        resume_file.save(resume_path)

        # Extract plain text from PDF for Gemini
        resume_file.seek(0)  # Reset file pointer after saving
        resume_plain_text = extract_text_from_pdf(resume_file)

        job = db.session.get(Job, job_id)
        if not job:
            return jsonify({"message": "Job not found"}), 404

        # Prepare content for Gemini API for eligibility scoring
        prompt_text = f"""
        You are an AI assistant for a job application system. Your task is to evaluate a candidate's resume against a job description and determine their eligibility score.

        Job Title: {job.title}
        Job Description: {job.description}
        Qualifications: {job.qualifications}
        Responsibilities: {job.responsibilities}
        Required Experience: {job.required_experience}
        Job Type: {job.job_type}
        Location: {job.location}

        Candidate Name: {applicant_name}
        Candidate Email: {applicant_email}
        Candidate Age: {applicant_age_str if applicant_age_str else 'Not provided'}
        Candidate Experience Summary (from form): {applicant_experience if applicant_experience else 'Not provided'}
        Candidate Education (from form): {education if education else 'Not provided'}
        Candidate Resume Text:
        {resume_plain_text}

        Based on the above information, assess the candidate's eligibility for the job. Provide a score from 0.0 to 10.0, where 10.0 is a perfect match and 0.0 is no match. Also, provide a brief reasoning for the score, highlighting strengths and weaknesses relevant to the job.

        Output should be in JSON format:
        {{
            "eligibility_score": float,
            "reasoning": "string"
        }}
        """

        try:
            model = genai.GenerativeModel('gemini-pro', generation_config=generation_config)
            response = model.generate_content(prompt_text)
            
            # Extracting text from the response and attempting to parse JSON
            gemini_output_text = response.text.strip()
            # Clean the string to ensure it's valid JSON
            # Sometimes Gemini might include markdown or extra text, try to extract only the JSON part
            json_match = re.search(r"```json\s*(\{.*?\})\s*```", gemini_output_text, re.DOTALL)
            if json_match:
                gemini_output_json_str = json_match.group(1)
            else:
                # If no markdown, assume the entire output is JSON
                gemini_output_json_str = gemini_output_text

            gemini_output = json.loads(gemini_output_json_str)
            
            eligibility_score = float(gemini_output.get('eligibility_score', 0.0))
            # reasoning = gemini_output.get('reasoning', 'No specific reasoning provided.')

        except Exception as e:
            print(f"Error calling Gemini API or parsing response: {e}")
            eligibility_score = 0.0 # Default score if AI call fails
            # reasoning = f"AI eligibility assessment failed: {e}"

        applicant_age = int(applicant_age_str) if applicant_age_str and applicant_age_str.isdigit() else None

        new_application = Application(
            job_id=job_id,
            applicant_name=applicant_name,
            applicant_age=applicant_age,
            applicant_email=applicant_email,
            applicant_experience=applicant_experience,
            education=education,
            resume_path=unique_filename,
            resume_plain_text=resume_plain_text,
            eligibility_score=eligibility_score
        )
        db.session.add(new_application)
        try:
            db.session.commit()
            return jsonify({"message": "Application submitted successfully! Your eligibility score has been calculated.", "eligibility_score": eligibility_score, "application_id": new_application.id, "job_id": job_id}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Error submitting application: {str(e)}"}), 500
    else:
        return jsonify({"message": "Invalid file type for resume"}), 400


@app.route('/resumes/<filename>', methods=['GET'])
def serve_resume(filename):
    safe_filename = secure_filename(filename)
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename)
    except FileNotFoundError:
        return jsonify({"message": "Resume not found"}), 404

@app.route('/applications', methods=['GET'])
def get_applications():
    applications = Application.query.all()
    applications_list = []
    for app_obj in applications:
        job = db.session.get(Job, app_obj.job_id)
        job_title = job.title if job else "N/A"
        applications_list.append({
            'id': app_obj.id,
            'job_id': app_obj.job_id,
            'job_title': job_title,
            'applicant_name': app_obj.applicant_name,
            'applicant_email': app_obj.applicant_email,
            'applied_at': app_obj.applied_at.isoformat(),
            'resume_path': app_obj.resume_path,
            'eligibility_score': app_obj.eligibility_score,
            'assessment_score': app_obj.assessment_score,
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
def serve_resume_file(filename):
    safe_filename = secure_filename(filename)
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename)
    except FileNotFoundError:
        return jsonify({"message": "Resume file not found"}), 404

@app.route('/submit_assessment/<int:application_id>', methods=['POST'])
def submit_assessment(application_id):
    application = db.session.get(Application, application_id)
    if not application:
        return jsonify({"message": "Application not found."}), 404

    job = db.session.get(Job, application.job_id)
    if not job:
        return jsonify({"message": "Associated job not found."}), 404

    assessment_answers = request.get_json()
    if not assessment_answers:
        return jsonify({"message": "No assessment answers provided."}), 400

    # Retrieve job's assessment questions
    job_assessment_questions = []
    if job.assessment_questions:
        try:
            job_assessment_questions = json.loads(job.assessment_questions)
        except json.JSONDecodeError:
            return jsonify({"message": "Error parsing job assessment questions."}), 500

    if not job_assessment_questions:
        return jsonify({"message": "No assessment questions defined for this job."}), 400

    # Prepare data for Gemini to score the assessment
    prompt_parts = [f"Job Title: {job.title}\n"]
    prompt_parts.append(f"Job Description: {job.description}\n")
    prompt_parts.append(f"Candidate Name: {application.applicant_name}\n")
    prompt_parts.append("Job Assessment Questions and Correct Answers:\n")
    
    # Include questions and expected answers (assuming questions structure has an 'answer' field)
    for i, q in enumerate(job_assessment_questions):
        # Depending on question type, construct the correct answer string
        if q['type'] == 'multiple-choice' or q['type'] == 'checkboxes':
            correct_options = [option['text'] for option in q['options'] if option.get('isCorrect')]
            prompt_parts.append(f"  Question {i+1} ({q['type']}): {q['questionText']}\n  Correct Answer(s): {', '.join(correct_options)}\n")
        elif q['type'] == 'true-false':
            prompt_parts.append(f"  Question {i+1} ({q['type']}): {q['questionText']}\n  Correct Answer: {'True' if q.get('isCorrect') else 'False'}\n")
        elif q['type'] == 'short-answer' or q['type'] == 'long-answer':
            prompt_parts.append(f"  Question {i+1} ({q['type']}): {q['questionText']}\n  Expected Keywords/Concepts: {q.get('expectedAnswer', 'No specific expected answer provided for scoring.')}\n")

    prompt_parts.append("\nCandidate's Submitted Answers:\n")
    for i, qa in enumerate(assessment_answers.get('answers', [])):
        prompt_parts.append(f"  Question {i+1}: {qa.get('questionText', 'N/A')}\n  Candidate's Answer: {qa.get('candidateAnswer', 'N/A')}\n")

    prompt_parts.append("\nBased on the job assessment questions and the candidate's submitted answers, provide a score for the candidate's performance on this assessment. The score should be between 0.0 and 10.0, where 10.0 is a perfect score. Also, provide a brief reasoning for the score, highlighting accuracy, completeness, and relevance of answers to the questions and job requirements.\n")
    prompt_parts.append("Output should be in JSON format:\n")
    prompt_parts.append("{\n  \"assessment_score\": float,\n  \"reasoning\": \"string\"\n}\n")

    gemini_prompt = "".join(prompt_parts)

    try:
        model = genai.GenerativeModel('gemini-pro', generation_config=generation_config)
        response = model.generate_content(gemini_prompt)
        
        gemini_output_text = response.text.strip()
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", gemini_output_text, re.DOTALL)
        if json_match:
            gemini_output_json_str = json_match.group(1)
        else:
            gemini_output_json_str = gemini_output_text
            
        gemini_output = json.loads(gemini_output_json_str)
        
        assessment_score = float(gemini_output.get('assessment_score', 0.0))
        # assessment_reasoning = gemini_output.get('reasoning', 'No specific reasoning provided.')

    except Exception as e:
        print(f"Error calling Gemini API for assessment scoring or parsing response: {e}")
        assessment_score = 0.0 # Default score if AI call fails
        # assessment_reasoning = f"AI assessment scoring failed: {e}"

    application.assessment_score = assessment_score
    application.status = 'Assessment Completed' # Update status after assessment
    try:
        db.session.commit()
        return jsonify({"message": "Assessment submitted and scored successfully!", "assessment_score": assessment_score}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Error saving assessment score: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True)