"""
PostgreSQL database module for LinkedIn job storage.

Provides enterprise-grade database support with better scalability
and concurrency for production deployments.

Requires: psycopg2-binary (or psycopg2)
Connection via DATABASE_URL environment variable or individual DB_* vars.
"""
from __future__ import annotations

import os
import json
from typing import Any, Dict, Iterable, List, Optional, Union
from pathlib import Path

try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    from psycopg2 import sql
except ImportError:
    raise ImportError(
        "PostgreSQL support requires psycopg2. Install with: pip install psycopg2-binary"
    )


# Connection pool (singleton)
_connection_pool: Optional[pool.SimpleConnectionPool] = None


def _get_db_config() -> Dict[str, Any]:
    """Get PostgreSQL connection configuration from environment."""
    # Try DATABASE_URL first (common in cloud deployments)
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {"dsn": database_url}
    
    # Fall back to individual parameters
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "linkedin_jobs"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


def get_db_path() -> str:
    """Get database identifier (for compatibility with SQLite API)."""
    config = _get_db_config()
    if "dsn" in config:
        return config["dsn"]
    return f"postgresql://{config['user']}@{config['host']}:{config['port']}/{config['database']}"


def _get_connection_pool():
    """Get or create connection pool."""
    global _connection_pool
    
    if _connection_pool is None:
        config = _get_db_config()
        
        # Create connection pool (1-20 connections)
        _connection_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=20,
            **config
        )
        
        print(f"[PostgreSQL] Connection pool created: {get_db_path()}")
        
        # Initialize schema on first connection
        conn = _connection_pool.getconn()
        try:
            _ensure_schema(conn)
            _migrate_schema(conn)
            conn.commit()
        finally:
            _connection_pool.putconn(conn)
    
    return _connection_pool


def get_connection():
    """Get a connection from the pool.
    
    Note: Caller should commit() and then call putconn() when done.
    For compatibility with SQLite API, we return a pseudo-connection
    that auto-returns to pool on context exit.
    """
    pool = _get_connection_pool()
    return pool.getconn()


def putconn(conn):
    """Return connection to pool."""
    pool = _get_connection_pool()
    pool.putconn(conn)


def _get_schema_version(conn) -> int:
    """Get current schema version from metadata table."""
    try:
        with conn.cursor() as cursor:
            # Create metadata table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                SELECT value FROM schema_metadata WHERE key = 'schema_version'
            """)
            
            result = cursor.fetchone()
            
            if result:
                return int(result[0])
            else:
                # Check if user_profiles exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'user_profiles'
                    )
                """)
                
                if cursor.fetchone()[0]:
                    # Existing database, version 1
                    cursor.execute("""
                        INSERT INTO schema_metadata (key, value) VALUES ('schema_version', '1')
                    """)
                    conn.commit()
                    return 1
                else:
                    # Fresh database
                    return 0
    except Exception as e:
        print(f"[Migration] Error getting schema version: {e}")
        return 0


