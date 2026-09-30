import os
import sys

sys.path.insert(0, os.path.abspath("."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# 1. Admin
admin_u = User.objects.filter(username="admin").first()
if admin_u:
    admin_u.set_password("admin123")
    admin_u.save()

# 2. Wardens
for w_name in ["warden", "rajesh.warden"]:
    wu = User.objects.filter(username=w_name).first()
    if wu:
        wu.set_password("warden123")
        wu.save()

# 3. All Students (123XXX)
count = 0
for su in User.objects.filter(username__startswith="123"):
    su.set_password("Student@123")
    su.save()
    count += 1

print(f"Password sync complete: admin (admin123), wardens (warden123), {count} students (Student@123)")
