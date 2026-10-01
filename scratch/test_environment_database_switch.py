import os
import sys
import importlib
import pytest
import django

# Setup Django project path
sys.path.append(r"c:\Users\ASUS\OneDrive\Desktop\rpl")

def test_database_selection():
    print("\n--- TEST: Database Configuration Selection by Environment ---")

    # 1. Test Development Mode (local SQLite)
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    
    # Reload settings module to test fresh import
    import config.settings.base as base_settings
    importlib.reload(base_settings)
    import config.settings as main_settings
    importlib.reload(main_settings)

    db_config = main_settings.DATABASES["default"]
    print(f"[Development Mode] Engine: {db_config['ENGINE']}, Name: {db_config['NAME']}")
    assert db_config["ENGINE"] == "django.db.backends.sqlite3", f"Expected sqlite3 backend in development, got {db_config['ENGINE']}"
    assert "db.sqlite3" in str(db_config["NAME"]), "Expected local db.sqlite3 path"
    print("-> SUCCESS: Development correctly resolved to local SQLite db.sqlite3.")

    # 2. Test Production Mode (Turso / libSQL)
    os.environ["ENVIRONMENT"] = "production"
    os.environ["TURSO_DATABASE_URL"] = "libsql://test-db-org.turso.io"
    os.environ["TURSO_AUTH_TOKEN"] = "test-turso-jwt-token-12345"

    importlib.reload(base_settings)
    importlib.reload(main_settings)

    prod_db_config = main_settings.DATABASES["default"]
    print(f"[Production Mode] Engine: {prod_db_config['ENGINE']}, Name: {prod_db_config['NAME']}")
    assert prod_db_config["ENGINE"] == "django_libsql", f"Expected django_libsql in production, got {prod_db_config['ENGINE']}"
    assert prod_db_config["NAME"] == "libsql://test-db-org.turso.io"
    assert prod_db_config["AUTH_TOKEN"] == "test-turso-jwt-token-12345"
    print("-> SUCCESS: Production correctly resolved to Turso/libSQL backend with credentials.")

    # 3. Test Production Mode without TURSO_DATABASE_URL (Should raise ValueError)
    os.environ["ENVIRONMENT"] = "production"
    os.environ["TURSO_DATABASE_URL"] = ""
    os.environ["DATABASE_URL"] = ""
    try:
        importlib.reload(base_settings)
        assert False, "Should have raised ValueError for missing TURSO_DATABASE_URL in production!"
    except ValueError as e:
        print(f"-> SUCCESS: Correctly raised ValueError when TURSO_DATABASE_URL is missing: {e}")

    # Reset environment back to development for remaining tests
    os.environ["ENVIRONMENT"] = "development"
    os.environ.pop("TURSO_DATABASE_URL", None)
    os.environ.pop("TURSO_AUTH_TOKEN", None)
    importlib.reload(base_settings)
    importlib.reload(main_settings)

def test_settings_preservation():
    print("\n--- TEST: Preserved Settings Integrity ---")
    import config.settings as settings

    # Check INSTALLED_APPS
    required_apps = [
        "django.contrib.admin", "django.contrib.auth", "django.contrib.staticfiles",
        "rest_framework", "apps.core", "apps.inventory", "apps.applications",
        "apps.allocation", "apps.waitlist", "apps.review", "apps.preferences"
    ]
    for app in required_apps:
        assert app in settings.INSTALLED_APPS, f"Missing {app} in INSTALLED_APPS"
    print(f"-> SUCCESS: All {len(settings.INSTALLED_APPS)} INSTALLED_APPS preserved.")

    # Check MIDDLEWARE
    assert "apps.core.middleware.AutoSeedMiddleware" in settings.MIDDLEWARE, "AutoSeedMiddleware missing"
    assert "django.contrib.auth.middleware.AuthenticationMiddleware" in settings.MIDDLEWARE
    print(f"-> SUCCESS: All {len(settings.MIDDLEWARE)} MIDDLEWARE entries preserved.")

    # Check TEMPLATES
    assert len(settings.TEMPLATES) > 0
    assert "apps.core.context_processors.user_roles" in settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
    print("-> SUCCESS: TEMPLATES configuration preserved.")

    # Check STATIC and MEDIA
    assert settings.STATIC_URL == "/static/"
    assert settings.MEDIA_URL == "/media/"
    print("-> SUCCESS: STATIC and MEDIA configurations preserved.")

def test_student_id_format_in_seed():
    print("\n--- TEST: Student ID 123xxxxx Format in Seed Command ---")
    import re
    
    # Initialize Django
    django.setup()
    from apps.core.management.commands.seed_sample_data import Command
    from apps.applications.models import Application
    from django.core.management import call_command

    # Run seed
    call_command("seed_sample_data")

    # Verify seeded student IDs match 123XXXXX format (8 digits, starts with 123)
    seeded_apps = Application.objects.filter(student_id__startswith="123")
    print(f"Found {seeded_apps.count()} seeded applications with 123XXXXX IDs:")
    for app in seeded_apps:
        print(f"  - {app.student_id}: {app.student_name} ({app.get_gender_display()}) Linked user: {getattr(app.user, 'username', 'None')}")
        assert re.match(r"^123\d{5}$", app.student_id), f"Invalid student_id format: {app.student_id}"
        if app.user:
            assert app.user.username == app.student_id, f"User username {app.user.username} does not match student ID {app.student_id}"

    assert seeded_apps.count() >= 5, "Expected at least 5 demonstrator student applications seeded!"
    print("-> SUCCESS: All demonstrator student IDs strictly follow 123xxxxx format and link to users.")

if __name__ == "__main__":
    test_database_selection()
    test_settings_preservation()
    test_student_id_format_in_seed()
    print("\n=== ALL DATABASE ENVIRONMENT & SEEDING TESTS PASSED SUCCESSFULLY! ===")
