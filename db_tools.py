# db_tools.py (ADD THIS NEW FUNCTION)
from models import db, Job, Application, Conversation, Message # Ensure all models are imported if needed elsewhere
from sqlalchemy import func
import logging
from datetime import datetime # Import datetime for default posted_at
from fuzzywuzzy import fuzz # Import for fuzzy matching

# Configure logging for db_tools
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Tool 1: Get Applicant Information by Name or Email ---
def get_applicant_info(applicant_identifier: str = None, applicant_email: str = None):
    
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

# --- Tool 5: Create Job Posting ---
def create_job_posting(
    title: str,
    description: str,
    qualifications: str,
    responsibilities: str,
    job_type: str,
    location: str,
    required_experience: str,
    assessment_timer: int = 0,
    assessment_questions: str = None,
    min_assesment_score: int = 0
):
    """
    Creates a new job posting in the database.
    This tool should be used when the user provides a full job description
    and expresses intent to 'post', 'create', or 'add' a new job.

    Args:
        title (str): The title of the job.
        description (str): A detailed description of the job.
        qualifications (str): The required qualifications for the job.
        responsibilities (str): The key responsibilities of the role.
        job_type (str): The type of employment (e.g., 'full-time', 'part-time', 'contract').
        location (str): The geographical location of the job (e.g., 'Hyderabad', 'Remote').
        required_experience (str): The required experience level (e.g., '2-4 years', 'Entry-level').
        assessment_timer (int, optional): Timer for the assessment in minutes. Defaults to 0.
        assessment_questions (str, optional): JSON string of assessment questions. Defaults to None.
        min_assesment_score (int, optional): Minimum score for the assessment. Defaults to 0.

    Returns:
        dict: A dictionary indicating success or failure, and the job title if successful.
              Returns {'status': 'success', 'job_title': title} or {'status': 'error', 'message': '...'}.
    """
    logger.info(f"Tool call: create_job_posting(title='{title}', job_type='{job_type}', location='{location}', ...)")
    
    try:
        new_job = Job(
            title=title,
            description=description,
            qualifications=qualifications,
            responsibilities=responsibilities,
            job_type=job_type,
            location=location,
            required_experience=required_experience,
            posted_at=datetime.utcnow(), # Ensure datetime is used for default
            assessment_timer=assessment_timer,
            assessment_questions=assessment_questions,
            min_assesment_score=min_assesment_score
        )
        db.session.add(new_job)
        db.session.commit()
        logger.info(f"Successfully created new job posting: {title}")
        return {"status": "success", "job_id": new_job.id, "job_title": title}
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create job posting '{title}': {e}")
        return {"status": "error", "message": str(e)}

# --- NEW TOOL: Open Specific Web Page ---
def open_web_page(name: str):
    """
    Opens a specific web page in the current browser tab based on a given page name.
    Uses fuzzy matching to identify the page.

    Args:
        name (str): The name or partial name of the page to open (e.g., 'application', 'job').

    Returns:
        dict: A dictionary indicating success or failure and the URL to open.
              Returns {'status': 'success', 'url': '...', 'message': 'Opening ...'}
              or {'status': 'error', 'message': 'Page not found.'}.
    """
    logger.info(f"Tool call: open_web_page(name='{name}')")

    # Define your dictionary of page names and URLs
    page_urls = {
        "application page": "https://spryple.com/careers/apply",
        "job page": "https://spryple.com/careers/jobs",
        # Add more pages as needed
        "home page": "https://spryple.com/",
        "contact us": "https://spryple.com/contact"
    }

    best_match_name = None
    highest_score = 0
    FUZZY_MATCH_THRESHOLD = 75 # Adjust this threshold as needed (0-100)

    for page_name, url in page_urls.items():
        score = fuzz.ratio(name.lower(), page_name.lower())
        if score > highest_score and score >= FUZZY_MATCH_THRESHOLD:
            highest_score = score
            best_match_name = page_name

    if best_match_name:
        url_to_open = page_urls[best_match_name]
        message = f"Opening the {best_match_name} for you."
        logger.info(f"Successfully matched '{name}' to '{best_match_name}'. Opening URL: {url_to_open}")
        return {"status": "success", "url": url_to_open, "message": message}
    else:
        message = f"Sorry, I couldn't find a page matching '{name}'. Please try a different name."
        logger.warning(f"No page found matching '{name}' with fuzzy threshold {FUZZY_MATCH_THRESHOLD}.")
        return {"status": "error", "message": message}

# You can add more tools here as needed, e.g.:
# - update_applicant_status(applicant_email, new_status)
# - get_job_applicants(job_title)