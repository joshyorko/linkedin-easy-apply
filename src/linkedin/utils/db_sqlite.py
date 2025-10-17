""">
SQLite database module for LinkedIn job storage.

Provides embedded database with excellent concurrency support via WAL mode.
Built into Python 3 - no additional dependencies required.
"""
from __future__ import annotations

import os
import json
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Union
from pathlib import Path
from sqlite3 import Connection


def get_db_path() -> str:
    """Get path to SQLite database file."""
    # Allow override via environment
    db_path = os.getenv("SQLITE_PATH")
    if db_path:
        return db_path
    
    # Default to workspace root
    workspace_root = Path(__file__).parent.parent.parent
    return str(workspace_root / "linkedin_jobs.sqlite")


# Singleton connection instance
_connection: Optional[Connection] = None


def get_connection() -> Connection:
    """Get or create a singleton SQLite connection.
    
    Uses singleton pattern to avoid connection overhead on each operation.
    The connection stays open for the lifetime of the process.
    """
    global _connection
    
    if _connection is None:
        db_path = get_db_path()
        # Create parent directory if needed
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        _connection = sqlite3.connect(db_path, check_same_thread=False)
        _connection.row_factory = sqlite3.Row  # Dict-like row access
        
        # Enable WAL mode for better concurrency
        _connection.execute("PRAGMA journal_mode = WAL")
        
        # Faster synchronous mode (safe for local use)
        _connection.execute("PRAGMA synchronous = NORMAL")
        
        # Use memory for temp tables
        _connection.execute("PRAGMA temp_store = MEMORY")
        
        # Increase cache size (10MB)
        _connection.execute("PRAGMA cache_size = -10000")
        
        _ensure_schema(_connection)
        _migrate_schema(_connection)  # Run migrations after schema creation
        
        print(f"[SQLite] Connected to: {db_path}")
    
    return _connection


def _get_schema_version(conn: Connection) -> int:
    """Get current schema version from metadata table."""
    try:
        # Create metadata table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        
        result = conn.execute("""
            SELECT value FROM schema_metadata WHERE key = 'schema_version'
        """).fetchone()
        
        if result:
            return int(result[0])
        else:
            # No version = fresh database or pre-migration database
            # Check if user_profiles exists to determine if this is fresh
            tables = conn.execute("""
                SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'
            """).fetchone()
            
            if tables:
                # Existing database, version 1 (pre-migration)
                conn.execute("""
                    INSERT INTO schema_metadata (key, value) VALUES ('schema_version', '1')
                """)
                conn.commit()
                return 1
            else:
                # Fresh database, will be created at latest version
                return 0
    except Exception as e:
        print(f"[Migration] Error getting schema version: {e}")
        return 0


def _set_schema_version(conn: Connection, version: int) -> None:
    """Update schema version in metadata table."""
    try:
        conn.execute("""
            INSERT OR REPLACE INTO schema_metadata (key, value, updated_at)
            VALUES ('schema_version', ?, datetime('now'))
        """, [str(version)])
        conn.commit()
        print(f"[Migration] Schema version updated to {version}")
    except Exception as e:
        print(f"[Migration] Error setting schema version: {e}")


def _migrate_schema(conn: Connection) -> None:
    """Run database migrations to update schema to latest version."""
    current_version = _get_schema_version(conn)
    
    if current_version == 0:
        # Fresh database, no migration needed
        print("[Migration] Fresh database, no migration needed")
        _set_schema_version(conn, 2)  # Latest version
        return
    
    print(f"[Migration] Current schema version: {current_version}")
    
    # Migration 1 -> 2: Add profile enrichment fields
    if current_version < 2:
        print("[Migration] Applying migration 1->2: Adding profile enrichment fields...")
        try:
            # Add new contact fields
            conn.execute("ALTER TABLE user_profiles ADD COLUMN first_name TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN last_name TEXT")
            
            # Add address fields
            conn.execute("ALTER TABLE user_profiles ADD COLUMN address_street TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN address_city TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN address_state TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN address_zip TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN address_country TEXT DEFAULT 'United States'")
            
            # Add additional URL
            conn.execute("ALTER TABLE user_profiles ADD COLUMN portfolio_url TEXT")
            
            # Add work authorization fields
            conn.execute("ALTER TABLE user_profiles ADD COLUMN work_authorization TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN requires_visa_sponsorship INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN security_clearance TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN veteran_status TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN disability_status TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN gender TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN race_ethnicity TEXT")
            
            # Add preference fields
            conn.execute("ALTER TABLE user_profiles ADD COLUMN salary_min INTEGER")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN salary_max INTEGER")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN salary_currency TEXT DEFAULT 'USD'")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN earliest_start_date TEXT")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN willing_to_relocate INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE user_profiles ADD COLUMN remote_preference TEXT")
            
            # Add experience field
            conn.execute("ALTER TABLE user_profiles ADD COLUMN years_of_experience INTEGER")
            
            # Add custom answers field
            conn.execute("ALTER TABLE user_profiles ADD COLUMN custom_answers TEXT")
            
            conn.commit()
            
            # Try to populate first_name/last_name from full_name
            _populate_name_fields(conn)
            
            _set_schema_version(conn, 2)
            print("[Migration] ✓ Migration 1->2 completed successfully!")
            
        except Exception as e:
            print(f"[Migration] Error in migration 1->2: {e}")
            # Don't fail - columns might already exist if partially migrated
            # Just update version and continue
            _set_schema_version(conn, 2)
    
    print(f"[Migration] Schema is now at version 2 (latest)")


