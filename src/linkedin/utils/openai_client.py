"""
OpenAI client for enriching LinkedIn job data and generating Easy Apply form answers.

This module provides integration with OpenAI Python SDK to:
1. Validate and refine scraped job data before database insertion
2. Generate personalized answers for Easy Apply forms
3. Use Structured Outputs for reliable JSON responses
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Union
import logging

from .prompts import (
    JOB_ENRICHMENT_SYSTEM_PROMPT,
    FORM_ANSWERING_SYSTEM_PROMPT,
    build_job_enrichment_prompt,
    build_form_answering_prompt,
    get_reasoning_effort_for_model,
)

try:
    from openai import OpenAI
    from pydantic import BaseModel, Field
except ImportError:
    raise ImportError(
        "OpenAI SDK not installed. Run: pip install openai"
    )

logger = logging.getLogger(__name__)


class JobEnrichment(BaseModel):
    """Structured output model for job data enrichment."""
    # Core fields that should be validated/corrected
    title: str
    company: str
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_country: Optional[str] = None
    location_type: Optional[str] = None  # Remote, Hybrid, On-site
    
    # Extracted/inferred fields
    experience_level: Optional[str] = None  # Entry level, Mid-Senior, Executive
    seniority_level: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    job_function: Optional[str] = None  # Engineering, Sales, Marketing
    employment_type: Optional[str] = None  # Full-time, Part-time, Contract
    
    # Compensation (if mentioned)
    salary_range: Optional[str] = None
    
    # Confidence scores
    confidence_score: float = 1.0  # 0.0-1.0 confidence in enrichment quality
    needs_manual_review: bool = False
    
    # Job fit analysis (based on user profile)
    good_fit: bool = False  # Should user apply to this job?
    fit_score: float = 0.0  # 0.0-1.0 how well job matches user's skills/experience
    fit_reasoning: Optional[str] = None  # Why is this a good/bad fit?


class FormAnswers(BaseModel):
    """Structured output model for Easy Apply form answers.
    
    Note: Using Optional fields to ensure OpenAI structured outputs compatibility.
    """
    answers: Optional[Dict[str, str]] = Field(default_factory=dict)  # field_id/name -> answer value
    confidence: Optional[float] = 1.0  # Overall confidence in answers
    unanswered_fields: Optional[List[str]] = Field(default_factory=list)  # Fields that couldn't be answered
    
    # Token usage (set externally after API call)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class OpenAIClient:
    """Client for interacting with OpenAI for LinkedIn job enrichment and form answering."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key (defaults to env OPENAI_API_KEY)
            model: Model to use (defaults to gpt-4o-mini for cost efficiency)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Use gpt-4o-mini by default (cost-effective, supports structured outputs)
        # User can override to gpt-4o for better quality if needed
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"[OpenAI] Initialized client with model: {self.model}")
    
    def enrich_job_data(self, raw_job_data: Dict[str, Any], user_profile: Optional[Dict[str, Any]] = None) -> JobEnrichment:
        """
        Refine and validate scraped job data using OpenAI structured outputs.
        
        This cleans up inconsistent data, extracts missing fields from job description,
        and validates the data before database insertion.
        
        Args:
            raw_job_data: Dictionary containing scraped job data
            user_profile: Optional user profile for fit analysis
            
        Returns:
            JobEnrichment object with validated and enriched data (including fit analysis if profile provided)
        """
        try:
            # Build prompt using centralized prompt builder
            prompt = build_job_enrichment_prompt(raw_job_data, user_profile or {})
            
            # Use structured outputs for reliable parsing
            # Add reasoning_effort for GPT-5 models to improve complex reasoning
            api_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": JOB_ENRICHMENT_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "response_format": JobEnrichment,
            }
            
            # Add reasoning_effort for GPT-5 reasoning models
            reasoning_effort = get_reasoning_effort_for_model(self.model)
            if reasoning_effort:
                api_params["reasoning_effort"] = reasoning_effort
            
            completion = self.client.beta.chat.completions.parse(**api_params)

            # Defensive checks for SDK response shape
            if not getattr(completion, "choices", None) or len(completion.choices) == 0:
                logger.error("[OpenAI] No choices returned from completion")
                return JobEnrichment(
                    title=raw_job_data.get("title", ""),
                    company=raw_job_data.get("company", ""),
                    confidence_score=0.0,
                    needs_manual_review=True
                )

            choice = completion.choices[0]
            if not getattr(choice, "message", None):
                logger.error("[OpenAI] Choice has no message")
                return JobEnrichment(
                    title=raw_job_data.get("title", ""),
                    company=raw_job_data.get("company", ""),
                    confidence_score=0.0,
                    needs_manual_review=True
                )

            enrichment = getattr(choice.message, "parsed", None)
            if enrichment is None:
                logger.error("[OpenAI] Received None from structured output parsing")
                return JobEnrichment(
                    title=raw_job_data.get("title", ""),
                    company=raw_job_data.get("company", ""),
                    confidence_score=0.0,
                    needs_manual_review=True
                )

            # Log token usage if present
            usage = getattr(completion, "usage", None)
            if usage:
                try:
                    logger.info(
                        f"[OpenAI] Job enrichment tokens: {usage.prompt_tokens} prompt + {usage.completion_tokens} completion"
                    )
                except Exception:
                    logger.debug("[OpenAI] Could not read usage fields from completion")

            logger.info(f"[OpenAI] Enriched job: {raw_job_data.get('job_id', 'unknown')}")
            return enrichment
            
        except Exception as e:
            logger.error(f"[OpenAI] Job enrichment failed: {e}")
            # Return minimal enrichment on error
            return JobEnrichment(
                title=raw_job_data.get("title", ""),
                company=raw_job_data.get("company", ""),
                confidence_score=0.0,
                needs_manual_review=True
            )
    
    def generate_form_answers(
        self,
        questions_json: Union[str, List[Dict]],
        user_profile: Dict[str, Any],
        job_context: Dict[str, Any]
    ) -> FormAnswers:
        """
        Generate personalized answers for LinkedIn Easy Apply form questions.
        
        Args:
            questions_json: Form questions data (can be JSON string or parsed dict)
            user_profile: User profile data (name, email, phone, skills, experience)
            job_context: Job details (title, company, description) for context
            
        Returns:
            FormAnswers object with generated answers
        """
        try:
            # Parse questions if needed
            if isinstance(questions_json, str):
                questions_data = json.loads(questions_json)
            else:
                questions_data = questions_json
            
            # Build prompt using centralized prompt builder
            prompt = build_form_answering_prompt(
                questions_data, user_profile, job_context
            )
            
            # Use structured outputs for reliable form answer generation
            # Add reasoning_effort for GPT-5 models to handle complex/meta questions
            api_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": FORM_ANSWERING_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "response_format": FormAnswers,
            }
            
            # Add reasoning_effort for GPT-5 reasoning models (critical for meta-questions)
            reasoning_effort = get_reasoning_effort_for_model(self.model)
            if reasoning_effort:
                api_params["reasoning_effort"] = reasoning_effort
            
            completion = self.client.beta.chat.completions.parse(**api_params)

            # Defensive handling of completion structure
            if not getattr(completion, "choices", None) or len(completion.choices) == 0:
                logger.error("[OpenAI] No choices returned from completion")
                return FormAnswers(answers={}, confidence=0.0, unanswered_fields=["Error: No choices returned"])

            choice = completion.choices[0]
            if not getattr(choice, "message", None):
                logger.error("[OpenAI] Choice has no message")
                return FormAnswers(answers={}, confidence=0.0, unanswered_fields=["Error: Choice missing message"])

            raw_parsed = getattr(choice.message, "parsed", None)
            if raw_parsed is None:
                logger.error("[OpenAI] Received None from structured output parsing")
                return FormAnswers(answers={}, confidence=0.0, unanswered_fields=["Error: Received None from API"])

            # Ensure we have a FormAnswers instance
            if isinstance(raw_parsed, FormAnswers):
                answers_obj = raw_parsed
            else:
                try:
                    answers_obj = FormAnswers.parse_obj(raw_parsed)
                except Exception as e:
                    logger.error(f"[OpenAI] Could not coerce parsed output to FormAnswers: {e}")
                    answers_obj = FormAnswers(answers={}, confidence=0.0, unanswered_fields=["Error: parse conversion failed"])

            # Attach token usage from API response if available
            usage = getattr(completion, "usage", None)
            if usage:
                try:
                    answers_obj.prompt_tokens = usage.prompt_tokens
                    answers_obj.completion_tokens = usage.completion_tokens
                    logger.info(
                        f"[OpenAI] Form answer tokens: {usage.prompt_tokens} prompt + {usage.completion_tokens} completion"
                    )
                except Exception:
                    logger.debug("[OpenAI] Could not read usage fields from completion")

            answers_dict = answers_obj.answers or {}
            unanswered_list = answers_obj.unanswered_fields or []
            logger.info(f"[OpenAI] Generated {len(answers_dict)} answers, {len(unanswered_list)} unanswered")

            return answers_obj
            
        except Exception as e:
            logger.error(f"[OpenAI] Form answer generation failed: {e}")
            return FormAnswers(
                answers={},
                confidence=0.0,
                unanswered_fields=["Error: " + str(e)]
            )
    


# Singleton instance
_openai_client: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """Get or create a singleton OpenAI client instance."""
    global _openai_client
    
    if _openai_client is None:
        _openai_client = OpenAIClient()
    
    return _openai_client


def enrich_job(job_data: Dict[str, Any], user_profile: Optional[Dict[str, Any]] = None) -> JobEnrichment:
    """
    Convenience function to enrich job data using OpenAI.
    
    Args:
        job_data: Raw scraped job data dictionary
        user_profile: Optional user profile for fit analysis
        
    Returns:
        JobEnrichment object with validated/enriched data (including fit analysis if profile provided)
    """
    client = get_openai_client()
    return client.enrich_job_data(job_data, user_profile)


def generate_answers(
    questions: Union[str, List[Dict]],
    profile: Dict[str, Any],
    job: Dict[str, Any]
) -> FormAnswers:
    """
    Convenience function to generate form answers using OpenAI.
    
    Args:
        questions: Form questions (JSON string or dict)
        profile: User profile data
        job: Job context data
        
    Returns:
        FormAnswers object with generated answers
    """
    client = get_openai_client()
    return client.generate_form_answers(questions, profile, job)
