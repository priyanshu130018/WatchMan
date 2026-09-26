"""
WatchMan Automated Production Database Backup Script.

Generates compressed, timestamped PostgreSQL backups from the live production database container.
"""

import os
import sys
import subprocess
import datetime
import gzip
from pathlib import Path


def run_backup(
    container_name: str = "watchman_prod_postgres",
    db_user: str = "watchman_prod_admin",
    db_name: str = "watchman_prod",
    backup_dir: str = "backups",
) -> Path:
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = target_dir / f"watchman_prod_backup_{timestamp}.sql.gz"

    print(f"[*] Starting production backup for database '{db_name}' in container '{container_name}'...")
    print(f"[*] Destination: {backup_file}")

    # Use docker exec to stream pg_dump
    docker_cmd = [
        "docker", "exec", container_name,
        "pg_dump", "-U", db_user, "-d", db_name, "--clean", "--if-exists"
    ]

    try:
        # Check if running under WSL or native
        proc = subprocess.Popen(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout_data, stderr_data = proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr_data.decode("utf-8", errors="replace")
            print(f"[!] Backup failed with return code {proc.returncode}: {err_msg}", file=sys.stderr)
            sys.exit(1)

        # Compress and write
        with gzip.open(backup_file, "wb") as f_out:
            f_out.write(stdout_data)

        size_kb = backup_file.stat().st_size / 1024.0
        print(f"[+] Backup completed successfully! Size: {size_kb:.2f} KB ({backup_file})")

        # Integrity check: decompress and verify header
        with gzip.open(backup_file, "rb") as f_in:
            head = f_in.read(100)
            if b"PostgreSQL database dump" not in head and b"SET " not in head and len(head) > 0:
                print(f"[!] Warning: unexpected header in dump: {head[:50]}", file=sys.stderr)

        return backup_file

    except Exception as e:
        print(f"[!] Exception during backup: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_backup()