def _populate_name_fields(conn: Connection) -> None:
    """Attempt to populate first_name/last_name from existing full_name."""
    try:
        # Get profiles with full_name but no first_name/last_name
        profiles = conn.execute("""
            SELECT profile_id, full_name 
            FROM user_profiles 
            WHERE full_name IS NOT NULL 
            AND (first_name IS NULL OR last_name IS NULL)
        """).fetchall()
        
        for row in profiles:
            profile_id = row[0]
            full_name = row[1]
            
            # Simple name splitting
            parts = full_name.strip().split()
            if len(parts) >= 2:
                first_name = parts[0]
                last_name = ' '.join(parts[1:])
            elif len(parts) == 1:
                first_name = parts[0]
                last_name = ""
            else:
                continue
            
            conn.execute("""
                UPDATE user_profiles 
                SET first_name = ?, last_name = ?
                WHERE profile_id = ?
            """, [first_name, last_name, profile_id])
            
            print(f"[Migration] Populated name fields for profile {profile_id}: {first_name} {last_name}")
        
        conn.commit()
        
    except Exception as e:
        print(f"[Migration] Error populating name fields: {e}")


def _ensure_schema(conn: Connection) -> None:
    """Create job_postings and user_profiles tables if they don't exist."""
    
    # Create job_postings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_postings (
            -- Primary key
            job_id TEXT PRIMARY KEY,
            
            -- Core job information
            title TEXT,
            company TEXT,
            job_url TEXT,
            easy_apply INTEGER DEFAULT 0,
            
            -- Location details
            location_raw TEXT,
            location_city TEXT,
            location_state TEXT,
            location_country TEXT,
            location_type TEXT,
            
            -- Company information
            company_size TEXT,
            industry TEXT,
            company_description TEXT,
            company_logo_url TEXT,
            company_linkedin_url TEXT,
            company_location TEXT,
            
            -- Application details
            is_viewed INTEGER DEFAULT 0,
            is_applied INTEGER DEFAULT 0,
            applicant_count TEXT,
            status_message TEXT,
            promoted_by_hirer INTEGER DEFAULT 0,
            
            -- Job requirements
            experience_level TEXT,
            seniority_level TEXT,
            education_requirements TEXT,
            required_skills TEXT,
            years_experience_required TEXT,
            
            -- Job details
            job_function TEXT,
            employment_type TEXT,
            remote_work_policy TEXT,
            application_deadline TEXT,
            external_apply_url TEXT,
            
            -- Compensation
            salary_range TEXT,
            benefits TEXT,
            compensation_raw TEXT,
            
            -- Engagement metrics
            views_count TEXT,
            is_saved INTEGER DEFAULT 0,
            urgently_hiring INTEGER DEFAULT 0,
            fair_chance_employer INTEGER DEFAULT 0,
            job_reposted INTEGER DEFAULT 0,
            
            -- Metadata
            date_posted TEXT,
            job_type TEXT,
            verified_company INTEGER DEFAULT 0,
            job_description TEXT,
            
            -- Form data
            form_snapshot_url TEXT,
            form_elements TEXT,
            questions_json TEXT,
            answer_template TEXT,
            
            -- AI-generated answers
            answers_json TEXT,
            enriched_dataset TEXT,
            
            -- OpenAI enrichment fields
            ai_confidence_score REAL,
            ai_needs_review INTEGER DEFAULT 0,
            ai_enriched_at TEXT,
            
            -- Processing flags
            processed INTEGER DEFAULT 0,
            good_fit INTEGER,
            fit_score REAL,
            priority INTEGER,
            
            -- Work item tracking
            work_item_id TEXT,
            run_id TEXT,
            first_run_id TEXT,
            
            -- Raw data
            raw_html TEXT,
            playwright_ref TEXT,
            
            -- Timestamps
            scraped_at TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Create indexes for common queries
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_postings_run_id 
        ON job_postings(run_id)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_postings_easy_apply 
        ON job_postings(easy_apply)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_postings_company 
        ON job_postings(company)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_postings_processed 
        ON job_postings(processed)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_postings_location_type 
        ON job_postings(location_type)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_postings_ai_confidence 
        ON job_postings(ai_confidence_score)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_postings_good_fit 
        ON job_postings(good_fit)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_postings_fit_score 
        ON job_postings(fit_score)
    """)
    
    # Create user_profiles table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            -- Primary key
            profile_id TEXT PRIMARY KEY,
            
            -- Profile metadata
            profile_name TEXT,
            profile_type TEXT DEFAULT 'default',
            is_active INTEGER DEFAULT 0,
            
            -- Contact info (expanded)
            full_name TEXT,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            phone TEXT,
            phone_country TEXT DEFAULT 'US',
            
            -- Address (for applications requiring location)
            address_street TEXT,
            address_city TEXT,
            address_state TEXT,
            address_zip TEXT,
            address_country TEXT DEFAULT 'United States',
            
            -- Links
            linkedin_url TEXT,
            github TEXT,
            website TEXT,
            portfolio_url TEXT,
            
            -- Professional info
            location TEXT,
            title TEXT,
            summary TEXT,
            
            -- Work Authorization & Legal
            work_authorization TEXT,
            requires_visa_sponsorship INTEGER DEFAULT 0,
            security_clearance TEXT,
            veteran_status TEXT,
            disability_status TEXT,
            gender TEXT,
            race_ethnicity TEXT,
            
            -- Preferences
            salary_min INTEGER,
            salary_max INTEGER,
            salary_currency TEXT DEFAULT 'USD',
            earliest_start_date TEXT,
            willing_to_relocate INTEGER DEFAULT 0,
            remote_preference TEXT,
            
            -- Experience
            years_of_experience INTEGER,
            
            -- Skills (stored as JSON array)
            skills TEXT,
            
            -- Custom Q&A (for common questions not in profile)
            custom_answers TEXT,
            
            -- Source tracking
            source_file TEXT,
            source_type TEXT,
            
            -- Versioning
            version INTEGER DEFAULT 1,
            parent_profile_id TEXT,
            
            -- Usage tracking
            applications_count INTEGER DEFAULT 0,
            success_rate REAL,
            last_used_at TEXT,
            
            -- Timestamps
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Create indexes for user_profiles
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_profiles_active 
        ON user_profiles(is_active)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_profiles_created 
        ON user_profiles(created_at)
    """)
    
    # Create enriched_answers table (if needed)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enriched_answers (
            answer_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            
            -- Generated answers
            answers_json TEXT NOT NULL,
            
            -- Metadata
            profile_id TEXT,
            generated_at TEXT DEFAULT (datetime('now')),
            confidence_score REAL,
            unanswered_fields TEXT,
            
            -- AI model info
            model_used TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            
            -- Status
            used_for_application INTEGER DEFAULT 0,
            application_date TEXT
        )
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_enriched_job_id 
        ON enriched_answers(job_id)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_enriched_generated 
        ON enriched_answers(generated_at)
    """)
    
    conn.commit()


def _bool_to_int(value: Any) -> int:
    """Convert boolean to integer (0 or 1)."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.lower() in ('true', '1', 'yes') else 0
    return 0


