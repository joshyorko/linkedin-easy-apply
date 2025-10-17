"""
Enhanced field extraction functions for LinkedIn job scraping.
These functions extract the missing high-value fields identified in MISSING_FIELDS_ANALYSIS.md
"""

import re
from typing import Dict, Any
from urllib.parse import urljoin


def extract_company_information(page, company_name: str) -> Dict[str, Any]:
    """Extract enhanced company information from LinkedIn job page"""
    company_info: Dict[str, Any] = {
        "company_size": None,
        "industry": None,
        "company_description": None,
        "company_logo_url": None,
        "company_linkedin_url": None,
        "company_location": None
    }
    
    try:
        # Company size patterns
        company_size_patterns = [
            r'(\d+(?:,\d+)*[-–]\d+(?:,\d+)*)\s+employees',
            r'(\d+(?:,\d+)*\+?)\s+employees',
            r'(Startup|Small|Medium|Large)\s+company',
            r'(\d+(?:,\d+)*[-–]\d+(?:,\d+)*)\s+people',
            r'Self-employed',
            r'Freelance'
        ]
        
        # Look for company size in various locations
        size_selectors = [
            'main .jobs-unified-top-card__subtitle-secondary-grouping',
            'main [data-test*="company-size"]',
            'main .company-size',
            'main span:has-text("employees")',
            'main span:has-text("people")'
        ]
        
        for selector in size_selectors:
            elements = page.locator(selector).all()
            for elem in elements:
                try:
                    text = elem.inner_text().strip()
                    for pattern in company_size_patterns:
                        match = re.search(pattern, text, re.IGNORECASE)
                        if match:
                            company_info["company_size"] = match.group(1)
                            break
                    if company_info["company_size"]:
                        break
                except Exception:
                    continue
            if company_info["company_size"]:
                break
        
        # Industry extraction
        industry_selectors = [
            'main .jobs-unified-top-card__subtitle-secondary-grouping',
            'main [data-test*="industry"]',
            'main .company-industry',
            'main span:has-text("Computer Software")',
            'main span:has-text("Technology")',
            'main span:has-text("Healthcare")',
            'main span:has-text("Financial Services")'
        ]
        
        for selector in industry_selectors:
            elements = page.locator(selector).all()
            for elem in elements:
                try:
                    text = elem.inner_text().strip()
                    # Filter out company size and other non-industry text
                    if (text and not any(word in text.lower() for word in 
                                       ['employee', 'people', 'ago', 'applicant', '·']) and
                        len(text) > 3 and len(text) < 100):
                        # Common industry keywords
                        industry_keywords = [
                            'Technology', 'Software', 'Healthcare', 'Finance', 'Financial Services',
                            'Education', 'Manufacturing', 'Retail', 'Media', 'Entertainment',
                            'Real Estate', 'Construction', 'Energy', 'Transportation', 'Logistics',
                            'Consulting', 'Marketing', 'Advertising', 'Telecommunications',
                            'Biotechnology', 'Pharmaceutical', 'Insurance', 'Banking'
                        ]
                        
                        for keyword in industry_keywords:
                            if keyword.lower() in text.lower():
                                company_info["industry"] = text
                                break
                        if company_info["industry"]:
                            break
                except Exception:
                    continue
            if company_info["industry"]:
                break
        
        # Company logo URL
        try:
            logo_selectors = [
                f'main img[alt*="{company_name}"]',
                'main .jobs-unified-top-card__company-logo img',
                'main [data-test*="company-logo"] img',
                'main .company-logo img'
            ]
            
            for selector in logo_selectors:
                logo_elem = page.locator(selector).first
                if logo_elem.count() > 0:
                    logo_url = logo_elem.get_attribute('src')
                    if logo_url and logo_url.startswith('http'):
                        company_info["company_logo_url"] = logo_url
                        break
        except Exception:
            pass
        
        # Company LinkedIn URL
        try:
            company_link_selectors = [
                f'main a[href*="/company/"]:has-text("{company_name}")',
                'main a[href*="/company/"]',
                'main .jobs-unified-top-card__company-name a'
            ]
            
            for selector in company_link_selectors:
                link_elem = page.locator(selector).first
                if link_elem.count() > 0:
                    href = link_elem.get_attribute('href')
                    if href and '/company/' in href:
                        if not href.startswith('http'):
                            href = urljoin("https://www.linkedin.com", href)
                        company_info["company_linkedin_url"] = href
                        break
        except Exception:
            pass
        
    except Exception as e:
        print(f"Error extracting company information: {e}")
    
    return company_info


