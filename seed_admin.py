"""
seed_admin.py — Create a default admin account for BhojanSetu.

Run once before first use:
    python seed_admin.py

Creates:
    email: admin@bhojansetu.local
    password: Admin@1234
    role: admin
"""

import sys
sys.path.insert(0, '.')

from auth.utils import create_user, get_user_by_email

ADMIN_EMAIL    = "admin@bhojansetu.local"
ADMIN_PASSWORD = "Admin@1234"
ADMIN_NAME     = "System Administrator"
ADMIN_INST     = "BhojanSetu Admin"

existing = get_user_by_email(ADMIN_EMAIL)
if existing:
    print(f"Admin account already exists: {ADMIN_EMAIL}")
    sys.exit(0)

try:
    user = create_user(
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
        full_name=ADMIN_NAME,
        role="admin",
        institution=ADMIN_INST,
    )
    # Mark as verified directly
    from auth.utils import mark_verified
    mark_verified(ADMIN_EMAIL)
    print("Admin account created and verified.")
    print(f"  Email   : {ADMIN_EMAIL}")
    print(f"  Password: {ADMIN_PASSWORD}")
    print("  Role    : admin")
    print("\nChange this password after first login.")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
