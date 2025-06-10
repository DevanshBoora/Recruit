# my_tiny_app/routes/general.py
from flask import Blueprint,render_template

# Create a blueprint for general routes
general_bp = Blueprint('general_bp', __name__)

@general_bp.route('/')
def home():
    return render_template('main_page.html')

@general_bp.route('/apply.html')
def apply_page():
    return render_template('apply.html')

@general_bp.route('/view_applications.html')
def view_applications_page():
    return render_template('view_applications.html')


@general_bp.route('/chat')
def chat_page():
    # This renders the HTML page for the chat interface
    return render_template('chat.html')