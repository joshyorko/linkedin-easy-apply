"""
Response and data models for LinkedIn Easy Apply actions.

Each action returns a typed Response subclass instead of a bare Response(result={...})
so that fields are validated, documented, and visible to MCP/tool consumers.
"""
from sema4ai.actions import Response
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import Field
import json


# ── Data Models ────────────────────────────────────────────────────────────


class LinkedInJob(Response):
    """LinkedIn job data model with comprehensive fields for scraping and AI enrichment"""

    # Core job information
    title: str = ""
    company: str = ""
    job_id: str = ""
    job_url: str = ""

    # Location details
    location_raw: str = ""
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_country: Optional[str] = None
    location_type: Optional[str] = None  # Remote, Hybrid, On-site

    # Company information
    company_size: Optional[str] = None
    industry: Optional[str] = None
    company_description: Optional[str] = None
    company_logo_url: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    company_location: Optional[str] = None

    # Application details
    easy_apply: bool = False
    is_viewed: bool = False
    is_applied: bool = False
    applicant_count: Optional[str] = None
    status_message: Optional[str] = None
    promoted_by_hirer: bool = False

    # Job requirements
    experience_level: Optional[str] = None
    seniority_level: Optional[str] = None
    education_requirements: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    years_experience_required: Optional[str] = None

    # Job details
    job_function: Optional[str] = None
    employment_type: Optional[str] = None
    remote_work_policy: Optional[str] = None
    application_deadline: Optional[str] = None
    external_apply_url: Optional[str] = None

    # Compensation
    salary_range: Optional[str] = None
    benefits: List[str] = Field(default_factory=list)
    compensation_raw: str = ""

    # Engagement metrics
    views_count: Optional[str] = None
    is_saved: bool = False
    urgently_hiring: bool = False
    fair_chance_employer: bool = False
    job_reposted: bool = False

    # Metadata
    date_posted: Optional[str] = None
    job_type: Optional[str] = None
    verified_company: bool = False

    # Job description
    job_description: str = ""

    # Form data for automation
    form_snapshot_url: str = ""
    form_elements: Dict[str, Any] = Field(default_factory=dict)
    questions_json: Optional[str] = None
    answer_template: Optional[str] = None
    answers_json: Optional[str] = None
    enriched_dataset: Optional[str] = None

    # Raw data for debugging
    playwright_ref: str = ""

    # Processing flags
    processed: bool = False
    good_fit: Optional[bool] = None
    fit_score: Optional[float] = None
    priority: Optional[int] = None

    # Work item tracking
    work_item_id: Optional[str] = None
    run_id: Optional[str] = None

    def to_db_record(self) -> Dict[str, Any]:
        """Convert to database-ready dictionary for SQLite/PostgreSQL"""
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "job_url": self.job_url,
            "easy_apply": self.easy_apply,
            "location_raw": self.location_raw,
            "location_city": self.location_city,
            "location_state": self.location_state,
            "location_country": self.location_country,
            "location_type": self.location_type,
            "company_size": self.company_size,
            "industry": self.industry,
            "company_description": self.company_description,
            "company_logo_url": self.company_logo_url,
            "company_linkedin_url": self.company_linkedin_url,
            "company_location": self.company_location,
            "is_viewed": self.is_viewed,
            "is_applied": self.is_applied,
            "applicant_count": self.applicant_count,
            "status_message": self.status_message,
            "promoted_by_hirer": self.promoted_by_hirer,
            "experience_level": self.experience_level,
            "seniority_level": self.seniority_level,
            "education_requirements": self.education_requirements,
            "required_skills": json.dumps(self.required_skills) if self.required_skills else None,
            "years_experience_required": self.years_experience_required,
            "job_function": self.job_function,
            "employment_type": self.employment_type,
            "remote_work_policy": self.remote_work_policy,
            "application_deadline": self.application_deadline,
            "external_apply_url": self.external_apply_url,
            "salary_range": self.salary_range,
            "benefits": json.dumps(self.benefits) if self.benefits else None,
            "compensation_raw": self.compensation_raw,
            "views_count": self.views_count,
            "is_saved": self.is_saved,
            "urgently_hiring": self.urgently_hiring,
            "fair_chance_employer": self.fair_chance_employer,
            "job_reposted": self.job_reposted,
            "date_posted": self.date_posted,
            "job_type": self.job_type,
            "verified_company": self.verified_company,
            "job_description": self.job_description,
            "form_snapshot_url": self.form_snapshot_url,
            "form_elements": json.dumps(self.form_elements) if self.form_elements else None,
            "questions_json": self.questions_json,
            "answer_template": self.answer_template,
            "answers_json": self.answers_json,
            "enriched_dataset": self.enriched_dataset or self.answers_json,
            "processed": self.processed,
            "good_fit": self.good_fit,
            "fit_score": self.fit_score,
            "priority": self.priority,
            "work_item_id": self.work_item_id,
            "run_id": self.run_id,
            "raw_html": getattr(self, 'raw_html', ''),
            "playwright_ref": self.playwright_ref,
            "scraped_at": datetime.now().isoformat()
        }