def _set_schema_version(conn, version: int) -> None:
    """Update schema version in metadata table."""
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO schema_metadata (key, value, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE 
                SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """, ['schema_version', str(version)])
            conn.commit()
            print(f"[Migration] Schema version updated to {version}")
    except Exception as e:
        print(f"[Migration] Error setting schema version: {e}")


def _migrate_schema(conn) -> None:
    """Run database migrations to update schema to latest version."""
    current_version = _get_schema_version(conn)
    
    if current_version == 0:
        print("[Migration] Fresh database, no migration needed")
        _set_schema_version(conn, 2)  # Latest version
        return
    
    print(f"[Migration] Current schema version: {current_version}")
    
    # Migration 1 -> 2: Add profile enrichment fields
    if current_version < 2:
        print("[Migration] Applying migration 1->2: Adding profile enrichment fields...")
        try:
            with conn.cursor() as cursor:
                # Add new columns (PostgreSQL allows multiple ADD COLUMN in one statement)
                cursor.execute("""
                    ALTER TABLE user_profiles 
                    ADD COLUMN IF NOT EXISTS first_name TEXT,
                    ADD COLUMN IF NOT EXISTS last_name TEXT,
                    ADD COLUMN IF NOT EXISTS address_street TEXT,
                    ADD COLUMN IF NOT EXISTS address_city TEXT,
                    ADD COLUMN IF NOT EXISTS address_state TEXT,
                    ADD COLUMN IF NOT EXISTS address_zip TEXT,
                    ADD COLUMN IF NOT EXISTS address_country TEXT DEFAULT 'United States',
                    ADD COLUMN IF NOT EXISTS portfolio_url TEXT,
                    ADD COLUMN IF NOT EXISTS work_authorization TEXT,
                    ADD COLUMN IF NOT EXISTS requires_visa_sponsorship BOOLEAN DEFAULT false,
                    ADD COLUMN IF NOT EXISTS security_clearance TEXT,
                    ADD COLUMN IF NOT EXISTS veteran_status TEXT,
                    ADD COLUMN IF NOT EXISTS disability_status TEXT,
                    ADD COLUMN IF NOT EXISTS gender TEXT,
                    ADD COLUMN IF NOT EXISTS race_ethnicity TEXT,
                    ADD COLUMN IF NOT EXISTS salary_min INTEGER,
                    ADD COLUMN IF NOT EXISTS salary_max INTEGER,
                    ADD COLUMN IF NOT EXISTS salary_currency TEXT DEFAULT 'USD',
                    ADD COLUMN IF NOT EXISTS earliest_start_date TEXT,
                    ADD COLUMN IF NOT EXISTS willing_to_relocate BOOLEAN DEFAULT false,
                    ADD COLUMN IF NOT EXISTS remote_preference TEXT,
                    ADD COLUMN IF NOT EXISTS years_of_experience INTEGER,
                    ADD COLUMN IF NOT EXISTS custom_answers TEXT
                """)
                
                conn.commit()
                
                # Populate first_name/last_name from full_name
                _populate_name_fields(conn)
                
                _set_schema_version(conn, 2)
                print("[Migration] ✓ Migration 1->2 completed successfully!")
                
        except Exception as e:
            print(f"[Migration] Error in migration 1->2: {e}")
            conn.rollback()
            # Try to set version anyway
            _set_schema_version(conn, 2)
    
    print(f"[Migration] Schema is now at version 2 (latest)")


def _populate_name_fields(conn) -> None:
    """Attempt to populate first_name/last_name from existing full_name."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT profile_id, full_name 
                FROM user_profiles 
                WHERE full_name IS NOT NULL 
                AND (first_name IS NULL OR last_name IS NULL)
            """)
            
            profiles = cursor.fetchall()
            
            for row in profiles:
                profile_id = row['profile_id']
                full_name = row['full_name']
                
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
                
                cursor.execute("""
                    UPDATE user_profiles 
                    SET first_name = %s, last_name = %s
                    WHERE profile_id = %s
                """, [first_name, last_name, profile_id])
                
                print(f"[Migration] Populated name fields for profile {profile_id}: {first_name} {last_name}")
            
            conn.commit()
            
    except Exception as e:
        print(f"[Migration] Error populating name fields: {e}")


def _ensure_schema(conn) -> None:
    """Create job_postings and user_profiles tables if they don't exist."""
    
    with conn.cursor() as cursor:
        # Create job_postings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_postings (
                -- Primary key
                job_id TEXT PRIMARY KEY,
                
                -- Core job information
                title TEXT,
                company TEXT,
                job_url TEXT,
                easy_apply BOOLEAN DEFAULT false,
                
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
                is_viewed BOOLEAN DEFAULT false,
                is_applied BOOLEAN DEFAULT false,
                applicant_count TEXT,
                status_message TEXT,
                promoted_by_hirer BOOLEAN DEFAULT false,
                
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
                is_saved BOOLEAN DEFAULT false,
                urgently_hiring BOOLEAN DEFAULT false,
                fair_chance_employer BOOLEAN DEFAULT false,
                job_reposted BOOLEAN DEFAULT false,
                
                -- Metadata
                date_posted TEXT,
                job_type TEXT,
                verified_company BOOLEAN DEFAULT false,
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
                ai_confidence_score DOUBLE PRECISION,
                ai_needs_review BOOLEAN DEFAULT false,
                ai_enriched_at TIMESTAMP,
                
                -- Processing flags
                processed BOOLEAN DEFAULT false,
                good_fit BOOLEAN,
                fit_score DOUBLE PRECISION,
                priority INTEGER,
                
                -- Work item tracking
                work_item_id TEXT,
                run_id TEXT,
                first_run_id TEXT,
                
                -- Raw data
                raw_html TEXT,
                playwright_ref TEXT,
                
                -- Timestamps
                scraped_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_postings_run_id 
            ON job_postings(run_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_postings_easy_apply 
            ON job_postings(easy_apply)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_postings_company 
            ON job_postings(company)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_postings_processed 
            ON job_postings(processed)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_postings_location_type 
            ON job_postings(location_type)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_postings_ai_confidence 
            ON job_postings(ai_confidence_score)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_postings_good_fit 
            ON job_postings(good_fit)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_postings_fit_score 
            ON job_postings(fit_score)
        """)
        
        # Create user_profiles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                -- Primary key
                profile_id TEXT PRIMARY KEY,
                
                -- Profile metadata
                profile_name TEXT,
                profile_type TEXT DEFAULT 'default',
                is_active BOOLEAN DEFAULT false,
                
                -- Contact info (expanded)
                full_name TEXT,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                phone TEXT,
                phone_country TEXT DEFAULT 'US',
                
                -- Address
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
                requires_visa_sponsorship BOOLEAN DEFAULT false,
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
                willing_to_relocate BOOLEAN DEFAULT false,
                remote_preference TEXT,
                
                -- Experience
                years_of_experience INTEGER,
                
                -- Skills (stored as JSON array)
                skills TEXT,
                
                -- Custom Q&A
                custom_answers TEXT,
                
                -- Source tracking
                source_file TEXT,
                source_type TEXT,
                
                -- Versioning
                version INTEGER DEFAULT 1,
                parent_profile_id TEXT,
                
                -- Usage tracking
                applications_count INTEGER DEFAULT 0,
                success_rate DOUBLE PRECISION,
                last_used_at TIMESTAMP,
                
                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for user_profiles
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_profiles_active 
            ON user_profiles(is_active)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_profiles_created 
            ON user_profiles(created_at)
        """)
        
        # Create enriched_answers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enriched_answers (
                answer_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                
                -- Generated answers
                answers_json TEXT NOT NULL,
                
                -- Metadata
                profile_id TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confidence_score DOUBLE PRECISION,
                unanswered_fields TEXT,
                
                -- AI model info
                model_used TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                
                -- Status
                used_for_application BOOLEAN DEFAULT false,
                application_date TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_enriched_job_id 
            ON enriched_answers(job_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_enriched_generated 
            ON enriched_answers(generated_at)
        """)
        
        conn.commit()


def write_jobs(job_records: Iterable[Dict[str, Any]]) -> int:
    """
    Insert or update job_postings rows in PostgreSQL.
    
    Args:
        job_records: List of job dictionaries matching the schema
        
    Returns:
        Number of rows processed
    """
    records = list(job_records)
    if not records:
        return 0
    
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        # Preserve critical state from existing records
        existing_map: Dict[str, Dict[str, Any]] = {}
        job_ids = [record.get("job_id") for record in records if record.get("job_id")]
        
        if job_ids:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT job_id, is_applied, answers_json, enriched_dataset,
                           good_fit, fit_score, priority, ai_confidence_score, 
                           ai_needs_review, ai_enriched_at, first_run_id, run_id
                    FROM job_postings
                    WHERE job_id = ANY(%s)
                """, [job_ids])
                
                for row in cursor.fetchall():
                    existing_map[row['job_id']] = dict(row)
        
        # Merge existing state
        for record in records:
            job_id = record.get("job_id")
            if not job_id:
                continue
            
            existing = existing_map.get(job_id)
            if not existing:
                continue
            
            # Preserve applied status
            if existing.get("is_applied"):
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
            
            # Set first_run_id: preserve existing or use current run_id
            if existing.get('first_run_id'):
                record['first_run_id'] = existing['first_run_id']
            else:
                record['first_run_id'] = record.get('run_id')
            
            # Mark as needing re-processing
            record["processed"] = False
        
        # Convert JSON fields to strings
        for record in records:
            for json_field in ['required_skills', 'benefits', 'form_elements', 
                              'questions_json', 'answer_template', 'answers_json',
                              'enriched_dataset']:
                if json_field in record and record[json_field] is not None:
                    if not isinstance(record[json_field], str):
                        record[json_field] = json.dumps(record[json_field])
            
            # Ensure first_run_id
            if 'first_run_id' not in record and 'run_id' in record:
                record['first_run_id'] = record['run_id']
        
        # Get columns from first record
        if not records:
            return 0
        
        columns = list(records[0].keys())
        
        # Build INSERT ... ON CONFLICT statement
        col_names = ', '.join(columns)
        placeholders = ', '.join(['%s' for _ in columns])
        
        # Build UPDATE clause (all columns except primary key)
        update_cols = [c for c in columns if c != 'job_id']
        update_clause = ', '.join([f"{col} = EXCLUDED.{col}" for col in update_cols])
        
        query = f"""
            INSERT INTO job_postings ({col_names})
            VALUES ({placeholders})
            ON CONFLICT (job_id) DO UPDATE SET {update_clause}
        """
        
        # Prepare data rows
        rows = [[record.get(col) for col in columns] for record in records]
        
        print(f"[PostgreSQL] Upserting {len(records)} records")
        
        # Execute batch insert
        with conn.cursor() as cursor:
            cursor.executemany(query, rows)
        
        conn.commit()
        
        # Verify
        if job_ids:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM job_postings WHERE job_id = ANY(%s)",
                    [job_ids]
                )
                count = cursor.fetchone()[0]
                print(f"[PostgreSQL] Verified {count}/{len(job_ids)} records exist")
        
        return len(records)
        
    finally:
        pool.putconn(conn)


