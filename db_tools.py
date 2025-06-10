# db_tools.py
from models import db, Job, Application
from sqlalchemy import func
import logging

# Configure logging for db_tools
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Tool 1: Get Applicant Information by Name or Email ---
def get_applicant_info(applicant_identifier: str = None, applicant_email: str = None):
    """
    Retrieves detailed information about an applicant by their name or email.
    Use fuzzy matching for names and exact matching for emails.

    Args:
        applicant_identifier (str): The name or partial name of the applicant.
        applicant_email (str): The exact email of the applicant.

    Returns:
        list[dict]: A list of dictionaries, each containing details of a matching applicant.
                    Returns an empty list if no applicant is found.
    """
    logger.info(f"Tool call: get_applicant_info(identifier='{applicant_identifier}', email='{applicant_email}')")
    
    query = Application.query

    if applicant_email:
        # Exact match for email (case-insensitive)
        query = query.filter(func.lower(Application.applicant_email) == func.lower(applicant_email))
    elif applicant_identifier:
        # Fuzzy match for name (case-insensitive, contains)
        # Using func.lower() for case-insensitive comparison with LIKE
        query = query.filter(func.lower(Application.applicant_name).like(f"%{applicant_identifier.lower()}%"))
    else:
        logger.warning("get_applicant_info called without a valid identifier or email.")
        return []

    applicants = query.limit(5).all() # Limit results to prevent overwhelming Gemini

    if not applicants:
        logger.info("No applicants found for the given identifier/email.")
        return []

    # Convert results to dictionaries
    results = [app.to_dict() for app in applicants]
    logger.info(f"Found {len(results)} applicants.")
    return results

# --- Tool 2: Get Job Details by Title ---
def get_job_details(job_title: str):
    """
    Retrieves detailed information about a job posting by its title.
    Uses fuzzy matching (case-insensitive, contains).

    Args:
        job_title (str): The title or partial title of the job.

    Returns:
        list[dict]: A list of dictionaries, each containing details of a matching job.
                    Returns an empty list if no job is found.
    """
    logger.info(f"Tool call: get_job_details(title='{job_title}')")
    
    # Fuzzy match for job title
    jobs = Job.query.filter(func.lower(Job.title).like(f"%{job_title.lower()}%")).limit(5).all()

    if not jobs:
        logger.info("No jobs found for the given title.")
        return []

    results = [job.to_dict() for job in jobs]
    logger.info(f"Found {len(results)} jobs.")
    return results

# --- Tool 3: Get Jobs by Type (e.g., 'full-time', 'part-time') ---
def get_jobs_by_type(job_type: str):
    """
    Retrieves a list of job titles and locations based on the job type.
    Uses fuzzy matching (case-insensitive, contains).

    Args:
        job_type (str): The type of job (e.g., 'full-time', 'contract').

    Returns:
        list[dict]: A list of dictionaries, each with 'title' and 'location' of matching jobs.
                    Returns an empty list if no jobs of that type are found.
    """
    logger.info(f"Tool call: get_jobs_by_type(type='{job_type}')")
    
    jobs = Job.query.filter(func.lower(Job.job_type).like(f"%{job_type.lower()}%")).limit(10).all()

    if not jobs:
        logger.info("No jobs found for the given type.")
        return []

    results = [{'title': job.title, 'location': job.location} for job in jobs]
    logger.info(f"Found {len(results)} jobs of type '{job_type}'.")
    return results

# --- Tool 4: Get Applications by Status (e.g., 'Pending', 'Approved', 'Rejected') ---
def get_applications_by_status(status: str):
    """
    Retrieves a list of applicants and their applied job titles based on application status.
    Uses fuzzy matching (case-insensitive, contains).

    Args:
        status (str): The status of the application (e.g., 'Pending', 'Approved').

    Returns:
        list[dict]: A list of dictionaries, each with 'applicant_name', 'job_title', and 'status'.
                    Returns an empty list if no applications with that status are found.
    """
    logger.info(f"Tool call: get_applications_by_status(status='{status}')")
    
    # Join with Job table to get job title
    applications = db.session.query(Application, Job).join(Job).filter(
        func.lower(Application.status).like(f"%{status.lower()}%")
    ).limit(10).all()

    if not applications:
        logger.info("No applications found for the given status.")
        return []

    results = [{'applicant_name': app.applicant_name, 'job_title': job.title, 'status': app.status} for app, job in applications]
    logger.info(f"Found {len(results)} applications with status '{status}'.")
    return results

# You can add more tools here as needed, e.g.:
# - create_job_posting(title, description, ...)
# - update_applicant_status(applicant_email, new_status)
# - get_job_applicants(job_title)