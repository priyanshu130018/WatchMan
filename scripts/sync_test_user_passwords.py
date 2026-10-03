from app.db.session import SessionLocal
from app.models.user import User
from app.models.recommendation import Recommendation
from app.models.collaborative import ALSUserFactors, ALSItemFactors
from app.models.interaction import SavedContent, WatchHistory
from app.models.review import Rating
from app.api.auth.router import hash_password, verify_password

def sync_passwords():
    db = SessionLocal()
    target_emails = [
        'aryan@gmail.com',
        'bharat@gmail.com',
        'aman@gmail.com',
        'saket@gmail.com',
        'priyanshu@gmail.com',
        'neha@gmail.com',
        'priya@gmail.com',
        'sakshi@gmail.com',
        'sid@gmail.com',
        'aditya@gmail.com'
    ]

    print("=== SYNCHRONIZING TEST USER PASSWORDS TO DEVELOPMENT PASSWORD (123456789) ===")
    
    # Record counts before
    rec_count_before = db.query(Recommendation).count()
    als_user_count_before = db.query(ALSUserFactors).count()
    als_item_count_before = db.query(ALSItemFactors).count()
    ratings_before = db.query(Rating).count()
    history_before = db.query(WatchHistory).count()
    saved_before = db.query(SavedContent).count()

    updated = 0
    for email in target_emails:
        u = db.query(User).filter(User.email == email).first()
        if not u:
            print(f"[-] User {email} not found in database!")
            continue
        
        # Check if already valid for 123456789
        if verify_password('123456789', u.password_hash):
            print(f"[=] User {email} already has valid password hash for 123456789")
        else:
            u.password_hash = hash_password('123456789')
            updated += 1
            print(f"[+] Updated password_hash for {email}")

    db.commit()
    print(f"\nCommitted updates for {updated} user accounts.")

    # Verification
    print("\n--- Verification of All 10 Test Accounts ---")
    all_valid = True
    for email in target_emails:
        u = db.query(User).filter(User.email == email).first()
        is_valid = verify_password('123456789', u.password_hash) if u and u.password_hash else False
        if not is_valid:
            all_valid = False
        print(f"User: {email:<25} | ID: {u.id} | Valid for 123456789: {is_valid}")

    # Verify recommendation and interaction counts remain completely unchanged
    rec_count_after = db.query(Recommendation).count()
    als_user_count_after = db.query(ALSUserFactors).count()
    als_item_count_after = db.query(ALSItemFactors).count()
    ratings_after = db.query(Rating).count()
    history_after = db.query(WatchHistory).count()
    saved_after = db.query(SavedContent).count()

    print("\n--- Data Integrity Verification ---")
    print(f"Recommendations count: {rec_count_before} -> {rec_count_after} (Unchanged: {rec_count_before == rec_count_after})")
    print(f"ALS User Factors count: {als_user_count_before} -> {als_user_count_after} (Unchanged: {als_user_count_before == als_user_count_after})")
    print(f"ALS Item Factors count: {als_item_count_before} -> {als_item_count_after} (Unchanged: {als_item_count_before == als_item_count_after})")
    print(f"Ratings count: {ratings_before} -> {ratings_after} (Unchanged: {ratings_before == ratings_after})")
    print(f"Watch History count: {history_before} -> {history_after} (Unchanged: {history_before == history_after})")
    print(f"Saved Content count: {saved_before} -> {saved_after} (Unchanged: {saved_before == saved_after})")

    db.close()
    return all_valid

if __name__ == '__main__':
    success = sync_passwords()
    print(f"\nAll 10 users valid for 123456789: {success}")
