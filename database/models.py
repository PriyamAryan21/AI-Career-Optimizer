"""
Database helper functions using PostgreSQL (Supabase).
"""

import json
import psycopg2
from datetime import datetime
from config.settings import DATABASE_URL


from psycopg2 import pool
import threading

db_pool = None
pool_lock = threading.Lock()

def _get_connection():
    global db_pool
    with pool_lock:
        if not db_pool:
            db_pool = pool.SimpleConnectionPool(1, 20, DATABASE_URL)
        return db_pool.getconn()

def _release_connection(conn):
    if db_pool and conn:
        with pool_lock:
            try:
                db_pool.putconn(conn)
            except Exception as e:
                print(f"Warning: Failed to release connection: {e}")


# ── Action Logs ────────────────────────────────────────

def log_action(action_type, description, details="",
               diff_before="", diff_after="", status="success"):
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO action_logs (action_type, description, details, diff_before, diff_after, status)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (action_type, description, details, diff_before, diff_after, status)
    )
    conn.commit()
    cur.close()
    _release_connection(conn)


def get_action_logs(limit=50):
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM action_logs ORDER BY created_at DESC LIMIT %s", (limit,))
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    _release_connection(conn)
    return rows


# ── Suggestions Queue ─────────────────────────────────

def add_suggestion(suggestion_type, suggestion_text, ai_reasoning=""):
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO suggestions_queue (suggestion_type, suggestion_text, ai_reasoning)
           VALUES (%s, %s, %s)""",
        (suggestion_type, suggestion_text, ai_reasoning)
    )
    conn.commit()
    cur.close()
    _release_connection(conn)


def get_pending_suggestions():
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM suggestions_queue WHERE status = 'pending' ORDER BY created_at DESC")
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    _release_connection(conn)
    return rows


def resolve_suggestion(suggestion_id, status):
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE suggestions_queue SET status = %s, resolved_at = %s WHERE id = %s",
        (status, datetime.now().isoformat(), suggestion_id)
    )
    conn.commit()
    cur.close()
    _release_connection(conn)


# ── Trend Data ─────────────────────────────────────────

def save_trend_data(skill_name, role, frequency, total_postings, scraped_date):
    demand_pct = round((frequency / total_postings) * 100, 2) if total_postings > 0 else 0
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO trend_data (skill_name, role, frequency, total_postings, demand_percentage, scraped_date)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (skill_name, role, frequency, total_postings, demand_pct, scraped_date)
    )
    conn.commit()
    cur.close()
    _release_connection(conn)


def get_trends_by_role(role, limit=20):
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT skill_name, AVG(demand_percentage) as avg_demand
           FROM trend_data WHERE role = %s
           GROUP BY skill_name ORDER BY avg_demand DESC LIMIT %s""",
        (role, limit)
    )
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    _release_connection(conn)
    return rows


# ── Profile Metrics ────────────────────────────────────

def save_profile_metrics(search_appearances_90d=0, search_appearances_7d=0, recruiter_actions_90d=0, activity_level="UNKNOWN", profile_completeness=0):
    conn = _get_connection()
    cur = conn.cursor()
    
    # 1. Insert today's metrics
    cur.execute(
        """INSERT INTO profile_metrics (search_appearances, search_appearances_7d, recruiter_actions, activity_level, profile_completeness, metric_date)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (search_appearances_90d, search_appearances_7d, recruiter_actions_90d, activity_level, profile_completeness, datetime.now().strftime("%Y-%m-%d"))
    )
    
    # 2. Garbage Collection: Delete metrics older than 30 days to stay cleanly within the free tier!
    cur.execute(
        """DELETE FROM profile_metrics 
           WHERE CAST(metric_date AS DATE) < CURRENT_DATE - INTERVAL '30 days'"""
    )
    
    conn.commit()
    cur.close()
    _release_connection(conn)

def get_profile_metrics():
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT metric_date, search_appearances, search_appearances_7d, recruiter_actions, activity_level, profile_completeness
           FROM profile_metrics
           ORDER BY metric_date ASC"""
    )
    rows = cur.fetchall()
    cur.close()
    _release_connection(conn)
    
    metrics = []
    for r in rows:
        metrics.append({
            "date": r[0],
            "search_app_90d": r[1],
            "search_app_7d": r[2],
            "recruiter_actions": r[3],
            "activity_level": r[4],
            "profile_completeness": r[5]
        })
    return metrics

