from sema4ai.actions import action, chat
import pandas as pd
import json
from datetime import datetime

from ..utils.db import get_jobs_by_run_id, read_job_by_id, read_easy_apply_answers_by_job_id, get_fit_summary


@action
def download_job_results(run_id: str, format: str = "csv") -> str:
    """Download job search results from a specific run.
    
    Exports job data to a file and attaches it to the chat for download.
    
    Args:
        run_id: The run ID from a previous search (e.g., "run_20250108_143022")
        format: Output format - "csv" or "json" (default: "csv")
        
    Returns:
        Success message with file attachment details
    """
    try:
        print(f"[Chat] Downloading job results for run: {run_id}, format: {format}")
        
        # Get jobs from database
        jobs = get_jobs_by_run_id(run_id)
        
        if not jobs:
            return f"❌ No jobs found for run_id: {run_id}"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format.lower() == "json":
            # Export as JSON
            filename = f"linkedin_jobs_{run_id}_{timestamp}.json"
            json_data = json.dumps(jobs, indent=2, default=str)
            chat.attach_file_content(filename, json_data.encode('utf-8'))
            
        else:  # CSV (default)
            # Export as CSV
            filename = f"linkedin_jobs_{run_id}_{timestamp}.csv"
            df = pd.DataFrame(jobs)
            csv_data = df.to_csv(index=False)
            chat.attach_file_content(filename, csv_data.encode('utf-8'))
        
        return f"✅ Exported {len(jobs)} jobs from {run_id}\n\n" \
               f"File: {filename}\n" \
               f"Format: {format.upper()}\n\n" \
               f"File has been attached to the chat for download."
        
    except Exception as e:
        print(f"[Chat] Error downloading job results: {e}")
        import traceback
        print(f"[Chat] Full traceback: {traceback.format_exc()}")
        return f"❌ Error: {str(e)}"


@action
def download_generated_answers(job_id: str) -> str:
    """Download AI-generated Easy Apply answers for a specific job.
    
    Exports the questions and generated answers as a JSON file attached to chat.
    
    Args:
        job_id: LinkedIn job ID (e.g., "3846477685")
        
    Returns:
        Success message with file attachment details
    """
    try:
        print(f"[Chat] Downloading generated answers for job: {job_id}")
        
        # Get job and answers from database
        job = read_job_by_id(job_id)
        if not job:
            return f"❌ Job not found: {job_id}"
        
        answers_data = read_easy_apply_answers_by_job_id(job_id)
        if not answers_data:
            return f"❌ No generated answers found for job: {job_id}\n\n" \
                   f"Run `generate_answers_for_run()` first to create answers."
        
        # Build export data
        export_data = {
            "job_id": job_id,
            "job_title": job.get("title"),
            "company": job.get("company"),
            "job_url": job.get("job_url"),
            "generated_at": answers_data.get("generated_at"),
            "ai_confidence": answers_data.get("ai_confidence"),
            "questions": json.loads(answers_data.get("questions_json", "[]")),
            "answers": json.loads(answers_data.get("answers_json", "{}"))
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"easy_apply_answers_{job_id}_{timestamp}.json"
        json_data = json.dumps(export_data, indent=2, default=str)
        
        chat.attach_file_content(filename, json_data.encode('utf-8'))
        
        return f"✅ Exported Easy Apply answers\n\n" \
               f"Job: {export_data['job_title']} at {export_data['company']}\n" \
               f"Job ID: {job_id}\n" \
               f"Questions: {len(export_data['questions'])}\n" \
               f"Confidence: {export_data['ai_confidence']}\n" \
               f"File: {filename}\n\n" \
               f"File has been attached to the chat for download."
        
    except Exception as e:
        print(f"[Chat] Error downloading answers: {e}")
        import traceback
        print(f"[Chat] Full traceback: {traceback.format_exc()}")
        return f"❌ Error: {str(e)}"


@action  
def export_fit_analysis(run_id: str) -> str:
    """Export job fit analysis results with scores and recommendations.
    
    Creates a detailed CSV with fit scores, good/bad fit flags, and notes
    for all jobs in a run. Attaches file to chat for download.
    
    Args:
        run_id: The run ID from a previous search
        
    Returns:
        Success message with analysis summary and file attachment
    """
    try:
        print(f"[Chat] Exporting fit analysis for run: {run_id}")
        
        # Get fit summary
        summary = get_fit_summary(run_id)
        if not summary.get("total_jobs"):
            return f"❌ No jobs found for run_id: {run_id}"
        
        # Get all jobs with fit data
        jobs = get_jobs_by_run_id(run_id)
        
        # Build export dataframe with key columns
        export_data = []
        for job in jobs:
            export_data.append({
                "job_id": job.get("job_id"),
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location_raw"),
                "easy_apply": job.get("easy_apply"),
                "fit_score": job.get("fit_score"),
                "good_fit": job.get("good_fit"),
                "priority": job.get("priority"),
                "fit_notes": job.get("fit_notes"),
                "required_skills": job.get("required_skills"),
                "experience_level": job.get("experience_level"),
                "ai_confidence_score": job.get("ai_confidence_score"),
                "job_url": job.get("job_url")
            })
        
        df = pd.DataFrame(export_data)
        
        # Sort by fit_score descending
        if "fit_score" in df.columns:
            df = df.sort_values("fit_score", ascending=False)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"fit_analysis_{run_id}_{timestamp}.csv"
        csv_data = df.to_csv(index=False)
        
        chat.attach_file_content(filename, csv_data.encode('utf-8'))
        
        return f"✅ Fit Analysis Exported\n\n" \
               f"Run: {run_id}\n" \
               f"Total Jobs: {summary['total_jobs']}\n" \
               f"Good Fit: {summary.get('good_fit_count', 0)}\n" \
               f"Bad Fit: {summary.get('bad_fit_count', 0)}\n" \
               f"Avg Score: {summary.get('avg_fit_score', 0):.2f}\n" \
               f"File: {filename}\n\n" \
               f"File has been attached to the chat for download."
        
    except Exception as e:
        print(f"[Chat] Error exporting fit analysis: {e}")
        import traceback
        print(f"[Chat] Full traceback: {traceback.format_exc()}")
        return f"❌ Error: {str(e)}"