def read_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single job_postings row by job_id."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM job_postings WHERE job_id = %s", [job_id])
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
            
            return job_dict
            
    finally:
        pool.putconn(conn)


def update_job_enrichment(job_id: str, updates: Dict[str, Any]) -> bool:
    """Update enrichment-related fields for a job posting."""
    if not updates:
        return False
    
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        # JSON fields need serialization
        json_fields = {'required_skills', 'benefits', 'form_elements',
                       'questions_json', 'answer_template', 'answers_json',
                       'enriched_dataset'}
        
        serialized_updates: Dict[str, Any] = {}
        for key, value in updates.items():
            if key in json_fields and value is not None and not isinstance(value, str):
                try:
                    serialized_updates[key] = json.dumps(value)
                except Exception:
                    serialized_updates[key] = value
            else:
                serialized_updates[key] = value
        
        set_clauses = [f"{column} = %s" for column in serialized_updates.keys()]
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        
        values = list(serialized_updates.values())
        values.append(job_id)
        
        query = f"""
            UPDATE job_postings
            SET {', '.join(set_clauses)}
            WHERE job_id = %s
        """
        
        with conn.cursor() as cursor:
            cursor.execute(query, values)
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"[PostgreSQL] Error updating enrichment for {job_id}: {e}")
        conn.rollback()
        return False
        
    finally:
        pool.putconn(conn)


