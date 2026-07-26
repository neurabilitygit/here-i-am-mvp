#!/usr/bin/env python3
"""Start a detached local process and record its final PID."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid-file', required=True, type=Path)
    parser.add_argument('--log-file', required=True, type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('a command is required after --')

    first_child = os.fork()
    if first_child:
        _, status = os.waitpid(first_child, 0)
        return os.waitstatus_to_exitcode(status)

    os.setsid()
    second_child = os.fork()
    if second_child:
        os._exit(0)

    os.chdir('/')
    os.umask(0o077)
    args.pid_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.pid_file.with_suffix(f'{args.pid_file.suffix}.tmp')
    temporary.write_text(str(os.getpid()), encoding='ascii')
    os.replace(temporary, args.pid_file)

    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    stdin = os.open(os.devnull, os.O_RDONLY)
    log = os.open(args.log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.dup2(stdin, 0)
    os.dup2(log, 1)
    os.dup2(log, 2)
    os.close(stdin)
    os.close(log)
    os.execvpe(command[0], command, os.environ.copy())
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
