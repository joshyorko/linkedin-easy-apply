"""
Test suite for SQLite database backend.

Tests all database functions to ensure compatibility with the SQLite implementation.
"""
import os
import sys
import pytest
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Set environment to use SQLite before importing db module
os.environ["DB_BACKEND"] = "sqlite"
os.environ["SQLITE_PATH"] = str(Path(tempfile.gettempdir()) / "test_linkedin_jobs.sqlite")


from linkedin.utils import db


@pytest.fixture(scope="function")
def clean_db():
    """Create a fresh test database for each test."""
    test_db_path = Path(os.environ["SQLITE_PATH"])
    
    # Remove test database if it exists
    if test_db_path.exists():
        test_db_path.unlink()
    
    # Also remove WAL files
    wal_path = Path(str(test_db_path) + "-wal")
    shm_path = Path(str(test_db_path) + "-shm")
    if wal_path.exists():
        wal_path.unlink()
    if shm_path.exists():
        shm_path.unlink()
    
    # Force reconnection
    import linkedin.utils.db_sqlite as db_sqlite
    db_sqlite._connection = None
    
    yield
    
    # Cleanup after test
    if test_db_path.exists():
        test_db_path.unlink()
    if wal_path.exists():
        wal_path.unlink()
    if shm_path.exists():
        shm_path.unlink()


def test_connection(clean_db):
    """Test database connection and schema creation."""
    conn = db.get_connection()
    assert conn is not None
    
    # Verify tables exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    tables = [row[0] for row in cursor.fetchall()]
    
    assert 'job_postings' in tables
    assert 'user_profiles' in tables
    assert 'enriched_answers' in tables


def test_write_and_read_job(clean_db):
    """Test writing and reading job records."""
    job_record = {
        'job_id': 'test123',
        'title': 'Senior Python Developer',
        'company': 'TestCorp',
        'job_url': 'https://linkedin.com/jobs/test123',
        'easy_apply': True,
        'location_type': 'Remote',
        'scraped_at': '2025-01-01T12:00:00',
        'required_skills': ['Python', 'Django', 'PostgreSQL']
    }
    
    # Write job
    count = db.write_jobs([job_record])
    assert count == 1
    
    # Read job back
    job = db.read_job_by_id('test123')
    assert job is not None
    assert job['job_id'] == 'test123'
    assert job['title'] == 'Senior Python Developer'
    assert job['company'] == 'TestCorp'
    assert job['easy_apply'] is True  # Should be converted back to boolean
    assert isinstance(job['required_skills'], list)
    assert 'Python' in job['required_skills']


def test_boolean_conversion(clean_db):
    """Test that booleans are correctly converted to/from integers."""
    job_record = {
        'job_id': 'bool_test',
        'title': 'Test Job',
        'company': 'TestCorp',
        'easy_apply': True,
        'is_applied': False,
        'urgently_hiring': True,
        'verified_company': False
    }
    
    db.write_jobs([job_record])
    
    # Read back and verify booleans
    job = db.read_job_by_id('bool_test')
    assert job['easy_apply'] is True
    assert job['is_applied'] is False
    assert job['urgently_hiring'] is True
    assert job['verified_company'] is False


def test_json_fields(clean_db):
    """Test JSON field serialization/deserialization."""
    job_record = {
        'job_id': 'json_test',
        'title': 'Test Job',
        'company': 'TestCorp',
        'required_skills': ['Python', 'Kubernetes', 'AWS'],
        'benefits': ['Health Insurance', '401k', 'Remote Work'],
        'answers_json': {'question1': 'answer1', 'question2': 'answer2'}
    }
    
    db.write_jobs([job_record])
    
    job = db.read_job_by_id('json_test')
    assert isinstance(job['required_skills'], list)
    assert len(job['required_skills']) == 3
    assert 'Python' in job['required_skills']
    
    assert isinstance(job['benefits'], list)
    assert 'Remote Work' in job['benefits']
    
    assert isinstance(job['answers_json'], dict)
    assert job['answers_json']['question1'] == 'answer1'


def test_update_job_enrichment(clean_db):
    """Test updating enrichment fields."""
    # Create initial job
    job_record = {
        'job_id': 'enrich_test',
        'title': 'Test Job',
        'company': 'TestCorp'
    }
    db.write_jobs([job_record])
    
    # Update enrichment
    updates = {
        'ai_confidence_score': 0.95,
        'good_fit': True,
        'fit_score': 0.87,
        'processed': True
    }
    
    success = db.update_job_enrichment('enrich_test', updates)
    assert success is True
    
    # Verify updates
    job = db.read_job_by_id('enrich_test')
    assert job['ai_confidence_score'] == 0.95
    assert job['good_fit'] is True
    assert job['fit_score'] == 0.87
    assert job['processed'] is True


