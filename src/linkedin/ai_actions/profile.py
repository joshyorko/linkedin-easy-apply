from sema4ai.actions import Response, action, chat
import dotenv
import os
import json
from typing import List, Optional
from pathlib import Path

from ..utils.resume_parser import parse_resume_from_file, _download_resume_from_url
from ..utils.db import get_active_profile, get_connection

dotenv.load_dotenv()


def _get_resume_file_from_chat(filename: str) -> str:
    """Helper: Get resume file from chat using chat.get_file().
    
    Args:
        filename: Name of file uploaded to chat
    
    Returns:
        Path to file retrieved from chat
    """
    print(f"[Resume] Getting file from chat: {filename}")
    file_path = chat.get_file(filename)
    print(f"[Resume] File retrieved: {file_path}")
    return str(file_path)


@action(is_consequential=False)
def parse_resume_and_save_profile(
    resume_source: str,
    is_url: bool = False,
    is_chat_file: bool = True
) -> Response:
    """
    Parse resume PDF and extract user profile using AI. Saves structured profile data (contact info, skills, experience, education) for Easy Apply automation.
    
    Args:
        resume_source: Resume filename (from chat), URL, or local file path
        is_url: Set True if resume_source is a URL to download from
        is_chat_file: Set True if resume_source is uploaded to chat (default)
    
    Returns:
        Response with extracted profile data and confirmation
    """
    try:
        print(f"[ACTION] Parsing resume: {resume_source} (url={is_url}, chat={is_chat_file})")
        
        # Step 1: Get the file based on source type
        if is_url:
            # Download from URL
            filename = os.path.basename(resume_source) or "resume.pdf"
            file_path = _download_resume_from_url(resume_source, filename)
        elif is_chat_file:
            # Get from chat upload
            file_path = _get_resume_file_from_chat(resume_source)
        else:
            # Use as local file path
            file_path = resume_source
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Local file not found: {file_path}")
            print(f"[ACTION] Using local file: {file_path}")
        
        # Step 2: Parse the resume (file_path is already a local file)
        user_profile = parse_resume_from_file(
            filename=file_path,
            save_profile=True  # Auto-save to database
        )
        
        # Get profile_id from the saved profile
        active_profile = get_active_profile()
        profile_id = active_profile.get('profile_id') if active_profile else 'unknown'
        
        return Response(result={
            "success": True,
            "message": "Successfully parsed resume and saved profile to database!",
            "profile": user_profile,
            "profile_id": profile_id,
            "saved_to": "SQLite database (user_profiles table)",
            "source_file": resume_source
        })
        
    except FileNotFoundError as e:
        print(f"[ACTION] File not found: {e}")
        return Response(result={
            "success": False,
            "error": "File not found. Make sure you've uploaded the resume file in chat first.",
            "message": str(e)
        })
    except Exception as e:
        print(f"[ACTION] Error parsing resume: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e),
            "message": "Failed to parse resume. Check that it's a valid PDF and try again."
        })


@action
def get_profile_history_list(limit: int = 20) -> Response:
    """
    Get a list of all saved user profile versions with metadata.
    
    This action shows your profile history from the database, including when each
    profile was created, how many applications used it, and success rates.
    Useful for tracking profile changes and seeing which versions perform best.
    
    Args:
        limit: Maximum number of profiles to return (default: 20)
    
    Returns:
        Response with list of profile metadata
    """
    try:
        from ..utils.db import get_profile_history
        
        print(f"[ACTION] Getting profile history (limit={limit})")
        
        # Get active profile info
        active = get_active_profile()
        
        # Get profile history
        profiles = get_profile_history(limit=limit)
        
        return Response(result={
            "success": True,
            "total_profiles": len(profiles),
            "active_profile": {
                "name": active.get('full_name') if active else None,
                "title": active.get('title') if active else None
            } if active else None,
            "profiles": profiles
        })
        
    except Exception as e:
        print(f"[ACTION] Error getting profile history: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e),
            "message": "Failed to get profile history."
        })


@action
def update_profile_skills(
    add_skills: Optional[List[str]] = None,
    remove_skills: Optional[List[str]] = None,
    set_skills: Optional[List[str]] = None
) -> Response:
    """
    Update skills in your active user profile without re-parsing resume.
    
    **Use this to quickly test fit analysis with different skill sets!**
    
    Args:
        add_skills: List of skills to add to existing skills
        remove_skills: List of skills to remove from existing skills  
        set_skills: Replace all skills with this list (ignores add/remove)
    
    Returns:
        Response with updated profile
        
    Examples:
        # Add Azure skills to test Azure jobs
        update_profile_skills(add_skills=["Azure", "Azure DevOps", "Bicep", "C#"])
        
        # Remove AWS skills to test non-AWS job matching
        update_profile_skills(remove_skills=["AWS", "EKS"])
        
        # Completely replace skills
        update_profile_skills(set_skills=["Python", "RPA", "UiPath", "Automation Anywhere"])
    """
    try:
        conn = get_connection()
        
        # Get active profile
        result = conn.execute("""
            SELECT profile_id, skills, full_name 
            FROM user_profiles 
            WHERE is_active = true 
            ORDER BY created_at DESC 
            LIMIT 1
        """).fetchone()
        
        if not result:
            return Response(result={
                "success": False,
                "error": "No active profile found. Run parse_resume_and_save_profile() first."
            })
        
        profile_id, current_skills_json, full_name = result
        
        # Parse current skills
        try:
            current_skills = json.loads(current_skills_json) if current_skills_json else []
        except:
            current_skills = []
        
        # Apply skill updates
        if set_skills is not None:
            # Replace all skills
            new_skills = set_skills
            print(f"[Profile] Replacing all skills with {len(set_skills)} new skills")
        else:
            new_skills = list(current_skills)
            
            if add_skills:
                for skill in add_skills:
                    if skill not in new_skills:
                        new_skills.append(skill)
                print(f"[Profile] Added {len(add_skills)} skills")
            
            if remove_skills:
                new_skills = [s for s in new_skills if s not in remove_skills]
                print(f"[Profile] Removed {len(remove_skills)} skills")
        
        # Update database
        conn.execute("""
            UPDATE user_profiles 
            SET skills = ?, 
                updated_at = CURRENT_TIMESTAMP
            WHERE profile_id = ?
        """, [json.dumps(new_skills), profile_id])
        
        conn.commit()
        
        print(f"[Profile] Updated skills for {full_name} ({profile_id})")
        print(f"[Profile] Old skill count: {len(current_skills)}, New: {len(new_skills)}")
        
        return Response(result={
            "success": True,
            "profile_id": profile_id,
            "full_name": full_name,
            "old_skills_count": len(current_skills),
            "new_skills_count": len(new_skills),
            "skills": new_skills,
            "message": f"Updated skills for {full_name}. Now has {len(new_skills)} skills."
        })
        
    except Exception as e:
        print(f"[ACTION] Error updating profile skills: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e)
        })