# ── Skill Inventory Sync ───────────────────────────────

def sync_skill_inventory(profile_data):
    """Syncs master_profile.yaml skills into the database for growth tracking."""
    conn = _get_connection()
    cur = conn.cursor()
    
    skills_dict = profile_data.get("skills", {})
    proven = skills_dict.get("proven", [])
    learning = skills_dict.get("learning", [])
    
    for skill in proven:
        cur.execute(
            """INSERT INTO skill_inventory (skill_name, category, proficiency)
               VALUES (%s, 'proven', 5)
               ON CONFLICT (skill_name) DO UPDATE 
               SET category = 'proven', proficiency = 5, updated_at = CURRENT_TIMESTAMP""",
            (skill,)
        )
        
    for skill in learning:
        cur.execute(
            """INSERT INTO skill_inventory (skill_name, category, proficiency)
               VALUES (%s, 'learning', 2)
               ON CONFLICT (skill_name) DO UPDATE 
               SET category = 'learning', updated_at = CURRENT_TIMESTAMP""",
            (skill,)
        )
        
    conn.commit()
    cur.close()
    _release_connection(conn)

def get_skill_inventory():
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT skill_name, category, proficiency, added_at, updated_at FROM skill_inventory ORDER BY added_at DESC")
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    _release_connection(conn)
    return rows


# ── Resume Versions ────────────────────────────────────

def save_resume_version(file_path, keywords_used, changes_summary):
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO resume_versions (file_path, keywords_used, ai_changes_summary)
           VALUES (%s, %s, %s)""",
        (file_path, json.dumps(keywords_used), changes_summary)
    )
    conn.commit()
    cur.close()
    _release_connection(conn)


# ── Session State ──────────────────────────────────────

def update_session_status(status, cookies_data=None):
    from config.settings import fernet_cipher
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM session_state WHERE platform = 'naukri'")
    existing = cur.fetchone()
    now = datetime.now().isoformat()
    
    encrypted_cookies = None
    if cookies_data:
        encrypted_cookies = fernet_cipher.encrypt(cookies_data.encode()).decode()

    if existing:
        if encrypted_cookies is not None:
            cur.execute(
                """UPDATE session_state SET status = %s, last_validated = %s, cookies_data = %s, updated_at = %s
                   WHERE platform = 'naukri'""",
                (status, now, encrypted_cookies, now)
            )
        else:
            cur.execute(
                """UPDATE session_state SET status = %s, last_validated = %s, updated_at = %s
                   WHERE platform = 'naukri'""",
                (status, now, now)
            )
    else:
        cur.execute(
            """INSERT INTO session_state (platform, status, last_validated, cookies_data)
               VALUES ('naukri', %s, %s, %s)""",
            (status, now, encrypted_cookies or "")
        )
    conn.commit()
    cur.close()
    _release_connection(conn)

# ── Hot Jobs Feed ──────────────────────────────────────

def save_hot_jobs(jobs: list[dict]):
    """Save the top ranked jobs to the database, clearing the old ones first."""
    conn = _get_connection()
    cur = conn.cursor()
    
    # Clear the old feed so we only keep the freshest jobs
    cur.execute("DELETE FROM hot_jobs")
    
    for job in jobs:
        # Convert the skills list into a comma-separated string for the DB
        skills_str = ",".join(job.get("skills", []))
        
        cur.execute(
            """INSERT INTO hot_jobs (title, company, location, apply_url, source, skills, salary, match_score, posted_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("apply_url", ""),
                job.get("source", ""),
                skills_str,
                job.get("salary", ""),
                job.get("match_score", 0),
                job.get("posted", "")
            )
        )
    
    conn.commit()
    cur.close()
    _release_connection(conn)


def get_session_status():
    from config.settings import fernet_cipher
    conn = _get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM session_state WHERE platform = 'naukri'")
    row = cur.fetchone()
    if row:
        columns = [desc[0] for desc in cur.description]
        result = dict(zip(columns, row))
        
        # Decrypt cookies if present
        if result.get('cookies_data'):
            try:
                result['cookies_data'] = fernet_cipher.decrypt(result['cookies_data'].encode()).decode()
            except Exception as e:
                print(f"Warning: Failed to decrypt cookies: {e}")
                result['cookies_data'] = "[]" # Invalidate corrupted/old unencrypted cookies
                
    else:
        result = {"status": "not_initialized"}
    cur.close()
    _release_connection(conn)
    return result