def test_update_answers_json(clean_db):
    """Test updating answers_json field."""
    job_record = {
        'job_id': 'answers_test',
        'title': 'Test Job',
        'company': 'TestCorp'
    }
    db.write_jobs([job_record])
    
    import json
    answers = {'question1': 'My answer 1', 'question2': 'My answer 2'}
    answers_json = json.dumps(answers)
    
    success = db.update_answers_json('answers_test', answers_json)
    assert success is True
    
    job = db.read_job_by_id('answers_test')
    assert job['answers_json'] == answers
    assert job['enriched_dataset'] == answers  # Should be synced


def test_update_is_applied(clean_db):
    """Test updating is_applied status."""
    job_record = {
        'job_id': 'applied_test',
        'title': 'Test Job',
        'company': 'TestCorp',
        'is_applied': False
    }
    db.write_jobs([job_record])
    
    success = db.update_is_applied('applied_test', True)
    assert success is True
    
    job = db.read_job_by_id('applied_test')
    assert job['is_applied'] is True


def test_get_jobs_by_run_id(clean_db):
    """Test querying jobs by run_id."""
    jobs = [
        {'job_id': 'run1_job1', 'title': 'Job 1', 'company': 'CompanyA', 'run_id': 'run_001'},
        {'job_id': 'run1_job2', 'title': 'Job 2', 'company': 'CompanyB', 'run_id': 'run_001'},
        {'job_id': 'run2_job1', 'title': 'Job 3', 'company': 'CompanyC', 'run_id': 'run_002'},
    ]
    
    db.write_jobs(jobs)
    
    run1_jobs = db.get_jobs_by_run_id('run_001')
    assert len(run1_jobs) == 2
    assert all(job['run_id'] == 'run_001' for job in run1_jobs)
    
    run2_jobs = db.get_jobs_by_run_id('run_002')
    assert len(run2_jobs) == 1
    assert run2_jobs[0]['job_id'] == 'run2_job1'


def test_query_jobs(clean_db):
    """Test flexible job querying."""
    jobs = [
        {'job_id': 'q1', 'title': 'Job 1', 'company': 'TestCorp', 'easy_apply': True, 'answers_json': '{"a": "b"}'},
        {'job_id': 'q2', 'title': 'Job 2', 'company': 'TestCorp', 'easy_apply': False},
        {'job_id': 'q3', 'title': 'Job 3', 'company': 'OtherCorp', 'easy_apply': True},
    ]
    
    db.write_jobs(jobs)
    
    # Query by company
    testcorp_jobs = db.query_jobs(company='TestCorp')
    assert len(testcorp_jobs) == 2
    
    # Query easy apply only
    easy_jobs = db.query_jobs(easy_apply_only=True)
    assert len(easy_jobs) == 2
    assert all(job['easy_apply'] for job in easy_jobs)
    
    # Query with answers
    answered_jobs = db.query_jobs(has_answers=True)
    assert len(answered_jobs) == 1
    assert answered_jobs[0]['job_id'] == 'q1'


def test_get_jobs_pending_enrichment(clean_db):
    """Test getting jobs that need enrichment."""
    jobs = [
        {'job_id': 'p1', 'title': 'Job 1', 'company': 'Test', 'easy_apply': True, 'questions_json': '{"q1": "text"}', 'processed': False},
        {'job_id': 'p2', 'title': 'Job 2', 'company': 'Test', 'easy_apply': True, 'questions_json': '{"q1": "text"}', 'processed': True},
        {'job_id': 'p3', 'title': 'Job 3', 'company': 'Test', 'easy_apply': False, 'questions_json': '{"q1": "text"}'},
    ]
    
    db.write_jobs(jobs)
    
    pending = db.get_jobs_pending_enrichment()
    assert len(pending) == 1
    assert pending[0]['job_id'] == 'p1'


