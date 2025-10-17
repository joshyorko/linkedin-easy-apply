"""
Database abstraction layer for LinkedIn job storage.

Supports both SQLite (embedded) and PostgreSQL (production) backends.
Backend selection via DATABASE_TYPE environment variable:
- DATABASE_TYPE=sqlite (default) - Embedded SQLite database
- DATABASE_TYPE=postgres - PostgreSQL database

SQLite Configuration:
- SQLITE_PATH: Custom database file location (default: ./linkedin_jobs.sqlite)

PostgreSQL Configuration:
- DATABASE_URL: Full connection string (preferred), OR
- DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD: Individual parameters
"""
from __future__ import annotations
import os

# Determine which backend to use
_database_type = os.getenv("DATABASE_TYPE", "sqlite").lower()

if _database_type == "postgres":
    print("[Database] Using PostgreSQL backend")
    from .db_postgres import (
        get_db_path,
        get_connection,
        write_jobs,
        read_job_by_id,
        update_job_enrichment,
        get_jobs_pending_enrichment,
        update_answers_json,
        update_is_applied,
        get_jobs_with_answers,
        get_jobs_by_run_id,
        query_jobs,
        read_easy_apply_answers_by_job_id,
        get_job_ids_with_generated_answers,
        save_profile_to_db,
        get_active_profile,
        get_profile_by_id,
        get_profile_history,
        set_active_profile,
        update_profile_usage,
        get_fit_summary,
        get_good_fit_jobs,
        get_bad_fit_jobs,
        update_job_fit_analysis,
    )
else:
    # Default to SQLite
    if _database_type != "sqlite":
        print(f"[Database] Unknown DATABASE_TYPE '{_database_type}', defaulting to SQLite")
    else:
        print("[Database] Using SQLite backend")
    
    from .db_sqlite import (
    get_db_path,
    get_connection,
    write_jobs,
    read_job_by_id,
    update_job_enrichment,
    get_jobs_pending_enrichment,
    update_answers_json,
    update_is_applied,
    get_jobs_with_answers,
    get_jobs_by_run_id,
    query_jobs,
    read_easy_apply_answers_by_job_id,
    get_job_ids_with_generated_answers,
    save_profile_to_db,
    get_active_profile,
    get_profile_by_id,
    get_profile_history,
    set_active_profile,
    update_profile_usage,
    get_fit_summary,
    get_good_fit_jobs,
    get_bad_fit_jobs,
    update_job_fit_analysis,
    )

# Export all functions
__all__ = [
    "get_db_path",
    "get_connection",
    "write_jobs",
    "read_job_by_id",
    "update_job_enrichment",
    "get_jobs_pending_enrichment",
    "update_answers_json",
    "update_is_applied",
    "get_jobs_with_answers",
    "get_jobs_by_run_id",
    "query_jobs",
    "read_easy_apply_answers_by_job_id",
    "get_job_ids_with_generated_answers",
    "save_profile_to_db",
    "get_active_profile",
    "get_profile_by_id",
    "get_profile_history",
    "set_active_profile",
    "update_profile_usage",
    "get_fit_summary",
    "get_good_fit_jobs",
    "get_bad_fit_jobs",
    "update_job_fit_analysis",
]
