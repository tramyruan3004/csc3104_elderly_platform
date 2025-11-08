import uuid
from datetime import datetime, timezone
from passlib.hash import bcrypt_sha256
import psycopg

conn = psycopg.connect("postgresql://auth:authpwd@127.0.0.1:55321/authentication")
user_id = uuid.uuid4()
now = datetime.now(timezone.utc)
name = "Admin User"
nric = "O1234567B"
role = "ORGANISER"
passcode = "01011980"
username = "admin"
password = "password"
with conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE nric=%s", (nric,))
        if cur.fetchone():
            print("User with NRIC already exists")
        else:
            cur.execute(
                "INSERT INTO users (id, name, nric, role, is_active, created_at, updated_at) VALUES (%s, %s, %s, %s::userrole, %s, %s, %s)",
                (str(user_id), name, nric, role, True, now, now),
            )
            passcode_hash = bcrypt_sha256.hash(passcode)
            password_hash = bcrypt_sha256.hash(password)
            cur.execute(
                "INSERT INTO credentials (user_id, passcode_hash, admin_username, admin_password_hash, created_at) VALUES (%s, %s, %s, %s, %s)",
                (str(user_id), passcode_hash, username, password_hash, now),
            )
            print(f"Created organiser with id {user_id}")