def test_user_profile_crud(clean_db):
    """Test user profile create, read, update operations."""
    profile_data = {
        'full_name': 'John Doe',
        'email': 'john@example.com',
        'phone': '+1234567890',
        'linkedin_url': 'https://linkedin.com/in/johndoe',
        'location': 'San Francisco, CA',
        'title': 'Senior DevOps Engineer',
        'summary': 'Experienced engineer...',
        'skills': ['Python', 'Kubernetes', 'AWS', 'Terraform']
    }
    
    # Save profile
    profile_id = db.save_profile_to_db(
        profile=profile_data,
        source_file='test_resume.pdf',
        source_type='resume_parser',
        profile_name='DevOps Profile',
        is_active=True
    )
    
    assert profile_id is not None
    
    # Get active profile
    active_profile = db.get_active_profile()
    assert active_profile is not None
    assert active_profile['full_name'] == 'John Doe'
    assert active_profile['email'] == 'john@example.com'
    assert 'Python' in active_profile['skills']
    assert 'Kubernetes' in active_profile['skills']
    
    # Get profile by ID
    profile_by_id = db.get_profile_by_id(profile_id)
    assert profile_by_id['full_name'] == 'John Doe'


def test_profile_history(clean_db):
    """Test profile versioning and history."""
    # Create multiple profiles
    profile1 = {
        'full_name': 'John Doe',
        'email': 'john@example.com',
        'title': 'DevOps Engineer',
        'skills': ['Python', 'Kubernetes']
    }
    
    profile2 = {
        'full_name': 'Jane Smith',
        'email': 'jane@example.com',
        'title': 'SRE',
        'skills': ['Go', 'Prometheus']
    }
    
    id1 = db.save_profile_to_db(profile1, 'resume1.pdf', is_active=True)
    id2 = db.save_profile_to_db(profile2, 'resume2.pdf', is_active=False)
    
    # Get profile history
    history = db.get_profile_history(limit=10)
    assert len(history) == 2
    
    # Most recent should be first
    assert history[0]['profile_id'] == id2
    assert history[1]['profile_id'] == id1
    
    # Check active status
    active_profile = db.get_active_profile()
    assert active_profile['profile_id'] == id1  # id1 should still be active


def test_fit_analysis(clean_db):
    """Test job fit analysis functions."""
    jobs = [
        {'job_id': 'fit1', 'title': 'Job 1', 'company': 'A', 'run_id': 'run1', 'good_fit': True, 'fit_score': 0.9},
        {'job_id': 'fit2', 'title': 'Job 2', 'company': 'B', 'run_id': 'run1', 'good_fit': True, 'fit_score': 0.85},
        {'job_id': 'fit3', 'title': 'Job 3', 'company': 'C', 'run_id': 'run1', 'good_fit': False, 'fit_score': 0.3},
        {'job_id': 'fit4', 'title': 'Job 4', 'company': 'D', 'run_id': 'run2', 'good_fit': True, 'fit_score': 0.95},
    ]
    
    db.write_jobs(jobs)
    
    # Get fit summary for all jobs
    summary = db.get_fit_summary()
    assert summary['total_jobs'] == 4
    assert summary['good_fits'] == 3
    assert summary['bad_fits'] == 1
    
    # Get fit summary for specific run
    run1_summary = db.get_fit_summary(run_id='run1')
    assert run1_summary['total_jobs'] == 3
    assert run1_summary['good_fits'] == 2
    assert run1_summary['bad_fits'] == 1
    
    # Get good fit jobs
    good_fits = db.get_good_fit_jobs(run_id='run1', easy_apply_only=False)
    assert len(good_fits) == 2
    assert all(job['fit_score'] >= 0.85 for job in good_fits)
    
    # Get bad fit jobs
    bad_fits = db.get_bad_fit_jobs(run_id='run1')
    assert len(bad_fits) == 1
    assert bad_fits[0]['job_id'] == 'fit3'


def test_concurrent_access(clean_db):
    """Test that multiple connections can access the database concurrently."""
    import threading
    import time
    
    # Write initial job
    job = {'job_id': 'concurrent_test', 'title': 'Test', 'company': 'Test'}
    db.write_jobs([job])
    
    results = []
    
    def read_job():
        # Simulate concurrent read
        job = db.read_job_by_id('concurrent_test')
        results.append(job is not None)
    
    # Create multiple threads
    threads = [threading.Thread(target=read_job) for _ in range(5)]
    
    # Start all threads
    for thread in threads:
        thread.start()
    
    # Wait for all to complete
    for thread in threads:
        thread.join()
    
    # All reads should succeed
    assert all(results)
    assert len(results) == 5


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
