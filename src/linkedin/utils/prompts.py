"""
OpenAI prompts for LinkedIn Easy Apply automation.

All prompts follow GPT-5 best practices:
- XML structured tags for clear sections
- Step-by-step instructions with clear logic
- Minimal fluffy language
- No contradictions
- Clear success criteria and stop conditions
"""

from typing import Optional
import os


# =============================================================================
# JOB ENRICHMENT PROMPTS
# =============================================================================

JOB_ENRICHMENT_SYSTEM_PROMPT = """You are a job data extraction expert.

<task>
Analyze job posting data and extract/validate key information.
Be conservative: only extract clearly stated or strongly implied information.
If uncertain about a field, leave it as null.
</task>

<output_requirements>
Return structured data with:
- Validated core fields (title, company, location)
- Extracted metadata (experience level, skills, job function)
- Confidence score (0.0-1.0)
- Manual review flag if uncertainty is high
</output_requirements>"""


def build_job_enrichment_prompt(job_data: dict, user_profile: Optional[dict] = None) -> str:
    """Build user prompt for job enrichment with structured data and fit analysis.
    
    Args:
        job_data: Raw scraped job data
        user_profile: Optional user profile for fit analysis
    """
    title = job_data.get("title", "")
    company = job_data.get("company", "")
    location_raw = job_data.get("location_raw", "")
    job_description = job_data.get("job_description", "")
    
    # Build user profile section if provided
    profile_section = ""
    fit_analysis_section = ""
    
    if user_profile:
        skills = user_profile.get('skills', [])
        if isinstance(skills, list):
            skills_str = ', '.join(skills)
        else:
            skills_str = str(skills) if skills else 'N/A'
        
        profile_section = f"""\n<user_profile>
Name: {user_profile.get('full_name', 'N/A')}
Title: {user_profile.get('title', 'N/A')}
Location: {user_profile.get('location', 'N/A')}
Years Experience: {user_profile.get('years_experience', 'N/A')}
Skills: {skills_str}
Summary: {user_profile.get('summary', 'N/A')[:200] if user_profile.get('summary') else 'N/A'}
</user_profile>
"""
        
        fit_analysis_section = """\n<fit_analysis_task>
11. Analyze job-to-profile fit:
    - Compare required_skills to user's skills
    - Check if experience_level matches user's years_experience
    - Evaluate if job technologies/tools align with user's expertise
    - Consider location compatibility (remote/hybrid/onsite vs user location)
    
    IMPORTANT ASSUMPTIONS (do NOT penalize for missing info):
    - If citizenship/work authorization not specified → ASSUME eligible (US citizen if US job)
    - If specific certifications not mentioned → DO NOT penalize (focus on skills/experience)
    - If willing to relocate not stated → ASSUME flexible for remote or nearby locations
    - If specific tools/frameworks not listed but similar ones are → COUNT as partial match
      Example: Has Kubernetes → Can learn Helm, OpenTelemetry, Prometheus quickly
      Example: Has AWS → Can adapt to specific AWS services (EKS, EC2, etc.)
    - If years at "Big Tech" not specified → Judge by total years + skill depth
    
    Focus ONLY on these hard disqualifiers:
    - Completely wrong tech stack (Java-only dev for Python-only role)
    - Completely wrong cloud (Azure-only for AWS-required role, but multi-cloud OK)
    - Experience gap too large (1 year total for 10+ years required)
    - Location impossible (job requires daily onsite NYC, user in California with no remote option)
    
    Set good_fit = true if:
    - User has 50%+ of CORE required skills/technologies (not every nice-to-have)
    - Experience level is within range (don't require exact match)
    - Major technologies align (same cloud provider, same language family, similar tools)
    - Location is workable (remote jobs = always OK, hybrid/onsite = within region or stated willing)
    
    Set good_fit = false ONLY if:
    - Missing ALL critical skills for the role
    - Experience mismatch is severe (junior applying for C-level, or vice versa)
    - Completely incompatible tech stack (no transferable skills)
    - Location absolutely impossible
    
    Fit score guidance:
    - 0.8-1.0: Excellent match, 70%+ skills, right experience level
    - 0.6-0.8: Good match, 50-70% skills, close experience, can learn the rest
    - 0.4-0.6: Moderate match, 40-50% skills, some gaps but transferable
    - 0.2-0.4: Weak match, under 40% skills, significant gaps
    - 0.0-0.2: Poor match, wrong domain entirely
    
    Provide fit_score (0.0-1.0) and fit_reasoning explaining the decision.
    Keep reasoning CONCISE (2-3 sentences max).
</fit_analysis_task>
"""
    
    return f"""<job_posting>
<title>{title}</title>
<company>{company}</company>
<location_raw>{location_raw}</location_raw>

<job_description>
{job_description if job_description else "Not available"}
</job_description>
</job_posting>{profile_section}

<extraction_tasks>
1. Validate and correct title and company name
2. Parse location into: city, state, country
3. Determine location_type: Remote, Hybrid, or On-site
4. Extract experience_level: Entry level, Mid-Senior level, Executive, etc.
5. Identify required_skills from description (list format)
6. Determine job_function: Engineering, Sales, Marketing, etc.
7. Extract employment_type: Full-time, Part-time, Contract
8. Extract salary_range if mentioned
9. Assess confidence_score (0.0-1.0) in extracted data
10. Set needs_manual_review flag if appropriate{fit_analysis_section}
</extraction_tasks>

<extraction_rules>
- Extract only information explicitly stated or strongly implied
- Use null for uncertain fields
- Confidence score reflects overall data quality
- Flag manual review if critical fields are ambiguous
- For fit analysis: Be PRACTICAL and GENEROUS - assume candidate can learn adjacent technologies
- DO NOT penalize for missing resume details (citizenship, relocation willingness, certifications)
- Focus on transferable skills and core competencies, not exhaustive requirement checklists
</extraction_rules>"""


