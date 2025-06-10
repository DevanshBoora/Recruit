# my_tiny_app/routes/admin.py
from flask import Blueprint,render_template,request,jsonify
from models import db, Job, Application
import PyPDF2 ,json,re,os,uuid
import google.generativeai as genai
from werkzeug.utils import secure_filename
from flask import current_app as app


# Create a blueprint for admin routes
# THIS LINE IS CRUCIAL FOR 'admin_bp' TO EXIST
submit_bp = Blueprint('submit_bp', __name__)


generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
}



ALLOWED_EXTENSIONS = {'pdf'}
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS




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




@submit_bp.route('/submit_application', methods=['POST'])
def submit_application():
    print("Received request to submit_application!") 
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

@submit_bp.route('/submit_assessment/<int:job_id>/<int:application_id>', methods=['POST'])
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
    min_assessment_score = job.min_assesment_score
    resume_text = application.resume_plain_text

    job_assessment_questions = json.loads(job.assessment_questions) if job.assessment_questions else []

    # Format answers for Gemini
    formatted_user_answers = []
    for ua in user_answers:
        idx = ua.get('question_index')
        answer = ua.get('answer')
        if 0 <= idx < len(job_assessment_questions):
            question_text = job_assessment_questions[idx]['text']

            question_text = job_assessment_questions[idx]
            print(question_text)
            formatted_user_answers.append(f"Question: {question_text}\nAnswer: {answer}")
    
    user_answers_str = "\\n\\n".join(formatted_user_answers)

    # Construct prompt for Gemini
    gemini_prompt = [
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
        Provide only a JSON output with the assessment score.
        If it is multiple choice see the correct answer using correct_option and match with the use answer give points based on it , give appropriate marks,( 1 question asked, if it correct give 100 marks, 2 questions asked only one correct give 50 marks , like divide marks for the quetions)
        for the coding assessment, give good marks , if their code should represent that they have minimum knowledge of the question asked,
        and if they have given a good answer to the question, give them good marks
        Example: {{"assessment_score": 85.5"}}


the gemini_score Evaluate using only the information provided below.

Job Title: {job.title}
Job Description: {job_description}
Qualifications: {job_qualifications}
Responsibilities: {job_responsibilities}

Applicant:
- Name: {application.applicant_name}
- Email: {application.applicant_email}
- Age: {application.applicant_age}
- Experience: {application.applicant_experience}
- Education: {application.education}
- Resume: {resume_text[:3000]}  # limit for long resumes

Assessment Answers:
{user_answers_str}

Output strict JSON like this:
{{
  "gemini_score": 85.5,
  "assessment_score": 86.7,
  "reasoning": "Strong alignment with qualifications and good answers."
}}
"""
    ]
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
        print(min_assessment_score)
        if ( assessment_score < min_assessment_score):
            print("deleteign it ")
            db.session.delete(application) # Delete application if assessment score is below minimum
            db.session.commit()
        # assessment_reasoning = gemini_output.get('reasoning', 'No specific reasoning provided.')

    except Exception as e:
        print(f"Error calling Gemini API for assessment scoring or parsing response: {e}")
        eligibilty_score = 0.0 # Default score if AI call fails
        # assessment_reasoning = f"AI assessment scoring failed: {e}"

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
