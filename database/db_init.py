"""
Database initialization - creates all required tables in Supabase PostgreSQL.
"""

import psycopg2
from config.settings import DATABASE_URL


def initialize_database():
    """Create all tables if they don't exist."""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hot_jobs (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT,
            apply_url TEXT,
            source TEXT,
            skills TEXT,
            salary TEXT,
            match_score INTEGER,
            posted_date TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_data (
            id SERIAL PRIMARY KEY,
            skill_name TEXT NOT NULL,
            role TEXT NOT NULL,
            frequency INTEGER DEFAULT 0,
            total_postings INTEGER DEFAULT 0,
            demand_percentage REAL DEFAULT 0.0,
            scraped_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_inventory (
            id SERIAL PRIMARY KEY,
            skill_name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL CHECK(category IN ('proven', 'learning', 'suggested')),
            proficiency TEXT DEFAULT 'intermediate',
            added_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_logs (
            id SERIAL PRIMARY KEY,
            action_type TEXT NOT NULL,
            description TEXT,
            details TEXT,
            diff_before TEXT,
            diff_after TEXT,
            status TEXT DEFAULT 'success' CHECK(status IN ('success', 'failed', 'skipped')),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suggestions_queue (
            id SERIAL PRIMARY KEY,
            suggestion_type TEXT NOT NULL CHECK(suggestion_type IN ('add_skill', 'remove_skill', 'update_content', 'other')),
            suggestion_text TEXT NOT NULL,
            ai_reasoning TEXT,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
            created_at TIMESTAMP DEFAULT NOW(),
            resolved_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_metrics (
            id SERIAL PRIMARY KEY,
            profile_views INTEGER DEFAULT 0,
            search_appearances INTEGER DEFAULT 0,
            recruiter_actions INTEGER DEFAULT 0,
            metric_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resume_versions (
            id SERIAL PRIMARY KEY,
            file_path TEXT NOT NULL,
            keywords_used TEXT,
            ai_changes_summary TEXT,
            generated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_state (
            id SERIAL PRIMARY KEY,
            platform TEXT DEFAULT 'naukri',
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'expired', 'error')),
            last_validated TIMESTAMP,
            cookies_data TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Database tables created in Supabase!")


if __name__ == "__main__":
    initialize_database()