def extract_job_requirements(page, job_description: str) -> Dict[str, Any]:
    """Extract job requirements and qualifications"""
    requirements: Dict[str, Any] = {
        "experience_level": None,
        "seniority_level": None,
        "education_requirements": None,
        "required_skills": [],
        "years_experience_required": None
    }
    
    try:
        # Experience level patterns
        experience_level_patterns = [
            r'(Entry level|Associate|Mid-Senior level|Director|Executive)',
            r'(Junior|Senior|Lead|Principal|Staff|Manager)',
            r'(Internship|Graduate|Entry|Senior|Executive)',
            r'(Level \d+|L\d+)'
        ]
        
        # Look for experience level in main content
        try:
            main_text = page.locator('main').inner_text()
            for pattern in experience_level_patterns:
                match = re.search(pattern, main_text, re.IGNORECASE)
                if match:
                    requirements["experience_level"] = match.group(1)
                    break
        except Exception:
            pass
        
        # Also check job description text
        if not requirements["experience_level"] and job_description:
            for pattern in experience_level_patterns:
                match = re.search(pattern, job_description, re.IGNORECASE)
                if match:
                    requirements["experience_level"] = match.group(1)
                    break
        
        # Years of experience patterns
        years_patterns = [
            r'(\d+(?:-\d+)?)\s+years?\s+(?:of\s+)?experience',
            r'(\d+\+?)\s+years?\s+(?:of\s+)?(?:relevant\s+)?experience',
            r'minimum\s+(?:of\s+)?(\d+)\s+years?',
            r'at least\s+(\d+)\s+years?'
        ]
        
        combined_text = f"{job_description} {main_text if 'main_text' in locals() else ''}"
        for pattern in years_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                requirements["years_experience_required"] = match.group(1)
                break
        
        # Education requirements patterns
        education_patterns = [
            r"(Bachelor'?s?|BS|BA)\s+(?:degree|Degree)",
            r"(Master'?s?|MS|MA|MBA)\s+(?:degree|Degree)",
            r"(PhD|Ph\.?D\.?|Doctorate)",
            r"(Associate'?s?)\s+(?:degree|Degree)",
            r"(High school|GED)",
            r"degree\s+(?:in|from)\s+([A-Za-z\s]+)",
            r"education:?\s*([^\.]+)"
        ]
        
        for pattern in education_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                requirements["education_requirements"] = match.group(0).strip()
                break
        
        # Skills extraction - comprehensive categories
        skill_categories = {
            'programming_languages': [
                'Python', 'Java', 'JavaScript', 'TypeScript', 'C++', 'C#', 'Go', 'Rust',
                'Ruby', 'PHP', 'Swift', 'Kotlin', 'Scala', 'R', 'MATLAB', 'SQL'
            ],
            'web_technologies': [
                'React', 'Angular', 'Vue.js', 'Node.js', 'Express', 'Django', 'Flask',
                'Spring', 'HTML', 'CSS', 'SASS', 'Bootstrap', 'jQuery'
            ],
            'cloud_platforms': [
                'AWS', 'Azure', 'Google Cloud', 'GCP', 'Heroku', 'DigitalOcean',
                'Kubernetes', 'Docker', 'Terraform', 'CloudFormation'
            ],
            'databases': [
                'MySQL', 'PostgreSQL', 'MongoDB', 'Redis', 'Cassandra', 'DynamoDB',
                'Oracle', 'SQL Server', 'SQLite', 'Elasticsearch'
            ],
            'tools_frameworks': [
                'Git', 'Jenkins', 'Jira', 'Confluence', 'Slack', 'Figma', 'Adobe',
                'Salesforce', 'HubSpot', 'Tableau', 'Power BI', 'Excel'
            ],
            'soft_skills': [
                'leadership', 'communication', 'teamwork', 'problem solving',
                'analytical', 'creative', 'detail oriented', 'organizational'
            ]
        }
        
        found_skills = []
        text_to_search = combined_text.lower()
        
        for category, skills in skill_categories.items():
            for skill in skills:
                # Use word boundaries to avoid partial matches
                pattern = r'\b' + re.escape(skill.lower()) + r'\b'
                if re.search(pattern, text_to_search):
                    found_skills.append(skill)
        
        # Remove duplicates and limit to most relevant
        requirements["required_skills"] = list(set(found_skills))[:20]  # Limit to top 20
        
    except Exception as e:
        print(f"Error extracting job requirements: {e}")
    
    return requirements


