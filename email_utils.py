import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Replace with your SMTP email credentials
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_ADDRESS = "damarlasaicharan0305@gmail.com"  # Change this
EMAIL_PASSWORD = "hvwa pprb uqer gfvx"  # Use app password

def send_schedule_email(to_email, interview_datetime, mode, interviewer, meeting_link=None, address=None, is_interviewer=False):
    subject = "Interview Scheduled"
    if is_interviewer:
        body = f"Dear {interviewer},\n\nAn interview has been scheduled.\n\n"
    else:
        body = f"Dear Candidate,\n\nYour interview has been scheduled.\n\n"

    body += f"🗓 Date & Time: {interview_datetime}\n"
    body += f"👤 Interviewer: {interviewer}\n"
    body += f"💼 Mode: {mode}\n"

    if mode == "Virtual":
        body += f"🔗 Meeting Link: {meeting_link}\n"
    else:
        body += f"📍 Address: {address}\n"

    body += "\nPlease be on time and prepare accordingly.\n\nBest regards,\nRecruitment Team"

    send_email(to_email, subject, body)

def send_rejection_email(to_email, name, summary):
    subject = "Application Status Update"
    body = f"""
Dear {name},

Thank you for taking the time to attend the interview.

After careful consideration, we regret to inform you that you have not been selected for the position at this time.

🔍 Interview Summary:
{summary}

We truly appreciate your interest and effort. We encourage you to apply for future opportunities with us.

Best wishes for your career ahead.

Sincerely,  
Recruitment Team
"""
    send_email(to_email, subject, body)

def send_reminder_email(to_email, interview_datetime, recipient_name, mode, meeting_link=None, address=None, is_interviewer=False):
    subject = "Interview Reminder"
    if is_interviewer:
        greeting = f"Dear {recipient_name},\n\nThis is a reminder that you have an upcoming interview scheduled.\n\n"
    else:
        greeting = f"Dear {recipient_name},\n\nThis is a reminder about your upcoming interview.\n\n"

    body = greeting
    body += f"🗓 Date & Time: {interview_datetime}\n"
    body += f"💼 Mode: {mode}\n"

    if mode == "Virtual":
        body += f"🔗 Meeting Link: {meeting_link}\n"
    else:
        body += f"📍 Address: {address}\n"

    body += "\nPlease be prepared and join on time.\n\nBest regards,\nRecruitment Team"

    send_email(to_email, subject, body)
    
    
def send_initial_rejection_email(to_email, name):
    subject = "Application Update - Not Shortlisted"
    body = f"""
Dear {name},

Thank you for your interest in the position at our company.

After carefully reviewing your application, we regret to inform you that you have not been shortlisted for the next stage of the selection process.

This decision was based on various factors including alignment with our current requirements.

We appreciate the time and effort you invested in your application and wish you all the best in your future endeavors.

Sincerely,  
Recruitment Team
"""
    send_email(to_email, subject, body)

def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        print(f"✅ Email sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")
