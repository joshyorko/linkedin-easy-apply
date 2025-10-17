from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple


UserProfile = Dict[str, Any]


def _find_email(text: str) -> Optional[str]:
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return m.group(0) if m else None


def _find_phone(text: str) -> Optional[str]:
    # Very liberal phone regex for +country and US formats
    m = re.search(r"(\+?\d[\d\s().-]{7,}\d)", text)
    return m.group(1) if m else None


def _find_link(text: str, domain: str) -> Optional[str]:
    pattern = rf"https?://[\w.-]*{re.escape(domain)}/[\w\-_/]*"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(0) if m else None


def _find_website(text: str) -> Optional[str]:
    # generic website (avoid linkedin/github which are found separately)
    m = re.search(r"https?://(?!.*(linkedin|github)\.com)[\w.-]+\.[A-Za-z]{2,}[/\w\-_.]*/?", text, flags=re.IGNORECASE)
    return m.group(0) if m else None


def _extract_name_and_title(lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
    # Heuristic: first non-empty line as name, second non-empty line as title
    non_empty = [l.strip() for l in lines if l.strip()]
    name = non_empty[0] if non_empty else None
    title = None
    if len(non_empty) > 1:
        # Avoid lines that look like location/contact details
        if not re.search(r"(\d|@|http|linkedin|github)", non_empty[1], re.IGNORECASE):
            title = non_empty[1]
    return name, title


def _extract_skills(text: str) -> List[str]:
    # Look for a Skills section
    skills: List[str] = []
    skills_section = re.search(r"(?is)\bskills\b[:\-\s]*\n(.+?)(\n\n|$)", text)
    if skills_section:
        block = skills_section.group(1)
        items = re.split(r"[,\n•\-]+", block)
        skills = [s.strip() for s in items if s.strip()]
    return skills


def parse_profile_text(text: str, env_defaults: Optional[Dict[str, str]] = None) -> UserProfile:
    """Parse a freeform profile text into a structured profile dict.

    The result is not persisted; callers can preview and then choose to save.
    """
    env_defaults = env_defaults or {}
    lines = text.splitlines()
    name, title = _extract_name_and_title(lines)

    email = _find_email(text) or env_defaults.get("PROFILE_EMAIL")
    phone = _find_phone(text) or env_defaults.get("PROFILE_PHONE")
    linkedin_url = _find_link(text, "linkedin.com") or env_defaults.get("PROFILE_LINKEDIN_URL")
    github = _find_link(text, "github.com") or env_defaults.get("PROFILE_GITHUB")
    website = _find_website(text) or env_defaults.get("PROFILE_WEBSITE")

    # Location heuristic: look for City, ST style or common separators
    location = env_defaults.get("PROFILE_LOCATION")
    if not location:
        m = re.search(r"([A-Za-z .'-]+,\s*[A-Z]{2,})", text)
        if m:
            location = m.group(1)

    summary = None
    # Try to capture a short summary near the top
    for i in range(min(6, len(lines))):
        l = lines[i].strip()
        if len(l) > 20 and not re.search(r"(@|http|linkedin|github)", l, re.IGNORECASE):
            summary = l
            break

    skills_list = _extract_skills(text)
    if not skills_list and env_defaults.get("PROFILE_SKILLS"):
        skills_list = [s.strip() for s in env_defaults.get("PROFILE_SKILLS", "").split(",") if s.strip()]

    profile: UserProfile = {
        "full_name": name or env_defaults.get("PROFILE_FULL_NAME"),
        "email": email,
        "phone": phone,
        "phone_country": env_defaults.get("PROFILE_PHONE_COUNTRY", "US"),
        "linkedin_url": linkedin_url,
        "github": github,
        "website": website,
        "location": location,
        "title": title or env_defaults.get("PROFILE_TITLE"),
        "summary": summary or env_defaults.get("PROFILE_SUMMARY"),
        "skills": skills_list,
    }
    return profile


def profile_to_row(profile: UserProfile) -> Dict[str, str]:
    """Flatten a profile into a single-row dict compatible with files.user_profile."""
    return {
        "full_name": (profile.get("full_name") or "").strip(),
        "email": (profile.get("email") or "").strip(),
        "phone": (profile.get("phone") or "").strip(),
        "phone_country": (profile.get("phone_country") or "").strip(),
        "linkedin_url": (profile.get("linkedin_url") or "").strip(),
        "github": (profile.get("github") or "").strip(),
        "website": (profile.get("website") or "").strip(),
        "location": (profile.get("location") or "").strip(),
        "title": (profile.get("title") or "").strip(),
        "summary": (profile.get("summary") or "").strip(),
        "skills": ", ".join(profile.get("skills") or []),
    }