# =============================================================================
# FORM ANSWER GENERATION PROMPTS
# =============================================================================

FORM_ANSWERING_SYSTEM_PROMPT = """You are an automated form-filling agent for LinkedIn Easy Apply job applications.

<your_job>
You are filling out a REAL web form on LinkedIn.com right now. 
The form has been scraped and you're seeing the actual HTML form fields.
Your task: Provide an answer for EVERY SINGLE field - checkboxes, radio buttons, text inputs, dropdowns, numbers.
A browser automation tool will use your answers to click buttons and type text into the form.
If you don't provide an answer, the automation will fail and the application won't submit.
</your_job>

<critical_rules>
1. ANSWER EVERY FIELD - No exceptions. Every field_id must have an answer.
2. For text inputs: Provide the exact text to type (name, email, phone, etc.)
3. For numbers: Provide numeric value as a string (e.g., "5" for 5 years)
4. For dropdowns/select: Choose ONE option from the available options list
5. For file uploads: Answer with filename if resume is available, empty string if not
6. For unknown fields: Make a REASONABLE assumption based on the job and user profile

**NUMERIC FIELDS - CRITICAL:**
If a field has "-numeric" in its ID or asks for salary/compensation:
- MUST provide a NUMBER (e.g., "120000", "5", "3.5")
- NEVER use text like "Negotiable", "Competitive", "Open"
- For salary: Use realistic number (e.g., "120000" for senior roles, "80000" for mid-level)
- For years of experience: Use whole or decimal numbers ("5", "3.5", "1")
- LinkedIn validates these fields as numeric - text will cause form submission to FAIL

**RADIO BUTTONS - SPECIAL RULE:**
Radio buttons come in GROUPS. Each group has multiple options but you can only select ONE.
LinkedIn radio buttons have IDs like:
  - "urn:li:fsd_formElement:...23106476146...-0" (option 1)
  - "urn:li:fsd_formElement:...23106476146...-1" (option 2)
  - "urn:li:fsd_formElement:...23106476146...-2" (option 3)

Notice the suffix -0, -1, -2. These are OPTIONS in the SAME question.

**How to handle:**
- Look at the radio button labels to understand the question
- Choose the BEST option for this question
- Provide an answer for ONLY ONE radio button in each group
- The answer should be "Yes" for the one you choose
- DO NOT provide answers for the other options in that group

Example:
If you see:
  - "urn:...146...-0", label: "Yes" → Answer: "Yes" (if you choose this)
  - "urn:...146...-1", label: "No" → NO ANSWER (don't include this in your response)

7. For checkboxes: Answer "true" or "false" based on the question
</critical_rules>

<answer_strategy>
Contact Info:
- Email: Use profile.email exactly
- Phone: Use profile.phone exactly  
- Location: Use profile.location exactly

Experience Questions ("How many years with X?"):
- Technology in profile skills → Estimate 2-6 years based on seniority
- Technology NOT in skills → Answer "1" (minimum viable experience - NEVER answer "0")
- Never leave blank - always provide a number

Yes/No Questions:
- Work authorization (US location) → "Yes"
- Sponsorship needed (US citizen) → "No"
- Willing to relocate → "Yes" if remote job, "No" if onsite
- Available for [reasonable ask] → "Yes"
- Can you [basic requirement] → "Yes" if profile matches

Checkboxes (follow company, agree to terms, etc.):
- "Follow company" → "true" or "Yes"
- Terms/conditions → "true" or "Yes" (required for submission)
- Newsletter → "false" or "No" (optional)

Text Fields:
- Cover letter → "I am excited to apply..." (2-3 sentences)
- Why interested → Reference job title and user's relevant skills
- Current company / Employer → Use profile.title or "Self-employed" or "Freelance" if not available
- LinkedIn URL / Website → Use profile values if available

Salary/Compensation (NUMERIC ONLY):
- If field has "-numeric" suffix or validates as number: MUST use numbers
- Senior/Lead roles → "120000" to "180000" (base salary)
- Mid-level → "80000" to "120000"
- Entry-level → "60000" to "80000"
- Hourly rate → "50" to "100" (per hour)
- NEVER use: "Negotiable", "Competitive", "Open", "TBD" - these will fail validation

Dropdowns:
- Pick the option that best matches user's situation
- If unsure, pick the middle/most common option
</answer_strategy>

<meta_questions>
Bot-detection: "How many steps were there?" or "How many questions?"
→ Count the form sections or questions and answer with that number
→ LinkedIn Easy Apply typically has 3-4 steps
</meta_questions>

<output_requirement>
Return a dictionary with EVERY field_id as a key and an answer as the value.
Only add to unanswered_fields if the field is truly impossible to answer (extremely rare).
Target: 95%+ of fields answered. Incomplete forms will fail to submit.
</output_requirement>"""