def get_jobs_pending_enrichment(
    limit: Optional[int] = None,
    run_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetch Easy Apply jobs that need AI enrichment/answers."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        conditions = [
            "easy_apply = true",
            "(questions_json IS NOT NULL AND questions_json != '' AND questions_json != 'null')",
            "(processed IS NULL OR processed = false OR ai_enriched_at IS NULL OR ai_enriched_at < scraped_at)"
        ]
        params: List[Any] = []
        
        if run_id:
            conditions.append("run_id = %s")
            params.append(run_id)
        
        query = f"""
            SELECT * 
            FROM job_postings
            WHERE {' AND '.join(conditions)}
            ORDER BY scraped_at DESC
        """
        if limit:
            query += f" LIMIT {int(limit)}"
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
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
            
            jobs.append(job_dict)
        
        return jobs
        
    finally:
        pool.putconn(conn)


def update_answers_json(job_id: str, answers_json: str) -> bool:
    """Update answers_json for a job."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE job_postings
                SET answers_json = %s,
                    enriched_dataset = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
            """, [answers_json, answers_json, job_id])
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"[PostgreSQL] Error updating answers_json: {e}")
        conn.rollback()
        return False
        
    finally:
        pool.putconn(conn)


def update_is_applied(job_id: str, is_applied: bool = True) -> bool:
    """Update is_applied status for a job."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE job_postings
                SET is_applied = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
            """, [is_applied, job_id])
        
        conn.commit()
        print(f"[PostgreSQL] Updated is_applied={is_applied} for job {job_id}")
        return True
        
    except Exception as e:
        print(f"[PostgreSQL] Error updating is_applied: {e}")
        conn.rollback()
        return False
        
    finally:
        pool.putconn(conn)


