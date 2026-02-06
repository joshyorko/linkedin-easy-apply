from sema4ai.actions import Response, action
from sema4ai_http import get as http_get, post as http_post
import os
import json
import urllib.parse
from typing import Optional

from ..utils.db import get_connection
from ..utils.responses import RunStatusResponse, RunListResponse, CancelRunResponse, ActionsListResponse


@action(is_consequential=False)
def check_run_status(run_id: str) -> RunStatusResponse:
    """Check the status of a long-running action using its run ID.
    
    When an action takes a long time (like parse_resume or search_linkedin), 
    it may timeout on the client side but continue running on the server.
    Use this action to check if it's still running or if it completed.
    
    Args:
        run_id: The run ID returned in response headers (x-action-server-run-id)
                or from a previous action that timed out
    
    Returns:
        Response with run status, result (if completed), and error (if failed)
        
    Status codes:
        0 = not started
        1 = running (still processing)
        2 = passed (completed successfully)
        3 = failed (error occurred)
        4 = cancelled (was manually cancelled)
    """
    try:
        print(f"[ACTION] Checking status of run: {run_id}")
        
        # Call the built-in action server API using sema4ai_http
        server_url = os.getenv("SERVER_URL", "http://localhost:8082")
        api_url = f"{server_url}/api/runs/{run_id}"
        
        response = http_get(api_url)
        
        if response.status_code == 404:
            return RunStatusResponse(
                result="Run ID not found",
                error="Run ID not found",
                success=False,
                run_id=run_id,
                hint="This run may not exist, or the server was restarted"
            )
        
        if response.status_code != 200:
            return RunStatusResponse(
                result=f"Server returned status code {response.status_code}",
                error=f"Server returned status code {response.status_code}",
                success=False,
                run_id=run_id
            )
        
        run_data = response.json()

        # Parse the status
        status = run_data.get("status")
        status_map = {
            0: "not_started",
            1: "running",
            2: "completed",
            3: "failed",
            4: "cancelled"
        }

        status_name = status_map.get(status, "unknown")

        # Build common fields
        log_url = None
        hint = None
        error_message = None
        result_message = ""

        if status == 1:  # Running
            elapsed = run_data.get("run_time", 0)
            result_message = f"Action is still running (elapsed: {elapsed:.1f}s)"
            hint = "Check again in 10-30 seconds"

        elif status == 2:  # Completed
            result_message = "Action completed successfully!"
            log_url = f"{server_url}/api/runs/{run_id}/log.html"

        elif status == 3:  # Failed
            result_message = "Action failed"
            error_message = run_data.get("error_message")
            log_url = f"{server_url}/api/runs/{run_id}/log.html"

        elif status == 4:  # Cancelled
            result_message = "Action was cancelled"

        else:  # Not started or unknown
            result_message = "Action has not started yet"

        print(f"[ACTION] Run status: {status_name} ({status})")
        return RunStatusResponse(
            result=result_message,
            success=True,
            run_id=run_id,
            status=status,
            status_name=status_name,
            action_id=run_data.get("action_id"),
            start_time=run_data.get("start_time"),
            run_time=run_data.get("run_time"),
            log_url=log_url,
            error_message=error_message,
            hint=hint
        )
        
    except Exception as e:
        print(f"[ACTION] Error checking run status: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return RunStatusResponse(
            result=f"Error checking run status: {e}",
            error=str(e),
            success=False,
            run_id=run_id,
            hint="Make sure the action server is running and the run_id is valid"
        )