# ── Search ──────────────────────────────────────────────────────────────────


class SearchResponse(Response[str]):
    """Response from search_linkedin_easy_apply."""
    run_id: str = ""
    search_query: str = ""
    job_ids_found: List[str] = Field(default_factory=list)
    easy_apply_job_ids: List[str] = Field(default_factory=list)
    total_jobs: int = 0
    easy_apply_count: int = 0
    db_records_written: int = 0
    csv_exported: str = ""
    pending_enrichment_job_ids: List[str] = Field(default_factory=list)
    pending_enrichment_count: int = 0
    filters: Dict[str, bool] = Field(default_factory=dict)
    log_file: str = ""


class ParallelSearchResponse(SearchResponse):
    """Response from parallel_search_linkedin_easy_apply."""
    failed_job_ids: List[str] = Field(default_factory=list)
    failed_jobs_details: Dict[str, str] = Field(default_factory=dict)
    failed_count: int = 0
    parallel_workers_used: int = 0


# ── Enrichment ──────────────────────────────────────────────────────────────


class EnrichmentResponse(Response[str]):
    """Response from enrich_and_generate_answers / generate_answers_for_run / reenrich_jobs."""
    success: bool = False
    run_id: Optional[str] = None
    processed: int = 0
    enriched: int = 0
    answers_generated: int = 0
    skipped: List[Dict[str, Any]] = Field(default_factory=list)
    failed: List[Dict[str, Any]] = Field(default_factory=list)
    profile_id: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)
    processed_job_ids: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    force_regenerate: Optional[bool] = None
    job_ids: Optional[List[str]] = None


class JobReadyResponse(Response[str]):
    """Response from check_which_jobs_ready."""
    job_ids_ready: List[str] = Field(default_factory=list)
    count: int = 0
    filtering_stats: Dict[str, int] = Field(default_factory=dict)


class FitAnalysisResponse(Response[str]):
    """Response from get_job_fit_analysis."""
    success: bool = False
    run_id: Optional[str] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
    good_fits_sample: List[Dict[str, Any]] = Field(default_factory=list)
    bad_fits_sample: List[Dict[str, Any]] = Field(default_factory=list)


class FitStatusUpdateResponse(Response[str]):
    """Response from update_job_fit_status."""
    success: bool = False
    updated_count: int = 0
    requested_job_count: int = 0
    changes_applied: Dict[str, Any] = Field(default_factory=dict)
    job_ids: List[str] = Field(default_factory=list)
    verification_sample: Optional[Dict[str, Any]] = None
    next_steps: str = ""


# ── Profile ─────────────────────────────────────────────────────────────────