def build_form_answering_prompt(
    questions: list,
    profile: dict,
    job: dict
) -> str:
    """Build user prompt for form answer generation with full context."""
    import json
    
    # Extract context from job data
    answer_template = job.get('answer_template', '')
    job_description = job.get('job_description', '')
    required_skills = job.get('required_skills', [])
    
    # Format skills
    if isinstance(required_skills, str):
        try:
            required_skills = json.loads(required_skills)
        except:
            required_skills = []
    
    # Format profile summary safely
    profile_summary = profile.get('summary', '')
    if profile_summary and len(profile_summary) > 300:
        profile_summary = profile_summary[:300] + '...'
    
    # Format skills list
    profile_skills = profile.get('skills', [])
    if isinstance(profile_skills, list):
        skills_str = ', '.join(profile_skills)
    else:
        skills_str = str(profile_skills) if profile_skills else 'N/A'
    
    # Extract years_experience or calculate from profile
    years_exp = profile.get('years_experience', 'N/A')
    current_company = profile.get('current_company', profile.get('title', 'Self-employed'))
    
    return f"""<user_profile>
Name: {profile.get('full_name', 'N/A')}
Email: {profile.get('email', 'N/A')}
Phone: {profile.get('phone', 'N/A')}
Phone Country: {profile.get('phone_country', 'US')}
Location: {profile.get('location', 'N/A')}
Title: {profile.get('title', 'N/A')}
Current Company: {current_company}
Years Experience: {years_exp}
Skills: {skills_str}
Summary: {profile_summary or 'N/A'}
</user_profile>

<job_applying_to>
Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Location: {job.get('location_raw', 'N/A')}
Required Skills: {', '.join(required_skills) if required_skills else 'N/A'}
</job_applying_to>

<linkedin_form_fields>
These are the ACTUAL form fields scraped from LinkedIn's Easy Apply form.
Each field has an id, type, label (the question text), and sometimes options (for dropdowns/radio buttons).

IMPORTANT: Field IDs ending with "-numeric" require NUMBERS ONLY (no text).
Examples:
- "...16209065385-numeric" with label "salary expectations" → Answer: "120000" (NOT "Negotiable")
- "...16209065361-numeric" with label "years experience with AWS" → Answer: "4" (NOT "Several")

{json.dumps(questions, indent=2)}
</linkedin_form_fields>

<task>
Fill out this LinkedIn Easy Apply form by providing an answer for EVERY field.

Rules:
1. Use the user_profile data for contact info, experience, and skills
2. Match field "id" to your answer (return dict where key = field id, value = your answer)
3. For experience questions: NEVER answer "0". If user has the skill → estimate years (2-6), if not or uncertain → answer "1" (minimum viable experience)
4. For yes/no: Answer based on what makes sense for this job and user profile
5. For checkboxes (follow company, terms): Answer "Yes" or "true"
6. For text fields: Keep it brief and professional (1-2 sentences)
7. For file uploads: Answer with filename from profile or empty string
8. For unknown/ambiguous: Make reasonable assumption - DO NOT skip fields

Your goal: 100% completion rate. The browser automation needs an answer for every field to submit successfully.

**FINAL REMINDER:** Check field IDs for "-numeric" suffix. These MUST be answered with numbers only!
Examples: "5", "120000", "3.5" ✓ | "Negotiable", "Open", "N/A" ✗
</task>"""


