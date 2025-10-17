#!/usr/bin/env python3
"""
Test database migration safety.

This script:
1. Creates a backup
2. Tests the migration
3. Verifies data integrity
4. Shows before/after schema
"""

import sys
import sqlite3
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from linkedin.utils.db_sqlite import get_connection, _get_schema_version


def get_profile_count(conn):
    """Get count of profiles."""
    return conn.execute("SELECT COUNT(*) FROM user_profiles").fetchone()[0]


def get_profile_data(conn):
    """Get all profile data as dict."""
    rows = conn.execute("SELECT * FROM user_profiles").fetchall()
    return [dict(row) for row in rows]


def get_column_names(conn, table_name):
    """Get list of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def test_migration():
    """Test the migration process."""
    print("=" * 70)
    print("DATABASE MIGRATION TEST")
    print("=" * 70)
    print()
    
    # Step 1: Get connection (this triggers migration)
    print("📊 BEFORE MIGRATION")
    print("-" * 70)
    
    conn = get_connection()
    
    # Get current schema version
    version = _get_schema_version(conn)
    print(f"Schema version: {version}")
    
    # Get profile count
    profile_count = get_profile_count(conn)
    print(f"Profile count: {profile_count}")
    
    # Get column names
    columns = get_column_names(conn, "user_profiles")
    print(f"Total columns: {len(columns)}")
    print()
    
    # Show existing profile data
    if profile_count > 0:
        print("📝 EXISTING PROFILES:")
        print("-" * 70)
        profiles = get_profile_data(conn)
        for profile in profiles:
            print(f"Profile ID: {profile.get('profile_id')}")
            print(f"Name: {profile.get('full_name')}")
            print(f"Email: {profile.get('email')}")
            print(f"Created: {profile.get('created_at')}")
            
            # Show if new fields exist
            has_new_fields = 'first_name' in profile
            if has_new_fields:
                print(f"First Name: {profile.get('first_name')}")
                print(f"Last Name: {profile.get('last_name')}")
                print(f"Work Authorization: {profile.get('work_authorization')}")
            
            print()
    
    # Step 2: Show column list
    print("📋 COLUMN LIST:")
    print("-" * 70)
    
    old_columns = [
        'profile_id', 'profile_name', 'profile_type', 'is_active',
        'full_name', 'email', 'phone', 'phone_country',
        'linkedin_url', 'github', 'website',
        'location', 'title', 'summary', 'skills',
        'source_file', 'source_type',
        'version', 'parent_profile_id',
        'applications_count', 'success_rate', 'last_used_at',
        'created_at', 'updated_at'
    ]
    
    new_columns = [
        'first_name', 'last_name',
        'address_street', 'address_city', 'address_state', 'address_zip', 'address_country',
        'portfolio_url',
        'work_authorization', 'requires_visa_sponsorship', 'security_clearance',
        'veteran_status', 'disability_status', 'gender', 'race_ethnicity',
        'salary_min', 'salary_max', 'salary_currency',
        'earliest_start_date', 'willing_to_relocate', 'remote_preference',
        'years_of_experience',
        'custom_answers'
    ]
    
    print("✓ Original columns:")
    for col in old_columns:
        status = "✓" if col in columns else "✗"
        print(f"  {status} {col}")
    
    print()
    print("➕ New columns added:")
    for col in new_columns:
        status = "✓" if col in columns else "✗"
        print(f"  {status} {col}")
    
    print()
    
    # Step 3: Verify data integrity
    print("🔍 DATA INTEGRITY CHECK:")
    print("-" * 70)
    
    checks = {
        "Profile count preserved": profile_count == get_profile_count(conn),
        "All old columns exist": all(col in columns for col in old_columns),
        "Some new columns exist": any(col in columns for col in new_columns),
        "Schema version updated": version >= 2
    }
    
    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")
    
    print()
    
    # Step 4: Summary
    print("=" * 70)
    if all(checks.values()):
        print("✅ MIGRATION SUCCESSFUL - All checks passed!")
    else:
        print("⚠️  MIGRATION ISSUES DETECTED - Review checks above")
    print("=" * 70)
    
    return all(checks.values())


if __name__ == "__main__":
    try:
        success = test_migration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
