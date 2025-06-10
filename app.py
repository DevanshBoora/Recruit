from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import os
import google.generativeai as genai
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from routes import register_blueprints
from models import db,Job,Application


app = Flask(__name__)
CORS(app)
register_blueprints(app)

# --- Configuration for Upload Folder ---
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/JobApplications'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


with app.app_context():
    db.create_all()


load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")
genai.configure(api_key=GEMINI_API_KEY)


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