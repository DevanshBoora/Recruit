# my_tiny_app/routes/admin.py
from flask import Blueprint,render_template

# Create a blueprint for admin routes
# THIS LINE IS CRUCIAL FOR 'admin_bp' TO EXIST
admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/')
def admin_home():
    # This route will be accessible at /admin/
   return render_template('main_page.html')

@admin_bp.route('/users')
def admin_users():
    # This route will be accessible at /admin/users
    return "<h1>Admin Users Management!</h1>"