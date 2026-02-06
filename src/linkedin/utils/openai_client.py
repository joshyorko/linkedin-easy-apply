"""
OpenAI client for enriching LinkedIn job data and generating Easy Apply form answers.

Uses the non-beta structured outputs API (client.chat.completions.parse)
with Pydantic models for guaranteed schema conformance.

Supports GPT-5 family parameters: reasoning_effort, verbosity.
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


class FormAnswer(BaseModel):
    """A single form field answer (strict structured outputs compatible)."""
    field_id: str
    value: str


class _FormAnswersSchema(BaseModel):
    """API response schema for OpenAI structured outputs.

    Uses List[FormAnswer] instead of Dict[str, str] because OpenAI strict
    structured outputs requires additionalProperties: false, which is
    incompatible with arbitrary-key dicts.

    This model is used ONLY as the response_format for the API call.
    Token usage fields are excluded — they are metadata set after the call.
    """
    answers: List[FormAnswer] = Field(default_factory=list)
    confidence: float = 1.0
    unanswered_fields: List[str] = Field(default_factory=list)


class FormAnswers(BaseModel):
    """Internal model for Easy Apply form answers with token tracking."""
    answers: List[FormAnswer] = Field(default_factory=list)
    confidence: float = 1.0
    unanswered_fields: List[str] = Field(default_factory=list)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

    @property
    def answers_dict(self) -> Dict[str, str]:
        """Convert answer list to dict for downstream compatibility."""
        return {a.field_id: a.value for a in self.answers}


class OpenAIClient:
    """Client for interacting with OpenAI for LinkedIn job enrichment and form answering."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"[OpenAI] Initialized client with model: {self.model}")

    def _build_api_params(
        self,
        messages: List[Dict[str, str]],
        response_format,
        verbosity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build common API params with optional GPT-5 parameters."""
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "response_format": response_format,
        }
        reasoning_effort = get_reasoning_effort_for_model(self.model)
        if reasoning_effort:
            params["reasoning_effort"] = reasoning_effort
        if verbosity:
            params["verbosity"] = verbosity
        return params

    def _parse_completion(self, completion, fallback):
        """Extract parsed result from completion, handling refusals."""
        if not getattr(completion, "choices", None) or len(completion.choices) == 0:
            logger.error("[OpenAI] No choices returned from completion")
            return fallback

        message = completion.choices[0].message

        # Check for model refusal before accessing parsed
        if getattr(message, "refusal", None):
            logger.error(f"[OpenAI] Model refused: {message.refusal}")
            return fallback

        parsed = getattr(message, "parsed", None)
        if parsed is None:
            logger.error("[OpenAI] Received None from structured output parsing")
            return fallback

        # Log token usage
        usage = getattr(completion, "usage", None)
        if usage:
            logger.info(
                f"[OpenAI] Tokens: {usage.prompt_tokens} prompt + {usage.completion_tokens} completion"
            )

        return parsed

    def enrich_job_data(self, raw_job_data: Dict[str, Any], user_profile: Optional[Dict[str, Any]] = None) -> JobEnrichment:
        """Enrich scraped job data and perform fit analysis using structured outputs."""
        fallback = JobEnrichment(
            title=raw_job_data.get("title", ""),
            company=raw_job_data.get("company", ""),
            confidence_score=0.0,
            needs_manual_review=True,
        )
        try:
            prompt = build_job_enrichment_prompt(raw_job_data, user_profile or {})
            api_params = self._build_api_params(
                messages=[
                    {"role": "system", "content": JOB_ENRICHMENT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format=JobEnrichment,
            )

            completion = self.client.chat.completions.parse(**api_params)
            result = self._parse_completion(completion, fallback)
            logger.info(f"[OpenAI] Enriched job: {raw_job_data.get('job_id', 'unknown')}")
            return result

        except Exception as e:
            logger.error(f"[OpenAI] Job enrichment failed: {e}")
            return fallback
    
    def generate_form_answers(
        self,
        questions_json: Union[str, List[Dict]],
        user_profile: Dict[str, Any],
        job_context: Dict[str, Any],
    ) -> FormAnswers:
        """Generate personalized answers for LinkedIn Easy Apply form questions."""
        fallback = FormAnswers(answers=[], confidence=0.0, unanswered_fields=["Error: generation failed"])
        try:
            if isinstance(questions_json, str):
                questions_data = json.loads(questions_json)
            else:
                questions_data = questions_json

            prompt = build_form_answering_prompt(
                questions_data, user_profile, job_context
            )

            # Use _FormAnswersSchema (no token fields) as the API response format
            api_params = self._build_api_params(
                messages=[
                    {"role": "system", "content": FORM_ANSWERING_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format=_FormAnswersSchema,
                verbosity="low",
            )

            completion = self.client.chat.completions.parse(**api_params)
            schema_fallback = _FormAnswersSchema(answers=[], confidence=0.0, unanswered_fields=["Error: generation failed"])
            parsed = self._parse_completion(completion, schema_fallback)

            if not isinstance(parsed, _FormAnswersSchema):
                return fallback

            # Convert API schema to internal FormAnswers with token tracking
            usage = getattr(completion, "usage", None)
            answers_obj = FormAnswers(
                answers=parsed.answers,
                confidence=parsed.confidence,
                unanswered_fields=parsed.unanswered_fields,
                prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            )

            logger.info(
                f"[OpenAI] Generated {len(answers_obj.answers)} answers, "
                f"{len(answers_obj.unanswered_fields)} unanswered"
            )
            return answers_obj

        except Exception as e:
            logger.error(f"[OpenAI] Form answer generation failed: {e}")
            return fallback
    


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
