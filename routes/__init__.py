
from .admin import admin_bp
from .general import general_bp
from .jobs import job_bp
from .submissions import submit_bp

def register_blueprints(app):
    
    app.register_blueprint(general_bp)  # Routes here will be accessible without a prefix
    app.register_blueprint(admin_bp, url_prefix='/admin') # Routes here will be prefixed with /admin
    app.register_blueprint(job_bp, url_prefix='/jobs')  # Routes here will be prefixed with /jobs
    app.register_blueprint(submit_bp, url_prefix='/submit')  # Routes here will be prefixed with /submit

    
    
    