def _int_to_bool(value: Any) -> bool:
    """Convert integer to boolean."""
    if value is None:
        return False
    return bool(value)


def write_jobs(job_records: Iterable[Dict[str, Any]]) -> int:
    """
    Insert or update job_postings rows in SQLite.
    
    Args:
        job_records: List of job dictionaries matching the schema
        
    Returns:
        Number of rows processed
    """
    records = list(job_records)
    if not records:
        return 0
    
    conn = get_connection()
    
    # Preserve critical state from existing records
    existing_map: Dict[str, Dict[str, Any]] = {}
    job_ids = [record.get("job_id") for record in records if record.get("job_id")]
    if job_ids:
        placeholders = ", ".join(["?" for _ in job_ids])
        cursor = conn.execute(
            f"""
            SELECT job_id, is_applied, answers_json, enriched_dataset,
                   good_fit, fit_score, priority, ai_confidence_score, 
                   ai_needs_review, ai_enriched_at
            FROM job_postings
            WHERE job_id IN ({placeholders})
            """,
            job_ids,
        )
        
        for row in cursor.fetchall():
            row_dict = dict(row)
            existing_map[row_dict['job_id']] = row_dict
    
    # Merge existing state
    for record in records:
        job_id = record.get("job_id")
        if not job_id:
            continue
        
        existing = existing_map.get(job_id)
        if not existing:
            continue
        
        # Preserve applied status
        if _int_to_bool(existing.get("is_applied")):
            record["is_applied"] = True
        
        # Keep enrichment data unless new values provided
        if existing.get("answers_json") and not record.get("answers_json"):
            record["answers_json"] = existing["answers_json"]
        if existing.get("enriched_dataset") and not record.get("enriched_dataset"):
            record["enriched_dataset"] = existing["enriched_dataset"]
        
        # Preserve enrichment metadata
        for field in ["good_fit", "fit_score", "priority", "ai_confidence_score",
                      "ai_needs_review", "ai_enriched_at"]:
            if record.get(field) in (None, "") and existing.get(field) not in (None, ""):
                record[field] = existing[field]
        
        # Mark as needing re-processing
        record["processed"] = False
    
    # Convert JSON fields to strings and booleans to integers
    for record in records:
        # JSON fields
        for json_field in ['required_skills', 'benefits', 'form_elements', 
                          'questions_json', 'answer_template', 'answers_json',
                          'enriched_dataset']:
            if json_field in record and record[json_field] is not None:
                if not isinstance(record[json_field], str):
                    record[json_field] = json.dumps(record[json_field])
        
        # Boolean fields
        bool_fields = ['easy_apply', 'is_viewed', 'is_applied', 'promoted_by_hirer',
                       'is_saved', 'urgently_hiring', 'fair_chance_employer', 
                       'job_reposted', 'verified_company', 'ai_needs_review', 'processed']
        for bool_field in bool_fields:
            if bool_field in record:
                record[bool_field] = _bool_to_int(record[bool_field])
    
    # Get columns from first record
    if not records:
        return 0
    
    columns = list(records[0].keys())
    
    # Build INSERT OR REPLACE statement with first_run_id preservation
    # For each record, check if it exists to preserve first_run_id
    conn = get_connection()
    
    for record in records:
        job_id = record.get('job_id')
        if not job_id:
            continue
            
        # Check if job already exists
        cursor = conn.execute(
            "SELECT first_run_id, run_id FROM job_postings WHERE job_id = ?",
            [job_id]
        )
        existing = cursor.fetchone()
        
        # Set first_run_id: preserve existing or use current run_id
        if existing and existing[0]:  # existing[0] is first_run_id
            record['first_run_id'] = existing[0]
        else:
            record['first_run_id'] = record.get('run_id')
    
    # Ensure first_run_id is in columns if not already
    if 'first_run_id' not in columns:
        columns.append('first_run_id')
    
    placeholders = ', '.join(['?' for _ in columns])
    col_names = ', '.join(columns)
    
    query = f"""
        INSERT OR REPLACE INTO job_postings ({col_names})
        VALUES ({placeholders})
    """
    
    # Prepare data rows
    rows = [[record.get(col) for col in columns] for record in records]
    
    print(f"[SQLite] Upserting {len(records)} records")
    print(f"[SQLite] Database: {get_db_path()}")
    
    # Execute batch insert
    conn.executemany(query, rows)
    conn.commit()
    
    # Verify
    if job_ids:
        placeholders = ', '.join(['?' for _ in job_ids])
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM job_postings WHERE job_id IN ({placeholders})",
            job_ids
        )
        count = cursor.fetchone()[0]
        print(f"[SQLite] Verified {count}/{len(job_ids)} records exist")
    
    return len(records)


