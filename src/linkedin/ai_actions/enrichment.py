from sema4ai.actions import ActionError, Response, action
import dotenv
import os
import uuid
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..utils.db import (
    read_job_by_id,
    update_answers_json,
    update_job_enrichment,
    get_jobs_by_run_id,
    get_jobs_pending_enrichment,
        get_active_profile,
    )
from ..utils.openai_client import enrich_job, generate_answers
from ..utils.tools import _load_profile
from ..utils.enriched_answers import (
    save_enriched_answers,
    get_enriched_answers,
    get_jobs_with_enriched_answers
)

dotenv.load_dotenv()

# OpenAI API key for job enrichment and form answering
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def _parse_iso_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp strings safely."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(value), fmt)
            except ValueError:
                continue
    return None

# _load_profile is now imported from tools.py


def _generate_answers_for_job(
    job_id: str,
    job: Dict[str, Any],
    profile: Optional[Dict[str, Any]] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    Generate AI answers for a single Easy Apply job.
    
    Args:
        job_id: LinkedIn job ID
        job: Full job dictionary (from database or scraping)
        profile: User profile dict (if None, will load from database)
        force: Regenerate answers even if they already exist
    
    Returns:
        Dict with generation outcome.
    """
    outcome: Dict[str, Any] = {
        "job_id": job_id,
        "generated": False,
        "skipped": False,
        "confidence": None,
        "reason": None,
        "error": None
    }
    
    try:
        # Load profile if not provided
        if not profile:
            profile = get_active_profile()
            if not profile:
                profile = _load_profile()
        
        if not profile:
            msg = "No profile available"
            print(f"[Helper] {msg} for job {job_id}, skipping answer generation")
            outcome["skipped"] = True
            outcome["reason"] = "missing_profile"
            return outcome
        
        # Check if enriched answers already exist
        existing_enriched = get_enriched_answers(job_id)
        if existing_enriched and existing_enriched.get('answers') and not force:
            print(f"[Helper] Job {job_id} already has enriched answers, skipping")
            outcome["skipped"] = True
            outcome["reason"] = "answers_exist"
            return outcome
        
        # Skip if no questions
        questions_json = job.get('questions_json')
        if not questions_json:
            print(f"[Helper] Job {job_id} has no questions, skipping answer generation")
            outcome["skipped"] = True
            outcome["reason"] = "no_questions"
            return outcome
        
        # Generate answers
        print(f"[Helper] Generating answers for job {job_id}")
        form_answers = generate_answers(
            questions=questions_json,
            profile=profile,
            job=job  # Pass full job dict as context
        )
        
        # Save to enriched_answers table
        if form_answers.answers:
            profile_id = profile.get('profile_id') or str(uuid.uuid4())
            answers_dict = form_answers.answers
            save_enriched_answers(
                job_id=job_id,
                answers=answers_dict,
                profile_id=profile_id,
                confidence_score=form_answers.confidence or 0.0,
                unanswered_fields=form_answers.unanswered_fields or [],
                model_used=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                prompt_tokens=form_answers.prompt_tokens,
                completion_tokens=form_answers.completion_tokens
            )
            # Keep legacy column in sync for backward compatibility
            try:
                update_answers_json(job_id, json.dumps(answers_dict))
            except Exception as sync_err:
                print(f"[Helper] Warning: failed to sync answers_json for {job_id}: {sync_err}")
            
            confidence = form_answers.confidence or 0.0
            print(f"[Helper] Successfully generated answers for job {job_id} (confidence: {confidence:.2f})")
            outcome["generated"] = True
            outcome["confidence"] = confidence
            return outcome
        else:
            print(f"[Helper] No answers generated for job {job_id}")
            outcome["skipped"] = True
            outcome["reason"] = "empty_response"
            return outcome
            
    except Exception as e:
        print(f"[Helper] Failed to generate answers for job {job_id}: {e}")
        outcome["error"] = str(e)
        return outcome


@action
def enrich_and_generate_answers(
    run_id: Optional[str] = None,
    job_ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
    enrich_jobs: bool = True,
    generate_answers: bool = True,
    force_reprocess: bool = False,
    force_answer_regeneration: bool = False
) -> Response:
    """
    Phase 2: Enrich scraped jobs with OpenAI and generate Easy Apply answers.
    
    Args:
        run_id: Optional search run identifier from search_linkedin_easy_apply()
        job_ids: Optional explicit list of job IDs to process
        limit: Optional maximum number of jobs to process (applied after filtering)
        enrich_jobs: Whether to run job-level enrichment (default: True)
        generate_answers: Whether to generate Easy Apply answers (default: True)
        force_reprocess: Re-run enrichment even if the job is already processed
        force_answer_regeneration: Regenerate answers even if they already exist
    
    Returns:
        Response summarizing enrichment and answer generation results.
    """
    if not OPENAI_API_KEY:
        raise ActionError("OPENAI_API_KEY is required for enrichment and answer generation.")
    
    if not enrich_jobs and not generate_answers:
        return Response(result={
            "success": True,
            "message": "Nothing to do (enrich_jobs=False and generate_answers=False).",
            "processed": 0
        })
    
    try:
        profile = get_active_profile()
        if not profile:
            profile = _load_profile()
        if not profile:
            raise ActionError(
                "No active user profile found. Upload a resume via parse_resume_and_save_profile() before enrichment."
            )
        
        # Collect candidate jobs
        candidate_jobs: List[Dict[str, Any]] = []
        skipped_jobs: List[Dict[str, Any]] = []
        
        if job_ids:
            for jid in job_ids:
                job = read_job_by_id(jid)
                if job:
                    candidate_jobs.append(job)
                else:
                    skipped_jobs.append({"job_id": jid, "reason": "not_found"})
        elif run_id:
            candidate_jobs = get_jobs_by_run_id(run_id)
        else:
            candidate_jobs = get_jobs_pending_enrichment(limit=limit)
        
        # Apply limit if provided and we did not already limit via SQL
        if limit and (job_ids or run_id):
            candidate_jobs = candidate_jobs[:limit]
        
        if not candidate_jobs:
            return Response(result={
                "success": True,
                "message": "No jobs to process.",
                "run_id": run_id,
                "processed": 0,
                "enriched": 0,
                "answers_generated": 0,
                "skipped": skipped_jobs
            })
        
        enriched_count = 0
        answers_count = 0
        processed_count = 0
        failed_jobs: List[Dict[str, Any]] = []
        processed_job_ids: List[str] = []
        
        for job in candidate_jobs:
            job_id = job.get("job_id")
            if not job_id:
                skipped_jobs.append({"job_id": None, "reason": "missing_job_id"})
                continue
            
            if not job.get("easy_apply"):
                skipped_jobs.append({"job_id": job_id, "reason": "not_easy_apply"})
                continue
            
            questions_present = bool(job.get("questions_json"))
            if generate_answers and not questions_present:
                skipped_jobs.append({"job_id": job_id, "reason": "no_questions"})
                continue
            
            scraped_at = _parse_iso_ts(job.get("scraped_at"))
            ai_enriched_at = _parse_iso_ts(job.get("ai_enriched_at"))
            
            existing_answers = get_enriched_answers(job_id) if generate_answers else None
            answers_generated_at = _parse_iso_ts(existing_answers.get("generated_at")) if existing_answers else None
            
            should_enrich = enrich_jobs and (
                force_reprocess
                or not job.get("processed")
                or not ai_enriched_at
                or (scraped_at and ai_enriched_at and ai_enriched_at < scraped_at)
            )
            should_generate = generate_answers and questions_present and (
                force_answer_regeneration
                or not existing_answers
                or (scraped_at and answers_generated_at and answers_generated_at < scraped_at)
            )
            
            if not should_enrich and not should_generate:
                skipped_jobs.append({"job_id": job_id, "reason": "already_processed"})
                continue
            
            job_processed = False
            job_update_context: Dict[str, Any] = {}
            enrichment_failed = False
            processed_flag_updated = False
            
            if should_enrich:
                try:
                    enrichment = enrich_job(job, profile)
                    enrichment_ts = datetime.utcnow().isoformat()
                    
                    updates_to_db: Dict[str, Any] = {
                        "processed": True,
                        "ai_confidence_score": enrichment.confidence_score,
                        "ai_needs_review": enrichment.needs_manual_review,
                        "ai_enriched_at": enrichment_ts
                    }
                    
                    if enrichment.title:
                        updates_to_db["title"] = enrichment.title
                        job_update_context["title"] = enrichment.title
                    if enrichment.company:
                        updates_to_db["company"] = enrichment.company
                        job_update_context["company"] = enrichment.company
                    if enrichment.location_city:
                        updates_to_db["location_city"] = enrichment.location_city
                        job_update_context["location_city"] = enrichment.location_city
                    if enrichment.location_state:
                        updates_to_db["location_state"] = enrichment.location_state
                        job_update_context["location_state"] = enrichment.location_state
                    if enrichment.location_country:
                        updates_to_db["location_country"] = enrichment.location_country
                        job_update_context["location_country"] = enrichment.location_country
                    if enrichment.location_type:
                        updates_to_db["location_type"] = enrichment.location_type
                        job_update_context["location_type"] = enrichment.location_type
                    if enrichment.experience_level:
                        updates_to_db["experience_level"] = enrichment.experience_level
                        job_update_context["experience_level"] = enrichment.experience_level
                    if enrichment.seniority_level:
                        updates_to_db["seniority_level"] = enrichment.seniority_level
                        job_update_context["seniority_level"] = enrichment.seniority_level
                    if enrichment.required_skills:
                        updates_to_db["required_skills"] = enrichment.required_skills
                        job_update_context["required_skills"] = enrichment.required_skills
                    if enrichment.job_function:
                        updates_to_db["job_function"] = enrichment.job_function
                        job_update_context["job_function"] = enrichment.job_function
                    if enrichment.employment_type:
                        updates_to_db["employment_type"] = enrichment.employment_type
                        job_update_context["employment_type"] = enrichment.employment_type
                    if enrichment.salary_range:
                        updates_to_db["salary_range"] = enrichment.salary_range
                        job_update_context["salary_range"] = enrichment.salary_range
                    
                    if profile:
                        updates_to_db["good_fit"] = enrichment.good_fit
                        updates_to_db["fit_score"] = enrichment.fit_score
                        job_update_context["good_fit"] = enrichment.good_fit
                        job_update_context["fit_score"] = enrichment.fit_score
                        
                        if enrichment.fit_score is not None:
                            priority = int(max(0, min(100, round((1 - max(0.0, min(1.0, enrichment.fit_score))) * 100))))
                            updates_to_db["priority"] = priority
                            job_update_context["priority"] = priority
                    
                    update_job_enrichment(job_id, updates_to_db)
                    job.update(job_update_context)
                    job.update({
                        "processed": True,
                        "ai_confidence_score": enrichment.confidence_score,
                        "ai_needs_review": enrichment.needs_manual_review,
                        "ai_enriched_at": enrichment_ts
                    })
                    job["processed"] = True
                    processed_flag_updated = True
                    
                    if enrichment.fit_reasoning:
                        print(f"[Enrichment] {job_id}: {enrichment.fit_reasoning}")
                    
                    enriched_count += 1
                    job_processed = True
                except Exception as enrich_err:
                    print(f"[Enrichment] Failed for {job_id}: {enrich_err}")
                    failed_jobs.append({"job_id": job_id, "error": str(enrich_err), "stage": "enrichment"})
                    enrichment_failed = True
            
            if should_generate:
                answer_result = _generate_answers_for_job(
                    job_id=job_id,
                    job=job,
                    profile=profile,
                    force=force_answer_regeneration
                )
                
                if answer_result.get("generated"):
                    answers_count += 1
                    job_processed = True
                    job["processed"] = True
                elif answer_result.get("error"):
                    failed_jobs.append({"job_id": job_id, "error": answer_result["error"], "stage": "answers"})
                else:
                    skipped_jobs.append({
                        "job_id": job_id,
                        "reason": answer_result.get("reason", "answers_skipped")
                    })
            
            if job_processed:
                if not processed_flag_updated:
                    update_job_enrichment(job_id, {"processed": True})
                job["processed"] = True
                processed_job_ids.append(job_id)
                processed_count += 1
        
        message = (
            f"Processed {processed_count} jobs "
            f"({enriched_count} enriched, {answers_count} answer sets generated)."
        )
        
        return Response(result={
            "success": True,
            "run_id": run_id,
            "processed": processed_count,
            "enriched": enriched_count,
            "answers_generated": answers_count,
            "skipped": skipped_jobs,
            "failed": failed_jobs,
            "profile_id": profile.get("profile_id"),
            "settings": {
                "enrich_jobs": enrich_jobs,
                "generate_answers": generate_answers,
                "force_reprocess": force_reprocess,
                "force_answer_regeneration": force_answer_regeneration,
                "limit": limit,
                "job_ids": job_ids,
                "run_id": run_id
            },
            "message": message,
            "processed_job_ids": processed_job_ids
        })
        
    except ActionError:
        raise
    except Exception as e:
        print(f"[ACTION] Error in enrich_and_generate_answers: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e),
            "run_id": run_id
        })


@action
def generate_answers_for_run(run_id: str) -> Response:
    """
    Deprecated wrapper for enrich_and_generate_answers(run_id=...).
    
    Left in-place for backward compatibility. For full control use enrich_and_generate_answers().
    
    Args:
        run_id: The search run ID from search_linkedin_easy_apply()
    
    Returns:
        Response with summary of answer generation (success/failed counts)
    """
    print(f"[ACTION] generate_answers_for_run is deprecated. Delegating to enrich_and_generate_answers(run_id='{run_id}').")
    delegated = enrich_and_generate_answers(
        run_id=run_id,
        enrich_jobs=False,
        generate_answers=True,
        force_reprocess=False,
        force_answer_regeneration=False
    )
    
    # Ensure we add a note without mutating the delegated Response in-place unexpectedly
    result_payload = dict(delegated.result) if isinstance(delegated.result, dict) else {"result": delegated.result}
    notes = result_payload.get("notes")
    if not notes:
        result_payload["notes"] = []
    if isinstance(result_payload["notes"], list):
        result_payload["notes"].append("generate_answers_for_run will be removed in a future release; use enrich_and_generate_answers instead.")
    else:
        result_payload["notes"] = [
            result_payload["notes"],
            "generate_answers_for_run will be removed in a future release; use enrich_and_generate_answers instead."
        ]
    result_payload.setdefault("message", delegated.result.get("message") if isinstance(delegated.result, dict) else None)
    result_payload["run_id"] = run_id
    
    return Response(result=result_payload)


@action
def reenrich_jobs(
    job_ids: Optional[List[str]] = None,
    run_id: Optional[str] = None,
    force_regenerate: bool = True
) -> Response:
    """
    Regenerate AI enrichments and form answers for existing database jobs using updated prompts or model settings. Useful after prompt changes or for low-confidence jobs.
    
    Args:
        job_ids: List of specific job IDs to re-enrich (optional)
        run_id: Re-enrich all jobs from a specific search run (optional)
        force_regenerate: If True, regenerate even if answers exist (default: True)
    
    Returns:
        Response with re-enrichment results
    """
    try:
        if not job_ids and not run_id:
            return Response(result={
                "success": False,
                "error": "Must provide either job_ids or run_id"
            })
        
        delegated = enrich_and_generate_answers(
            run_id=run_id,
            job_ids=job_ids,
            enrich_jobs=True,
            generate_answers=True,
            force_reprocess=True,
            force_answer_regeneration=force_regenerate
        )
        
        payload = dict(delegated.result) if isinstance(delegated.result, dict) else {"result": delegated.result}
        payload.setdefault("message", "Re-enrichment complete.")
        payload.setdefault("notes", [])
        if isinstance(payload["notes"], list):
            payload["notes"].append("reenrich_jobs delegates to enrich_and_generate_answers with force_reprocess=True.")
        else:
            payload["notes"] = [
                payload["notes"],
                "reenrich_jobs delegates to enrich_and_generate_answers with force_reprocess=True."
            ]
        payload["force_regenerate"] = force_regenerate
        payload["job_ids"] = job_ids
        payload["run_id"] = run_id
        
        return Response(result=payload)
        
    except Exception as e:
        print(f"[ACTION] Error in reenrich_jobs: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e)
        })


@action
def check_which_jobs_ready() -> Response:
    """Check which jobs have AI-generated answers ready and are good fits.
    
    Returns a list of job_ids that:
    - Have enriched answers in the enriched_answers table
    - Have NOT been applied to yet (is_applied = false)
    - Are marked as good_fit (good_fit = true)
    - Have a minimum fit score >= 0.6
    
    Returns:
        Response containing list of job_ids with generated answers and filtering stats
    """
    try:
        from ..utils.db_sqlite import get_connection
        
        conn = get_connection()
        
        # Get total jobs with enriched answers
        total_with_answers = conn.execute("""
            SELECT COUNT(DISTINCT job_id) FROM enriched_answers
            WHERE LENGTH(answers_json) > 2
        """).fetchone()[0]
        
        # Get jobs already applied to
        already_applied = conn.execute("""
            SELECT COUNT(DISTINCT ea.job_id)
            FROM enriched_answers ea
            INNER JOIN job_postings jp ON ea.job_id = jp.job_id
            WHERE LENGTH(ea.answers_json) > 2 AND jp.is_applied = 1
        """).fetchone()[0]
        
        # Get bad fit jobs
        bad_fit_jobs = conn.execute("""
            SELECT COUNT(DISTINCT ea.job_id)
            FROM enriched_answers ea
            INNER JOIN job_postings jp ON ea.job_id = jp.job_id
            WHERE LENGTH(ea.answers_json) > 2 
              AND (jp.is_applied = 0 OR jp.is_applied IS NULL)
              AND jp.good_fit = 0
        """).fetchone()[0]
        
        # Get jobs ready to apply (the actual list)
        job_ids = get_jobs_with_enriched_answers()
        
        return Response(result={
            "job_ids_ready": job_ids,
            "count": len(job_ids),
            "filtering_stats": {
                "total_with_answers": total_with_answers,
                "already_applied": already_applied,
                "bad_fit_filtered": bad_fit_jobs,
                "ready_to_apply": len(job_ids)
            },
            "message": f"Found {len(job_ids)} jobs ready for application (filtered out {already_applied} already applied, {bad_fit_jobs} bad fits)"
        })
    except Exception as e:
        print(f"[ACTION] Error in check_which_jobs_ready: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "job_ids_ready": [],
            "count": 0,
            "error": str(e)
        })


@action
def get_job_fit_analysis(run_id: Optional[str] = None) -> Response:
    """
    Get job-to-profile fit analysis results. Returns statistics on how jobs match your profile, including good fits (ready to apply) and bad fits (filtered out).
    
    Args:
        run_id: Optional run_id from search to analyze specific search results.
                If not provided, analyzes all jobs in database.
    
    Returns:
        Response with fit analysis statistics and job lists
    """
    try:
        from ..utils.db import get_fit_summary, get_good_fit_jobs, get_bad_fit_jobs
        
        print(f"[ACTION] Getting fit analysis{f' for run_id: {run_id}' if run_id else ' (all jobs)'}...")
        
        # Get summary statistics
        summary = get_fit_summary(run_id)
        
        if not summary or summary.get('total_jobs', 0) == 0:
            return Response(result={
                "success": False,
                "error": f"No jobs found{f' for run_id: {run_id}' if run_id else ''}",
                "run_id": run_id
            })
        
        # Get good fit jobs (top 20)
        good_fits = get_good_fit_jobs(run_id=run_id, limit=20)
        
        # Get bad fit jobs (top 10 for analysis)
        bad_fits = get_bad_fit_jobs(run_id=run_id, limit=10)
        
        # Format output
        print(f"\n[Fit Analysis Summary]")
        print(f"  Total jobs: {summary['total_jobs']}")
        print(f"  Good fits: {summary['good_fits']} ({summary['good_fit_rate']*100:.1f}%)")
        print(f"  Bad fits: {summary['bad_fits']}")
        print(f"  Not analyzed: {summary['not_analyzed']}")
        print(f"  Avg fit score: {summary['avg_fit_score']}")
        print(f"  Score range: {summary['min_fit_score']} - {summary['max_fit_score']}")
        
        if good_fits:
            print(f"\n[Top Good Fits]")
            for job in good_fits[:5]:
                print(f"  • {job['title']} @ {job['company']} (score: {job['fit_score']:.2f})")
        
        if bad_fits:
            print(f"\n[Bad Fits (for analysis)]")
            for job in bad_fits[:5]:
                print(f"  • {job['title']} @ {job['company']} (score: {job['fit_score']:.2f})")
        
        return Response(result={
            "success": True,
            "run_id": run_id,
            "summary": summary,
            "good_fits_sample": good_fits[:20],  # Top 20 good fits
            "bad_fits_sample": bad_fits[:10],    # Top 10 bad fits for review
            "message": f"Found {summary['good_fits']} good fit jobs out of {summary['total_jobs']} total jobs ({summary['good_fit_rate']*100:.1f}% pass rate)"
        })
        
    except Exception as e:
        print(f"[ACTION] Error in get_job_fit_analysis: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e)
        })


@action(is_consequential=True)
def update_job_fit_status(
    job_ids: List[str],
    mark_as_good_fit: bool = True,
    fit_score: Optional[float] = None
) -> Response:
    """
    Update job fit analysis results for one or more jobs.
    
    This action allows you to manually override AI-generated fit analysis,
    marking jobs as good/bad fits and setting custom fit scores. Useful for:
    - Forcing jobs into the "ready to apply" pool
    - Correcting AI mistakes
    - Bulk updating fit status for testing
    
    Args:
        job_ids: List of LinkedIn job IDs to update (e.g., ["3846477685", "3912345678"])
        mark_as_good_fit: Set True to mark as good fit, False for bad fit (default: True)
        fit_score: Optional fit score 0.0-1.0 (if None, will set to 0.8 for good_fit=True, 0.3 for False)
        
    Returns:
        Response with update results including count of jobs updated
        
    Examples:
        # Mark multiple jobs as good fits with default high score
        update_job_fit_status(["123", "456", "789"], mark_as_good_fit=True)
        
        # Mark jobs as bad fits
        update_job_fit_status(["999"], mark_as_good_fit=False)
        
        # Set custom fit score
        update_job_fit_status(["123"], mark_as_good_fit=True, fit_score=0.95)
    """
    from ..utils.db import update_job_fit_analysis
    
    try:
        print(f"[ACTION] Updating fit status for {len(job_ids)} jobs")
        print(f"[ACTION] mark_as_good_fit={mark_as_good_fit}, fit_score={fit_score}")
        
        # Validate inputs
        if not job_ids:
            return Response(result={
                "success": False,
                "error": "No job_ids provided. Please provide at least one job ID."
            })
        
        # Set default fit_score if not provided
        if fit_score is None:
            fit_score = 0.8 if mark_as_good_fit else 0.3
        
        # Validate fit_score range
        if not (0.0 <= fit_score <= 1.0):
            return Response(result={
                "success": False,
                "error": f"fit_score must be between 0.0 and 1.0, got {fit_score}"
            })
        
        # Update database
        result = update_job_fit_analysis(
            job_ids=job_ids,
            good_fit=mark_as_good_fit,
            fit_score=fit_score
        )
        
        if result["success"]:
            updated_count = result["updated_count"]
            
            # Get verification - read back one of the updated jobs
            from ..utils.db import read_job_by_id
            verification = None
            if job_ids and updated_count > 0:
                try:
                    sample_job = read_job_by_id(job_ids[0])
                    if sample_job:
                        verification = {
                            "job_id": sample_job.get("job_id"),
                            "title": sample_job.get("title"),
                            "company": sample_job.get("company"),
                            "good_fit": sample_job.get("good_fit"),
                            "fit_score": sample_job.get("fit_score")
                        }
                except Exception as e:
                    print(f"[ACTION] Could not verify update: {e}")
            
            return Response(result={
                "success": True,
                "message": f"Successfully updated {updated_count} job(s)",
                "updated_count": updated_count,
                "requested_job_count": len(job_ids),
                "changes_applied": {
                    "good_fit": mark_as_good_fit,
                    "fit_score": fit_score
                },
                "job_ids": job_ids,
                "verification_sample": verification,
                "next_steps": (
                    "Jobs are now marked as good fits and ready for application. "
                    "Use check_which_jobs_ready() to see all jobs ready to apply."
                ) if mark_as_good_fit else (
                    "Jobs are now marked as bad fits and filtered out from applications."
                )
            })
        else:
            return Response(result={
                "success": False,
                "error": result.get("error", "Unknown error during update"),
                "updated_count": 0
            })
            
    except Exception as e:
        print(f"[ACTION] Error in update_job_fit_status: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e)
        })