@action
def enrich_user_profile(
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    address_street: Optional[str] = None,
    address_city: Optional[str] = None,
    address_state: Optional[str] = None,
    address_zip: Optional[str] = None,
    work_authorization: Optional[str] = None,
    requires_visa_sponsorship: Optional[bool] = None,
    security_clearance: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    earliest_start_date: Optional[str] = None,
    willing_to_relocate: Optional[bool] = None,
    years_of_experience: Optional[int] = None,
    portfolio_url: Optional[str] = None
) -> Response:
    """
    Enrich active user profile with additional fields not captured from resume.
    
    This fills gaps in your profile for common application questions like:
    - Work authorization status
    - Address/location details
    - Salary expectations
    - Start date availability
    - Security clearance
    
    Args:
        first_name: First name (if not in resume)
        last_name: Last name (if not in resume)
        address_street: Street address
        address_city: City
        address_state: State/Province
        address_zip: ZIP/Postal code
        work_authorization: e.g., "US Citizen", "Green Card", "H1B", "Requires Sponsorship"
        requires_visa_sponsorship: True/False
        security_clearance: e.g., "None", "Secret", "Top Secret"
        salary_min: Minimum desired salary (USD)
        salary_max: Maximum desired salary (USD)
        earliest_start_date: e.g., "Immediately", "2 weeks", "1 month"
        willing_to_relocate: True/False
        years_of_experience: Total years of professional experience
        portfolio_url: Portfolio or personal website
    
    Returns:
        Response with updated profile
        
    Example:
        enrich_user_profile(
            work_authorization="US Citizen",
            requires_visa_sponsorship=False,
            salary_min=120000,
            salary_max=160000,
            earliest_start_date="2 weeks",
            willing_to_relocate=False,
            years_of_experience=8
        )
    """
    try:
        conn = get_connection()
        
        # Get active profile
        result = conn.execute("""
            SELECT profile_id, full_name 
            FROM user_profiles 
            WHERE is_active = true 
            ORDER BY created_at DESC 
            LIMIT 1
        """).fetchone()
        
        if not result:
            return Response(result={
                "success": False,
                "error": "No active profile found. Run parse_resume_and_save_profile() first."
            })
        
        profile_id, full_name = result
        
        # Build update query dynamically based on provided fields
        updates = []
        values = []
        
        field_mapping = {
            'first_name': first_name,
            'last_name': last_name,
            'address_street': address_street,
            'address_city': address_city,
            'address_state': address_state,
            'address_zip': address_zip,
            'work_authorization': work_authorization,
            'requires_visa_sponsorship': requires_visa_sponsorship,
            'security_clearance': security_clearance,
            'salary_min': salary_min,
            'salary_max': salary_max,
            'earliest_start_date': earliest_start_date,
            'willing_to_relocate': willing_to_relocate,
            'years_of_experience': years_of_experience,
            'portfolio_url': portfolio_url
        }
        
        for field, value in field_mapping.items():
            if value is not None:
                updates.append(f"{field} = ?")
                values.append(value)
        
        if not updates:
            return Response(result={
                "success": False,
                "error": "No fields provided to update. Specify at least one field."
            })
        
        # Add profile_id to values and update timestamp
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(profile_id)
        
        query = f"""
            UPDATE user_profiles 
            SET {', '.join(updates)}
            WHERE profile_id = ?
        """
        
        conn.execute(query, values)
        conn.commit()
        
        print(f"[Profile] Enriched profile {profile_id} with {len([v for v in field_mapping.values() if v is not None])} fields")
        
        return Response(result={
            "success": True,
            "profile_id": profile_id,
            "full_name": full_name,
            "fields_updated": [k for k, v in field_mapping.items() if v is not None],
            "message": f"Successfully enriched profile for {full_name}!"
        })
        
    except Exception as e:
        print(f"[ACTION] Error enriching profile: {e}")
        import traceback
        print(f"[ACTION] Full traceback: {traceback.format_exc()}")
        return Response(result={
            "success": False,
            "error": str(e)
        })
