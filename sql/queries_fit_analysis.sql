-- ============================================================================
-- Fit Analysis Queries for LinkedIn Jobs
-- ============================================================================
-- Use these queries to analyze job-to-profile fit results

-- ============================================================================
-- 1. FIT OVERVIEW
-- ============================================================================

-- Get fit distribution by run_id
SELECT 
    run_id,
    COUNT(*) as total_jobs,
    SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as good_fits,
    SUM(CASE WHEN good_fit = false THEN 1 ELSE 0 END) as bad_fits,
    SUM(CASE WHEN good_fit IS NULL THEN 1 ELSE 0 END) as not_analyzed,
    ROUND(AVG(fit_score), 3) as avg_fit_score,
    ROUND(MIN(fit_score), 3) as min_fit_score,
    ROUND(MAX(fit_score), 3) as max_fit_score
FROM job_postings
GROUP BY run_id
ORDER BY run_id DESC;

-- ============================================================================
-- 2. GOOD FIT JOBS (Ready to Apply)
-- ============================================================================

-- Get all good fit jobs with highest scores first
SELECT 
    job_id,
    title,
    company,
    location_type,
    fit_score,
    ai_confidence_score,
    easy_apply,
    date_posted,
    job_url
FROM job_postings
WHERE good_fit = true
  AND easy_apply = true
ORDER BY fit_score DESC, ai_confidence_score DESC;

-- Good fit jobs by specific run
SELECT 
    job_id,
    title,
    company,
    fit_score,
    required_skills,
    experience_level
FROM job_postings
WHERE run_id = 'YOUR_RUN_ID'
  AND good_fit = true
ORDER BY fit_score DESC;

-- ============================================================================
-- 3. BAD FIT JOBS (Analysis/Debug)
-- ============================================================================

-- Jobs that were filtered out (bad fit)
SELECT 
    job_id,
    title,
    company,
    fit_score,
    required_skills,
    experience_level,
    job_description
FROM job_postings
WHERE good_fit = false
ORDER BY fit_score DESC;

-- Bad fit jobs by tech stack (to identify pattern)
SELECT 
    job_id,
    title,
    company,
    fit_score,
    required_skills
FROM job_postings
WHERE good_fit = false
  AND required_skills LIKE '%GCP%'  -- Example: GCP jobs when user has AWS
ORDER BY fit_score DESC;

-- ============================================================================
-- 4. BORDERLINE JOBS (Manual Review)
-- ============================================================================

-- Jobs with fit_score between 0.5 and 0.7 (borderline cases)
SELECT 
    job_id,
    title,
    company,
    fit_score,
    good_fit,
    required_skills,
    experience_level
FROM job_postings
WHERE fit_score BETWEEN 0.5 AND 0.7
ORDER BY fit_score DESC;

-- ============================================================================
-- 5. FIT BY LOCATION TYPE
-- ============================================================================

-- Average fit score by location type (Remote/Hybrid/On-site)
SELECT 
    location_type,
    COUNT(*) as total_jobs,
    SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as good_fits,
    ROUND(AVG(fit_score), 3) as avg_fit_score
FROM job_postings
WHERE location_type IS NOT NULL
GROUP BY location_type
ORDER BY avg_fit_score DESC;

-- ============================================================================
-- 6. FIT BY EXPERIENCE LEVEL
-- ============================================================================

-- Average fit score by experience level
SELECT 
    experience_level,
    COUNT(*) as total_jobs,
    SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as good_fits,
    ROUND(AVG(fit_score), 3) as avg_fit_score
FROM job_postings
WHERE experience_level IS NOT NULL
GROUP BY experience_level
ORDER BY avg_fit_score DESC;

-- ============================================================================
-- 7. COMPANIES WITH BEST FIT RATES
-- ============================================================================

-- Companies with highest average fit scores
SELECT 
    company,
    COUNT(*) as total_jobs,
    SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as good_fits,
    ROUND(AVG(fit_score), 3) as avg_fit_score
FROM job_postings
WHERE company IS NOT NULL
GROUP BY company
HAVING COUNT(*) >= 2  -- At least 2 jobs from company
ORDER BY avg_fit_score DESC
LIMIT 20;

-- ============================================================================
-- 8. SKILLS ANALYSIS
-- ============================================================================

-- Extract skill patterns from good fit jobs
-- (Note: required_skills is stored as JSON text)
SELECT 
    job_id,
    title,
    company,
    fit_score,
    required_skills
FROM job_postings
WHERE good_fit = true
  AND required_skills IS NOT NULL
  AND required_skills != '[]'
ORDER BY fit_score DESC
LIMIT 50;

-- ============================================================================
-- 9. READY FOR APPLICATION
-- ============================================================================

-- Jobs that are:
-- 1. Good fit
-- 2. Easy Apply
-- 3. Have enriched answers
-- 4. Not yet applied
SELECT 
    job_id,
    title,
    company,
    fit_score,
    ai_confidence_score,
    job_url
FROM job_postings
WHERE good_fit = true
  AND easy_apply = true
  AND answers_json IS NOT NULL
  AND answers_json != ''
  AND is_applied = false
ORDER BY fit_score DESC, ai_confidence_score DESC;

-- ============================================================================
-- 10. FIT SCORE DISTRIBUTION
-- ============================================================================

-- Histogram of fit scores
SELECT 
    CASE 
        WHEN fit_score < 0.2 THEN '0.0-0.2'
        WHEN fit_score < 0.4 THEN '0.2-0.4'
        WHEN fit_score < 0.6 THEN '0.4-0.6'
        WHEN fit_score < 0.8 THEN '0.6-0.8'
        ELSE '0.8-1.0'
    END as fit_range,
    COUNT(*) as count,
    SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as marked_good,
    SUM(CASE WHEN good_fit = false THEN 1 ELSE 0 END) as marked_bad
FROM job_postings
WHERE fit_score IS NOT NULL
GROUP BY fit_range
ORDER BY fit_range;

-- ============================================================================
-- 11. RECENT JOBS BY FIT
-- ============================================================================

-- Most recent jobs sorted by fit score
SELECT 
    job_id,
    title,
    company,
    fit_score,
    good_fit,
    date_posted,
    scraped_at
FROM job_postings
WHERE fit_score IS NOT NULL
ORDER BY scraped_at DESC
LIMIT 50;

-- ============================================================================
-- 12. AI CONFIDENCE vs FIT SCORE
-- ============================================================================

-- Compare AI enrichment confidence with fit scores
SELECT 
    ROUND(fit_score, 1) as fit_score_bucket,
    COUNT(*) as count,
    ROUND(AVG(ai_confidence_score), 3) as avg_ai_confidence,
    SUM(CASE WHEN good_fit = true THEN 1 ELSE 0 END) as good_fits
FROM job_postings
WHERE fit_score IS NOT NULL
  AND ai_confidence_score IS NOT NULL
GROUP BY fit_score_bucket
ORDER BY fit_score_bucket DESC;
