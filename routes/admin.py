# my_tiny_app/routes/admin.py
from flask import Blueprint,render_template,request,jsonify,url_for,session,json
from models import Application, Slot, db,Job,Company,User,AcceptedCandidate,Feedback,JobOffer
from email_utils import send_email
from datetime import datetime , timezone
from sqlalchemy import desc
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
        1. Click on the following link to log in: http://localhost:5000/login
        2. Enter your Username and Temporary Password provided above.
        3. You will be prompted to create a new, strong password. Please choose a password that is unique and difficult to guess.
        4. Once logged in, you can [mention next steps, e.g., "explore your dashboard," "complete your profile"].

        If you have any questions or encounter any issues, please do not hesitate to contact our support team at [Support Email Address] or [Support Phone Number].

        Thank you,

        The Team at {company_name}
        http://localhost:5000
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

@admin_bp.route('/offer',methods=['GET','POST','PUT'])
def offer():
    if request.method =='POST':
        data = request.get_json()
        company_name = session.get('company_name')
        company_role = data['job_role']

        if not company_name or not company_role:
            return jsonify({'error': 'Company name and role not found in session. Please log in or set session variables.'}), 400


        job_entry = Job.query.filter_by(title=company_name, responsibilities=company_role).first()

        if not job_entry:
            return jsonify({'error': f'Job entry not found for company: {company_name}, role: {company_role}'}), 404

        number_of_available_jobs = job_entry.number_of_positions
        if number_of_available_jobs <= 0:
            return jsonify({'message': 'No available jobs for this role at this company.'}), 200

        accepted_candidates = AcceptedCandidate.query.filter_by(
            company_name=company_name,
            company_role=company_role
        ).all()

        if not accepted_candidates:
            return jsonify({'message': 'No accepted candidates found for this company and role.'}), 200

        accepted_candidate_ids = [ac.candidate_id for ac in accepted_candidates]

        eligible_candidates_feedback = Feedback.query.filter(
            Feedback.candidate_id.in_(accepted_candidate_ids),
            Feedback.decision == 'Accepted'
        ).order_by(
            desc(Feedback.communication_score),
            desc(Feedback.technical_score),
            desc(Feedback.problem_solving_score)
        ).all()

        candidates_to_offer = eligible_candidates_feedback[:number_of_available_jobs]

        if not candidates_to_offer:
            return jsonify({'message': 'No eligible candidates with feedback found to send offers to.'}), 200
        
        candidate_ids_to_delete_from_accepted = []
        offers_sent_count = 0
        for feedback_entry in candidates_to_offer:
            existing_offer = JobOffer.query.filter_by(application_id=feedback_entry.candidate_id, company_name=company_name, company_role=company_role).first()
            if existing_offer:
                print(f"Offer already exists for candidate {feedback_entry.candidate_id} for {company_name} - {company_role}. Skipping.")
                continue

            # Create a new JobOffer entry
            new_offer = JobOffer(
                application_id=feedback_entry.candidate_id,
                status='Pending',
                offer_sent=True,
                offer_sent_time=datetime.now(timezone.utc),
                company_name=company_name,
                company_role=company_role
            )
            db.session.add(new_offer)
            offers_sent_count += 1
            candidate_ids_to_delete_from_accepted.append(feedback_entry.candidate_id)

            # Simulate sending an email
            # In a real application, you would integrate with an email service here
            candidate_app = Application.query.get(feedback_entry.candidate_id)
            if candidate_app:
                print(f"Simulating offer letter sent to: {candidate_app.applicant_name} ({candidate_app.applicant_email}) for {company_role} at {company_name}")
            else:
                print(f"Simulating offer letter sent to candidate ID: {feedback_entry.candidate_id} for {company_role} at {company_name}")



        if candidate_ids_to_delete_from_accepted:
            # Filter AcceptedCandidate entries by candidate_id, company_name, and company_role
            # This ensures we only delete the specific entries related to this offer batch for this role/company
            AcceptedCandidate.query.filter(
                AcceptedCandidate.candidate_id.in_(candidate_ids_to_delete_from_accepted),
                AcceptedCandidate.company_name == company_name,
                AcceptedCandidate.company_role == company_role
            ).delete(synchronize_session='fetch')
            print(f"Deleted {len(candidate_ids_to_delete_from_accepted)} accepted candidate entries from the database.")

            updated_applications_count = Application.query.filter(
                    Application.id.in_(candidate_ids_to_delete_from_accepted)
                ).update(
                    {'status': 'offerExtended'},
                    synchronize_session=False # Important for bulk updates
                )
        db.session.commit()

        if offers_sent_count > 0:
            return jsonify({'message': f'{offers_sent_count} offer letters successfully sent to the top candidates.'}), 200
        else:
            return jsonify({'message': 'No new offer letters were sent.'}), 200
    if request.method =='PUT':
        data = request.get_json()
        application_id = data.get('applicationId')
        status = data.get('status') 

        if not application_id or not status:
            return jsonify({'error': 'Missing application_id or status in request body.','sucess':False}), 400

        # Find the job offer
        job_offer = JobOffer.query.filter_by(application_id=application_id).first()

        if not job_offer:
            return jsonify({'error': f'Job offer not found for application ID: {application_id}','success':False}), 404

        company_name = job_offer.company_name
        company_role = job_offer.company_role

        if status == 'Accepted':
            # Update offer status to accepted
            job_offer.status = 'Accepted'
            db.session.add(job_offer) # Mark for update

            # Find the job entry to decrement available jobs
            job_entry = Job.query.filter_by(title=company_name, responsibilities=company_role).first()

            updated_applications_count = Application.query.filter_by(id=application_id).update(
                    {'status': 'OfferAccepted'}, # Ensure this status string is correct
                    synchronize_session=False # Important for bulk/direct updates
                )

            if job_entry:
                if job_entry.number_of_positions > 0:
                    job_entry.number_of_positions -= 1
                    db.session.add(job_entry) # Mark for update
                    print(f"Decremented available jobs for {company_role} at {company_name}. New count: {job_entry.number_of_positions}")
                else:
                    print(f"Warning: Available jobs for {company_role} at {company_name} is already 0.")

                # If available jobs become 0, delete all remaining accepted candidates for this role
                if job_entry.number_of_positions == 0:

                    all_accepted_candidates_for_job_ids = [
                        ac.candidate_id for ac in AcceptedCandidate.query.filter_by(
                            company_name=company_name,
                            company_role=company_role
                        ).all()
                    ]

                    deleted_count = AcceptedCandidate.query.filter_by(
                        company_name=company_name,
                        company_role=company_role
                    ).delete(synchronize_session='fetch')
                    print(f"Deleted {deleted_count} accepted candidates for {company_role} at {company_name} as jobs are filled.")

                    updated_applications_count = Application.query.filter(
                        Application.id.in_(all_accepted_candidates_for_job_ids)
                    ).update(
                        {'status': 'Rejected'},
                        synchronize_session=False # Important for bulk updates
                    )
            else:
                print(f"Warning: Job entry not found for {company_name}, {company_role}. Cannot decrement available jobs.")

            db.session.commit()
            return jsonify({'message': f'Offer for application {application_id} accepted. Available jobs updated.','success':True}), 200

        elif status == 'Declined':
            # Update offer status to declined
            job_offer.status = 'Declined'
            db.session.add(job_offer) # Mark for update

            accepted_candidates_for_role = AcceptedCandidate.query.filter_by(
                company_name=company_name,
                company_role=company_role
            ).all()

            updated_applications_count = Application.query.filter_by(id=application_id).update(
                    {'status': 'OfferDeclined'}, # Ensure this status string is correct
                    synchronize_session=False # Important for bulk/direct updates
                )
            if not accepted_candidates_for_role:
                db.session.commit()
                return jsonify({'message': f'Offer for application {application_id} declined. No more accepted candidates for {company_role} at {company_name} to send new offers.'}), 200

            # Get a list of candidate_ids from the accepted candidates for this role
            accepted_candidate_ids_for_role = [ac.candidate_id for ac in accepted_candidates_for_role]

            # Find candidates who HAVE NOT YET received a pending/accepted offer for this specific role/company
            # This prevents resending offers to someone who already has one or accepted one.
            candidates_with_existing_offers = db.session.query(JobOffer.application_id).filter(
                JobOffer.company_name == company_name,
                JobOffer.company_role == company_role,
                JobOffer.status.in_(['Pending', 'accepted'])
            ).all()

            candidates_with_existing_offers_ids = [res[0] for res in candidates_with_existing_offers]

            # Filter and order candidates by feedback scores, excluding those who already have an offer
            eligible_candidates_feedback = Feedback.query.filter(
                Feedback.candidate_id.in_(accepted_candidate_ids_for_role),
                Feedback.decision == 'Accepted', # Ensure they are marked as accepted in feedback
                ~Feedback.candidate_id.in_(candidates_with_existing_offers_ids) # Exclude those already offered
            ).order_by(
                desc(Feedback.communication_score),
                desc(Feedback.technical_score),
                desc(Feedback.problem_solving_score)
            ).first() # Get only the top 1 next candidate

            if eligible_candidates_feedback:
                new_offer = JobOffer(
                    application_id=eligible_candidates_feedback.candidate_id,
                    status='Pending',
                    offer_sent=True,
                    offer_sent_time=datetime.now(timezone.utc),
                    company_name=company_name,
                    company_role=company_role
                )
                db.session.add(new_offer)

                candidate_app = Application.query.get(eligible_candidates_feedback.candidate_id)
                if candidate_app:
                    print(f"Simulating new offer letter sent to: {candidate_app.applicant_name} ({candidate_app.applicant_email}) for {company_role} at {company_name} due to a decline.")
                else:
                    print(f"Simulating new offer letter sent to candidate ID: {eligible_candidates_feedback.candidate_id} for {company_role} at {company_name} due to a decline.")

                # Delete this candidate from AcceptedCandidate (as their offer has been processed/sent)
                AcceptedCandidate.query.filter_by(
                    candidate_id=eligible_candidates_feedback.candidate_id,
                    company_name=company_name,
                    company_role=company_role
                ).delete(synchronize_session='fetch')
                print(f"Deleted accepted candidate entry for {eligible_candidates_feedback.candidate_id} after sending new offer.")

                db.session.commit()
                return jsonify({'message': f'Offer for application {application_id} declined. New offer sent to next eligible candidate.','success':True}), 200
            else:
                db.session.commit()
                return jsonify({'message': f'Offer for application {application_id} declined. No more eligible candidates to send new offers for {company_role} at {company_name}.','success':True}), 200

        else:
            return jsonify({'error': 'Invalid status provided. Must be "accepted" or "declined".'}), 400
    return render_template('admins/sendOffer.html')





@admin_bp.route('/jobs', methods=['GET'])
def get_jobs_for_admin():
    print("came here")
    company_name = session.get('company_name')

    if not company_name:
        return jsonify({'error': 'company_name is required'}), 400

    # 🔍 Filter by company_name, then select distinct job titles
    jobs = Job.query.filter_by(title=company_name).with_entities(Job.responsibilities).distinct().all()
    job_titles = [job.responsibilities for job in jobs]

    return jsonify({'job_roles': job_titles}), 200

    