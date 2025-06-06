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
    min_assesment_score = db.Column(db.Integer, nullable=True, default=0)

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

# In app.py
@app.route('/assessment/<int:job_id>/<int:application_id>', methods=['GET'])
def assessment_page_route(job_id, application_id):
    # Validate if job and application exist and belong together
    job = db.session.get(Job, job_id)
    application = db.session.get(Application, application_id)

    if not job:
        # It's better to show a specific error if job is not found for this URL
        return render_template('main_page.html', message="Assessment Error: Job not found."), 404
    if not application:
        return render_template('main_page.html', message="Assessment Error: Application not found."), 404
    if application.job_id != job.id:
        return render_template('main_page.html', message="Assessment Error: Application does not belong to this job."), 400

    # If all checks pass, simply render the HTML page.
    # The JavaScript on assessment_page.html will extract job_id and application_id
    # from the URL itself and then make an API call to /jobs/<job_id>
    # to fetch assessment questions and timer.
    return render_template('assessment_page.html')

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
        min_assesment_score = request.form.get('minAssessmentScore')
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
            assessment_questions=assessment_questions,
            min_assesment_score=min_assesment_score
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
                'assessment_questions': json.loads(job.assessment_questions) if job.assessment_questions else [],
                'min_assesment_score': job.min_assesment_score
            })
        return jsonify(jobs_list), 200

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
            'assessment_questions': json.loads(job.assessment_questions) if job.assessment_questions else [],
            'min_assesment_score': job.min_assesment_score
        }), 200

    elif request.method == 'PUT':
        title = request.form.get('jobTitle')
        description = request.form.get('jobDescription')
        qualifications = request.form.get('qualifications')
        responsibilities = request.form.get('responsibilities')
        job_type = request.form.get('jobType')
        location = request.form.get('jobLocation')
        required_experience = request.form.get('requiredExperience')
        assessment_timer_str = request.form.get('assessmentTimer')
        assessment_questions = request.form.get('assessmentQuestions')
        min_assesment_score = request.form.get('minAssesmentScore')

        if not all([title, description, qualifications, responsibilities, job_type, location, required_experience]):
            return jsonify({"message": "Missing required fields."}), 400
        
        job.title = title
        job.description = description
        job.qualifications = qualifications
        job.responsibilities = responsibilities
        job.job_type = job_type
        job.location = location
        job.required_experience = required_experience
        job.assessment_timer = int(assessment_timer_str) if assessment_timer_str and assessment_timer_str.isdigit() else 0
        job.assessment_questions = assessment_questions
        job.min_assesment_score = float(min_assesment_score) if min_assesment_score and min_assesment_score.replace('.', '', 1).isdigit() else 0.0

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

@app.route('/submit_application', methods=['POST'])
def submit_application():
    job_id = request.form.get('jobId')
    name = request.form.get('name')
    applicant_age_str = request.form.get('age') # Retrieved from form
    email = request.form.get('email')
    applicant_experience = request.form.get('experience') # Retrieved from form
    education = request.form.get('education') # Retrieved from form

    resume_file = request.files.get('resume')

    if not all([job_id, name, applicant_age_str, email, applicant_experience, education, resume_file]):
        return jsonify({"message": "Missing required application fields."}), 400

    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"message": "Job not found."}), 404
    assessment_timer = job.assessment_timer

    if resume_file and allowed_file(resume_file.filename):
        filename = secure_filename(f"{uuid.uuid4()}_{resume_file.filename}")
        resume_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        resume_file.save(resume_path)

        # Extract text from PDF for eligibility scoring
        with open(resume_path, 'rb') as f:
            resume_plain_text = extract_text_from_pdf(f)

        # Basic eligibility scoring (can be enhanced with Gemini)
        eligibility_score = 0.0
        # Example: Check if keywords from job description are in resume
        job_keywords = set(re.findall(r'\b\w+\b', job.description.lower()))
        resume_keywords = set(re.findall(r'\b\w+\b', resume_plain_text.lower()))
        common_keywords = len(job_keywords.intersection(resume_keywords))
        
        if len(job_keywords) > 0: # Avoid division by zero
            eligibility_score = (common_keywords / len(job_keywords)) * 100

        applicant_age = int(applicant_age_str) if applicant_age_str and applicant_age_str.isdigit() else None

        new_application = Application(
            job_id=job_id,
            applicant_name=name,
            applicant_age=applicant_age,
            applicant_email=email,
            applicant_experience=applicant_experience,
            education=education,
            resume_path=filename,
            resume_plain_text=resume_plain_text,
            eligibility_score=eligibility_score,
            status='Pending'
        )
        db.session.add(new_application)
        try:
            db.session.commit()
            return jsonify({
                "message": "Application submitted successfully! Please proceed to assessment.",
                "job_id": job_id,
                "application_id": new_application.id,
                "assessment_timer":assessment_timer
            }), 201
        except Exception as e:
            db.session.rollback()
            # Clean up the uploaded resume if DB transaction fails
            if os.path.exists(resume_path):
                os.remove(resume_path)
            return jsonify({"message": f"Error submitting application: {str(e)}"}), 500
    else:
        return jsonify({"message": "Invalid file type. Only PDF is allowed."}), 400

