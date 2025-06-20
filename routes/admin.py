# my_tiny_app/routes/admin.py
from flask import Blueprint,render_template,request,jsonify,url_for,session
from models import Application, Slot, db,Job

# Create a blueprint for admin routes
# THIS LINE IS CRUCIAL FOR 'admin_bp' TO EXIST
admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/applications' ,methods=['POST', 'GET'])
def admin_applications():
    if request.method == 'POST':
        if 'company_name' not in session:
            return jsonify({"message": "Unauthorized access. Please log in."}), 403

        
        
        name_filter = session.get('company_filter', None)
        applications_query = Application.query


        if name_filter:
            applications_query = applications_query.filter(Job.title.ilike(f'%{name_filter}%'))


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
