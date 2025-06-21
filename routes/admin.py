# my_tiny_app/routes/admin.py
from flask import Blueprint,render_template,request,jsonify,url_for,session,json
from models import Application, Slot, db,Job,Company,User
from email_utils import send_email
# Create a blueprint for admin routes
# THIS LINE IS CRUCIAL FOR 'admin_bp' TO EXIST
admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/applications' ,methods=['POST', 'GET'])
def admin_applications():
    if request.method == 'POST':
        if 'company_name' not in session:
            return jsonify({"message": "Unauthorized access. Please log in."}), 403
        
        name_filter = session.get('company_name')
        applications_query = Application.query
        print(name_filter)
        if name_filter is None:
            return jsonify([]), 200
        if name_filter:
            applications_query = applications_query.join(Application.job).filter(Job.title.ilike(f'%{name_filter}%'))


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
    return render_template('admins/adminviewapplication.html')

@admin_bp.route('/job')
def admin():
    return render_template("admins/job.html")

@admin_bp.route('/slots',methods=['POST', 'GET'])
def admin_slots():
    if request.method == 'GET':
        if 'company_name' not in session:
            return jsonify({"message": "Unauthorized access. Please log in."}), 403
        company_name= session.get('company_name')
        
        if not company_name:
            return jsonify({"message": "company not found"}), 404

        slots_query = Slot.query.filter_by(is_booked=False).order_by(Slot.interview_time)

        # Filter slots based on the logged-in user's company (if they have one)
        slots_query = slots_query.filter_by(company_name=company_name)

        available_slots = slots_query.all()
        
        # You might want to filter by job title/role as well if the user has a specific job they are hiring for
        # Example: If `user` has an associated job they are managing. This would depend on your user-job relationship.
        
        return render_template('admins/adminviewslots.html', slots=available_slots) 



@admin_bp.route('/register', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        password = "thub123@"
        company_name = session.get('company_name')
        role = data.get('role') 
        position = data.get('position')
        company =  Company.query.filter_by(company_name=company_name).first()
        if not name or not password:
            return jsonify({"message": "Name and password are required"}), 400

        existing_user = User.query.filter_by(name=name).first()
        if existing_user:
            return jsonify({"message": "Username already exists"}), 409

        new_user = User(name=name, email=email ,password=password, company_name=company_name, role=role,position=position)
        db.session.add(new_user)
        subject = f"Your New Account Credentials for {company_name}"

        body = f"""Dear {name},

        Welcome to {company_name}! Your account has been successfully created.

        Here are your temporary login credentials:

        * Username: {name}
        * Temporary Password: {password}

        Important Security Notice:
        For your security, please log in immediately and change your password.

        Steps to get started:
        1. Click on the following link to log in: http://127.0.0.1:5000/login
        2. Enter your Username and Temporary Password provided above.
        3. You will be prompted to create a new, strong password. Please choose a password that is unique and difficult to guess.
        4. Once logged in, you can [mention next steps, e.g., "explore your dashboard," "complete your profile"].

        If you have any questions or encounter any issues, please do not hesitate to contact our support team at [Support Email Address] or [Support Phone Number].

        Thank you,

        The Team at {company_name}
        http://127.0.0.1:5000
        """
        send_email(email,subject , body)
        try:
            db.session.commit()
            return jsonify({"message": "User registered successfully!", "user": new_user.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Error registering user: {str(e)}"}), 500
    return render_template('admins/register.html')


@admin_bp.route('/fetch/jobs', methods=['POST'])
def fetch_job():
        company_name= session.get('company_name')
        if company_name:
            jobs = Job.query.filter_by(title=company_name).all()
        else:
            return jsonify([])
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

    