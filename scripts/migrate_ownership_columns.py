#!/usr/bin/env python3
"""
Migration Script: Backfill Ownership Columns
==============================================

This script migrates existing processing_jobs records by extracting ownership
information from the processing_metadata JSON field and populating the new
user_id and organization_id columns.

Purpose:
    - Promote ownership data from JSON metadata to first-class database columns
    - Enable performant ownership-based queries and security checks
    - Part of RBAC implementation for Image API

Usage:
    python scripts/migrate_ownership_columns.py

Requirements:
    - SQLite database at /data/processor.db (or override with DB_PATH env var)
    - Existing processing_jobs with processing_metadata containing:
        - uploader_id: User who uploaded the image
        - org_id: Organization the user belongs to

Safety:
    - Only updates rows where user_id IS NULL (idempotent)
    - Logs all operations with clear error messages
    - Transaction-based updates for consistency
"""

import asyncio
import aiosqlite
import json
import os
import sys
from datetime import datetime


# Configuration
DB_PATH = os.getenv("DATABASE_PATH", "/data/processor.db")


async def migrate_ownership_data():
    """Migrate ownership data from JSON metadata to dedicated columns."""

    print(f"{'='*70}")
    print(f"Ownership Column Migration - {datetime.utcnow().isoformat()}")
    print(f"{'='*70}")
    print(f"Database: {DB_PATH}\n")

    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"❌ ERROR: Database not found at {DB_PATH}")
        print(f"   Please ensure the database exists before running migration.")
        sys.exit(1)

    try:
        print(f"🔌 Connecting to database...")
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Step 1: Count total jobs needing migration
            print(f"\n📊 Analyzing migration scope...")
            async with db.execute(
                "SELECT COUNT(*) as count FROM processing_jobs WHERE user_id IS NULL"
            ) as cursor:
                row = await cursor.fetchone()
                total_to_migrate = row['count']

            print(f"   Total jobs requiring migration: {total_to_migrate}")

            if total_to_migrate == 0:
                print(f"\n✅ No migration needed - all records already have ownership data.")
                return

            # Step 2: Fetch jobs needing migration
            print(f"\n🔍 Fetching jobs with missing ownership data...")
            async with db.execute("""
                SELECT job_id, processing_metadata
                FROM processing_jobs
                WHERE user_id IS NULL
            """) as cursor:
                jobs = await cursor.fetchall()

            # Step 3: Process and update each job
            print(f"\n🔄 Processing {len(jobs)} jobs...\n")

            migrated_count = 0
            skipped_count = 0
            error_count = 0

            for idx, job in enumerate(jobs, 1):
                job_id = job['job_id']

                try:
                    # Parse metadata JSON
                    if not job['processing_metadata']:
                        print(f"   [{idx}/{total_to_migrate}] ⚠️  SKIP: {job_id[:8]}... - No metadata")
                        skipped_count += 1
                        continue

                    metadata = json.loads(job['processing_metadata'])
                    user_id = metadata.get('uploader_id')
                    org_id = metadata.get('org_id')

                    # Validate required fields exist
                    if not user_id or not org_id:
                        print(f"   [{idx}/{total_to_migrate}] ⚠️  SKIP: {job_id[:8]}... - Missing uploader_id or org_id")
                        skipped_count += 1
                        continue

                    # Update database record
                    await db.execute("""
                        UPDATE processing_jobs
                        SET user_id = ?, organization_id = ?
                        WHERE job_id = ?
                    """, (user_id, org_id, job_id))

                    migrated_count += 1

                    # Progress indicator (print every 10 records or if last)
                    if idx % 10 == 0 or idx == total_to_migrate:
                        print(f"   [{idx}/{total_to_migrate}] ✅ Migrated: {job_id[:8]}... (user: {user_id[:8]}...)")

                except json.JSONDecodeError as e:
                    print(f"   [{idx}/{total_to_migrate}] ❌ ERROR: {job_id[:8]}... - Invalid JSON: {e}")
                    error_count += 1
                except Exception as e:
                    print(f"   [{idx}/{total_to_migrate}] ❌ ERROR: {job_id[:8]}... - {type(e).__name__}: {e}")
                    error_count += 1

            # Step 4: Commit transaction
            print(f"\n💾 Committing changes to database...")
            await db.commit()

            # Step 5: Verify migration results
            print(f"\n🔍 Verifying migration results...")
            async with db.execute(
                "SELECT COUNT(*) as count FROM processing_jobs WHERE user_id IS NOT NULL"
            ) as cursor:
                row = await cursor.fetchone()
                total_with_ownership = row['count']

            # Summary
            print(f"\n{'='*70}")
            print(f"Migration Summary")
            print(f"{'='*70}")
            print(f"✅ Successfully migrated:  {migrated_count} records")
            print(f"⚠️  Skipped (no data):     {skipped_count} records")
            print(f"❌ Errors:                 {error_count} records")
            print(f"📊 Total with ownership:   {total_with_ownership} records")
            print(f"{'='*70}\n")

            if error_count > 0:
                print(f"⚠️  Warning: Some records failed to migrate. Review logs above.")
                sys.exit(1)
            elif skipped_count > 0:
                print(f"⚠️  Note: {skipped_count} records were skipped due to missing metadata.")
                print(f"   These jobs may not have ownership checks enforced.")
            else:
                print(f"✨ Migration completed successfully!")

    except Exception as e:
        print(f"\n❌ FATAL ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def verify_schema():
    """Verify that the database schema includes the new ownership columns."""

    print(f"\n🔍 Verifying database schema...")

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if user_id column exists
            async with db.execute("PRAGMA table_info(processing_jobs)") as cursor:
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                has_user_id = 'user_id' in column_names
                has_org_id = 'organization_id' in column_names

                if not has_user_id or not has_org_id:
                    print(f"❌ ERROR: Database schema is missing ownership columns!")
                    print(f"   Expected columns: user_id, organization_id")
                    print(f"   Found columns: {', '.join(column_names)}")
                    print(f"\n   Please run schema migration first:")
                    print(f"   1. Update app/db/schema.sql with new columns")
                    print(f"   2. Restart the application to apply schema changes")
                    sys.exit(1)

                print(f"✅ Schema verified - ownership columns exist")

    except Exception as e:
        print(f"❌ Schema verification failed: {e}")
        sys.exit(1)


def main():
    """Main entry point for migration script."""

    try:
        # Verify schema first
        asyncio.run(verify_schema())

        # Run migration
        asyncio.run(migrate_ownership_data())

    except KeyboardInterrupt:
        print(f"\n\n⚠️  Migration cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