def extract_job_details(page, job_description: str) -> Dict[str, Any]:
    """Extract enhanced job details"""
    details: Dict[str, Any] = {
        "job_function": None,
        "employment_type": None,
        "remote_work_policy": None,
        "application_deadline": None,
        "external_apply_url": None
    }
    
    try:
        # Job function/department patterns
        function_patterns = [
            r'(Engineering|Development|Software)',
            r'(Sales|Business Development|Account Management)',
            r'(Marketing|Digital Marketing|Content)',
            r'(Design|UX|UI|Product Design)',
            r'(Product Management|Product)',
            r'(Data Science|Analytics|Data)',
            r'(Operations|DevOps|Infrastructure)',
            r'(Finance|Accounting|Financial)',
            r'(Human Resources|HR|People)',
            r'(Customer Success|Customer Support)',
            r'(Legal|Compliance|Risk)',
            r'(Research|R&D)',
            r'(Quality Assurance|QA|Testing)',
            r'(Security|Information Security|Cybersecurity)'
        ]
        
        main_text = page.locator('main').inner_text()
        combined_text = f"{job_description} {main_text}"
        
        for pattern in function_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                details["job_function"] = match.group(1)
                break
        
        # Employment type (more detailed than basic job_type)
        employment_types = [
            'Full-time', 'Part-time', 'Contract', 'Temporary', 'Freelance',
            'Internship', 'Volunteer', 'Apprenticeship', 'Seasonal',
            'Permanent', 'Fixed-term', 'Consultant'
        ]
        
        for emp_type in employment_types:
            if re.search(r'\b' + re.escape(emp_type) + r'\b', combined_text, re.IGNORECASE):
                details["employment_type"] = emp_type
                break
        
        # Remote work policy (more detailed than location_type)
        remote_patterns = [
            r'(Fully remote|100% remote|Remote-first)',
            r'(Hybrid|Remote-friendly|Flexible remote)',
            r'(On-site|In-office|Office-based)',
            r'(Remote with travel|Remote with occasional office)',
            r'(\d+ days? remote|\d+ days? in office)'
        ]
        
        for pattern in remote_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                details["remote_work_policy"] = match.group(1)
                break
        
        # Application deadline patterns
        deadline_patterns = [
            r'application deadline:?\s*([^\.]+)',
            r'apply by:?\s*([^\.]+)',
            r'deadline:?\s*([^\.]+)',
            r'applications close:?\s*([^\.]+)'
        ]
        
        for pattern in deadline_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                details["application_deadline"] = match.group(1).strip()
                break
        
        # External apply URL (for non-Easy Apply jobs)
        try:
            external_apply_selectors = [
                'main a[href*="apply"]:not([href*="linkedin"])',
                'main a:has-text("Apply on company website")',
                'main a:has-text("Apply externally")',
                'main button:has-text("Apply on company website")'
            ]
            
            for selector in external_apply_selectors:
                link_elem = page.locator(selector).first
                if link_elem.count() > 0:
                    href = link_elem.get_attribute('href')
                    if href and not href.startswith('#') and 'linkedin.com' not in href:
                        details["external_apply_url"] = href
                        break
        except Exception:
            pass
        
    except Exception as e:
        print(f"Error extracting job details: {e}")
    
    return details


def extract_engagement_metrics(page) -> Dict[str, Any]:
    """Extract engagement and status metrics"""
    metrics: Dict[str, Any] = {
        "views_count": None,
        "is_saved": False,
        "urgently_hiring": False,
        "fair_chance_employer": False,
        "job_reposted": False
    }
    
    try:
        # Views count patterns
        views_patterns = [
            r'(\d+(?:,\d+)*)\s+views?',
            r'viewed\s+(\d+(?:,\d+)*)\s+times?'
        ]
        
        main_text = page.locator('main').inner_text()
        for pattern in views_patterns:
            match = re.search(pattern, main_text, re.IGNORECASE)
            if match:
                metrics["views_count"] = match.group(1)
                break
        
        # Saved status
        try:
            save_selectors = [
                'main button[aria-label*="Unsave"]',
                'main [data-test*="saved"]',
                'main .saved-job'
            ]
            
            for selector in save_selectors:
                if page.locator(selector).count() > 0:
                    metrics["is_saved"] = True
                    break
        except Exception:
            pass
        
        # Urgently hiring flag
        urgency_keywords = [
            'urgently hiring', 'urgent', 'immediate start', 'asap',
            'hiring immediately', 'urgent need'
        ]
        
        for keyword in urgency_keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', main_text, re.IGNORECASE):
                metrics["urgently_hiring"] = True
                break
        
        # Fair chance employer
        fair_chance_keywords = [
            'fair chance employer', 'equal opportunity', 'diverse employer',
            'inclusive employer', 'fair chance'
        ]
        
        for keyword in fair_chance_keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', main_text, re.IGNORECASE):
                metrics["fair_chance_employer"] = True
                break
        
        # Job reposted status
        repost_keywords = [
            'reposted', 're-posted', 'posted again', 'job reposted'
        ]
        
        for keyword in repost_keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', main_text, re.IGNORECASE):
                metrics["job_reposted"] = True
                break
        
    except Exception as e:
        print(f"Error extracting engagement metrics: {e}")
    
    return metrics


def enhance_job_extraction(job_data: dict, page, job_description: str) -> dict:
    """
    Main function to enhance existing job data with missing fields
    """
    try:
        # Extract company information
        company_info = extract_company_information(page, job_data.get('company', ''))
        job_data.update(company_info)
        
        # Extract job requirements
        requirements = extract_job_requirements(page, job_description)
        job_data.update(requirements)
        
        # Extract job details
        details = extract_job_details(page, job_description)
        job_data.update(details)
        
        # Extract engagement metrics
        metrics = extract_engagement_metrics(page)
        job_data.update(metrics)
        
        print(f"Enhanced job data with {len(company_info) + len(requirements) + len(details) + len(metrics)} additional fields")
        
    except Exception as e:
        print(f"Error in enhance_job_extraction: {e}")
    
    return job_data
