# my_tiny_app/routes/general.py
from flask import Blueprint,render_template,session,jsonify
from models import Application,db
from sqlalchemy.orm import selectinload
from sqlalchemy import desc

# Create a blueprint for general routes
user_bp = Blueprint('user_bp', __name__)

@user_bp.route('/')
def home():
    return render_template('users/userHome.html')


@user_bp.route('/applications', methods=['GET'])
def get_user_applications():
    """
    API endpoint to retrieve all job applications for the logged-in user.
    It fetches related job, interview, feedback, and job offer data.
    """
    user_email = session.get('candidate_email')
    user_name = session.get('candidate_name')

    if not user_email:
        # If no user is logged in, return an error. Frontend should redirect to login.
        return jsonify({'message': 'Unauthorized: Please log in to view applications.'}), 401
    
    try:
        # Query applications for the logged-in user's email (more reliable than name)
        # Use `selectinload` for better performance with one-to-many relationships
        applications = Application.query.filter_by(applicant_email=user_email).options(
            selectinload(Application.job),
            selectinload(Application.interview_schedule),
            selectinload(Application.job_offer)  # Correct relationship name from your model
        ).order_by(desc(Application.applied_at)).all()

        applications_data = []
        for app in applications:
            app_dict = app.to_dict()
            
            # Add job title
            app_dict['job_title'] = app.job.title if app.job else 'N/A'
            
            # Add interview details
            if app.interview_schedule:
                app_dict['interview_details'] = [schedule.to_dict() for schedule in app.interview_schedule]
            else:
                app_dict['interview_details'] = []
            
            
            # Add job offer details
            if app.job_offer:  # Correct relationship name from your model
                app_dict['job_offer_details'] = [offer.to_dict() for offer in app.job_offer]
            else:
                app_dict['job_offer_details'] = []
                
            applications_data.append(app_dict)

        return jsonify({
            'applications': applications_data, 
            'user_name': user_name,
            'total_applications': len(applications_data)
        }), 200
        
    except Exception as e:
        # Log the error for debugging
        print(f"Error fetching applications: {str(e)}")
        return jsonify({'message': 'Error fetching applications. Please try again later.'}), 500


@user_bp.route('/myapp')
def fetchi():
    return render_template('users/userapplication.html')