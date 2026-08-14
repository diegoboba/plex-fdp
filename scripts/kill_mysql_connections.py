#!/usr/bin/env python3
"""Kill stale MySQL connections from the ETL service account.

Usage:
    python scripts/kill_mysql_connections.py          # List connections (dry run)
    python scripts/kill_mysql_connections.py --kill    # Kill all ETL connections
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connector import DatabaseConnector

def kill_connections(database_name: str, dry_run: bool = True):
    """List and optionally kill connections for a database"""
    db = DatabaseConnector()
    conn = db.get_mysql_connection(database_name)

    with conn.cursor() as cursor:
        cursor.execute("SHOW PROCESSLIST")
        processes = cursor.fetchall()

    # Our own connection ID so we don't kill ourselves
    with conn.cursor() as cursor:
        cursor.execute("SELECT CONNECTION_ID() as id")
        my_id = cursor.fetchone()['id']

    print(f"\n{'='*60}")
    print(f"  {database_name.upper()} - {len(processes)} total connections")
    print(f"  My connection ID: {my_id}")
    print(f"{'='*60}")

    # Show all connections
    killable = []
    for p in processes:
        pid = p.get('Id')
        user = p.get('User', '')
        host = p.get('Host', '')
        db = p.get('db', '')
        command = p.get('Command', '')
        time_val = p.get('Time', 0)
        state = p.get('State', '')
        info = (p.get('Info') or '')[:60]

        is_me = pid == my_id
        marker = " <-- ME" if is_me else ""

        print(f"  ID:{pid:>6} | User:{user:<15} | Time:{time_val:>6}s | Cmd:{command:<8} | {info}{marker}")

        # Mark for killing: not our connection, not system users
        if not is_me and user not in ('system user', 'event_scheduler', 'rdsadmin'):
            killable.append(pid)

    print(f"\n  Killable connections: {len(killable)}")

    if dry_run:
        print(f"  Run with --kill to terminate them")
        return len(killable)

    # Kill them
    killed = 0
    conn2 = DatabaseConnector().get_mysql_connection(database_name)
    for pid in killable:
        try:
            with conn2.cursor() as cursor:
                cursor.execute(f"KILL {pid}")
            killed += 1
            print(f"  Killed connection {pid}")
        except Exception as e:
            print(f"  Could not kill {pid}: {e}")

    conn2.close()
    conn.close()
    print(f"\n  Killed {killed}/{len(killable)} connections")
    return killed


if __name__ == "__main__":
    dry_run = "--kill" not in sys.argv

    if dry_run:
        print("DRY RUN - showing connections only (use --kill to terminate)")
    else:
        print("KILL MODE - will terminate stale connections")

    for db_name in ['plex', 'quantio']:
        try:
            kill_connections(db_name, dry_run=dry_run)
        except Exception as e:
            print(f"Error connecting to {db_name}: {e}")

    print("\nDone.")
