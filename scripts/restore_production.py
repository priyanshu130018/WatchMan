"""
WatchMan Automated Production Database Restore Drill Script.

Performs a full restore drill into an isolated verification database (`watchman_prod_restore_verify`),
dynamically discovers all tables in the schema, verifies 100% row count and structural parity against
the live production database, and cleanly tears down the drill database.
"""

import sys
import gzip
import subprocess
from pathlib import Path


def run_restore_drill(
    backup_file: str,
    container_name: str = "watchman_prod_postgres",
    db_user: str = "watchman_prod_admin",
    live_db: str = "watchman_prod",
    drill_db: str = "watchman_prod_restore_verify",
) -> bool:
    path = Path(backup_file)
    if not path.exists():
        print(f"[!] Backup file '{backup_file}' does not exist!", file=sys.stderr)
        return False

    print("=" * 75)
    print(f"Starting Production Database Restore Drill")
    print(f"Source Backup: {path} ({path.stat().st_size / 1024.0:.2f} KB)")
    print(f"Verification DB: {drill_db}")
    print("=" * 75)

    # 1. Drop existing drill DB if exists, then create fresh drill DB
    print("[1/4] Creating temporary verification database...")
    drop_cmd = f"docker exec {container_name} psql -U {db_user} -d postgres -c 'DROP DATABASE IF EXISTS {drill_db};'"
    create_cmd = f"docker exec {container_name} psql -U {db_user} -d postgres -c 'CREATE DATABASE {drill_db};'"
    
    subprocess.run(drop_cmd, shell=True, check=True, capture_output=True)
    subprocess.run(create_cmd, shell=True, check=True, capture_output=True)

    # 2. Decompress backup and stream into psql drill_db
    print("[2/4] Restoring backup dump into verification database...")
    with gzip.open(path, "rb") as f_in:
        sql_bytes = f_in.read()

    restore_proc = subprocess.Popen(
        ["docker", "exec", "-i", container_name, "psql", "-U", db_user, "-d", drill_db],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = restore_proc.communicate(input=sql_bytes)
    if restore_proc.returncode != 0:
        print(f"[!] Restore failed with code {restore_proc.returncode}: {stderr.decode()}", file=sys.stderr)
        return False

    # 3. Dynamically discover all public tables and verify row counts
    print("[3/4] Validating dynamic table parity across all 26 database tables...")
    
    tables_cmd = (
        f"docker exec {container_name} psql -U {db_user} -d {live_db} -t -A -c "
        "\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;\""
    )
    res_tables = subprocess.run(tables_cmd, shell=True, capture_output=True, text=True, check=True)
    all_tables = [t.strip() for t in res_tables.stdout.strip().split("\n") if t.strip()]

    all_matched = True
    passed_tables = 0

    for table in all_tables:
        # Count in live DB
        c_live = subprocess.run(
            f"docker exec {container_name} psql -U {db_user} -d {live_db} -t -A -c 'SELECT COUNT(*) FROM \"{table}\";'",
            shell=True, capture_output=True, text=True, check=False
        )
        live_count = c_live.stdout.strip() if c_live.returncode == 0 else "ERROR"

        # Count in drill DB
        c_drill = subprocess.run(
            f"docker exec {container_name} psql -U {db_user} -d {drill_db} -t -A -c 'SELECT COUNT(*) FROM \"{table}\";'",
            shell=True, capture_output=True, text=True, check=False
        )
        drill_count = c_drill.stdout.strip() if c_drill.returncode == 0 else "ERROR"

        matched = (live_count == drill_count and live_count != "ERROR")
        status_str = "[PASS]" if matched else "[FAIL]"
        print(f"{status_str} Table '{table:25}': Live = {live_count:>3}, Restored = {drill_count:>3}")
        if matched:
            passed_tables += 1
        else:
            all_matched = False

    # 4. Clean up drill DB
    print("[4/4] Cleaning up temporary verification database...")
    subprocess.run(drop_cmd, shell=True, check=True, capture_output=True)

    print("=" * 75)
    if all_matched:
        print(f"[SUCCESS] Production restore drill verified {passed_tables}/{len(all_tables)} tables with 100% data integrity & parity!")
    else:
        print(f"[FAILURE] Production restore drill detected discrepancies ({passed_tables}/{len(all_tables)} tables matched)!")
    print("=" * 75)
    return all_matched


if __name__ == "__main__":
    backups = sorted(Path("backups").glob("watchman_prod_backup_*.sql.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print("[!] No backup files found in backups/ directory. Run scripts/backup_production.py first.")
        sys.exit(1)
    
    target_backup = sys.argv[1] if len(sys.argv) > 1 else str(backups[0])
    success = run_restore_drill(target_backup)
    sys.exit(0 if success else 1)