def get_jobs_with_answers() -> List[str]:
    """Get list of job_ids that have AI-generated answers ready."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT job_id 
                FROM job_postings
                WHERE answers_json IS NOT NULL
                  AND answers_json != ''
                  AND answers_json != 'null'
            """)
            
            job_ids = [row[0] for row in cursor.fetchall()]
            print(f"[PostgreSQL] Found {len(job_ids)} jobs with answers")
            return job_ids
            
    finally:
        pool.putconn(conn)


def get_jobs_by_run_id(run_id: str) -> List[Dict[str, Any]]:
    """Get all jobs from a specific search run."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM job_postings WHERE run_id = %s", [run_id])
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
            
            jobs.append(job_dict)
        
        return jobs
        
    finally:
        pool.putconn(conn)


def query_jobs(
    easy_apply_only: bool = False,
    has_answers: bool = False,
    company: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Query jobs with various filters."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        where_clauses = []
        params = []
        
        if easy_apply_only:
            where_clauses.append("easy_apply = true")
        
        if has_answers:
            where_clauses.append("answers_json IS NOT NULL AND answers_json != ''")
        
        if company:
            where_clauses.append("company ILIKE %s")
            params.append(f"%{company}%")
        
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        query = f"""
            SELECT * FROM job_postings
            {where_sql}
            ORDER BY scraped_at DESC
            LIMIT %s
        """
        params.append(limit)
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
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
            
            jobs.append(job_dict)
        
        return jobs
        
    finally:
        pool.putconn(conn)


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
    """Save user profile to PostgreSQL and return profile_id."""
    import uuid
    from datetime import datetime
    
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        # Deactivate other profiles if this is active
        if is_active:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE user_profiles SET is_active = false")
        
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
        
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_profiles (
                    profile_id, profile_name, profile_type, is_active,
                    full_name, email, phone, phone_country,
                    linkedin_url, github, website,
                    location, title, summary, skills,
                    source_file, source_type, version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [
                profile_id,
                profile_name,
                'default',
                is_active,
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
        
        print(f"[PostgreSQL] Saved profile {profile_id} (active={is_active})")
        return profile_id
        
    finally:
        pool.putconn(conn)


def get_active_profile() -> Optional[Dict[str, Any]]:
    """Load the active profile from PostgreSQL."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM user_profiles 
                WHERE is_active = true 
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
            
    finally:
        pool.putconn(conn)


