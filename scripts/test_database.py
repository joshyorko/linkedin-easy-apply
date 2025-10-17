#!/usr/bin/env python3
"""
Database connection test utility.

Tests the configured database backend (SQLite or PostgreSQL) and verifies:
- Connection can be established
- Schema is created correctly
- Basic read/write operations work

Usage:
    python scripts/test_database.py
    
Environment variables:
    DATABASE_TYPE - "sqlite" or "postgres"
    DATABASE_URL - PostgreSQL connection string (if using postgres)
    SQLITE_PATH - SQLite database path (if using sqlite)
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from linkedin.utils import db


def test_connection():
    """Test database connection."""
    print("=" * 60)
    print("DATABASE CONNECTION TEST")
    print("=" * 60)
    
    # Show configuration
    db_type = os.getenv("DATABASE_TYPE", "sqlite")
    print(f"\n📊 Database Type: {db_type}")
    print(f"📍 Database Path: {db.get_db_path()}")
    
    # Test connection
    print("\n🔌 Testing connection...")
    try:
        conn = db.get_connection()
        print("✅ Connection successful!")
        
        # For PostgreSQL, return connection to pool
        if db_type == "postgres":
            from linkedin.utils.db_postgres import putconn
            putconn(conn)
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    
    return True


def test_schema():
    """Test that schema exists."""
    print("\n🗂️  Testing schema...")
    
    try:
        # Try to query the job_postings table
        jobs = db.query_jobs(limit=1)
        print(f"✅ Schema exists! Found {len(jobs)} jobs in database.")
        
        # Check for user_profiles table
        profile = db.get_active_profile()
        if profile:
            print(f"✅ Found active profile: {profile.get('full_name', 'Unknown')}")
        else:
            print("ℹ️  No active profile found (this is normal for new database)")
        
        return True
        
    except Exception as e:
        print(f"❌ Schema check failed: {e}")
        return False


def test_write_read():
    """Test basic write and read operations."""
    print("\n📝 Testing write/read operations...")
    
    try:
        # Create a test job
        test_job = {
            "job_id": "test_job_12345",
            "title": "Test Job - Database Test",
            "company": "Test Company",
            "easy_apply": True,
            "run_id": "test_run",
            "location_type": "Remote",
        }
        
        # Write
        print(f"   Writing test job {test_job['job_id']}...")
        count = db.write_jobs([test_job])
        print(f"   ✅ Wrote {count} job(s)")
        
        # Read
        print(f"   Reading test job...")
        job = db.read_job_by_id("test_job_12345")
        
        if job:
            print(f"   ✅ Read successful: {job['title']}")
            print(f"   ✅ Company: {job['company']}")
            print(f"   ✅ Location: {job['location_type']}")
            
            # Clean up test data
            print(f"\n🧹 Cleaning up test data...")
            # Note: We don't have a delete function, but that's okay for testing
            print("   ℹ️  Test job remains in database (no auto-cleanup)")
            
            return True
        else:
            print("   ❌ Could not read test job")
            return False
        
    except Exception as e:
        print(f"❌ Write/Read test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_profile_operations():
    """Test profile operations."""
    print("\n👤 Testing profile operations...")
    
    try:
        # Get profile history
        profiles = db.get_profile_history(limit=5)
        print(f"   ✅ Profile history query successful: {len(profiles)} profile(s)")
        
        if profiles:
            for p in profiles:
                print(f"   - {p.get('profile_name', 'Unnamed')} (active: {p.get('is_active')})")
        
        return True
        
    except Exception as e:
        print(f"❌ Profile operations failed: {e}")
        return False


def main():
    """Run all tests."""
    results = []
    
    # Test 1: Connection
    results.append(("Connection", test_connection()))
    
    # Test 2: Schema
    results.append(("Schema", test_schema()))
    
    # Test 3: Write/Read
    results.append(("Write/Read", test_write_read()))
    
    # Test 4: Profile Operations
    results.append(("Profile Ops", test_profile_operations()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:12} {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 All tests passed! Database is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check configuration and logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
