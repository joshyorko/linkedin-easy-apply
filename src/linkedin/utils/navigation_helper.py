"""Lightweight navigation helper for Easy Apply forms - optimized for speed."""

import time
from typing import Dict, Any


def navigate_and_fill_steps(page, dlg, profile: Dict[str, Any], answers: Dict[str, Any], max_steps: int = 10) -> Dict[str, Any]:
    """
    Navigate through Easy Apply form steps, filling each one.
    
    Lightweight version that doesn't rebuild form config on every step.
    Just fills, checks for Next/Review button, clicks it, repeats.
    
    Returns:
        Dict with summary: {
            "steps_completed": int,
            "total_filled": int,
            "reached_submit": bool
        }
    """
    from .apply_tools import _fill_easy_apply_dialog
    from .tools import _detect_step_info
    
    summary = {
        "steps_completed": 0,
        "total_filled": 0,
        "reached_submit": False
    }
    
    try:
        # Detect total steps at start
        step_info = _detect_step_info(dlg)
        detected_total = step_info.get("total")
        if detected_total:
            print(f"[Navigation] Detected {detected_total} total steps")
        
        last_progress = -1  # Track progress to detect stuck loops
        stuck_count = 0  # Count consecutive stuck iterations
        
        for step_num in range(max_steps):
            print(f"[Navigation] Step {step_num + 1}...")
            
            # Check current progress
            step_info = _detect_step_info(dlg)
            progress = step_info.get("progress", 0)
            print(f"[Navigation] Progress: {progress}%")
            
            # Check if we're at 100% (final/review step) BEFORE filling
            # This prevents unnecessary form scanning on the submit page
            if progress == 100:
                print(f"[Navigation] ✓ Reached 100% - final step (skipping fill)")
                summary["steps_completed"] = step_num + 1
                summary["reached_submit"] = True
                break
            
            # Detect if stuck (progress not changing)
            if progress == last_progress and last_progress >= 0:
                stuck_count += 1
                if stuck_count >= 2:
                    print(f"[Navigation] ⚠️ STUCK at {progress}% - progress not changing after 2 clicks")
                    print(f"[Navigation] Possible validation error or missing required field")
                    break
            else:
                stuck_count = 0  # Reset if progress changed
            
            last_progress = progress
            
            # Fill current step (only if not at 100%)
            try:
                step_result = _fill_easy_apply_dialog(page, dlg, profile, answers)
                filled = step_result.get("filled", 0)
                summary["total_filled"] += filled
                print(f"[Navigation] Filled {filled} fields")
                
                # Check for error messages after filling
                try:
                    error_selectors = [
                        '.artdeco-inline-feedback--error',
                        '[data-test-form-element-error]',
                        '.fb-dash-form-element__error-text'
                    ]
                    for err_sel in error_selectors:
                        errors = dlg.locator(err_sel)
                        if errors.count() > 0:
                            error_text = errors.first.inner_text()
                            print(f"[Navigation] ⚠️ Form error detected: {error_text}")
                            break
                except Exception:
                    pass
                    
            except Exception as e:
                print(f"[Navigation] Error filling step: {e}")
            
            summary["steps_completed"] = step_num + 1
            time.sleep(0.3)
            
            # Look for Next/Continue or Review button
            next_btn = None
            button_type = None
            
            # Fast button detection - try common patterns
            button_selectors = [
                ('button:has-text("Continue to next step")', 'Continue'),
                ('button:has-text("Review your application")', 'Review'),
                ('button:has-text("Review")', 'Review'),
                ('button:has-text("Next")', 'Next'),
                ('button:has-text("Continue")', 'Continue'),
                ('button[aria-label*="Continue"]', 'Continue'),
                ('button[aria-label*="Review"]', 'Review'),
                ('button[aria-label*="Next"]', 'Next'),
                # LinkedIn-specific classes
                ('button.artdeco-button--primary', 'Primary'),
                ('footer button[aria-label]', 'Footer Button')
            ]
            
            print(f"[Navigation] Looking for Next/Continue/Review button...")
            for sel, btn_type in button_selectors:
                try:
                    btn = dlg.locator(sel).first
                    if btn.count() > 0 and btn.is_visible():
                        # Check if enabled (but don't fail if check throws)
                        try:
                            is_enabled = btn.is_enabled()
                        except Exception:
                            is_enabled = True  # Assume enabled if check fails
                        
                        if is_enabled:
                            next_btn = btn
                            button_type = btn_type
                            print(f"[Navigation] Found {btn_type} button: {sel}")
                            break
                except Exception as e:
                    print(f"[Navigation] Selector '{sel}' failed: {e}")
                    continue
            
            if not next_btn:
                print(f"[Navigation] ⚠️ No Next/Review button found - assuming final step")
                print(f"[Navigation] Current progress: {progress}%, filled: {summary['total_filled']} fields")
                break
            
            # Click the button
            try:
                # Try normal click first
                try:
                    next_btn.click(timeout=3000)
                    print(f"[Navigation] ✓ Clicked {button_type} button (normal click)")
                except Exception as e1:
                    print(f"[Navigation] Normal click failed: {e1}")
                    print(f"[Navigation] Trying force click...")
                    try:
                        next_btn.click(timeout=3000, force=True)
                        print(f"[Navigation] ✓ Clicked {button_type} button (force click)")
                    except Exception as e2:
                        print(f"[Navigation] Force click also failed: {e2}")
                        raise e2
                
                time.sleep(0.8)  # Wait for next step to load
                
                # Refresh dialog reference after navigation
                dlg = page.locator('[role="dialog"]').first
                if dlg.count() == 0:
                    print(f"[Navigation] Dialog disappeared after click")
                    break
                    
            except Exception as e:
                print(f"[Navigation] ✗ Failed to click button after multiple attempts: {e}")
                print(f"[Navigation] Breaking navigation loop")
                break
        
        return summary
        
    except Exception as e:
        print(f"[Navigation] Error in navigate_and_fill_steps: {e}")
        return summary
