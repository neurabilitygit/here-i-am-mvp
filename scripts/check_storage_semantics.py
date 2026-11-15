#!/usr/bin/env python3
"""Synthetic checks in a NEW scratch directory; never opens the memoir library.

Compare the same volume natively and through Docker. Files are deliberately
retained for diagnosis; this is not a crash/power-loss durability test.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch-root', type=Path, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='semantics-', dir=args.scratch_root))
    trials = []
    for index in range(10):
        destination = root / f'synthetic-{index}.txt'
        temporary = root / f'.temporary-{index}'
        payload = f'Synthetic storage test {index}'.encode()
        with temporary.open('wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        fd = os.open(root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        errors = []
        matched = False
        for attempt in range(11):
            try:
                matched = destination.read_bytes() == payload
                if matched:
                    break
                errors.append('content_mismatch')
            except OSError as exc:
                errors.append(type(exc).__name__)
            if attempt < 10:
                time.sleep(.1)
        trials.append({'immediate_match': not errors, 'matched_within_one_second': matched, 'errors': errors})
    lock_path = root / 'synthetic.lock'
    child = "import fcntl,sys; f=open(sys.argv[1],'a+'); fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)"
    with lock_path.open('a+') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        result = subprocess.run([sys.executable, '-c', child, str(lock_path)], capture_output=True, timeout=5)
    database = None
    try:
        database = sqlite3.connect(root / 'synthetic.sqlite')
        database.execute('PRAGMA journal_mode=WAL')
        database.execute('CREATE TABLE synthetic (id INTEGER PRIMARY KEY)')
        for value in range(10):
            database.execute('INSERT INTO synthetic VALUES (?)', (value,))
            database.commit()
        sqlite_result = {'rows':database.execute('SELECT COUNT(*) FROM synthetic').fetchone()[0]}
    except sqlite3.Error as exc:
        sqlite_result = {'error_type':type(exc).__name__, 'error':str(exc)}
    finally:
        if database is not None:
            database.close()
    print(json.dumps({'scratch_directory':str(root), 'platform':sys.platform, 'trials':trials, 'second_process_lock_blocked':result.returncode != 0 and b'BlockingIOError' in result.stderr, 'sqlite_wal':sqlite_result}, indent=2))


if __name__ == '__main__':
    main()
