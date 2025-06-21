# my_tiny_app/routes/general.py
from flask import Blueprint,render_template

# Create a blueprint for general routes
user_bp = Blueprint('user_bp', __name__)

@user_bp.route('/')
def home():
    return render_template('users/userHome.html')