@app.route('/submit_assessment/<int:job_id>/<int:application_id>', methods=['POST'])
def submit_assessment(job_id, application_id):
    application = db.session.get(Application, application_id)
    job = db.session.get(Job, job_id)

    if not application or not job:
        return jsonify({"message": "Application or Job not found."}), 404

    data = request.get_json()
    user_answers = data.get('answers', [])

    job_description = job.description
    job_qualifications = job.qualifications
    job_responsibilities = job.responsibilities
    resume_text = application.resume_plain_text
    job_assessment_questions = json.loads(job.assessment_questions) if job.assessment_questions else []

    # Prepare user answers for Gemini
   
    formatted_user_answers = []
    for ua in user_answers:
        idx = ua.get('question_index')
        answer = ua.get('answer')
        if 0 <= idx < len(job_assessment_questions):

            question_text = job_assessment_questions[idx]['text']
            formatted_user_answers.append(f"Question: {question_text}\nAnswer: {answer}")
    
    user_answers_str = "\\n\\n".join(formatted_user_answers)


    # Construct prompt for Gemini
    prompt_parts = [
        f"""
        You are an advanced AI expert in resume screening and candidate-job matching.

You will receive a job description and a resume. Analyze the resume in detail against the job description and provide a comprehensive evaluation.

Instructions:

Score the resume out of 100, considering the following criteria:

skills: How well the candidate's skills match the required skills in the job description.

qualifications: Whether the candidate's qualifications meet or exceed the requirements.

achievements: Relevance and quantity of achievements related to the required skills.

certifications: Number and relevance of certifications to the job requirements.

projects: How well the candidate's project experience aligns with the job description.

location: Whether the candidate's preferred location (e.g., hybrid, remote) matches the job's requirements.

experience: Whether the candidate's work experience meets or exceeds the job requirements.

resume_quality: The overall quality of the resume, including presence of LinkedIn links, contact information, location, and overall professionalism.

For each criterion, assign a score out of 100.


Calculate the overall score (out of 100) as a weighted or averaged value of the above criteria.

Based on the overall score and individual criteria, provide a "Decision" field with either "accept" or "reject".

Output should be strictly in the following JSON format and nothing else:


json

   {{"gemini_score": 85.5, "reasoning": "Strong alignment with qualifications and good answers.", assessment_score:86.7}}

   
also the assesment_score should be purely 
Based on the provided applicants their answers to assessment questions,
        provide an assessment score from 0.0 to 100.0.

        Assessment Questions and User Answers:
        {user_answers_str}

        Evalutate the answers based on the given question for it 
        Provide only a JSON output with the assessment score and a brief reasoning.
        Example: {{"assessment_score": 85.5, "reasoning": "Strong alignment with qualifications and good answers."}}


the gemini_score Evaluate using only the information provided below.

        Job Title: {job.title}
        Job Description: {job_description}
        Qualifications: {job_qualifications}
        Responsibilities: {job_responsibilities}

        Applicant Name: {application.applicant_name}
        Applicant Email: {application.applicant_email}
        Applicant Age: {application.applicant_age}
        Applicant Experience: {application.applicant_experience}
        Applicant Education: {application.education}
        Resume Text: {resume_text}

        """,
    ]

   
    

    gemini_prompt = "".join(prompt_parts)

    try:
        model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)
       
        response = model.generate_content(gemini_prompt)
        
        gemini_output_text = response.text.strip()
        json_match = re.search(r"```json\s*(\{.*?})\s*```", gemini_output_text, re.DOTALL)
        if json_match:
            gemini_output_json_str = json_match.group(1)
        else:
            gemini_output_json_str = gemini_output_text
            
        gemini_output = json.loads(gemini_output_json_str)
        
        gemini_score = float(gemini_output.get('gemini_score', 0.0))
        assessment_score = float(gemini_output.get('assessment_score', 0.0))
        # assessment_reasoning = gemini_output.get('reasoning', 'No specific reasoning provided.')

    except Exception as e:
        print(f"Error calling Gemini API for assessment scoring or parsing response: {e}")
        eligibilty_score = 0.0 # Default score if AI call fails
        # assessment_reasoning = f"AI assessment scoring failed: {e}"

    application.eligibility_score = gemini_score
    application.assessment_score = assessment_score
    application.status = 'Pending' # Update status after assessment
    try:
        db.session.commit()
        return jsonify({"message": "Assessment submitted and scored successfully!", "assessment_score": assessment_score}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Error submitting assessment: {str(e)}"}), 500


# API endpoint to get all applications
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
            'applicant_age': app_obj.applicant_age,           # ADDED
            'applicant_experience': app_obj.applicant_experience, # ADDED
            'education': app_obj.education,                 # ADDED
            'applied_at': app_obj.applied_at.isoformat(),
            'resume_path': app_obj.resume_path,
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
    except FileNotFoundError:
        return jsonify({"message": "Resume file not found."}), 404

if __name__ == '__main__':
    app.run(debug=True)