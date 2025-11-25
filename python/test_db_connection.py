#!/usr/bin/env python3
"""
Database Connection Test Script for SDNCheck

Tests the PostgreSQL database connection and verifies schema setup.

Usage:
    python test_db_connection.py
    
Environment Variables:
    DB_HOST: Database host (default: localhost)
    DB_PORT: Database port (default: 5432)
    DB_NAME: Database name (default: sdn_database)
    DB_USER: Database user (default: sdn_user)
    DB_PASSWORD: Database password (default: sdn_password)
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

def test_basic_connection():
    """Test basic PostgreSQL connection using psycopg2."""
    print("\n" + "=" * 60)
    print("🔍 Testing Basic PostgreSQL Connection")
    print("=" * 60)
    
    try:
        import psycopg2
        
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        database = os.getenv("DB_NAME", "sdn_database")
        user = os.getenv("DB_USER", "sdn_user")
        password = os.getenv("DB_PASSWORD", "sdn_password")
        
        print(f"\n📡 Connecting to: {host}:{port}/{database}")
        print(f"👤 User: {user}")
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        
        print(f"\n✅ CONEXIÓN EXITOSA A POSTGRESQL")
        print(f"📊 Versión de la Base de Datos: {version}")
        
        cursor.close()
        conn.close()
        return True
        
    except ImportError:
        print("❌ psycopg2 not installed. Install with: pip install psycopg2-binary")
        return False
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        return False


def test_sqlalchemy_connection():
    """Test SQLAlchemy connection and ORM setup."""
    print("\n" + "=" * 60)
    print("🔍 Testing SQLAlchemy Connection")
    print("=" * 60)
    
    try:
        from database.connection import init_db, get_db_manager, close_db
        
        # Initialize database
        db_manager = init_db(echo=False)
        
        # Health check
        if db_manager.health_check():
            print("\n✅ SQLAlchemy connection healthy")
        else:
            print("\n❌ SQLAlchemy health check failed")
            return False
        
        # Test session
        with db_manager.session() as session:
            from sqlalchemy import text
            result = session.execute(text("SELECT current_database(), current_user;"))
            row = result.fetchone()
            print(f"📊 Database: {row[0]}, User: {row[1]}")
        
        close_db()
        return True
        
    except ImportError as e:
        print(f"⚠️ SQLAlchemy test skipped (import error): {e}")
        return True  # Not a failure, just not available
    except Exception as e:
        print(f"\n❌ SQLAlchemy test failed: {e}")
        return False


def test_schema_tables():
    """Verify database schema tables exist."""
    print("\n" + "=" * 60)
    print("🔍 Verifying Database Schema")
    print("=" * 60)
    
    expected_tables = [
        'sanctioned_entities',
        'entity_aliases',
        'identity_documents',
        'entity_addresses',
        'entity_features',
        'sanctions_programs',
        'entity_programs',
        'screening_requests',
        'screening_results',
        'screening_matches',
        'audit_logs',
        'data_sources',
        'data_updates'
    ]
    
    try:
        import psycopg2
        
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        database = os.getenv("DB_NAME", "sdn_database")
        user = os.getenv("DB_USER", "sdn_user")
        password = os.getenv("DB_PASSWORD", "sdn_password")
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        
        cursor = conn.cursor()
        
        # Get all tables in public schema
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\n📋 Found {len(existing_tables)} tables in database:")
        
        all_present = True
        for table in expected_tables:
            if table in existing_tables:
                print(f"  ✅ {table}")
            else:
                print(f"  ❌ {table} (MISSING)")
                all_present = False
        
        # Check for any extra tables
        extra_tables = set(existing_tables) - set(expected_tables)
        if extra_tables:
            print(f"\n📋 Additional tables found:")
            for table in extra_tables:
                print(f"  ℹ️  {table}")
        
        cursor.close()
        conn.close()
        
        if all_present:
            print(f"\n✅ All {len(expected_tables)} expected tables are present!")
        else:
            print("\n⚠️ Some tables are missing. Run the init script.")
        
        return all_present
        
    except ImportError:
        print("❌ psycopg2 not installed")
        return False
    except Exception as e:
        print(f"\n❌ Schema verification failed: {e}")
        return False


def test_data_sources():
    """Verify initial data is populated."""
    print("\n" + "=" * 60)
    print("🔍 Checking Initial Data")
    print("=" * 60)
    
    try:
        import psycopg2
        
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        database = os.getenv("DB_NAME", "sdn_database")
        user = os.getenv("DB_USER", "sdn_user")
        password = os.getenv("DB_PASSWORD", "sdn_password")
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        
        cursor = conn.cursor()
        
        # Check data sources
        cursor.execute("SELECT code, name, source_type FROM data_sources ORDER BY code;")
        sources = cursor.fetchall()
        
        print(f"\n📊 Data Sources ({len(sources)} found):")
        for code, name, source_type in sources:
            print(f"  • {code}: {name} ({source_type})")
        
        # Check sanctions programs
        cursor.execute("SELECT code, name FROM sanctions_programs WHERE is_active = true ORDER BY code;")
        programs = cursor.fetchall()
        
        print(f"\n📊 Active Sanctions Programs ({len(programs)} found):")
        for code, name in programs:
            print(f"  • {code}: {name}")
        
        cursor.close()
        conn.close()
        
        return len(sources) > 0 and len(programs) > 0
        
    except Exception as e:
        print(f"\n❌ Data check failed: {e}")
        return False


def test_extensions():
    """Verify required PostgreSQL extensions are installed."""
    print("\n" + "=" * 60)
    print("🔍 Checking PostgreSQL Extensions")
    print("=" * 60)
    
    required_extensions = ['uuid-ossp', 'pg_trgm']
    
    try:
        import psycopg2
        
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        database = os.getenv("DB_NAME", "sdn_database")
        user = os.getenv("DB_USER", "sdn_user")
        password = os.getenv("DB_PASSWORD", "sdn_password")
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT extname FROM pg_extension;")
        installed = [row[0] for row in cursor.fetchall()]
        
        print("\n📦 Extensions:")
        all_present = True
        for ext in required_extensions:
            if ext in installed:
                print(f"  ✅ {ext}")
            else:
                print(f"  ❌ {ext} (MISSING)")
                all_present = False
        
        cursor.close()
        conn.close()
        
        return all_present
        
    except Exception as e:
        print(f"\n❌ Extension check failed: {e}")
        return False


def main():
    """Run all database tests."""
    print("\n" + "=" * 60)
    print("🚀 SDNCheck Database Connection Test")
    print("=" * 60)
    
    results = {}
    
    # Run tests
    results['basic'] = test_basic_connection()
    results['sqlalchemy'] = test_sqlalchemy_connection()
    results['schema'] = test_schema_tables()
    results['data'] = test_data_sources()
    results['extensions'] = test_extensions()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✅ All tests passed! Database is ready.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
