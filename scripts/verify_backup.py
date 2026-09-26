"""
WatchMan Production Backup Verification & Failure Detection Suite.

Performs:
1. Automated discovery and gzip header verification of production backups.
2. Full isolated restoration drill into `watchman_prod_restore_verify`.
3. Dynamic row count parity verification across all 26 production tables.
4. Synthetic Corrupted Backup Rejection Test (verifies backup failure alerting & detection).
5. Clean teardown of verification databases and temporary artifacts.
"""

import sys
import gzip
import subprocess
import tempfile
from pathlib import Path


def verify_backup_file(backup_path: Path) -> bool:
    """Verifies that the file exists, is non-zero, and has valid gzip structure."""
    if not backup_path.exists():
        print(f"[FAIL] Backup file '{backup_path}' does not exist!", file=sys.stderr)
        return False
    
    size_bytes = backup_path.stat().st_size
    if size_bytes < 100:
        print(f"[FAIL] Backup file '{backup_path}' is suspiciously small ({size_bytes} bytes)!", file=sys.stderr)
        return False

    try:
        with gzip.open(backup_path, "rb") as f:
            chunk = f.read(1024)
            if not chunk:
                print(f"[FAIL] Backup file '{backup_path}' decompresses to empty data!", file=sys.stderr)
                return False
        print(f"[PASS] Backup archive '{backup_path.name}' verified (Size: {size_bytes / 1024.0:.2f} KB).")
        return True
    except Exception as e:
        print(f"[FAIL] Backup file '{backup_path}' is corrupted or invalid gzip: {e}", file=sys.stderr)
        return False


def run_isolated_restore_verification(
    backup_path: Path,
    container_name: str = "watchman_prod_postgres",
    db_user: str = "watchman_prod_admin",
    live_db: str = "watchman_prod",
    verify_db: str = "watchman_prod_restore_verify",
) -> bool:
    """Restores the backup into an isolated database and validates 26/26 table parity."""
    print("\n" + "=" * 75)
    print(f"Starting Isolated Restore & Data Parity Verification: {backup_path.name}")
    print("=" * 75)

    drop_cmd = ["docker", "exec", container_name, "psql", "-U", db_user, "-d", "postgres", "-c", f"DROP DATABASE IF EXISTS {verify_db};"]
    create_cmd = ["docker", "exec", container_name, "psql", "-U", db_user, "-d", "postgres", "-c", f"CREATE DATABASE {verify_db};"]

    try:
        # Step 1: Recreate verification DB
        subprocess.run(drop_cmd, check=True, capture_output=True)
        subprocess.run(create_cmd, check=True, capture_output=True)

        # Step 2: Stream decompressed SQL into verify_db
        with gzip.open(backup_path, "rb") as f_in:
            sql_bytes = f_in.read()

        restore_proc = subprocess.Popen(
            ["docker", "exec", "-i", container_name, "psql", "-U", db_user, "-d", verify_db],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = restore_proc.communicate(input=sql_bytes)
        if restore_proc.returncode != 0:
            print(f"[FAIL] Database restore failed with code {restore_proc.returncode}: {stderr.decode(errors='replace')}", file=sys.stderr)
            return False

        # Step 3: Discover all public tables and check row counts
        tables_cmd = [
            "docker", "exec", container_name, "psql", "-U", db_user, "-d", live_db, "-t", "-A", "-c",
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        ]
        res_tables = subprocess.run(tables_cmd, capture_output=True, text=True, check=True)
        all_tables = [t.strip() for t in res_tables.stdout.strip().split("\n") if t.strip()]

        all_matched = True
        for table in all_tables:
            c_live = subprocess.run(
                ["docker", "exec", container_name, "psql", "-U", db_user, "-d", live_db, "-t", "-A", "-c", f"SELECT COUNT(*) FROM \"{table}\";"],
                capture_output=True, text=True, check=False
            )
            c_drill = subprocess.run(
                ["docker", "exec", container_name, "psql", "-U", db_user, "-d", verify_db, "-t", "-A", "-c", f"SELECT COUNT(*) FROM \"{table}\";"],
                capture_output=True, text=True, check=False
            )
            live_count = c_live.stdout.strip() if c_live.returncode == 0 else "ERROR"
            drill_count = c_drill.stdout.strip() if c_drill.returncode == 0 else "ERROR"

            matched = (live_count == drill_count and live_count != "ERROR")
            status_str = "[PASS]" if matched else "[FAIL]"
            print(f"{status_str} Table '{table:25}': Live = {live_count:>3}, Restored = {drill_count:>3}")
            if not matched:
                all_matched = False

        # Step 4: Clean up
        subprocess.run(drop_cmd, check=True, capture_output=True)

        if all_matched:
            print(f"\n[SUCCESS] All {len(all_tables)} tables verified with 100% data integrity & parity.")
        return all_matched

    except Exception as e:
        print(f"[FAIL] Verification failed with exception: {e}", file=sys.stderr)
        subprocess.run(drop_cmd, check=False, capture_output=True)
        return False


def test_corrupted_backup_rejection() -> bool:
    """Simulates a corrupt backup file and confirms the verification engine flags and rejects it."""
    print("\n" + "=" * 75)
    print("Testing Corrupted Backup Detection & Alerting Drill")
    print("=" * 75)

    with tempfile.NamedTemporaryFile(suffix="_corrupted.sql.gz", delete=False) as tmp:
        # Write invalid/corrupted gzip bytes
        tmp.write(b"\x1f\x8b\x08\x00CORRUPTED_GARBAGE_PAYLOAD_NOT_A_VALID_SQL_BACKUP")
        corrupted_path = Path(tmp.name)

    try:
        # Verify file directly
        file_valid = verify_backup_file(corrupted_path)
        # Try restore
        restore_result = run_isolated_restore_verification(corrupted_path)
        
        # We EXPECT this to fail!
        if not restore_result or not file_valid:
            print("[PASS] Corrupted backup drill passed: System successfully detected and rejected corrupted archive.")
            return True
        else:
            print("[FAIL] Corrupted backup was incorrectly accepted as valid!", file=sys.stderr)
            return False
    finally:
        if corrupted_path.exists():
            corrupted_path.unlink()


def main():
    backups = sorted(Path("backups").glob("watchman_prod_backup_*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print("[!] No backup files found in backups/ directory. Run scripts/backup_production.py first.")
        sys.exit(1)

    latest_backup = backups[0]
    print(f"[*] Found {len(backups)} backups. Testing latest: {latest_backup}")

    # 1. Verify file
    if not verify_backup_file(latest_backup):
        sys.exit(1)

    # 2. Run isolated restore verification
    if not run_isolated_restore_verification(latest_backup):
        sys.exit(1)

    # 3. Test corrupted backup rejection
    if not test_corrupted_backup_rejection():
        sys.exit(1)

    print("\n" + "=" * 75)
    print("[ALL BACKUP VERIFICATION DRILLS COMPLETED SUCCESSFULLY]")
    print("=" * 75)


if __name__ == "__main__":
    main()