def read_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single job_postings row by job_id.
    
    Args:
        job_id: LinkedIn job ID
        
    Returns:
        Job dictionary or None if not found
    """
    conn = get_connection()
    
    cursor = conn.execute(
        "SELECT * FROM job_postings WHERE job_id = ?",
        [job_id]
    )
    
    row = cursor.fetchone()
    if not row:
        return None
    
    job_dict = dict(row)
    
    # Parse JSON fields
    for json_field in ['required_skills', 'benefits', 'form_elements',
                      'questions_json', 'answer_template', 'answers_json',
                      'enriched_dataset']:
        if json_field in job_dict and job_dict[json_field]:
            try:
                job_dict[json_field] = json.loads(job_dict[json_field])
            except (json.JSONDecodeError, TypeError):
                pass
    
    # Convert integer booleans back to Python booleans
    bool_fields = ['easy_apply', 'is_viewed', 'is_applied', 'promoted_by_hirer',
                   'is_saved', 'urgently_hiring', 'fair_chance_employer', 
                   'job_reposted', 'verified_company', 'ai_needs_review', 'processed',
                   'good_fit']
    for bool_field in bool_fields:
        if bool_field in job_dict:
            job_dict[bool_field] = _int_to_bool(job_dict[bool_field])
    
    return job_dict


def update_job_enrichment(job_id: str, updates: Dict[str, Any]) -> bool:
    """
    Update enrichment-related fields for a job posting.
    
    Args:
        job_id: LinkedIn job ID
        updates: Dict of column -> value to update
    
    Returns:
        True if the update executed, False otherwise
    """
    if not updates:
        return False
    
    conn = get_connection()
    
    # JSON fields need serialization
    json_fields = {'required_skills', 'benefits', 'form_elements',
                   'questions_json', 'answer_template', 'answers_json',
                   'enriched_dataset'}
    
    # Boolean fields need conversion
    bool_fields = {'easy_apply', 'is_viewed', 'is_applied', 'promoted_by_hirer',
                   'is_saved', 'urgently_hiring', 'fair_chance_employer', 
                   'job_reposted', 'verified_company', 'ai_needs_review', 'processed',
                   'good_fit'}
    
    serialized_updates: Dict[str, Any] = {}
    for key, value in updates.items():
        if key in json_fields and value is not None and not isinstance(value, str):
            try:
                serialized_updates[key] = json.dumps(value)
            except Exception:
                serialized_updates[key] = value
        elif key in bool_fields:
            serialized_updates[key] = _bool_to_int(value)
        else:
            serialized_updates[key] = value
    
    set_clauses = [f"{column} = ?" for column in serialized_updates.keys()]
    set_clauses.append("updated_at = datetime('now')")
    
    values = list(serialized_updates.values())
    values.append(job_id)
    
    query = f"""
        UPDATE job_postings
        SET {', '.join(set_clauses)}
        WHERE job_id = ?
    """
    
    try:
        conn.execute(query, values)
        conn.commit()
        return True
    except Exception as e:
        print(f"[SQLite] Error updating enrichment for {job_id}: {e}")
        return False


def get_jobs_pending_enrichment(
    limit: Optional[int] = None,
    run_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch Easy Apply jobs that need AI enrichment/answers.
    
    Args:
        limit: Maximum number of jobs to return
        run_id: Optional run identifier to scope the query
    
    Returns:
        List of job dictionaries ready for enrichment
    """
    conn = get_connection()
    
    conditions = [
        "easy_apply = 1",
        "(questions_json IS NOT NULL AND questions_json != '' AND questions_json != 'null')",
        "(processed IS NULL OR processed = 0 OR ai_enriched_at IS NULL OR ai_enriched_at < scraped_at)"
    ]
    params: List[Any] = []
    
    if run_id:
        conditions.append("run_id = ?")
        params.append(run_id)
    
    query = f"""
        SELECT * 
        FROM job_postings
        WHERE {' AND '.join(conditions)}
        ORDER BY scraped_at DESC
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    
    if not rows:
        return []
    
    jobs: List[Dict[str, Any]] = []
    
    for row in rows:
        job_dict = dict(row)
        
        # Parse JSON fields
        for json_field in ['required_skills', 'benefits', 'form_elements',
                           'questions_json', 'answer_template', 'answers_json',
                           'enriched_dataset']:
            if job_dict.get(json_field):
                try:
                    job_dict[json_field] = json.loads(job_dict[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Convert booleans
        bool_fields = ['easy_apply', 'is_viewed', 'is_applied', 'promoted_by_hirer',
                       'is_saved', 'urgently_hiring', 'fair_chance_employer', 
                       'job_reposted', 'verified_company', 'ai_needs_review', 'processed',
                       'good_fit']
        for bool_field in bool_fields:
            if bool_field in job_dict:
                job_dict[bool_field] = _int_to_bool(job_dict[bool_field])
        
        jobs.append(job_dict)
    
    return jobs


def update_answers_json(job_id: str, answers_json: str) -> bool:
    """
    Update answers_json (and enriched_dataset alias) for a job.
    
    Args:
        job_id: LinkedIn job ID
        answers_json: JSON string with generated form answers
        
    Returns:
        True if successful, False otherwise
    """
    conn = get_connection()
    
    try:
        conn.execute("""
            UPDATE job_postings
            SET answers_json = ?,
                enriched_dataset = ?,
                updated_at = datetime('now')
            WHERE job_id = ?
        """, [answers_json, answers_json, job_id])
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"[SQLite] Error updating answers_json: {e}")
        return False


def update_is_applied(job_id: str, is_applied: bool = True) -> bool:
    """
    Update is_applied status for a job after successful application.
    
    Args:
        job_id: LinkedIn job ID
        is_applied: Application status (default: True)
        
    Returns:
        True if successful, False otherwise
    """
    conn = get_connection()
    
    try:
        conn.execute("""
            UPDATE job_postings
            SET is_applied = ?,
                updated_at = datetime('now')
            WHERE job_id = ?
        """, [_bool_to_int(is_applied), job_id])
        
        conn.commit()
        print(f"[SQLite] Updated is_applied={is_applied} for job {job_id}")
        return True
        
    except Exception as e:
        print(f"[SQLite] Error updating is_applied: {e}")
        return False


def get_jobs_with_answers() -> List[str]:
    """
    Get list of job_ids that have AI-generated answers ready.
    
    Returns:
        List of job_id strings
    """
    conn = get_connection()
    
    cursor = conn.execute("""
        SELECT job_id 
        FROM job_postings
        WHERE answers_json IS NOT NULL
          AND answers_json != ''
          AND answers_json != 'null'
    """)
    
    job_ids = [row[0] for row in cursor.fetchall()]
    print(f"[SQLite] Found {len(job_ids)} jobs with answers")
    return job_ids


def get_jobs_by_run_id(run_id: str) -> List[Dict[str, Any]]:
    """
    Get all jobs from a specific search run.
    
    Args:
        run_id: Search run ID
        
    Returns:
        List of job dictionaries
    """
    conn = get_connection()
    
    cursor = conn.execute(
        "SELECT * FROM job_postings WHERE run_id = ?",
        [run_id]
    )
    
    rows = cursor.fetchall()
    if not rows:
        return []
    
    jobs = []
    
    for row in rows:
        job_dict = dict(row)
        
        # Parse JSON fields
        for json_field in ['required_skills', 'benefits', 'form_elements',
                          'questions_json', 'answer_template', 'answers_json',
                          'enriched_dataset']:
            if json_field in job_dict and job_dict[json_field]:
                try:
                    job_dict[json_field] = json.loads(job_dict[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Convert booleans
        bool_fields = ['easy_apply', 'is_viewed', 'is_applied', 'promoted_by_hirer',
                       'is_saved', 'urgently_hiring', 'fair_chance_employer', 
                       'job_reposted', 'verified_company', 'ai_needs_review', 'processed']
        for bool_field in bool_fields:
            if bool_field in job_dict:
                job_dict[bool_field] = _int_to_bool(job_dict[bool_field])
        
        jobs.append(job_dict)
    
    return jobs


def query_jobs(
    easy_apply_only: bool = False,
    has_answers: bool = False,
    company: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Query jobs with various filters.
    
    Args:
        easy_apply_only: Only return Easy Apply jobs
        has_answers: Only return jobs with AI-generated answers
        company: Filter by company name (partial match)
        limit: Maximum number of results
        
    Returns:
        List of job dictionaries
    """
    conn = get_connection()
    
    where_clauses = []
    params = []
    
    if easy_apply_only:
        where_clauses.append("easy_apply = 1")
    
    if has_answers:
        where_clauses.append("answers_json IS NOT NULL AND answers_json != ''")
    
    if company:
        where_clauses.append("company LIKE ?")
        params.append(f"%{company}%")
    
    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    
    query = f"""
        SELECT * FROM job_postings
        {where_sql}
        ORDER BY scraped_at DESC
        LIMIT ?
    """
    params.append(limit)
    
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    
    if not rows:
        return []
    
    jobs = []
    
    for row in rows:
        job_dict = dict(row)
        
        # Parse JSON fields
        for json_field in ['required_skills', 'benefits', 'form_elements',
                          'questions_json', 'answer_template', 'answers_json',
                          'enriched_dataset']:
            if job_dict.get(json_field):
                try:
                    job_dict[json_field] = json.loads(job_dict[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Convert booleans
        bool_fields = ['easy_apply', 'is_viewed', 'is_applied', 'promoted_by_hirer',
                       'is_saved', 'urgently_hiring', 'fair_chance_employer', 
                       'job_reposted', 'verified_company', 'ai_needs_review', 'processed',
                       'good_fit']
        for bool_field in bool_fields:
            if bool_field in job_dict:
                job_dict[bool_field] = _int_to_bool(job_dict[bool_field])
        
        jobs.append(job_dict)
    
    return jobs


# Backward compatibility aliases
def read_easy_apply_answers_by_job_id(job_id: str) -> Optional[Dict[str, Any]]:
    """Legacy function name for compatibility."""
    job = read_job_by_id(job_id)
    if job and job.get('answers_json'):
        return {
            'job_id': job_id,
            'generated_answers_json': job['answers_json']
        }
    return None


def get_job_ids_with_generated_answers() -> List[str]:
    """Legacy function name for compatibility."""
    return get_jobs_with_answers()


# ============================================================================
# User Profile Management
# ============================================================================

def save_profile_to_db(
    profile: Dict[str, Any],
    source_file: str,
    source_type: str = "resume_parser",
    profile_name: Optional[str] = None,
    is_active: bool = True
) -> str:
    """
    Save user profile to SQLite and return profile_id.
    
    Args:
        profile: Profile dictionary
        source_file: Original resume filename or source
        source_type: "resume_parser", "manual", "api"
        profile_name: Optional name like "DevOps", "SRE"
        is_active: Whether to set as active profile
        
    Returns:
        profile_id (UUID string)
    """
    import uuid
    from datetime import datetime
    
    conn = get_connection()
    
    # Deactivate other profiles if this is active
    if is_active:
        conn.execute("UPDATE user_profiles SET is_active = 0")
    
    profile_id = str(uuid.uuid4())
    
    # Auto-generate profile name if not provided
    if not profile_name:
        title = profile.get('title', '')
        if title:
            profile_name = title
        else:
            profile_name = f"Profile {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # Prepare skills as JSON string
    skills_json = json.dumps(profile.get('skills', []))
    
    conn.execute("""
        INSERT INTO user_profiles (
            profile_id, profile_name, profile_type, is_active,
            full_name, email, phone, phone_country,
            linkedin_url, github, website,
            location, title, summary, skills,
            source_file, source_type, version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        profile_id,
        profile_name,
        'default',
        _bool_to_int(is_active),
        profile.get('full_name'),
        profile.get('email'),
        profile.get('phone'),
        profile.get('phone_country', 'US'),
        profile.get('linkedin_url'),
        profile.get('github'),
        profile.get('website'),
        profile.get('location'),
        profile.get('title'),
        profile.get('summary'),
        skills_json,
        source_file,
        source_type,
        1  # version
    ])
    
    conn.commit()
    
    print(f"[SQLite] Saved profile {profile_id} (active={is_active})")
    return profile_id


def get_active_profile() -> Optional[Dict[str, Any]]:
    """
    Load the active profile from SQLite.
    
    Returns:
        Profile dictionary or None if no active profile
    """
    conn = get_connection()
    
    cursor = conn.execute("""
        SELECT * FROM user_profiles 
        WHERE is_active = 1 
        ORDER BY created_at DESC 
        LIMIT 1
    """)
    
    row = cursor.fetchone()
    if not row:
        return None
    
    profile_row = dict(row)
    
    # Convert to UserProfile format
    profile = {
        'profile_id': profile_row.get('profile_id'),
        'full_name': profile_row.get('full_name', ''),
        'email': profile_row.get('email', ''),
        'phone': profile_row.get('phone', ''),
        'phone_country': profile_row.get('phone_country', 'US'),
        'linkedin_url': profile_row.get('linkedin_url', ''),
        'github': profile_row.get('github', ''),
        'website': profile_row.get('website', ''),
        'location': profile_row.get('location', ''),
        'title': profile_row.get('title', ''),
        'summary': profile_row.get('summary', ''),
        'skills': []
    }
    
    # Parse skills JSON
    if profile_row.get('skills'):
        try:
            profile['skills'] = json.loads(profile_row['skills'])
        except (json.JSONDecodeError, TypeError):
            profile['skills'] = []
    
    return profile


def get_profile_by_id(profile_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific profile by ID.
    
    Args:
        profile_id: Profile UUID
        
    Returns:
        Profile dictionary or None
    """
    conn = get_connection()
    
    cursor = conn.execute("""
        SELECT * FROM user_profiles 
        WHERE profile_id = ?
    """, [profile_id])
    
    row = cursor.fetchone()
    if not row:
        return None
    
    profile_row = dict(row)
    
    # Convert to UserProfile format
    profile = {
        'full_name': profile_row.get('full_name', ''),
        'email': profile_row.get('email', ''),
        'phone': profile_row.get('phone', ''),
        'phone_country': profile_row.get('phone_country', 'US'),
        'linkedin_url': profile_row.get('linkedin_url', ''),
        'github': profile_row.get('github', ''),
        'website': profile_row.get('website', ''),
        'location': profile_row.get('location', ''),
        'title': profile_row.get('title', ''),
        'summary': profile_row.get('summary', ''),
        'skills': []
    }
    
    # Parse skills JSON
    if profile_row.get('skills'):
        try:
            profile['skills'] = json.loads(profile_row['skills'])
        except (json.JSONDecodeError, TypeError):
            profile['skills'] = []
    
    return profile


def get_profile_history(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get all profile versions ordered by creation date.
    
    Args:
        limit: Maximum number of profiles to return
        
    Returns:
        List of profile metadata dictionaries
    """
    conn = get_connection()
    
    cursor = conn.execute("""
        SELECT 
            profile_id, profile_name, profile_type, is_active,
            full_name, title, source_file, source_type,
            version, applications_count, success_rate,
            created_at, updated_at, last_used_at
        FROM user_profiles 
        ORDER BY created_at DESC
        LIMIT ?
    """, [limit])
    
    rows = cursor.fetchall()
    if not rows:
        return []
    
    profiles = []
    for row in rows:
        profile_dict = dict(row)
        # Convert is_active to boolean
        profile_dict['is_active'] = _int_to_bool(profile_dict.get('is_active'))
        profiles.append(profile_dict)
    
    return profiles


def set_active_profile(profile_id: str) -> bool:
    """
    Set a profile as the active profile.
    
    Args:
        profile_id: Profile UUID to activate
        
    Returns:
        True if successful, False if profile not found
    """
    conn = get_connection()
    
    # Check if profile exists
    cursor = conn.execute("""
        SELECT profile_id FROM user_profiles WHERE profile_id = ?
    """, [profile_id])
    
    if not cursor.fetchone():
        return False
    
    # Deactivate all profiles
    conn.execute("UPDATE user_profiles SET is_active = 0")
    
    # Activate the specified profile
    conn.execute("""
        UPDATE user_profiles 
        SET is_active = 1, updated_at = datetime('now')
        WHERE profile_id = ?
    """, [profile_id])
    
    conn.commit()
    
    print(f"[SQLite] Set profile {profile_id} as active")
    return True


def update_profile_usage(profile_id: str, success: bool = False) -> None:
    """
    Update profile usage statistics after an application.
    
    Args:
        profile_id: Profile UUID
        success: Whether the application was successful
    """
    conn = get_connection()
    
    # Get current stats
    cursor = conn.execute("""
        SELECT applications_count, success_rate 
        FROM user_profiles 
        WHERE profile_id = ?
    """, [profile_id])
    
    row = cursor.fetchone()
    if not row:
        return
    
    current_count = row[0] or 0
    current_rate = row[1] or 0.0
    
    # Calculate new stats
    new_count = current_count + 1
    if success:
        new_rate = ((current_rate * current_count) + 1.0) / new_count
    else:
        new_rate = (current_rate * current_count) / new_count
    
    # Update
    conn.execute("""
        UPDATE user_profiles 
        SET 
            applications_count = ?,
            success_rate = ?,
            last_used_at = datetime('now'),
            updated_at = datetime('now')
        WHERE profile_id = ?
    """, [new_count, new_rate, profile_id])
    
    conn.commit()


# =============================================================================
# Fit Analysis Helper Functions
# =============================================================================

def get_fit_summary(run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get summary statistics for job fit analysis.
    
    Args:
        run_id: Optional run_id to filter by
        
    Returns:
        Dictionary with fit statistics
    """
    conn = get_connection()
    
    if run_id:
        query = """
            SELECT 
                COUNT(*) as total_jobs,
                SUM(CASE WHEN good_fit = 1 THEN 1 ELSE 0 END) as good_fits,
                SUM(CASE WHEN good_fit = 0 THEN 1 ELSE 0 END) as bad_fits,
                SUM(CASE WHEN good_fit IS NULL THEN 1 ELSE 0 END) as not_analyzed,
                ROUND(AVG(fit_score), 3) as avg_fit_score,
                ROUND(MIN(fit_score), 3) as min_fit_score,
                ROUND(MAX(fit_score), 3) as max_fit_score
            FROM job_postings
            WHERE run_id = ?
        """
        cursor = conn.execute(query, [run_id])
    else:
        query = """
            SELECT 
                COUNT(*) as total_jobs,
                SUM(CASE WHEN good_fit = 1 THEN 1 ELSE 0 END) as good_fits,
                SUM(CASE WHEN good_fit = 0 THEN 1 ELSE 0 END) as bad_fits,
                SUM(CASE WHEN good_fit IS NULL THEN 1 ELSE 0 END) as not_analyzed,
                ROUND(AVG(fit_score), 3) as avg_fit_score,
                ROUND(MIN(fit_score), 3) as min_fit_score,
                ROUND(MAX(fit_score), 3) as max_fit_score
            FROM job_postings
        """
        cursor = conn.execute(query)
    
    row = cursor.fetchone()
    if not row:
        return {}
    
    return {
        "total_jobs": row[0] or 0,
        "good_fits": row[1] or 0,
        "bad_fits": row[2] or 0,
        "not_analyzed": row[3] or 0,
        "avg_fit_score": row[4],
        "min_fit_score": row[5],
        "max_fit_score": row[6],
        "good_fit_rate": round((row[1] or 0) / (row[0] or 1), 3)
    }


def get_good_fit_jobs(
    run_id: Optional[str] = None,
    min_fit_score: float = 0.0,
    easy_apply_only: bool = True,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get jobs that are good fits for the user profile.
    
    Args:
        run_id: Optional run_id to filter by
        min_fit_score: Minimum fit score (0.0-1.0)
        easy_apply_only: Only return Easy Apply jobs
        limit: Maximum number of jobs to return
        
    Returns:
        List of job dictionaries
    """
    conn = get_connection()
    
    conditions = ["good_fit = 1"]
    params = []
    
    if run_id:
        conditions.append("run_id = ?")
        params.append(run_id)
    
    if min_fit_score > 0:
        conditions.append("fit_score >= ?")
        params.append(min_fit_score)
    
    if easy_apply_only:
        conditions.append("easy_apply = 1")
    
    where_clause = " AND ".join(conditions)
    params.append(limit)
    
    query = f"""
        SELECT 
            job_id, title, company, location_type,
            fit_score, ai_confidence_score, easy_apply,
            date_posted, job_url, required_skills, experience_level
        FROM job_postings
        WHERE {where_clause}
        ORDER BY fit_score DESC, ai_confidence_score DESC
        LIMIT ?
    """
    
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    
    if not rows:
        return []
    
    jobs = []
    for row in rows:
        job_dict = dict(row)
        # Convert easy_apply to boolean
        if 'easy_apply' in job_dict:
            job_dict['easy_apply'] = _int_to_bool(job_dict['easy_apply'])
        jobs.append(job_dict)
    
    return jobs


def get_bad_fit_jobs(
    run_id: Optional[str] = None,
    max_fit_score: float = 1.0,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get jobs that are bad fits (for analysis/debugging).
    
    Args:
        run_id: Optional run_id to filter by
        max_fit_score: Maximum fit score to include
        limit: Maximum number of jobs to return
        
    Returns:
        List of job dictionaries
    """
    conn = get_connection()
    
    conditions = ["good_fit = 0"]
    params = []
    
    if run_id:
        conditions.append("run_id = ?")
        params.append(run_id)
    
    if max_fit_score < 1.0:
        conditions.append("fit_score <= ?")
        params.append(max_fit_score)
    
    where_clause = " AND ".join(conditions)
    params.append(limit)
    
    query = f"""
        SELECT 
            job_id, title, company, 
            fit_score, required_skills, experience_level,
            location_type, job_description
        FROM job_postings
        WHERE {where_clause}
        ORDER BY fit_score DESC
        LIMIT ?
    """
    
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    
    if not rows:
        return []
    
    jobs = []
    for row in rows:
        jobs.append(dict(row))
    
    return jobs


def update_job_fit_analysis(
    job_ids: Union[str, List[str]],
    good_fit: Optional[bool] = None,
    fit_score: Optional[float] = None
) -> Dict[str, Any]:
    """
    Update fit analysis fields (good_fit, fit_score) for one or more jobs.
    
    This is useful for manually overriding AI fit analysis results or bulk updates.
    
    Args:
        job_ids: Single job_id string or list of job_ids
        good_fit: Set to True/False to update good_fit column (None = no change)
        fit_score: Set to a value 0.0-1.0 to update fit_score (None = no change)
        
    Returns:
        Dict with success status and count of updated jobs
        
    Examples:
        # Mark single job as good fit with high score
        update_job_fit_analysis("123456", good_fit=True, fit_score=0.85)
        
        # Mark multiple jobs as good fits
        update_job_fit_analysis(["123", "456", "789"], good_fit=True)
        
        # Just update fit scores
        update_job_fit_analysis(["123", "456"], fit_score=0.75)
    """
    if not job_ids:
        return {"success": False, "error": "No job_ids provided", "updated_count": 0}
    
    # Normalize to list
    if isinstance(job_ids, str):
        job_ids = [job_ids]
    
    # Validate inputs
    if good_fit is None and fit_score is None:
        return {
            "success": False,
            "error": "Must provide at least one of: good_fit or fit_score",
            "updated_count": 0
        }
    
    if fit_score is not None and not (0.0 <= fit_score <= 1.0):
        return {
            "success": False,
            "error": "fit_score must be between 0.0 and 1.0",
            "updated_count": 0
        }
    
    conn = get_connection()
    
    # Build UPDATE query dynamically based on what's being updated
    updates = []
    params = []
    
    if good_fit is not None:
        updates.append("good_fit = ?")
        params.append(_bool_to_int(good_fit))
    
    if fit_score is not None:
        updates.append("fit_score = ?")
        params.append(fit_score)
    
    # Always update timestamp
    updates.append("updated_at = datetime('now')")
    
    # Add job_ids to params for WHERE IN clause
    placeholders = ",".join(["?"] * len(job_ids))
    params.extend(job_ids)
    
    query = f"""
        UPDATE job_postings
        SET {', '.join(updates)}
        WHERE job_id IN ({placeholders})
    """
    
    try:
        cursor = conn.execute(query, params)
        conn.commit()
        updated_count = cursor.rowcount
        
        print(f"[SQLite] Updated fit analysis for {updated_count} jobs")
        
        return {
            "success": True,
            "updated_count": updated_count,
            "job_ids": job_ids,
            "changes": {
                "good_fit": good_fit,
                "fit_score": fit_score
            }
        }
    except Exception as e:
        print(f"[SQLite] Error updating fit analysis: {e}")
        return {
            "success": False,
            "error": str(e),
            "updated_count": 0
        }