class ProfileParseResponse(Response[str]):
    """Response from parse_resume_and_save_profile."""
    success: bool = False
    profile: Optional[Dict[str, Any]] = None
    profile_id: Optional[str] = None
    saved_to: Optional[str] = None
    source_file: Optional[str] = None


class ProfileHistoryResponse(Response[str]):
    """Response from get_profile_history_list."""
    success: bool = False
    total_profiles: int = 0
    active_profile: Optional[Dict[str, Any]] = None
    profiles: List[Dict[str, Any]] = Field(default_factory=list)


class ProfileSkillsResponse(Response[str]):
    """Response from update_profile_skills."""
    success: bool = False
    profile_id: Optional[str] = None
    full_name: Optional[str] = None
    old_skills_count: int = 0
    new_skills_count: int = 0
    skills: List[str] = Field(default_factory=list)


class ProfileEnrichResponse(Response[str]):
    """Response from enrich_user_profile."""
    success: bool = False
    profile_id: Optional[str] = None
    full_name: Optional[str] = None
    fields_updated: List[str] = Field(default_factory=list)


# ── Apply ───────────────────────────────────────────────────────────────────


class ApplyJobResponse(Response[str]):
    """Response from apply_to_single_job."""
    success: bool = False
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    submitted: Optional[bool] = None
    verified: Optional[bool] = None
    verification_message: Optional[str] = None
    allow_submit: bool = False
    steps_completed: Optional[int] = None
    fields_filled: Optional[int] = None
    reached_submit: Optional[bool] = None
    used_enriched_answers: bool = False
    good_fit: Optional[bool] = None
    fit_score: Optional[float] = None
    log_file: str = ""


class BatchApplyResponse(Response[str]):
    """Response from batch_apply_by_run_id."""
    success: bool = False
    run_id: str = ""
    total_jobs: int = 0
    applied: int = 0
    skipped: int = 0
    failed: int = 0
    submitted: bool = False
    results: List[Dict[str, Any]] = Field(default_factory=list)


class OneoffApplyResponse(Response[str]):
    """Response from apply_to_job_by_url."""
    success: bool = False
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    company: Optional[str] = None
    submitted: Optional[bool] = None
    allow_submit: bool = False
    steps_completed: Optional[int] = None
    fields_filled: Optional[int] = None
    reached_submit: Optional[bool] = None
    questions_scraped: int = 0
    answers_generated: int = 0
    confidence: float = 0.0
    saved_to_database: bool = False
    easy_apply: Optional[bool] = None
    log_file: str = ""


# ── Server / Database ──────────────────────────────────────────────────────


class QueryDatabaseResponse(Response[str]):
    """Response from query_database."""
    success: bool = False
    query: str = ""
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0


class RunStatusResponse(Response[str]):
    """Response from check_run_status."""
    success: bool = False
    run_id: str = ""
    status: Optional[int] = None
    status_name: str = ""
    action_id: Optional[str] = None
    start_time: Optional[str] = None
    run_time: Optional[float] = None
    log_url: Optional[str] = None
    error_message: Optional[str] = None
    hint: Optional[str] = None


class RunListResponse(Response[str]):
    """Response from list_runs."""
    success: bool = False
    runs: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    filters: Dict[str, Any] = Field(default_factory=dict)


class CancelRunResponse(Response[str]):
    """Response from cancel_run."""
    success: bool = False
    run_id: str = ""
    action_name: Optional[str] = None
    log_url: Optional[str] = None
    current_status: Optional[int] = None


class ActionsListResponse(Response[str]):
    """Response from list_available_actions."""
    success: bool = False
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    server_url: str = ""


# ── Browser ─────────────────────────────────────────────────────────────────


class BrowserContextResponse(Response[str]):
    """Response from set_browser_context."""
    success: Optional[bool] = None
    status: str = "unknown"
    current_url: Optional[str] = None
    recommendation: Optional[str] = None
    log_file: str = ""
