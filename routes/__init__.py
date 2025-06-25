
from .admin import admin_bp
from .general import general_bp
from .jobs import job_bp
from .submissions import submit_bp
from .chat import chat_bp
from .compnay import company_bp
from .users import user_bp

def register_blueprints(app):
    
    app.register_blueprint(general_bp)  # Routes here will be accessible without a prefix
    app.register_blueprint(admin_bp, url_prefix='/admin') # Routes here will be prefixed with /admin
    app.register_blueprint(job_bp, url_prefix='/jobs')  # Routes here will be prefixed with /jobs
    app.register_blueprint(submit_bp, url_prefix='/submit')  # Routes here will be prefixed with /submit
    app.register_blueprint(chat_bp, url_prefix='/api/chat')  # Routes here will be prefixed with /chat
    app.register_blueprint(company_bp, url_prefix='/auth')  # Routes here will be prefixed with /company
    app.register_blueprint(user_bp, url_prefix='/user')
    
    
    