"""
Resume parser for extracting user profile from PDF/DOCX files.

Uses Sema4AI's file upload API + OpenAI to extract structured profile data.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Dict, Optional
from pathlib import Path

try:
    from sema4ai.actions import chat
    from sema4ai_http import get as http_get
    from openai import OpenAI
    from pypdf import PdfReader
    from pydantic import BaseModel
except ImportError:
    raise ImportError(
        "Missing dependencies. Run: pip install pypdf openai"
    )

from .profile import UserProfile
from .prompts import (
    RESUME_PARSING_SYSTEM_PROMPT,
    build_resume_parsing_prompt,
    get_reasoning_effort_for_model
)

logger = logging.getLogger(__name__)


class SkillCategory(BaseModel):
    """Categorized skills for better job matching"""
    category: str  # e.g., "Programming Languages", "Cloud Platforms", "DevOps Tools"
    skills: list[str]
    proficiency: Optional[str] = None  # "Expert", "Advanced", "Intermediate"


class WorkExperience(BaseModel):
    """Detailed work history with achievements and metrics"""
    company: str
    title: str
    location: Optional[str] = None
    start_date: Optional[str] = None  # "June 2023" or "2023-06"
    end_date: Optional[str] = None    # "Present" or "2024-03"
    is_current: bool = False
    
    # Critical additions for better job matching:
    responsibilities: list[str] = []  # Bullet points from resume
    achievements: list[str] = []  # Quantifiable wins with metrics
    technologies: list[str] = []  # Tech stack used in this role
    team_size: Optional[str] = None


class Project(BaseModel):
    """Open-source and personal projects"""
    name: str
    description: str
    role: Optional[str] = None  # "Creator", "Maintainer", "Contributor"
    url: Optional[str] = None  # GitHub/portfolio link
    technologies: list[str] = []
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    highlights: list[str] = []  # Key achievements


class Education(BaseModel):
    """Education details"""
    institution: str
    degree: str  # "B.A. in English", "M.S. in Computer Science"
    field_of_study: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None
    honors: Optional[str] = None


class Certification(BaseModel):
    """Professional certifications and credentials"""
    name: str
    issuing_organization: str
    issue_date: Optional[str] = None
    expiration_date: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None


class ResumeProfile(BaseModel):
    """Enhanced structured output model for comprehensive resume parsing.
    
    Captures detailed work history, projects, categorized skills, and achievements.
    Designed to extract maximum value from multi-page resumes with complex formatting.
    """
    # Contact Information
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    
    # Professional Identity
    current_title: Optional[str] = None  # Most recent job title
    target_titles: list[str] = []  # All roles you're qualified for
    professional_summary: Optional[str] = None  # Elevator pitch
    
    # Skills (Categorized for better matching!)
    skill_categories: list[SkillCategory] = []
    core_competencies: list[str] = []  # Top 5-10 most important skills
    
    # Experience (Detailed with achievements!)
    work_experience: list[WorkExperience] = []
    total_years_experience: Optional[int] = None
    
    # Projects & Open Source (CRITICAL - often missed!)
    projects: list[Project] = []
    open_source_contributions: list[str] = []  # Brief descriptions
    
    # Education
    education: list[Education] = []
    
    # Certifications
    certifications: list[Certification] = []
    
    # Achievements & Metrics (For "tell me about a time" questions)
    key_achievements: list[str] = []  # Quantifiable wins across all roles
    
    # Additional
    languages: Optional[list[Dict[str, str]]] = None  # [{"language": "English", "proficiency": "Native"}]
    publications: list[str] = []
    awards: list[str] = []


def extract_text_from_pdf(file_path: str) -> str:
    """Extract all text from a PDF file."""
    try:
        reader = PdfReader(file_path)
        text_parts = []
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        
        full_text = "\n".join(text_parts)
        logger.info(f"[Resume] Extracted {len(full_text)} characters from PDF")
        return full_text
    except Exception as e:
        logger.error(f"[Resume] Error extracting PDF text: {e}")
        raise


def parse_resume_with_openai(resume_text: str, api_key: Optional[str] = None, model: Optional[str] = None) -> ResumeProfile:
    """
    Parse resume text using OpenAI structured outputs.
    
    Args:
        resume_text: Raw text extracted from resume
        api_key: OpenAI API key (defaults to env)
        model: Model to use (defaults to gpt-5-nano for cost efficiency)
    
    Returns:
        ResumeProfile with extracted structured data
    """
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY required for resume parsing")
    
    model = model or os.getenv("OPENAI_MODEL", "gpt-5-nano")
    client = OpenAI(api_key=api_key)
    
    logger.info(f"[Resume] Parsing with {model}")
    logger.info(f"[Resume] Resume text length: {len(resume_text)} chars, ~{len(resume_text.split())} words")
    
    # Build prompt using centralized prompt builder
    max_chars = 15000  # ~3750 tokens
    user_prompt = build_resume_parsing_prompt(resume_text, max_chars=max_chars)
    
    try:
        # Get reasoning effort for model (optional env override)
        reasoning_effort = get_reasoning_effort_for_model(model)

        parse_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": RESUME_PARSING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": ResumeProfile,
        }
        if reasoning_effort:
            parse_kwargs["reasoning_effort"] = reasoning_effort

        completion = client.beta.chat.completions.parse(**parse_kwargs)
        
        profile = completion.choices[0].message.parsed
        if profile is None:
            raise ValueError("OpenAI returned no parsed profile")
        logger.info(f"[Resume] Successfully parsed profile: {profile.full_name}")
        return profile
        
    except Exception as e:
        logger.error(f"[Resume] OpenAI parsing error: {e}")
        raise


def resume_profile_to_user_profile(resume_profile: ResumeProfile) -> UserProfile:
    """Convert enhanced ResumeProfile to UserProfile dict format.
    
    Flattens the rich structured data into the current database schema.
    TODO: Update database schema to store full structured data.
    """
    import json
    
    # Extract years of experience
    years_exp = resume_profile.total_years_experience
    if years_exp is None and resume_profile.work_experience:
        # Heuristic: count jobs, assume ~2.5 years each
        years_exp = len(resume_profile.work_experience) * 2
    
    # Get current company from most recent job
    current_company = ""
    if resume_profile.work_experience:
        current_company = resume_profile.work_experience[0].company
    
    # Flatten categorized skills into simple list (for now)
    all_skills = []
    for category in resume_profile.skill_categories:
        all_skills.extend(category.skills)
    # Add core competencies if not already included
    for skill in resume_profile.core_competencies:
        if skill not in all_skills:
            all_skills.append(skill)
    
    # Build rich summary from professional_summary + key achievements
    summary_parts = []
    if resume_profile.professional_summary:
        summary_parts.append(resume_profile.professional_summary)
    if resume_profile.key_achievements:
        summary_parts.append("\n\nKey Achievements:")
        for achievement in resume_profile.key_achievements[:3]:  # Top 3
            summary_parts.append(f"• {achievement}")
    summary = "\n".join(summary_parts) if summary_parts else ""
    
    # Prepare extended data as JSON strings for future database migration
    extended_data = {
        "skill_categories": [cat.model_dump() for cat in resume_profile.skill_categories],
        "work_experience": [exp.model_dump() for exp in resume_profile.work_experience],
        "projects": [proj.model_dump() for proj in resume_profile.projects],
        "education": [edu.model_dump() for edu in resume_profile.education],
        "certifications": [cert.model_dump() for cert in resume_profile.certifications],
        "key_achievements": resume_profile.key_achievements,
        "open_source_contributions": resume_profile.open_source_contributions,
        "target_titles": resume_profile.target_titles,
    }
    
    return {
        # Basic contact info
        "full_name": resume_profile.full_name or "",
        "email": resume_profile.email or "",
        "phone": resume_profile.phone or "",
        "phone_country": "US",  # Default, user can update
        "linkedin_url": resume_profile.linkedin_url or "",
        "github": resume_profile.github or "",
        "website": resume_profile.website or "",
        "location": resume_profile.location or "",
        # Professional identity
        "title": resume_profile.current_title or "",
        "current_company": current_company,
        "years_experience": years_exp or 0,
        "summary": summary,
        # Skills (flattened for now)
        "skills": all_skills,
        # Extended data (JSON strings for custom_answers field or future schema)
        "_extended_data": json.dumps(extended_data),  # Store for future use
    }


def _download_resume_from_url(url: str, filename: str) -> str:
    """Helper: Download resume from URL using sema4ai_http.
    
    Args:
        url: URL to download from
        filename: Target filename to save as
    
    Returns:
        Path to downloaded file
    """
    print(f"[Resume] Downloading from URL: {url}")
    response = http_get(url)
    response.raise_for_status()
    
    # Use temp directory for container compatibility
    import tempfile
    temp_dir = tempfile.gettempdir()
    file_path = Path(temp_dir) / filename
    
    # Support several possible response attributes depending on HTTP client
    bytes_content = getattr(response, "data", None)
    if bytes_content is None:
        bytes_content = getattr(response, "content", None)
    # Some wrappers expose a read() method
    if bytes_content is None and hasattr(response, "read"):
        try:
            bytes_content = response.read()
        except Exception:
            bytes_content = None

    if bytes_content is None:
        raise RuntimeError("[Resume] Download response contains no data")

    file_path.write_bytes(bytes_content)
    print(f"[Resume] Downloaded to: {file_path}")
    return str(file_path)

def load_resume_from_file(filename: str) -> str:
    """
    Load resume file from local path.
    
    Args:
        filename: Full path to the resume file
    
    Returns:
        Path to the file
    """
    # Just verify the file exists and return the path
    if os.path.exists(filename):
        logger.info(f"[Resume] Using file: {filename}")
        return filename
    else:
        raise FileNotFoundError(f"Resume file not found: {filename}")


def parse_resume_from_file(
    filename: str,
    save_profile: bool = True
) -> UserProfile:
    """
    Complete workflow: Load resume file → Extract text → Parse with OpenAI → Save.
    
    Args:
        filename: Full path to resume file
        save_profile: If True, save to database
    
    Returns:
        UserProfile dict ready to use
    """
    import time
    start_time = time.time()
    
    # Step 1: Get the file
    logger.info(f"[Resume] Step 1: Loading file {filename}")
    step_start = time.time()
    file_path = load_resume_from_file(filename)
    logger.info(f"[Resume] Step 1 complete in {time.time() - step_start:.2f}s")
    
    # Step 2: Extract text (currently only PDF, can extend to DOCX)
    logger.info(f"[Resume] Step 2: Extracting text from PDF")
    step_start = time.time()
    if file_path.lower().endswith('.pdf'):
        resume_text = extract_text_from_pdf(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path}. Currently only PDF is supported.")
    logger.info(f"[Resume] Step 2 complete in {time.time() - step_start:.2f}s - Extracted {len(resume_text)} chars")
    
    # Step 3: Parse with OpenAI
    logger.info(f"[Resume] Step 3: Parsing with OpenAI (this may take 1-3 seconds)")
    step_start = time.time()
    resume_profile = parse_resume_with_openai(resume_text)
    logger.info(f"[Resume] Step 3 complete in {time.time() - step_start:.2f}s")
    
    # Step 4: Convert to UserProfile format
    logger.info(f"[Resume] Step 4: Converting to UserProfile format")
    user_profile = resume_profile_to_user_profile(resume_profile)
    
    # Step 5: Save to database (single source of truth)
    logger.info(f"[Resume] Step 5: Saving to database")
    step_start = time.time()
    if save_profile:
        try:
            from .db import save_profile_to_db
            profile_id = save_profile_to_db(
                profile=user_profile,
                source_file=filename,
                source_type="resume_parser",
                is_active=True  # Mark as active profile
            )
            logger.info(f"[Resume] Saved profile to database: {profile_id}")
        except Exception as e:
            logger.error(f"[Resume] Failed to save to database: {e}")
            raise  # Make this a critical error
    logger.info(f"[Resume] Step 5 complete in {time.time() - step_start:.2f}s")
    
    total_time = time.time() - start_time
    logger.info(f"[Resume] ✅ Total time: {total_time:.2f}s")
    
    return user_profile

