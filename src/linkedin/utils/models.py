from sema4ai.actions import Response
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import Field
import json


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
    
    # Company information (NEW)
    company_size: Optional[str] = None  # e.g., "1-10 employees", "10,001+ employees"
    industry: Optional[str] = None  # e.g., "Technology", "Healthcare"
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
    
    # Job requirements (NEW)
    experience_level: Optional[str] = None  # Entry level, Mid-Senior, Executive
    seniority_level: Optional[str] = None  # Internship, Entry, Associate, Mid-Senior, Director, Executive
    education_requirements: Optional[str] = None  # Bachelor's, Master's, etc.
    required_skills: List[str] = Field(default_factory=list)
    years_experience_required: Optional[str] = None  # e.g., "3-5 years"
    
    # Job details (ENHANCED)
    job_function: Optional[str] = None  # Engineering, Sales, Marketing, etc.
    employment_type: Optional[str] = None  # More detailed than job_type
    remote_work_policy: Optional[str] = None  # Detailed remote policy
    application_deadline: Optional[str] = None
    external_apply_url: Optional[str] = None  # For non-Easy Apply jobs
    
    # Compensation
    salary_range: Optional[str] = None
    benefits: List[str] = Field(default_factory=list)
    compensation_raw: str = ""
    
    # Engagement metrics (NEW)
    views_count: Optional[str] = None
    is_saved: bool = False
    urgently_hiring: bool = False
    fair_chance_employer: bool = False
    job_reposted: bool = False
    
    # Metadata
    date_posted: Optional[str] = None
    job_type: Optional[str] = None  # Keep for backward compatibility
    verified_company: bool = False

    # Job description (About the job section)
    job_description: str = ""
    
    # Form data for automation
    form_snapshot_url: str = ""
    form_elements: Dict[str, Any] = Field(default_factory=dict)
    questions_json: Optional[str] = None
    # AI/Agent artifacts
    answer_template: Optional[str] = None  # JSON mapping of question keys -> answer placeholders/metadata
    answers_json: Optional[str] = None     # JSON mapping filled by LLM/agent with concrete answers
    # Optional: canonical field name for downstream tools expecting "enriched_dataset"
    enriched_dataset: Optional[str] = None  # often same as answers_json
    
    # Raw data for debugging
    #raw_html: str = ""
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
            # Core fields
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "job_url": self.job_url,
            "easy_apply": self.easy_apply,
            
            # Location
            "location_raw": self.location_raw,
            "location_city": self.location_city,
            "location_state": self.location_state,
            "location_country": self.location_country,
            "location_type": self.location_type,
            
            # Company information
            "company_size": self.company_size,
            "industry": self.industry,
            "company_description": self.company_description,
            "company_logo_url": self.company_logo_url,
            "company_linkedin_url": self.company_linkedin_url,
            "company_location": self.company_location,
            
            # Application status
            "is_viewed": self.is_viewed,
            "is_applied": self.is_applied,
            "applicant_count": self.applicant_count,
            "status_message": self.status_message,
            "promoted_by_hirer": self.promoted_by_hirer,
            
            # Job requirements
            "experience_level": self.experience_level,
            "seniority_level": self.seniority_level,
            "education_requirements": self.education_requirements,
            "required_skills": json.dumps(self.required_skills) if self.required_skills else None,
            "years_experience_required": self.years_experience_required,
            
            # Job details
            "job_function": self.job_function,
            "employment_type": self.employment_type,
            "remote_work_policy": self.remote_work_policy,
            "application_deadline": self.application_deadline,
            "external_apply_url": self.external_apply_url,
            
            # Compensation
            "salary_range": self.salary_range,
            "benefits": json.dumps(self.benefits) if self.benefits else None,
            "compensation_raw": self.compensation_raw,
            
            # Engagement metrics
            "views_count": self.views_count,
            "is_saved": self.is_saved,
            "urgently_hiring": self.urgently_hiring,
            "fair_chance_employer": self.fair_chance_employer,
            "job_reposted": self.job_reposted,
            
            # Metadata
            "date_posted": self.date_posted,
            "job_type": self.job_type,
            "verified_company": self.verified_company,
            "job_description": self.job_description,
            
            # Form data
            "form_snapshot_url": self.form_snapshot_url,
            "form_elements": json.dumps(self.form_elements) if self.form_elements else None,
            "questions_json": self.questions_json,
            "answer_template": self.answer_template,
            "answers_json": self.answers_json,
            "enriched_dataset": self.enriched_dataset or self.answers_json,
            
            # Processing fields
            "processed": self.processed,
            "good_fit": self.good_fit,
            "fit_score": self.fit_score,
            "priority": self.priority,
            
            # Tracking
            "work_item_id": self.work_item_id,
            "run_id": self.run_id,
            
            # Raw data
            "raw_html": getattr(self, 'raw_html', ''),
            "playwright_ref": self.playwright_ref,
            "scraped_at": datetime.now().isoformat()
        }



class LinkedInSearchResult(Response):
    """Streamlined search result focused on apply workflow handoff"""
    
    # Essential fields for apply workflow - prominently displayed
    apply_inputs: List[Dict[str, Optional[str]]] = Field(
        default_factory=list,
        description="Minimal payload for apply_linkedin_easy_apply: [{job_id, job_url, answers_json}]"
    )
    run_id: str = ""
    
    # Still capture everything for CSV/DB but focus response on apply_inputs
    search_query: str = ""
    jobs: List[LinkedInJob] = Field(default_factory=list)
    total_jobs_found: int = 0
    jobs_with_easy_apply: int = 0
    search_url: str = ""
    search_filters: Dict[str, Any] = Field(default_factory=dict)
    search_metadata: Dict[str, Any] = Field(default_factory=dict)
        
    def to_summary(self) -> Dict[str, Any]:
        """Create a summary for status reporting"""
        return {
            "run_id": self.run_id,
            "search_query": self.search_query,
            "total_jobs_found": self.total_jobs_found,
            "jobs_with_easy_apply": self.jobs_with_easy_apply,
            "jobs_scraped": len(self.jobs),
            "search_url": self.search_url,
            "search_filters": self.search_filters,
            "timestamp": datetime.now().isoformat()
        }


