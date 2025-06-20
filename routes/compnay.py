# my_tiny_app/routes/admin.py
from flask import Blueprint,render_template,request,jsonify,url_for,session
from models import Company, db

# Create a blueprint for admin routes
# THIS LINE IS CRUCIAL FOR 'admin_bp' TO EXIST
company_bp = Blueprint('company_bp', __name__)

@company_bp.route('/')
def company_home():
    # This route will be accessible at /company/
    return render_template('register_company.html')

@company_bp.route('/register_company', methods=['GET', 'POST'])
def register_company():
    if request.method == 'POST':
        data = request.get_json() # Expecting JSON from the frontend

        company_name = data.get('company_name')
        password = data.get('password')

        if not company_name or not password:
            return jsonify({"message": "Company name and password are required."}), 400

        # Check if company already exists
        existing_company = Company.query.filter_by(company_name=company_name).first()
        if existing_company:
            return jsonify({"message": "Company name already registered. Please choose another."}), 409 # Conflict

        try:
            new_company = Company(company_name=company_name, password=password)
            db.session.add(new_company)
            db.session.commit()
            return jsonify({"message": "Company registered successfully!"}), 201 # Created
        except Exception as e:
            db.session.rollback()
            print(f"Error registering company: {e}")
            return jsonify({"message": "An error occurred during registration. Please try again."}), 500

    return render_template('register_company.html')

@company_bp.route('/company_login', methods=['GET', 'POST'])
def company_login():
    if request.method == 'POST':
        data = request.get_json()
        company_name = data.get('company_name')
        password = data.get('password')

        if not company_name or not password:
            return jsonify({"message": "Company name and password are required."}), 400

        company = Company.query.filter_by(company_name=company_name).first()

        if not company or not company.check_password(password):
            return jsonify({"message": "Invalid company name or password."}), 401

        # Log the company in
        session['company_id'] = company.id
        session['company_name'] = company.company_name
        session['company_logged_in'] = True
        
        return jsonify({"message": "Logged in successfully!", "redirect_url": url_for('view_slots')}) # Redirect to view slots or company dashboard

    return render_template('company_login.html') # You'll need to create this HTML too