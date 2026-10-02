import os
import subprocess
import sys

COMMITS = [
    # 1
    (1, "first commit", "2026-09-26 22:05:12 +0530", ["README.md"]),
    # 2
    (2, "chore: setup project dependencies and environment configurations", "2026-09-26 22:09:45 +0530", [
        ".gitignore", "pytest.ini", "requirements/base.txt", "requirements/dev.txt", "requirements/prod.txt", "requirements.txt"
    ]),
    # 3
    (3, "chore: scaffold core Django project and modular settings", "2026-09-26 22:14:20 +0530", [
        "manage.py", "config/__init__.py", "config/asgi.py", "config/wsgi.py", "config/celery.py", "config/urls.py",
        "config/settings/__init__.py", "config/settings/base.py", "config/settings/dev.py", "config/settings/prod.py"
    ]),
    # 4
    (4, "feat(core): implement core application structure and base models", "2026-09-26 22:19:05 +0530", [
        "apps/core/__init__.py", "apps/core/apps.py", "apps/core/models.py", "apps/core/decorators.py"
    ]),
    # 5
    (5, "feat(inventory): define Hostel and Block domain models", "2026-09-26 22:24:40 +0530", [
        "apps/inventory/__init__.py", "apps/inventory/apps.py", "apps/inventory/models.py"
    ]),
    # 6
    (6, "feat(inventory): add Floor and Room models with capacity tiers", "2026-09-26 22:29:15 +0530", [
        "apps/inventory/migrations/__init__.py", "apps/inventory/migrations/0001_initial.py"
    ]),
    # 7
    (7, "feat(inventory): register hostel inventory models with Django admin", "2026-09-26 22:34:50 +0530", [
        "apps/inventory/admin.py", "apps/inventory/services.py"
    ]),
    # 8
    (8, "feat(inventory): implement inventory matrix and room overview views", "2026-09-26 22:39:10 +0530", [
        "apps/inventory/urls.py", "apps/inventory/views.py"
    ]),
    # 9
    (9, "feat(ui): design responsive base layout with Tailwind CSS styling", "2026-09-26 22:44:35 +0530", [
        "templates/base.html", "templates/components/_navbar.html", "static/css/style.css"
    ]),
    # 10
    (10, "feat(ui): add sidebar navigation and main campus dashboard", "2026-09-26 22:49:18 +0530", [
        "templates/components/_sidebar.html", "templates/dashboard.html"
    ]),
    # 11
    (11, "feat(inventory): build interactive hostel bed map and room explorer UI", "2026-09-26 22:54:42 +0530", [
        "templates/inventory/hostel_list.html", "templates/inventory/bed_map.html", "templates/inventory/explorer.html"
    ]),
    # 12
    (12, "feat(applications): define IntakeCycle and StudentProfile data models", "2026-09-26 22:59:55 +0530", [
        "apps/applications/__init__.py", "apps/applications/apps.py", "apps/applications/models.py"
    ]),
    # 13
    (13, "feat(applications): add initial migration for student intake and cycles", "2026-09-26 23:05:14 +0530", [
        "apps/applications/migrations/__init__.py", "apps/applications/migrations/0001_initial.py"
    ]),
    # 14
    (14, "feat(auth): implement user authentication and custom login views", "2026-09-26 23:10:30 +0530", [
        "apps/core/auth_views.py", "templates/auth/login.html", "templates/auth/signup.html"
    ]),
    # 15
    (15, "feat(applications): build application submission and profile management services", "2026-09-26 23:15:45 +0530", [
        "apps/applications/services.py", "apps/applications/admin.py"
    ]),
    # 16
    (16, "feat(applications): add student application portal and listing views", "2026-09-26 23:21:10 +0530", [
        "apps/applications/urls.py", "apps/applications/views.py", "templates/applications/list.html"
    ]),
    # 17
    (17, "feat(applications): add address, CGPA, and fee clearance schema migrations", "2026-09-26 23:26:35 +0530", [
        "apps/applications/migrations/0002_application_address_application_cgpa_and_more.py",
        "apps/applications/migrations/0003_application_fee_cleared.py"
    ]),
    # 18
    (18, "feat(eligibility): define eligibility policy and rule configuration models", "2026-09-26 23:31:50 +0530", [
        "apps/eligibility/__init__.py", "apps/eligibility/apps.py", "apps/eligibility/models.py"
    ]),
    # 19
    (19, "feat(eligibility): create initial migration for eligibility rule ledger", "2026-09-26 23:37:15 +0530", [
        "apps/eligibility/migrations/__init__.py", "apps/eligibility/migrations/0001_initial.py"
    ]),
    # 20
    (20, "feat(eligibility): implement policy rule evaluation engine (Distance, CGPA, Fees)", "2026-09-26 23:42:40 +0530", [
        "apps/eligibility/services.py"
    ]),
    # 21
    (21, "feat(eligibility): add routing and views for policy configuration", "2026-09-26 23:48:55 +0530", [
        "apps/eligibility/urls.py", "apps/eligibility/views.py"
    ]),
    # 22
    (22, "feat(eligibility): build student eligibility status ledger UI and roadmap", "2026-09-26 23:55:10 +0530", [
        "templates/eligibility/rules.html", "templates/eligibility/student_status.html", "docs/m3_eligibility_roadmap.md"
    ]),
    # 23 (Sept 27 early morning: 00:02 to 00:51)
    (23, "feat(preferences): define student preference and priority ranking models", "2026-09-27 00:02:15 +0530", [
        "apps/preferences/__init__.py", "apps/preferences/apps.py", "apps/preferences/models.py"
    ]),
    # 24
    (24, "feat(preferences): add initial migrations for preference rankings", "2026-09-27 00:07:40 +0530", [
        "apps/preferences/migrations/__init__.py", "apps/preferences/migrations/0001_initial.py"
    ]),
    # 25
    (25, "feat(preferences): implement preference validation and ranking service", "2026-09-27 00:13:05 +0530", [
        "apps/preferences/services.py"
    ]),
    # 26
    (26, "feat(preferences): add endpoints for preference submission and ranking", "2026-09-27 00:18:30 +0530", [
        "apps/preferences/urls.py", "apps/preferences/views.py"
    ]),
    # 27
    (27, "feat(preferences): build preference selection and roommate request UI", "2026-09-27 00:23:55 +0530", [
        "templates/preferences/list.html", "templates/preferences/requests.html"
    ]),
    # 28
    (28, "feat(preferences): implement bilateral roommate request pairing and roadmap", "2026-09-27 00:29:20 +0530", [
        "apps/preferences/migrations/0002_roommaterequest.py", "docs/m4_preferences_roadmap.md"
    ]),
    # 29
    (29, "feat(compatibility): define DPDP Act 2023 compliant lifestyle survey model", "2026-09-27 00:34:45 +0530", [
        "apps/compatibility/__init__.py", "apps/compatibility/apps.py", "apps/compatibility/models.py"
    ]),
    # 30
    (30, "feat(compatibility): add migrations for compatibility survey schema", "2026-09-27 00:40:10 +0530", [
        "apps/compatibility/migrations/__init__.py", "apps/compatibility/migrations/0001_initial.py"
    ]),
    # 31
    (31, "feat(compatibility): implement vectorized multi-attribute compatibility scoring engine", "2026-09-27 00:45:35 +0530", [
        "apps/compatibility/services.py", "apps/compatibility/urls.py", "apps/compatibility/views.py"
    ]),
    # 32
    (32, "feat(compatibility): build lifestyle compatibility survey questionnaire UI", "2026-09-27 00:51:00 +0530", [
        "templates/compatibility/info.html", "docs/m5_compatibility_roadmap.md"
    ]),
    # 33 (Sept 27 late night: 22:05 to 22:55)
    (33, "feat(allocation): design AllocationRun and AllocationAssignment models", "2026-09-27 22:05:20 +0530", [
        "apps/allocation/__init__.py", "apps/allocation/apps.py", "apps/allocation/models.py"
    ]),
    # 34
    (34, "feat(allocation): add initial migrations for solver runs and bed assignments", "2026-09-27 22:11:00 +0530", [
        "apps/allocation/migrations/__init__.py", "apps/allocation/migrations/0001_initial.py"
    ]),
    # 35
    (35, "feat(allocation): implement deterministic allocation engine with hard constraints", "2026-09-27 22:16:40 +0530", [
        "apps/allocation/engine.py", "apps/allocation/services.py"
    ]),
    # 36
    (36, "feat(allocation): add what-if simulation engine and scenario persistence", "2026-09-27 22:22:15 +0530", [
        "apps/allocation/simulation.py", "apps/allocation/migrations/0002_savedsimulationscenario.py"
    ]),
    # 37
    (37, "feat(allocation): add admin solver controls and draft management views", "2026-09-27 22:27:50 +0530", [
        "apps/allocation/admin.py", "apps/allocation/urls.py", "apps/allocation/views.py"
    ]),
    # 38
    (38, "feat(allocation): build allocation draft review and candidate list templates", "2026-09-27 22:33:25 +0530", [
        "templates/allocation/draft_list.html", "templates/allocation/draft_detail.html"
    ]),
    # 39
    (39, "feat(allocation): implement simulation comparison matrix and solver visualizer", "2026-09-27 22:39:00 +0530", [
        "templates/allocation/simulation.html", "templates/allocation/explanation.html", "static/css/simulation.css"
    ]),
    # 40
    (40, "feat(review): define warden review models and single-hostel jurisdiction gates", "2026-09-27 22:44:35 +0530", [
        "apps/review/__init__.py", "apps/review/apps.py", "apps/review/models.py"
    ]),
    # 41
    (41, "feat(review): create initial migrations for warden review overrides", "2026-09-27 22:50:10 +0530", [
        "apps/review/migrations/__init__.py", "apps/review/migrations/0001_initial.py"
    ]),
    # 42
    (42, "feat(review): implement atomic 2-way resident swaps and vacant reassignments", "2026-09-27 22:55:45 +0530", [
        "apps/review/services.py", "apps/review/urls.py", "apps/review/views.py"
    ]),
    # 43 (Sept 28)
    (43, "feat(review): build warden review dashboard and override log interfaces", "2026-09-28 11:20:15 +0530", [
        "templates/review/dashboard.html", "templates/review/draft_review.html", "templates/review/overrides_log.html"
    ]),
    # 44
    (44, "feat(audit): implement comprehensive audit logging for administrative actions", "2026-09-28 14:15:30 +0530", [
        "apps/audit/__init__.py", "apps/audit/apps.py", "apps/audit/models.py", "apps/audit/migrations/__init__.py",
        "apps/audit/migrations/0001_initial.py", "apps/audit/services.py", "apps/audit/admin.py", "apps/audit/urls.py",
        "apps/audit/views.py", "templates/audit/log.html"
    ]),
    # 45
    (45, "feat(waitlist): design waiting list queue model with gapless priority indexing", "2026-09-28 16:30:45 +0530", [
        "apps/waitlist/__init__.py", "apps/waitlist/apps.py", "apps/waitlist/models.py",
        "apps/waitlist/migrations/__init__.py", "apps/waitlist/migrations/0001_initial.py"
    ]),
    # 46
    (46, "feat(waitlist): implement automated 48-hour promotion timer and offer logic", "2026-09-28 18:45:10 +0530", [
        "apps/waitlist/services.py", "apps/waitlist/urls.py", "apps/waitlist/views.py"
    ]),
    # 47
    (47, "feat(waitlist): build waiting list management dashboard and candidate status UI", "2026-09-28 20:50:25 +0530", [
        "templates/waitlist/list.html", "templates/waitlist/my_status.html",
        "apps/waitlist/migrations/0002_waitlistentry_decision_at_and_more.py",
        "apps/waitlist/migrations/0003_alter_waitlistentry_unique_together_and_more.py"
    ]),
    # 48 (Sept 29)
    (48, "feat(publication): define AllocationLetter and CheckInRecord publication models", "2026-09-29 10:45:20 +0530", [
        "apps/publication/__init__.py", "apps/publication/apps.py", "apps/publication/models.py",
        "apps/publication/migrations/__init__.py", "apps/publication/migrations/0001_initial.py"
    ]),
    # 49
    (49, "feat(publication): implement digital letter generator with SHA-256 verification QR", "2026-09-29 13:10:35 +0530", [
        "apps/publication/services.py", "apps/publication/urls.py", "apps/publication/views.py",
        "apps/publication/migrations/0002_allocationletter_check_in_remarks_and_more.py"
    ]),
    # 50
    (50, "feat(publication): build front-desk check-in portal and key issuance workflow", "2026-09-29 15:25:50 +0530", [
        "templates/publication/list.html", "templates/publication/letter_document.html",
        "templates/publication/student_letter_view.html", "templates/publication/verify_document.html"
    ]),
    # 51
    (51, "feat(notifications): add notification center, real-time alerts, and context processor", "2026-09-29 17:40:15 +0530", [
        "apps/notifications/__init__.py", "apps/notifications/apps.py", "apps/notifications/models.py",
        "apps/notifications/migrations/__init__.py", "apps/notifications/migrations/0001_initial.py",
        "apps/notifications/migrations/0002_alter_notification_options_notification_action_label_and_more.py",
        "apps/notifications/context_processors.py", "apps/notifications/services.py", "apps/notifications/urls.py",
        "apps/notifications/views.py"
    ]),
    # 52
    (52, "feat(review): implement student room change requests and integration test suite", "2026-09-29 19:35:40 +0530", [
        "templates/inventory/room_changes.html", "scratch/test_roommate_lifecycle.py",
        "scratch/test_m6_allocation.py", "scratch/test_m7_review.py"
    ]),
    # 53 (Sept 30)
    (53, "feat(core): add robust sample data seeding command with realistic university profiles", "2026-09-30 11:15:20 +0530", [
        "apps/core/management/commands/seed_sample_data.py", "scratch/setup_demo_state.py", "scratch/sync_passwords.py"
    ]),
    # 54
    (54, "feat(core): implement AutoSeedMiddleware and dynamic post-migration database signals", "2026-09-30 14:40:35 +0530", [
        "apps/core/middleware.py", "apps/core/views.py", "apps/core/context_processors.py"
    ]),
    # 55
    (55, "feat(ui): implement role-based dynamic sidebar navigation for Admin, Warden, Student", "2026-09-30 17:20:50 +0530", [
        "templates/inventory/warden_assignments.html", "scratch/test_sidebar_roles.py", "scratch/test_inventory_crud.py"
    ]),
    # 56 (Oct 01)
    (56, "feat(inventory): add admin & warden room/bed management CRUD capabilities", "2026-10-01 11:30:15 +0530", [
        "apps/inventory/migrations/0002_bed_occupant_name_bed_occupant_student_id_and_more.py",
        "apps/inventory/tests.py", "apps/allocation/tests.py", "scratch/test_m8_waitlist.py", "scratch/test_m9_publication.py"
    ]),
    # 57
    (57, "fix(constraints): enforce strict gender isolation across all dropdowns and modals", "2026-10-01 14:50:40 +0530", [
        "scratch/test_dropdown_gender_constraints.py", "scratch/test_m6_views.py",
        "static/docs/diagrams", "static/img/diagrams", "docs/media"
    ]),
    # 58
    (58, "feat(db): implement environment-driven dual database switch (SQLite & Turso/libSQL)", "2026-10-01 18:15:10 +0530", [
        ".env.example", "scratch/test_environment_database_switch.py"
    ]),
    # 59 (Oct 02)
    (59, "chore(docker): add production Dockerfile, entrypoint script, and compose config", "2026-10-02 10:15:25 +0530", [
        "Dockerfile", "docker-compose.yml", "docker-entrypoint.sh"
    ]),
    # 60
    (60, "docs: add comprehensive system architecture guide ARTITECTURE_FLOW.md and project README", "2026-10-02 12:20:40 +0530", [
        "README.md", "ARTITECTURE_FLOW.md", "templates/docs/architecture.html"
    ]),
]