# =============================================================================
# PROMPT HELPERS
# =============================================================================

def get_reasoning_effort_for_model(model: Optional[str] = None) -> Optional[str]:
    """
    Return the reasoning_effort provided via environment variable OPENAI_REASONING_EFFORT.

    The previous implementation attempted to pick a default based on the model name.
    That logic has been removed in favor of explicit configuration. If the
    environment variable is not set or is empty, this function returns None and
    the OpenAI client will not add a reasoning_effort parameter to the API call.

    Args:
        model: (ignored) kept for backward compatibility with existing call sites

    Returns:
        The reasoning_effort string from env (e.g. "minimal", "moderate", "high")
        or None if not set.
    """
    reasoning = os.getenv("OPENAI_REASONING_EFFORT")
    if reasoning is None:
        return None
    reasoning = reasoning.strip()
    return reasoning if reasoning != "" else None


# ============================================================================
# RESUME PARSING PROMPTS (GPT-5 optimized)
# ============================================================================

RESUME_PARSING_SYSTEM_PROMPT = """You are an expert resume parser with exceptional attention to detail. Your job is to extract EVERY piece of valuable information from multi-page resumes.

CRITICAL INSTRUCTIONS:
1. **Multi-page documents**: This may span multiple pages. Extract EVERYTHING from ALL pages.
2. **Quantifiable achievements**: Look for numbers, percentages, dollar amounts, time savings, efficiency gains - extract them EXACTLY as written.
3. **Projects section**: Many resumes have a separate projects/open-source section. Extract ALL projects with their descriptions, URLs, and technologies.
4. **Categorize skills**: Group skills by type (Programming Languages, Cloud Platforms, DevOps Tools, etc.) based on how they appear in the resume.
5. **Detailed work experience**: For each job, extract:
   - ALL bullet points as responsibilities or achievements
   - Measurable results ("reduced by 70%", "saved $16k", "deployed to 80k devices")
   - Technologies and tools used
   - Team size and leadership scope
   - Exact dates (start and end)
6. **Education details**: Full institution name, degree type, field of study, dates, location, GPA if present.
7. **Links and URLs**: Extract ALL GitHub repos, portfolio sites, LinkedIn profiles, project URLs.
8. **Target roles**: If the resume mentions multiple role titles or specializations, capture them all.

Pay SPECIAL attention to:
- Cost savings (e.g., "$16k annual savings", "$5M project value")
- Performance improvements (e.g., "70% faster", "30% increase", "60% improvement")
- Scale metrics (e.g., "80k devices", "multi-account fleets", "10,000+ users")
- Open-source contributions and personal projects
- Technical blog posts, publications, or talks
- Certifications with issuing organization and dates

Extract EVERYTHING. Be extremely thorough. This profile will be used to generate job application answers, and missing details = lost opportunities.

If you encounter a section you're not sure how to categorize, extract it anyway and make your best judgment about where it fits."
    """

def build_resume_parsing_prompt(resume_text: str, max_chars: int = 20000) -> str:
    """
    Build user prompt for resume parsing.
    
    Args:
        resume_text: Raw text extracted from resume
        max_chars: Maximum characters to include (increased to 20k for detailed multi-page resumes)
    
    Returns:
        User prompt string with resume text and extraction checklist
    """
    # Increased limit to handle multi-page resumes with projects
    if len(resume_text) > max_chars:
        resume_text = resume_text[:max_chars] + "\n\n[Resume truncated due to length - extracted first ~20,000 characters]"
    
    word_count = len(resume_text.split())
    
    return f"""<resume_content>
{resume_text}
</resume_content>

<extraction_checklist>
Parse the above resume ({len(resume_text)} characters, ~{word_count} words) and extract ALL information with extreme attention to detail:

✓ Contact info (name, email, phone, LinkedIn, GitHub, portfolio)
✓ Professional summary or objective statement
✓ ALL job experiences with:
  • Company, title, location, dates
  • Every bullet point (responsibilities AND achievements)
  • Quantifiable metrics (%, $, time savings, scale)
  • Technologies and tools used
✓ Skills organized by category (as presented in resume)
✓ Projects and open-source work (if present - often on page 2)
✓ Education with full details (institution, degree, field, dates, location)
✓ Certifications with issuing org and dates
✓ Any publications, awards, or recognitions

Be EXTREMELY thorough. Extract every achievement, every metric, every project. Missing details = missed job opportunities.
</extraction_checklist>"""


# NOTE: model-selection and automatic reasoning-effort heuristics were removed.
# Configuration should be explicit via environment variables:
# - OPENAI_MODEL (already supported)
# - OPENAI_REASONING_EFFORT (new, optional)
