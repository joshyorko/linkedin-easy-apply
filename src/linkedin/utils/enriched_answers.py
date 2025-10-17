"""
Enriched Answers Management

Handles storage and retrieval of AI-generated form answers in a separate table.
"""
import json
import uuid
from typing import Dict, Any, Optional, List
from .db import get_connection


def save_enriched_answers(
    job_id: str,
    answers: Dict[str, Any],
    profile_id: Optional[str] = None,
    confidence_score: float = 0.0,
    unanswered_fields: Optional[List[str]] = None,
    model_used: str = "gpt-5-nano",
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None
) -> str:
    """
    Save AI-generated answers to enriched_answers table.
    
    Args:
        job_id: Job ID (FK to job_postings)
        answers: Dict mapping field_id -> answer value
        profile_id: Which user profile was used
        confidence_score: AI confidence (0.0-1.0)
        unanswered_fields: List of field IDs that couldn't be answered
        model_used: OpenAI model name
        prompt_tokens: Number of prompt tokens used
        completion_tokens: Number of completion tokens used
        
    Returns:
        answer_id (UUID)
    """
    conn = get_connection()
    answer_id = str(uuid.uuid4())
    
    try:
        conn.execute("""
            INSERT INTO enriched_answers (
                answer_id, job_id, answers_json, profile_id,
                confidence_score, unanswered_fields, model_used,
                prompt_tokens, completion_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            answer_id,
            job_id,
            json.dumps(answers),
            profile_id,
            confidence_score,
            json.dumps(unanswered_fields or []),
            model_used,
            prompt_tokens,
            completion_tokens
        ])
        
        conn.commit()  # CRITICAL: Commit the transaction!
        
        print(f"[Database] Saved enriched answers {answer_id} for job {job_id}")
        return answer_id
        
    finally:
        pass  # Singleton connection - do not close


def get_enriched_answers(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get enriched answers for a job.
    
    Args:
        job_id: Job ID
        
    Returns:
        Dict with answers_json, profile_id, confidence_score, etc. or None
    """
    conn = get_connection()
    
    try:
        result = conn.execute("""
            SELECT 
                answer_id, job_id, answers_json, profile_id,
                generated_at, confidence_score, unanswered_fields,
                model_used, used_for_application, application_date
            FROM enriched_answers
            WHERE job_id = ?
            ORDER BY generated_at DESC
            LIMIT 1
        """, [job_id]).fetchone()
        
        if not result:
            return None

        # result is a sqlite3.Row thanks to connection.row_factory; convert to dict
        enriched = dict(result)

        # Parse JSON fields
        if enriched.get('answers_json'):
            try:
                enriched['answers'] = json.loads(enriched['answers_json'])
            except Exception:
                enriched['answers'] = {}

        if enriched.get('unanswered_fields'):
            try:
                enriched['unanswered_fields'] = json.loads(enriched['unanswered_fields'])
            except Exception:
                enriched['unanswered_fields'] = []

        return enriched
        
    finally:
        pass  # Singleton connection - do not close


def mark_answers_used(job_id: str) -> None:
    """Mark enriched answers as used for an application."""
    conn = get_connection()
    
    try:
        conn.execute("""
            UPDATE enriched_answers
            SET used_for_application = 1,
                application_date = CURRENT_TIMESTAMP
            WHERE job_id = ?
        """, [job_id])
        
        conn.commit()  # CRITICAL: Commit the transaction!
        
    finally:
        pass  # Singleton connection - do not close


def get_jobs_with_enriched_answers() -> List[str]:
    """Get list of job IDs that have enriched answers ready.
    
    Filters to only include jobs that:
    - Have enriched answers
    - Have NOT been applied to yet (is_applied = false)
    - Are marked as good_fit (good_fit = true)
    - Have a minimum fit score (fit_score >= 0.6)
    """
    conn = get_connection()
    
    try:
        results = conn.execute("""
            SELECT DISTINCT ea.job_id 
            FROM enriched_answers ea
            INNER JOIN job_postings jp ON ea.job_id = jp.job_id
            WHERE LENGTH(ea.answers_json) > 2
              AND (jp.is_applied = 0 OR jp.is_applied IS NULL)
              AND jp.good_fit = 1
              AND (jp.fit_score >= 0.6 OR jp.fit_score IS NULL)
            ORDER BY ea.generated_at DESC
        """).fetchall()
        
        return [r[0] for r in results]
        
    finally:
        pass  # Singleton connection - do not close
