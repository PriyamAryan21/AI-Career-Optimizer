import re
import smtplib
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
import os
from pathlib import Path

from config.settings import SMTP_HOST, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD, load_master_profile
from database.models import _get_connection, log_action
from core.resume_generator import generate_resume_pdf

def extract_emails(text: str) -> list[str]:
    """Extract all email addresses from a given text."""
    if not text:
        return []
    # Basic email regex
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(email_pattern, text)))

def generate_jd_specific_resume(job_title: str, company: str, job_skills: list) -> str:
    """
    Programmatically tailors the resume without using AI tokens.
    Modifies the summary and pushes matching skills to the front.
    """
    profile = load_master_profile()
    
    # Create a custom summary for this specific job
    original_summary = profile.get("personal", {}).get("summary", "")
    custom_summary = (
        f"Highly motivated professional actively seeking the {job_title} position at {company}. "
        f"{original_summary}"
    )
    
    # Create an optimized content dictionary to override the master profile
    optimized_content = {
        "summary": {"rewritten": custom_summary},
        "keywords_used": job_skills[:5]  # log top 5 skills
    }
    
    # We could also reorder skills here if we wanted to build a custom HTML,
    # but for programmatic speed, updating the summary and generating the PDF is highly effective.
    
    pdf_path = generate_resume_pdf(optimized_content)
    return pdf_path

def draft_email(job_title: str, company: str, profile: dict, job_skills: list) -> str:
    """
    Draft a customized cover letter email programmatically.
    """
    name = profile.get("personal", {}).get("name", "Applicant")
    
    skills_text = ""
    if job_skills:
        top_skills = [s.strip() for s in job_skills[:3] if s.strip()]
        if top_skills:
            skills_text = f" My background in {', '.join(top_skills)} aligns perfectly with the requirements for this role."

    body = f"""Dear Hiring Manager,

I am writing to express my strong interest in the {job_title} position at {company}. 

As a dedicated professional with a passion for building high-quality solutions, I am excited about the opportunity to contribute to your team.{skills_text}

I have attached my resume for your review, which further details my experience and technical projects. I would welcome the opportunity to discuss how my skills and drive would be a great fit for {company}.

Thank you for your time and consideration.

Best regards,
{name}
"""
    return body

def send_application_email(to_email: str, subject: str, body_text: str, attachment_path: str) -> bool:
    """Send an email with the PDF attachment."""
    if not all([SMTP_EMAIL, SMTP_PASSWORD, SMTP_HOST]):
        print("⚠️ Email credentials not configured.")
        return False

    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body_text, 'plain'))

    # Attach PDF
    try:
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
            msg.attach(part)
    except Exception as e:
        print(f"❌ Failed to attach resume {attachment_path}: {e}")
        return False

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")
        return False

def run_auto_apply_cycle():
    """
    Scans the database for jobs with emails, tailors the resume, and sends the application.
    """
    print("=" * 60)
    print("  🚀 Starting Programmatic Auto-Apply Cycle")
    print("=" * 60)
    
    conn = _get_connection()
    cur = conn.cursor()
    
    # In a real scenario, you'd fetch jobs that haven't been applied to yet.
    # We only want to process jobs from our verified_email_jobs pool
    cur.execute("SELECT id, title, company, verified_email, description FROM verified_email_jobs WHERE status = 'pending' ORDER BY created_at DESC")
    jobs = cur.fetchall()
    
    profile = load_master_profile()
    applied_count = 0
    
    for job in jobs:
        job_id, title, company, target_email, description = job
        
        # 1. Global Recruiter Cooldown Check (Prevents emailing the same HR for slightly different job posts)
        from datetime import datetime, timedelta
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "SELECT id FROM verified_email_jobs WHERE verified_email = %s AND status = 'applied' AND created_at >= %s", 
            (target_email, thirty_days_ago)
        )
        if cur.fetchone():
            print(f"   ⏭️ Skipping {target_email} - Already applied to this recruiter in the last 30 days.")
            continue
            
        print(f"\n💼 Found verified target: {title} @ {company} -> {target_email}")
        
        # 2. Extract skills from description if present, else just use a generic list
        job_skills = []
        if "Skills needed:" in description:
            try:
                raw_skills = description.split("Skills needed:")[1].split("|")[0]
                job_skills = [s.strip() for s in raw_skills.split(",")]
            except:
                pass
        
        # 3. Generate tailored resume
        print("   -> Generating tailored resume...")
        pdf_path = generate_jd_specific_resume(title, company, job_skills)
        
        # 4. Draft email
        subject = f"Application for {title} - {profile.get('personal', {}).get('name', '')}"
        body = draft_email(title, company, profile, job_skills)
        
        # 5. Send Email
        print(f"   -> Sending application email to {target_email}...")
        success = send_application_email(target_email, subject, body, pdf_path)
        
        if success:
            print("   ✅ Application sent successfully!")
            cur.execute("UPDATE verified_email_jobs SET status = 'applied' WHERE id = %s", (job_id,))
            conn.commit()
            log_action("auto_apply", f"Applied via email to {company}", details=f"Role: {title}\nEmail: {target_email}", status="success")
            applied_count += 1
        else:
            log_action("auto_apply", f"Failed applying to {company}", status="failed")
            
        # Add a delay to prevent spam flags
        import time
        import random
        time.sleep(random.uniform(5, 12))
        
        # Limit to 5 per run for safety during testing
        if applied_count >= 5:
            print("\n🛑 Reached daily batch limit of 5 for safety.")
            break

    cur.close()
    conn.close()
    
    print(f"\n✅ Auto-apply cycle complete. Total applications sent: {applied_count}")
    return applied_count

if __name__ == "__main__":
    run_auto_apply_cycle()
