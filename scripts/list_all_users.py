from app.db.session import SessionLocal
from app.models.user import User
from app.api.auth.router import verify_password

def list_all_users():
    db = SessionLocal()
    users = db.query(User).all()
    print(f"Total users in DB: {len(users)}")
    for u in users:
        v_123 = verify_password('123456789', u.password_hash) if u.password_hash else False
        v_dev = verify_password('watchman_secure_dev_pass_123', u.password_hash) if u.password_hash else False
        print(f"ID: {u.id} | Email: {u.email:<25} | Active: {u.is_active} | Has Hash: {bool(u.password_hash)} | Valid 123456789: {v_123} | Valid dev_pass: {v_dev}")
    db.close()

if __name__ == '__main__':
    list_all_users()
