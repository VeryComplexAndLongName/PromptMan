import sys

print("Testing imports...")
try:
    from models import Base, User
    print(f"✓ models imported, Base={Base}, User={User}")
except Exception as e:
    print(f"✗ models error: {e}")
    sys.exit(1)

try:
    from schemas import AuthResponse
    print(f"✓ schemas imported, AuthResponse={AuthResponse}")
except Exception as e:
    print(f"✗ schemas error: {e}")
    sys.exit(1)

try:
    import auth as auth_service
    print(f"✓ auth imported, get_current_user={auth_service.get_current_user}")
except Exception as e:
    print(f"✗ auth error: {e}")
    sys.exit(1)

print("\nAll imports successful!")