@action(is_consequential=False)
def list_runs(
    action_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20
) -> RunListResponse:
    """List all action runs with optional filtering.
    
    View all LinkedIn scraping jobs, filter by status, and monitor activity.
    Useful for finding failed runs or checking what's been executed.
    
    Args:
        action_name: Filter by action name (e.g., "search_linkedin_easy_apply")
        status: Filter by status - "running", "completed", "failed", "cancelled"
        limit: Maximum number of runs to return (default: 20)
    
    Returns:
        Response with list of runs and their details
    """
    try:
        print(f"[ACTION] Listing runs (action={action_name}, status={status}, limit={limit})")
        
        conn = get_connection()
        
        # Get distinct run_ids with aggregated statistics
        query = """
            SELECT 
                run_id,
                MIN(scraped_at) as start_time,
                MAX(scraped_at) as end_time,
                COUNT(*) as job_count,
                SUM(CASE WHEN processed = true THEN 1 ELSE 0 END) as processed_count,
                SUM(CASE WHEN answers_json IS NOT NULL AND answers_json != '' THEN 1 ELSE 0 END) as answers_count,
                SUM(CASE WHEN is_applied = true THEN 1 ELSE 0 END) as applied_count,
                SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as good_fit_count,
                AVG(fit_score) as avg_fit_score,
                AVG(ai_confidence_score) as avg_confidence
            FROM job_postings
            WHERE run_id IS NOT NULL AND run_id != ''
            GROUP BY run_id
            ORDER BY start_time DESC
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        results = conn.execute(query).fetchall()
        
        if not results:
            return RunListResponse(
                result="No runs found in database",
                success=True,
                runs=[],
                count=0
            )
        
        columns = ['run_id', 'start_time', 'end_time', 'job_count', 'processed_count', 
                   'answers_count', 'applied_count', 'good_fit_count', 'avg_fit_score', 'avg_confidence']
        
        enhanced_runs = []
        for row in results:
            run_dict = dict(zip(columns, row))
            
            # Calculate run status based on processing
            if run_dict['processed_count'] == run_dict['job_count']:
                status_name = "completed"
            elif run_dict['processed_count'] > 0:
                status_name = "in_progress"
            else:
                status_name = "pending"
            
            enhanced_run = {
                "run_id": run_dict["run_id"],
                "start_time": str(run_dict["start_time"]) if run_dict["start_time"] else None,
                "end_time": str(run_dict["end_time"]) if run_dict["end_time"] else None,
                "status": status_name,
                "job_count": run_dict["job_count"],
                "processed_count": run_dict["processed_count"],
                "answers_ready": run_dict["answers_count"],
                "applied_count": run_dict["applied_count"],
                "good_fit_count": run_dict["good_fit_count"],
                "avg_fit_score": round(run_dict["avg_fit_score"], 2) if run_dict["avg_fit_score"] else None,
                "avg_confidence": round(run_dict["avg_confidence"], 2) if run_dict["avg_confidence"] else None
            }
            enhanced_runs.append(enhanced_run)
        
        print(f"[ACTION] Found {len(enhanced_runs)} runs")
        
        return RunListResponse(
            result=f"Found {len(enhanced_runs)} runs",
            success=True,
            runs=enhanced_runs,
            count=len(enhanced_runs),
            filters={
                "action_name": action_name,
                "status": status,
                "limit": limit
            }
        )
        
    except Exception as e:
        print(f"[ACTION] Error listing runs: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return RunListResponse(
            result=f"Error listing runs: {e}",
            error=str(e),
            success=False
        )


@action(is_consequential=True)
def cancel_run(run_id: str) -> CancelRunResponse:
    """Cancel a running action by its run ID.
    
    Stop a long-running LinkedIn scrape if you made a mistake, LinkedIn is blocking,
    or you need to stop for any reason. Only works on currently running actions.
    
    Args:
        run_id: The run ID to cancel (from check_run_status or list_runs)
    
    Returns:
        Response confirming cancellation
    """
    try:
        print(f"[ACTION] Cancelling run: {run_id}")
        
        # First check if run is actually running
        server_url = os.getenv("SERVER_URL", "http://localhost:8082")
        status_url = f"{server_url}/api/runs/{run_id}"
        
        status_response = http_get(status_url)
        if status_response.status_code == 404:
            return CancelRunResponse(
                result="Run ID not found",
                error="Run ID not found",
                success=False,
                run_id=run_id
            )
        
        status_data = status_response.json()
        current_status = status_data.get("status")
        
        if current_status != 1:  # Not running
            status_names = {0: "not started", 1: "running", 2: "completed", 3: "failed", 4: "cancelled"}
            error_msg = f"Run is not currently running (status: {status_names.get(current_status, 'unknown')})"
            return CancelRunResponse(
                result=error_msg,
                error=error_msg,
                success=False,
                run_id=run_id,
                current_status=current_status
            )
        
        # Cancel the run
        cancel_url = f"{server_url}/api/runs/{run_id}/cancel"
        
        cancel_response = http_post(cancel_url, json={})
        
        if cancel_response.status_code != 200:
            return CancelRunResponse(
                result=f"Server returned status code {cancel_response.status_code}",
                error=f"Server returned status code {cancel_response.status_code}",
                success=False,
                run_id=run_id
            )
        
        print(f"[ACTION] Successfully cancelled run {run_id}")
        
        return CancelRunResponse(
            result=f"Run {run_id} has been cancelled",
            success=True,
            run_id=run_id,
            action_name=status_data.get("action_name"),
            log_url=f"{server_url}/api/runs/{run_id}/log.html"
        )
        
    except Exception as e:
        print(f"[ACTION] Error cancelling run: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return CancelRunResponse(
            result=f"Error cancelling run: {e}",
            error=str(e),
            success=False,
            run_id=run_id
        )


@action(is_consequential=False)
def list_available_actions() -> ActionsListResponse:
    """List all available actions in the action server.
    
    Discover what actions are available, useful for API exploration and documentation.
    Shows action names, descriptions, and parameters.
    
    Returns:
        Response with list of all actions and their metadata
    """
    try:
        print(f"[ACTION] Listing available actions")
        
        server_url = os.getenv("SERVER_URL", "http://localhost:8082")
        api_url = f"{server_url}/api/actionPackages"
        
        response = http_get(api_url)
        
        if response.status_code != 200:
            return ActionsListResponse(
                result=f"Server returned status code {response.status_code}",
                error=f"Server returned status code {response.status_code}",
                success=False
            )
        
        packages_data = response.json()
        
        # Extract actions from all packages
        simplified_actions = []
        for package in packages_data:
            package_name = package.get("name", "Unknown Package")
            for action in package.get("actions", []):
                simplified_actions.append({
                    "name": action.get("name"),
                    "docs": action.get("docs", "").strip(),
                    "action_id": action.get("id"),
                    "package_name": package_name,
                    "is_consequential": action.get("is_consequential"),
                    "file": action.get("file"),
                    "lineno": action.get("lineno")
                })
        
        print(f"[ACTION] Found {len(simplified_actions)} actions")
        
        return ActionsListResponse(
            result=f"Found {len(simplified_actions)} actions",
            success=True,
            actions=simplified_actions,
            count=len(simplified_actions),
            server_url=server_url
        )
        
    except Exception as e:
        print(f"[ACTION] Error listing actions: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return ActionsListResponse(
            result=f"Error listing actions: {e}",
            error=str(e),
            success=False
        )


@action(is_consequential=False)
def get_action_run_logs(run_id: str) -> Response[str]:
    """Get the execution logs for a specific action run.
    
    Returns action run logs in plain text by requesting them from the action server.
    This is extremely useful for debugging failed runs or understanding what happened
    during execution.
    
    Args:
        run_id: The ID of the run to fetch logs for (from check_run_status or list_runs)
    
    Returns:
        Response with the plain text output logs of the run
    """
    try:
        print(f"[ACTION] Fetching logs for run: {run_id}")
        
        server_url = os.getenv("SERVER_URL", "http://localhost:8082")
        
        # The action server stores output in a special artifact
        artifact = "__action_server_output.txt"
        
        target_url = urllib.parse.urljoin(
            server_url,
            f"/api/runs/{run_id}/artifacts/text-content?artifact_names={artifact}",
        )
        
        response = http_get(target_url)
        
        if response.status_code == 404:
            return Response(result=f"Logs not found for run_id: {run_id}")
        
        if response.status_code != 200:
            return Response(result=f"Error fetching logs: Server returned status code {response.status_code}")
        
        payload = response.json()
        output = payload.get(artifact, "No output available")
        
        print(f"[ACTION] Successfully fetched logs for run {run_id} ({len(output)} characters)")
        
        return Response(result=output)
        
    except Exception as e:
        print(f"[ACTION] Error fetching run logs: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result=f"Error fetching logs: {str(e)}")


@action(is_consequential=False)
def get_action_run_logs_latest() -> Response[str]:
    """Fetch plain-text logs for the most recent action run.

    Convenience wrapper that looks up the latest run on the action server and
    returns its output logs—ideal for quick post-run debugging.
    """
    try:
        print(f"[ACTION] Fetching logs for latest run")
        
        server_url = os.getenv("SERVER_URL", "http://localhost:8082")
        
        # Get the list of runs
        runs_list_url = urllib.parse.urljoin(server_url, "/api/runs")
        runs_response = http_get(runs_list_url)
        
        if runs_response.status_code != 200:
            return Response(result=f"Error fetching runs list: Server returned status code {runs_response.status_code}")
        
        runs_payload = runs_response.json()
        
        if not runs_payload:
            return Response(result="No runs found on the action server")
        
        # Get the last run (most recent)
        last_run = runs_payload[-1]
        run_id = last_run.get("id")
        action_name = last_run.get("action_name", "unknown")
        
        print(f"[ACTION] Latest run is {run_id} (action: {action_name})")
        
        # Fetch logs for that run
        return get_action_run_logs(run_id)
        
    except Exception as e:
        print(f"[ACTION] Error fetching latest run logs: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result=f"Error fetching latest logs: {str(e)}")

