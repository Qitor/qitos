"""Trusted backend supervisor program; completion is written only by this worker.

The controller requests cancellation. It never manufactures an exit status.
Process groups are the supported cancellation boundary; escaped groups remain
outside this capability and are contained by eventual owned-container cleanup.
"""

SUPERVISOR = r'''
import ctypes, json, os, pathlib, select, signal, subprocess, sys, time
base, command = sys.argv[1:3]
root = pathlib.Path(base)
root.parent.mkdir(parents=True, exist_ok=True)
try:
    if sys.platform.startswith('linux'):
        ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)
except (AttributeError, OSError):
    pass

def publish(value):
    path = pathlib.Path(base + '.state')
    temporary = pathlib.Path(base + '.state.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(path)

def group_alive(group):
    if pathlib.Path('/proc').is_dir():
        for item in pathlib.Path('/proc').iterdir():
            if not item.name.isdigit():
                continue
            try:
                fields = (item / 'stat').read_text().rsplit(') ', 1)[1].split()
                if int(fields[2]) == group and fields[0] not in {'Z', 'X'}:
                    return True
            except (FileNotFoundError, ProcessLookupError):
                continue
        return False
    result = subprocess.run(['ps', '-axo', 'pgid=,stat='], capture_output=True,
                            text=True, check=True)
    return any(int(parts[0]) == group and not parts[1].startswith('Z')
               for line in result.stdout.splitlines() if len(parts := line.split()) == 2)

def adopted_alive():
    if not pathlib.Path('/proc').is_dir():
        return False
    for item in pathlib.Path('/proc').iterdir():
        if not item.name.isdigit():
            continue
        try:
            fields = (item / 'stat').read_text().rsplit(') ', 1)[1].split()
            if int(fields[1]) == os.getpid() and fields[0] not in {'Z', 'X'}:
                return True
        except (FileNotFoundError, ProcessLookupError):
            continue
    return False

try:
    process = subprocess.Popen(['sh', '-lc', command], start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    group = process.pid
    streams = {process.stdout.fileno(): 'stdout', process.stderr.fileno(): 'stderr'}
    tails = {'stdout': b'', 'stderr': b''}
    cancel_at = None
    grace = 1
    while True:
        rc = process.poll()
        if rc is not None:
            while True:
                try:
                    pid, _ = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break
                except ChildProcessError:
                    break
        alive = group_alive(group)
        descendants = adopted_alive()
        cancel = pathlib.Path(base + '.cancel')
        if cancel.exists() and (alive or descendants):
            if cancel_at is None:
                grace = max(0, min(30, int(cancel.read_text())))
                cancel_at = time.monotonic()
            signum = signal.SIGTERM if time.monotonic() - cancel_at < grace else signal.SIGKILL
            if alive:
                try:
                    os.killpg(group, signum)
                except ProcessLookupError:
                    pass
        ready, _, _ = select.select(list(streams), [], [], .05) if streams else ([], [], [])
        for fd in ready:
            data = os.read(fd, 65536)
            if not data:
                del streams[fd]
            else:
                name = streams[fd]
                tails[name] = (tails[name] + data)[-64000:]
        # Keep draining closed-worker pipes before publishing terminal output.
        terminal = rc is not None and not alive and not descendants and not streams
        publish({'status': 'terminal' if terminal else 'running',
                 'returncode': rc if terminal else None,
                 'stdout': tails['stdout'].decode('utf-8', errors='replace'),
                 'stderr': tails['stderr'].decode('utf-8', errors='replace'),
                 'worker_still_running': not terminal, 'outcome_unknown': False,
                 'completion_source': 'backend_supervisor',
                 'supervisor_pid': os.getpid()})
        if terminal:
            break
        if not streams:
            time.sleep(.05)
except BaseException:
    publish({'status': 'unknown', 'returncode': None,
             'worker_still_running': True, 'outcome_unknown': True,
             'stdout': '', 'stderr': '', 'completion_source': 'supervisor_failure'})
'''

POLL = r'''
import json, pathlib, sys
path = pathlib.Path(sys.argv[1] + '.state')
if path.exists():
    print(path.read_text())
else:
    print(json.dumps({'status': 'unknown', 'returncode': None,
                      'worker_still_running': True, 'outcome_unknown': True,
                      'stdout': '', 'stderr': ''}))
'''
