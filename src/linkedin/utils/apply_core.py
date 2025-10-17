"""Core Easy Apply logic - single source of truth for applying to jobs.

This module contains the consolidated logic for applying to LinkedIn jobs.
Both single and batch apply actions use this same core function.
"""

import time
import re
from typing import Dict, Any


def _apply_to_job_core(
    page,
    job_id: str,
    job_url: str,
    job_title: str,
    company: str,
    profile: Dict[str, Any],
    answers: Dict[str, Any],
    allow_submit: bool
) -> Dict[str, Any]:
    """
    Core function to apply to a single LinkedIn Easy Apply job.
    
    This is the single source of truth for applying to jobs.
    Both apply_to_single_job and batch_apply_by_run_id call this function.
    
    Args:
        page: Playwright page object (already configured and logged in)
        job_id: LinkedIn job ID
        job_url: Full job URL
        job_title: Job title (for logging)
        company: Company name (for logging)
        profile: User profile dictionary
        answers: AI-generated answers dictionary
        allow_submit: Whether to actually submit (False = safe/dry-run mode)
    
    Returns:
        Dict with result: {
            "success": bool,
            "submitted": bool,
            "verified": bool,
            "steps_completed": int,
            "fields_filled": int,
            "error": str (if failed)
        }
    """
    result = {
        "success": False,
        "submitted": False,
        "verified": False,
        "steps_completed": 0,
        "fields_filled": 0,
        "reached_submit": False,
        "error": None
    }
    
    try:
        print(f"[Core] Applying to: {job_title} at {company} ({job_id})")
        
        # Navigate to job page
        page.goto(job_url, timeout=30000)
        page.wait_for_load_state("domcontentloaded", timeout=20000)
        time.sleep(1)
        
        # Click Easy Apply button - Multiple strategies
        easy_apply_clicked = False
        
        # Strategy 1: Role-based selector (most reliable)
        try:
            btn = page.get_by_role("button", name=re.compile(r"Easy Apply", re.I)).first
            btn.wait_for(state="attached", timeout=8000)
            btn.click(timeout=10000, force=True)
            easy_apply_clicked = True
            print(f"[Core] ✓ Easy Apply clicked (role-based)")
        except Exception as e:
            print(f"[Core] Role-based click failed: {e}")
        
        # Strategy 2: Text match
        if not easy_apply_clicked:
            try:
                btn = page.locator('button:has-text("Easy Apply")').first
                btn.wait_for(state="attached", timeout=5000)
                btn.click(timeout=10000, force=True)
                easy_apply_clicked = True
                print(f"[Core] ✓ Easy Apply clicked (text match)")
            except Exception as e:
                print(f"[Core] Text match click failed: {e}")
        
        # Strategy 3: CSS selectors
        if not easy_apply_clicked:
            selectors = [
                '[aria-label*="Easy Apply"]',
                'button[data-test*="easy-apply"]',
                '.jobs-apply-button--top-card button'
            ]
            for sel in selectors:
                try:
                    btn = page.locator(sel).first
                    btn.wait_for(state="attached", timeout=3000)
                    btn.click(timeout=10000, force=True)
                    easy_apply_clicked = True
                    print(f"[Core] ✓ Easy Apply clicked ({sel})")
                    break
                except Exception:
                    continue
        
        if not easy_apply_clicked:
            result["error"] = "Easy Apply button not found"
            return result
        
        # Wait for dialog
        time.sleep(1.5)
        
        # Get dialog with multiple selectors
        dlg = None
        for selector in ['.jobs-easy-apply-modal', '[role="dialog"]', '.artdeco-modal']:
            try:
                dlg_candidate = page.locator(selector).first
                if dlg_candidate.count() > 0:
                    dlg = dlg_candidate
                    print(f"[Core] ✓ Dialog found: {selector}")
                    break
            except Exception:
                continue
        
        if not dlg or dlg.count() == 0:
            result["error"] = "Easy Apply dialog not visible"
            return result
        
        # Fill form with step navigation
        from .navigation_helper import navigate_and_fill_steps
        
        nav_summary = navigate_and_fill_steps(
            page=page,
            dlg=dlg,
            profile=profile,
            answers=answers,
            max_steps=10
        )
        
        result["steps_completed"] = nav_summary.get("steps_completed", 0)
        result["fields_filled"] = nav_summary.get("total_filled", 0)
        result["reached_submit"] = nav_summary.get("reached_submit", False)
        
        print(f"[Core] Navigation complete: {result['steps_completed']} steps, {result['fields_filled']} fields")
        
        # Handle submit page - CRITICAL: uncheck "Follow company" and avoid scrolling
        if result["reached_submit"]:
            print(f"[Core] On submit page - handling final checkboxes...")
            
            # Refresh dialog reference
            dlg = page.locator('[role="dialog"]').first
            
            # Uncheck "Follow company" checkbox - click the label (avoids interception)
            try:
                checked_checkboxes = dlg.locator('input[type="checkbox"]:checked')
                count = checked_checkboxes.count()
                
                if count > 0:
                    print(f"[Core] Found {count} checked checkbox(es), unchecking...")
                    first_checkbox = checked_checkboxes.first
                    
                    # Get checkbox ID to find the associated label (labels intercept clicks)
                    checkbox_id = first_checkbox.get_attribute('id')
                    if checkbox_id:
                        # Click the LABEL instead of the checkbox (avoids interception)
                        label = dlg.locator(f'label[for="{checkbox_id}"]').first
                        if label.count() > 0:
                            label.click(timeout=2000)
                            print(f"[Core] ✓ Unchecked 'Follow company' checkbox")
                        else:
                            first_checkbox.click(force=True, timeout=1000)
                            print(f"[Core] ✓ Unchecked checkbox (force click)")
                    else:
                        first_checkbox.click(force=True, timeout=1000)
                        print(f"[Core] ✓ Unchecked checkbox (force click)")
                else:
                    print(f"[Core] No checked checkboxes found")
                        
            except Exception as e:
                print(f"[Core] Checkbox operation failed: {e}")
            
            # NO SCROLLING on submit page
            
            # PAUSE for inspection in dry-run mode
            if not allow_submit:
                print(f"[Core] DRY-RUN: Pausing 5 seconds for inspection...")
                time.sleep(2)
            
            # NO SCROLLING on submit page - it's unnecessary and can cause issues
            
            # Handle submission based on allow_submit flag
            if allow_submit:
                print(f"[Core] SUBMIT MODE: Looking for Submit button...")
                
                submit_selectors = [
                    'button:has-text("Submit application")',
                    'button[aria-label*="Submit application"]',
                    'button[aria-label*="Submit"]',
                    'button:has-text("Submit")'
                ]
                
                submit_btn = None
                for sel in submit_selectors:
                    try:
                        btn = dlg.locator(sel).first
                        if btn.count() > 0 and btn.is_visible() and btn.is_enabled():
                            submit_btn = btn
                            print(f"[Core] Found Submit button: {sel}")
                            break
                    except Exception:
                        continue
                
                if submit_btn:
                    try:
                        submit_btn.click(timeout=5000)
                        print(f"[Core] ✅ SUBMITTED application")
                        result["submitted"] = True
                        time.sleep(1.5)
                        
                        # Quick verification - check if dialog closed
                        try:
                            if dlg.count() == 0 or not dlg.is_visible():
                                print(f"[Core] ✓ Dialog closed - submission successful")
                            else:
                                success_msgs = page.locator('text=/application.*submitted|successfully.*applied/i')
                                if success_msgs.count() > 0:
                                    print(f"[Core] ✓ Success message found")
                        except Exception:
                            pass
                        
                    except Exception as e:
                        print(f"[Core] ✗ Error clicking Submit: {e}")
                        result["error"] = f"Submit click failed: {e}"
                        return result
                else:
                    result["error"] = "Submit button not found"
                    return result
                    
            else:
                print(f"[Core] DRY-RUN MODE: Skipping submission (allow_submit=False)")
                result["submitted"] = False
        
        # Mark as success
        result["success"] = True
        
        return result
        
    except Exception as e:
        print(f"[Core] Error applying to job: {e}")
        result["error"] = str(e)
        return result
