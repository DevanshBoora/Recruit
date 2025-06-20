from flask import Blueprint, render_template, request, jsonify, current_app as app
from models import db, Job, Application
import PyPDF2, json, re, os, uuid
import google.generativeai as genai
from werkzeug.utils import secure_filename

# Blueprint setup
submit_bp = Blueprint('submit_bp', __name__)

# Gemini config
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
}

# Allowed file types
ALLOWED_EXTENSIONS = {'pdf'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Resume text extraction
def extract_text_from_pdf(pdf_file_object):
    text = ""
    try:
        reader = PyPDF2.PdfReader(pdf_file_object)
        for page in reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        text = "Error extracting resume text."
    return text

# Submit application route
@submit_bp.route('/submit_application', methods=['POST'])
def submit_application():
    print("Received request to submit_application!") 
    job_id = request.form.get('jobId')
    name = request.form.get('name')
    applicant_age_str = request.form.get('age')
    email = request.form.get('email')
    applicant_experience = request.form.get('experience')
    education = request.form.get('education')
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

        with open(resume_path, 'rb') as f:
            resume_plain_text = extract_text_from_pdf(f)

        job_keywords = set(re.findall(r'\b\w+\b', job.description.lower()))
        resume_keywords = set(re.findall(r'\b\w+\b', resume_plain_text.lower()))
        common_keywords = len(job_keywords.intersection(resume_keywords))
        eligibility_score = (common_keywords / len(job_keywords)) * 100 if len(job_keywords) > 0 else 0.0

        applicant_age = int(applicant_age_str) if applicant_age_str.isdigit() else None

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
                "assessment_timer": assessment_timer
            }), 201
        except Exception as e:
            db.session.rollback()
            if os.path.exists(resume_path):
                os.remove(resume_path)
            return jsonify({"message": f"Error submitting application: {str(e)}"}), 500
    else:
        return jsonify({"message": "Invalid file type. Only PDF is allowed."}), 400

# Submit assessment route
@submit_bp.route('/submit_assessment/<int:job_id>/<int:application_id>', methods=['POST'])
def submit_assessment(job_id, application_id):
    application = db.session.get(Application, application_id)
    job = db.session.get(Job, job_id)

    if not application or not job:
        return jsonify({"message": "Application or Job not found."}), 404

    data = request.get_json()
    user_answers = data.get('answers', [])

    print("submitted assesment")

    job_description = job.description
    job_qualifications = job.qualifications
    job_responsibilities = job.responsibilities
    min_assessment_score = job.min_assesment_score
    resume_text = application.resume_plain_text
    job_assessment_questions = json.loads(job.assessment_questions) if job.assessment_questions else []

    formatted_user_answers = []
    for ua in user_answers:
        idx = ua.get('question_index')
        answer = ua.get('answer')
        if 0 <= idx < len(job_assessment_questions):
            question_text = job_assessment_questions[idx]
            formatted_user_answers.append(f"Question: {question_text}\nAnswer: {answer}")

    user_answers_str = "\\n\\n".join(formatted_user_answers)

    gemini_prompt = [
        f"""
        You are an advanced AI expert in resume screening and candidate-job matching.

        You will receive a job description and a resume. Analyze the resume in detail against the job description and provide a comprehensive evaluation.
        if the name in the resume and the name in the applicant_name do not match, return a score of 0.
        Score the resume out of 100 based on:
        - skills, qualifications, achievements, certifications, projects, location, experience, resume_quality

         if the name in the resume and the name in the applicant_name do not match, return a score of 0.
        Also evaluate assessment answers (provided below) on a 0–100 scale.

        also extrct the good summary of the resume in Resume Summary field
        If the name in the resume and the name in the applicant_anme do not match, return a score of 0.

        Format:
        {{
          "gemini_score": 85.5,
          "assessment_score": 86.7,
          "reasoning": "Strong alignment with qualifications and good answers.",
          "Resume Summary": "The candidate has relevant experience and skills.",
        }}

        Job Title: {job.title}
        Description: {job_description}
        Qualifications: {job_qualifications}
        Responsibilities: {job_responsibilities}
        if the name in the resume and the name in the applicant_name do not match, return a score of 0.
        Applicant:
        - Name: {application.applicant_name}
        - Email: {application.applicant_email}
        - Age: {application.applicant_age}
        - Experience: {application.applicant_experience}
        - Education: {application.education}
        - Resume: {resume_text[:3000]}
        if the name in the resume and the name in the applicant_name do not match, return a score of 0.
        Name in the Resume should matcht the applicant_name other wise return 0 score
        Assessment Answers:
        {user_answers_str}
        if the name in the resume and the name in the applicant_name do not match, return a score of 0.
        """
    ]

    try:
        model = genai.GenerativeModel('gemini-2.0-flash', generation_config=generation_config)
        response = model.generate_content(gemini_prompt)
        gemini_output_text = response.text.strip()

        json_match = re.search(r"```json\s*(\{.*?})\s*```", gemini_output_text, re.DOTALL)
        gemini_output_json_str = json_match.group(1) if json_match else gemini_output_text
        gemini_output = json.loads(gemini_output_json_str)

        gemini_score = float(gemini_output.get('gemini_score', 0.0))
        assessment_score = float(gemini_output.get('assessment_score', 0.0))

        if assessment_score < min_assessment_score:
            db.session.delete(application)
            db.session.commit()
            return jsonify({
                "message": "Application rejected. Assessment score below minimum threshold.",
                "assessment_score": assessment_score
            }), 200

        application.eligibility_score = gemini_score
        application.assessment_score = assessment_score
        application.status = "Pending"
        db.session.commit()

        return jsonify({
            "message": "Assessment submitted and scored successfully!",
            "gemini_score": gemini_score,
            "assessment_score": assessment_score
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"[Gemini Error] {e}")
        return jsonify({"message": f"Error during Gemini evaluation: {str(e)}"}), 500
