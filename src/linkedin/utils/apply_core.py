"""Core Easy Apply logic - single source of truth for applying to jobs.

This module contains the consolidated logic for applying to LinkedIn jobs.
Both single and batch apply actions use this same core function.
"""

import time
import re
from typing import Dict, Any, Optional


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
        
        # Handle submit page - CRITICAL: check required terms, uncheck optional "Follow company"
        if result["reached_submit"]:
            print(f"[Core] On submit page - handling final checkboxes...")
            
            # Refresh dialog reference
            dlg = page.locator('[role="dialog"]').first
            
            # Find ALL checkboxes and their labels
            try:
                all_checkboxes = dlg.locator('input[type="checkbox"]')
                checkbox_count = all_checkboxes.count()
                print(f"[Core] Found {checkbox_count} checkbox(es) on submit page")
                
                for i in range(checkbox_count):
                    try:
                        checkbox = all_checkboxes.nth(i)
                        checkbox_id = checkbox.get_attribute('id')
                        is_checked = checkbox.is_checked()

                        # Find associated label or descriptive text
                        label = None
                        label_text = ""

                        def _strip(text: Optional[str]) -> str:
                            return text.strip() if isinstance(text, str) else ""

                        try:
                            if checkbox_id:
                                candidate = dlg.locator(f'label[for="{checkbox_id}"]').first
                                if candidate.count() > 0:
                                    label = candidate
                                    label_text = _strip(candidate.inner_text())
                        except Exception:
                            pass

                        if not label_text:
                            try:
                                parent_label = checkbox.locator('xpath=ancestor::label[1]')
                                if parent_label.count() > 0:
                                    label = parent_label.first
                                    label_text = _strip(parent_label.first.inner_text())
                            except Exception:
                                pass

                        if not label_text:
                            aria_label = checkbox.get_attribute('aria-label')
                            if aria_label:
                                label_text = _strip(aria_label)

                        if not label_text:
                            describedby = checkbox.get_attribute('aria-describedby')
                            if describedby:
                                texts = []
                                for desc_id in describedby.split():
                                    try:
                                        desc_el = dlg.locator(f'#{desc_id}').first
                                        if desc_el.count() > 0:
                                            texts.append(_strip(desc_el.inner_text()))
                                    except Exception:
                                        continue
                                if texts:
                                    label_text = " ".join([t for t in texts if t])

                        if not label_text:
                            try:
                                # Attempt to read nearby text nodes via JS (limited to 200 chars)
                                label_text = checkbox.evaluate(
                                    """
                                    el => {
                                        const cleanup = txt => (txt || '').replace(/\s+/g, ' ').trim();
                                        const pieces = [];
                                        const label = el.closest('label');
                                        if (label) {
                                            const text = cleanup(label.innerText);
                                            if (text) return text.slice(0, 200);
                                        }
                                        if (el.parentElement) {
                                            const parentText = cleanup(el.parentElement.innerText);
                                            if (parentText) pieces.push(parentText);
                                        }
                                        if (el.previousElementSibling) {
                                            const prevText = cleanup(el.previousElementSibling.innerText);
                                            if (prevText) pieces.push(prevText);
                                        }
                                        if (el.nextElementSibling) {
                                            const nextText = cleanup(el.nextElementSibling.innerText);
                                            if (nextText) pieces.push(nextText);
                                        }
                                        return pieces.join(' ').slice(0, 200);
                                    }
                                    """
                                ) or ""
                            except Exception:
                                label_text = ""

                        label_text = _strip(label_text)
                        label_text_lower = label_text.lower()

                        print(f"[Core] Checkbox {i+1}: '{label_text_lower[:80]}...' - Currently {'✓' if is_checked else '☐'}")
                        
                        # Determine action based on label text
                        is_terms = any(keyword in label_text_lower for keyword in [
                            'terms', 'conditions', 'privacy', 'policy', 'agree', 
                            'understand', 'consent', 'acknowledge'
                        ])
                        is_follow = 'follow' in label_text_lower and 'terms' not in label_text_lower
                        
                        if is_terms and not is_checked:
                            # Must CHECK this (terms/conditions/privacy)
                            print(f"[Core] ⚠️  REQUIRED checkbox not checked: '{label_text[:50]}' - CHECKING NOW...")
                            
                            # Try multiple strategies to check the box
                            checked_successfully = False
                            
                            # Strategy 1: Click the label (most reliable for LinkedIn)
                            if label and label.count() > 0:
                                try:
                                    # Wait for label to be ready
                                    label.wait_for(state="visible", timeout=2000)
                                    label.scroll_into_view_if_needed(timeout=2000)
                                    time.sleep(0.3)
                                    label.click(timeout=3000, force=False)
                                    time.sleep(0.3)
                                    
                                    # Verify it worked
                                    if checkbox.is_checked():
                                        checked_successfully = True
                                        print(f"[Core] ✅ Checked via label click")
                                except Exception as e:
                                    print(f"[Core] Label click failed: {e}")
                            
                            # Strategy 2: Direct checkbox click (force)
                            if not checked_successfully:
                                try:
                                    checkbox.scroll_into_view_if_needed(timeout=2000)
                                    time.sleep(0.2)
                                    checkbox.click(force=True, timeout=3000)
                                    time.sleep(0.3)
                                    
                                    if checkbox.is_checked():
                                        checked_successfully = True
                                        print(f"[Core] ✅ Checked via force click")
                                except Exception as e:
                                    print(f"[Core] Force click failed: {e}")
                            
                            # Strategy 3: JavaScript click
                            if not checked_successfully:
                                try:
                                    checkbox.evaluate("el => el.click()")
                                    time.sleep(0.3)
                                    
                                    if checkbox.is_checked():
                                        checked_successfully = True
                                        print(f"[Core] ✅ Checked via JavaScript")
                                except Exception as e:
                                    print(f"[Core] JavaScript click failed: {e}")
                            
                            # Strategy 4: Set checked property directly
                            if not checked_successfully:
                                try:
                                    checkbox.evaluate("el => el.checked = true")
                                    checkbox.evaluate("el => el.dispatchEvent(new Event('change', { bubbles: true }))")
                                    time.sleep(0.3)
                                    
                                    if checkbox.is_checked():
                                        checked_successfully = True
                                        print(f"[Core] ✅ Checked via property set")
                                except Exception as e:
                                    print(f"[Core] Property set failed: {e}")
                            
                            if not checked_successfully:
                                print(f"[Core] ❌ FAILED to check required checkbox - all strategies exhausted")
                            
                        elif is_terms and is_checked:
                            print(f"[Core] ✓ Required checkbox already checked: '{label_text[:50]}'")
                            
                        elif is_follow and is_checked:
                            # Must UNCHECK this (follow company)
                            print(f"[Core] Unchecking 'Follow company' checkbox...")
                            if label and label.count() > 0:
                                label.click(timeout=3000)
                            else:
                                checkbox.click(force=True, timeout=3000)
                            print(f"[Core] ✓ Unchecked 'Follow company' checkbox")
                            
                    except Exception as e:
                        print(f"[Core] Error processing checkbox {i+1}: {e}")
                        continue
                        
            except Exception as e:
                print(f"[Core] Checkbox scan failed: {e}")
            
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
                        time.sleep(2.0)  # Wait for submission to process
                        
                        # ENHANCED VERIFICATION: Check LinkedIn "My Jobs" page
                        # This is the most reliable verification method
                        verification_passed = False
                        verification_methods = []
                        
                        try:
                            # PRIMARY CHECK: Navigate to Applied Jobs page and verify job is there
                            print(f"[Core] Verifying submission via 'My Jobs' page...")
                            page.goto("https://www.linkedin.com/my-items/saved-jobs/?cardType=APPLIED", timeout=30000)
                            time.sleep(2.5)  # Allow page to fully load
                            
                            page_content = page.content()
                            if job_id in page_content:
                                print(f"[Core] ✓ VERIFIED: Job {job_id} found in Applied Jobs page")
                                result["verified"] = True
                                result["verification_message"] = f"Verified: Job {job_id} appears on LinkedIn Applied Jobs page"
                                verification_passed = True
                                verification_methods.append("LinkedIn Applied Jobs page")
                            else:
                                print(f"[Core] ⚠️ Job {job_id} not yet visible on Applied Jobs page (may need time to propagate)")
                                result["verification_message"] = f"Job {job_id} not yet visible on Applied Jobs page (may take 1-2 minutes)"
                        
                        except Exception as e:
                            print(f"[Core] Applied Jobs page check failed: {e}")
                            result["verification_message"] = f"Could not verify via Applied Jobs page: {e}"
                        
                        # FALLBACK CHECKS (less reliable but still useful)
                        if not verification_passed:
                            try:
                                # Return to job page to check for "Applied" badge
                                print(f"[Core] Fallback: Checking job page for 'Applied' badge...")
                                page.goto(job_url, timeout=30000)
                                time.sleep(1.5)
                                
                                # Look for "Applied" indicator
                                applied_indicators = page.locator('text=/Applied|You applied|application sent/i')
                                if applied_indicators.count() > 0:
                                    indicator_text = applied_indicators.first.inner_text()
                                    print(f"[Core] ✓ Found 'Applied' indicator: {indicator_text}")
                                    result["verified"] = True
                                    result["verification_message"] = f"Verified: 'Applied' badge found on job page"
                                    verification_passed = True
                                    verification_methods.append("Job page 'Applied' badge")
                            
                            except Exception as e:
                                print(f"[Core] Job page fallback check failed: {e}")
                        
                        if verification_passed:
                            print(f"[Core] ✅ Verification successful via: {', '.join(verification_methods)}")
                        else:
                            print(f"[Core] ⚠️ Could not verify submission - check logs and Applied Jobs page manually")
                                
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