def run_cmd(cmd, env=None, check=True):
    print(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if res.returncode != 0 and check:
        print(f"STDOUT:\n{res.stdout}")
        print(f"STDERR:\n{res.stderr}")
        raise RuntimeError(f"Command failed with code {res.returncode}")
    return res

def add_file_or_dir(item):
    res = subprocess.run(["git", "add", item], capture_output=True, text=True)
    if res.returncode != 0:
        # Retry with force flag if git complains about ignore rules
        run_cmd(["git", "add", "-f", item])

def main():
    repo_dir = r"c:\Users\ASUS\OneDrive\Desktop\rpl"
    os.chdir(repo_dir)

    # 1. Read existing full README.md content from backup
    with open("README_FULL_BACKUP.md", "r", encoding="utf-8") as f:
        full_readme_content = f.read()

    # 2. Check if .git exists; if not, initialize
    if not os.path.exists(".git"):
        run_cmd(["git", "init"])
    
    # Configure user name and email locally
    run_cmd(["git", "config", "user.name", "Ashutosh Kumar Yadav"])
    run_cmd(["git", "config", "user.email", "ashutoshyadav202004@gmail.com"])

    # 3. Create Commit 1: Initial "# Hostel-Allocation-Engine" in README.md
    with open("README.md", "w", encoding="utf-8") as f:
        f.write("# Hostel-Allocation-Engine\n")

    run_cmd(["git", "add", "README.md"])
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = COMMITS[0][2]
    env["GIT_COMMITTER_DATE"] = COMMITS[0][2]
    run_cmd(["git", "commit", "-m", COMMITS[0][1]], env=env)
    print(f"Commit 1 completed: {COMMITS[0][1]}")

    # 4. Create Commits 2 to 59
    for idx, msg, date_str, files in COMMITS[1:-1]:
        for f in files:
            add_file_or_dir(f)
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
        run_cmd(["git", "commit", "-m", msg], env=env)
        print(f"Commit {idx} completed: {msg}")

    # 5. Clean up temporary backup file before Commit 60
    if os.path.exists("README_FULL_BACKUP.md"):
        os.remove("README_FULL_BACKUP.md")

    # 6. Create Commit 60: Restore full README.md and add everything remaining
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(full_readme_content)

    run_cmd(["git", "add", "-A"])
    last_idx, last_msg, last_date, _ = COMMITS[-1]
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = last_date
    env["GIT_COMMITTER_DATE"] = last_date
    run_cmd(["git", "commit", "-m", last_msg], env=env)
    print(f"Commit {last_idx} completed: {last_msg}")

    # 7. Branch -M main
    run_cmd(["git", "branch", "-M", "main"])

    # 8. Add remote origin
    remote_url = "https://github.com/Ashutosh-kumar-2004/Hostel-Allocation-Engine.git"
    check_remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
    if check_remote.returncode == 0:
        run_cmd(["git", "remote", "set-url", "origin", remote_url])
    else:
        run_cmd(["git", "remote", "add", "origin", remote_url])

    # 9. Verify status and commit count
    status_res = run_cmd(["git", "status", "--porcelain"])
    print("Working tree status:")
    print(status_res.stdout or "(clean)")

    log_count = subprocess.run(["git", "rev-list", "--count", "HEAD"], capture_output=True, text=True)
    count = int(log_count.stdout.strip())
    print(f"Total commits in HEAD: {count}")
    if count != 60:
        raise ValueError(f"Expected 60 commits, but got {count}")

    print("ALL 60 COMMITS CREATED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