def get_profile_by_id(profile_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific profile by ID."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM user_profiles 
                WHERE profile_id = %s
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
            
    finally:
        pool.putconn(conn)


def get_profile_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get all profile versions ordered by creation date."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT 
                    profile_id, profile_name, profile_type, is_active,
                    full_name, title, source_file, source_type,
                    version, applications_count, success_rate,
                    created_at, updated_at, last_used_at
                FROM user_profiles 
                ORDER BY created_at DESC
                LIMIT %s
            """, [limit])
            
            rows = cursor.fetchall()
            if not rows:
                return []
            
            profiles = [dict(row) for row in rows]
            return profiles
            
    finally:
        pool.putconn(conn)


def set_active_profile(profile_id: str) -> bool:
    """Set a profile as the active profile."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        # Check if profile exists
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT profile_id FROM user_profiles WHERE profile_id = %s
            """, [profile_id])
            
            if not cursor.fetchone():
                return False
            
            # Deactivate all profiles
            cursor.execute("UPDATE user_profiles SET is_active = false")
            
            # Activate the specified profile
            cursor.execute("""
                UPDATE user_profiles 
                SET is_active = true, updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = %s
            """, [profile_id])
        
        conn.commit()
        
        print(f"[PostgreSQL] Set profile {profile_id} as active")
        return True
        
    finally:
        pool.putconn(conn)


def update_profile_usage(profile_id: str, success: bool = False) -> None:
    """Update profile usage statistics after an application."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        # Get current stats
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT applications_count, success_rate 
                FROM user_profiles 
                WHERE profile_id = %s
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
            cursor.execute("""
                UPDATE user_profiles 
                SET 
                    applications_count = %s,
                    success_rate = %s,
                    last_used_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE profile_id = %s
            """, [new_count, new_rate, profile_id])
        
        conn.commit()
        
    finally:
        pool.putconn(conn)


# =============================================================================
# Fit Analysis Helper Functions
# =============================================================================

def get_fit_summary(run_id: Optional[str] = None) -> Dict[str, Any]:
    """Get summary statistics for job fit analysis."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        with conn.cursor() as cursor:
            if run_id:
                query = """
                    SELECT 
                        COUNT(*) as total_jobs,
                        SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as good_fits,
                        SUM(CASE WHEN good_fit = false THEN 1 ELSE 0 END) as bad_fits,
                        SUM(CASE WHEN good_fit IS NULL THEN 1 ELSE 0 END) as not_analyzed,
                        ROUND(AVG(fit_score)::numeric, 3) as avg_fit_score,
                        ROUND(MIN(fit_score)::numeric, 3) as min_fit_score,
                        ROUND(MAX(fit_score)::numeric, 3) as max_fit_score
                    FROM job_postings
                    WHERE run_id = %s
                """
                cursor.execute(query, [run_id])
            else:
                query = """
                    SELECT 
                        COUNT(*) as total_jobs,
                        SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as good_fits,
                        SUM(CASE WHEN good_fit = false THEN 1 ELSE 0 END) as bad_fits,
                        SUM(CASE WHEN good_fit IS NULL THEN 1 ELSE 0 END) as not_analyzed,
                        ROUND(AVG(fit_score)::numeric, 3) as avg_fit_score,
                        ROUND(MIN(fit_score)::numeric, 3) as min_fit_score,
                        ROUND(MAX(fit_score)::numeric, 3) as max_fit_score
                    FROM job_postings
                """
                cursor.execute(query)
            
            row = cursor.fetchone()
            if not row:
                return {}
            
            return {
                "total_jobs": row[0] or 0,
                "good_fits": row[1] or 0,
                "bad_fits": row[2] or 0,
                "not_analyzed": row[3] or 0,
                "avg_fit_score": float(row[4]) if row[4] else None,
                "min_fit_score": float(row[5]) if row[5] else None,
                "max_fit_score": float(row[6]) if row[6] else None,
                "good_fit_rate": round((row[1] or 0) / (row[0] or 1), 3)
            }
            
    finally:
        pool.putconn(conn)


def get_good_fit_jobs(
    run_id: Optional[str] = None,
    min_fit_score: float = 0.0,
    easy_apply_only: bool = True,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get jobs that are good fits for the user profile."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        conditions = ["good_fit = true"]
        params = []
        
        if run_id:
            conditions.append("run_id = %s")
            params.append(run_id)
        
        if min_fit_score > 0:
            conditions.append("fit_score >= %s")
            params.append(min_fit_score)
        
        if easy_apply_only:
            conditions.append("easy_apply = true")
        
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
            LIMIT %s
        """
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        
        if not rows:
            return []
        
        jobs = [dict(row) for row in rows]
        return jobs
        
    finally:
        pool.putconn(conn)


def get_bad_fit_jobs(
    run_id: Optional[str] = None,
    max_fit_score: float = 1.0,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get jobs that are bad fits (for analysis/debugging)."""
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        conditions = ["good_fit = false"]
        params = []
        
        if run_id:
            conditions.append("run_id = %s")
            params.append(run_id)
        
        if max_fit_score < 1.0:
            conditions.append("fit_score <= %s")
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
            LIMIT %s
        """
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        
        if not rows:
            return []
        
        jobs = [dict(row) for row in rows]
        return jobs
        
    finally:
        pool.putconn(conn)


def update_job_fit_analysis(
    job_ids: Union[str, List[str]],
    good_fit: Optional[bool] = None,
    fit_score: Optional[float] = None
) -> Dict[str, Any]:
    """Update fit analysis fields for one or more jobs."""
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
    
    pool = _get_connection_pool()
    conn = pool.getconn()
    
    try:
        # Build UPDATE query dynamically
        updates = []
        params = []
        
        if good_fit is not None:
            updates.append("good_fit = %s")
            params.append(good_fit)
        
        if fit_score is not None:
            updates.append("fit_score = %s")
            params.append(fit_score)
        
        # Always update timestamp
        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        # Add job_ids to params
        params.append(job_ids)
        
        query = f"""
            UPDATE job_postings
            SET {', '.join(updates)}
            WHERE job_id = ANY(%s)
        """
        
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            updated_count = cursor.rowcount
        
        conn.commit()
        
        print(f"[PostgreSQL] Updated fit analysis for {updated_count} jobs")
        
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
        print(f"[PostgreSQL] Error updating fit analysis: {e}")
        conn.rollback()
        return {
            "success": False,
            "error": str(e),
            "updated_count": 0
        }
        
    finally:
        pool.putconn(conn)
