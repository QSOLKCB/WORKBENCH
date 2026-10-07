"""Bounded subprocess transport: no shell, deadline, cancellation, both pipes."""
import codecs
import os
import queue
import signal
import subprocess
import threading
import time

MAX_OUTPUT = 1024 * 1024


def execute(plan, cancel=None, emit=None, timeout=120, max_output=MAX_OUTPUT):
    cancel = cancel or threading.Event()
    if cancel.is_set():
        return {"status": "cancelled", "exit_code": None, "stdout": "", "stderr": ""}
    proc = subprocess.Popen(plan.argv, cwd=plan.cwd, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=(os.name == "posix"), shell=False)
    chunks = queue.Queue(maxsize=64)
    stop = threading.Event()

    def put(item):
        while not stop.is_set():
            try:
                chunks.put(item, timeout=.1)
                return
            except queue.Full:
                pass

    def read(name, pipe):
        try:
            while data := pipe.read1(4096):
                put((name, data))
        finally:
            pipe.close()
            put((name, None))

    def write():
        try:
            if plan.stdin:
                proc.stdin.write(plan.stdin.encode())
                proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            proc.stdin.close()

    readers = [threading.Thread(target=read, args=(name, pipe), daemon=True)
               for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr))]
    for thread in readers:
        thread.start()
    writer = threading.Thread(target=write, daemon=True)
    writer.start()
    buffers = {"stdout": [], "stderr": []}
    decoders = {name: codecs.getincrementaldecoder("utf-8")("replace") for name in buffers}
    ended, size, started, reason = set(), 0, time.monotonic(), None

    def kill():
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            elif proc.poll() is None:
                proc.kill()
        except ProcessLookupError:
            pass

    try:
        while len(ended) < 2 or proc.poll() is None:
            if cancel.is_set():
                reason = "cancelled"
                break
            if time.monotonic() - started >= timeout:
                reason = "timed_out"
                break
            try:
                name, data = chunks.get(timeout=.05)
            except queue.Empty:
                continue
            if data is None:
                ended.add(name)
                text = decoders[name].decode(b"", final=True)
            else:
                remaining = max_output - size
                text = decoders[name].decode(data[:remaining])
                size += len(data)
                if size > max_output:
                    reason = "output_limit"
            if text:
                buffers[name].append(text)
                if emit:
                    emit(name, text)
            if reason:
                break
    finally:
        # Also closes descendants holding pipes after their parent exits.
        kill()
        stop.set()
        proc.wait(timeout=5)
        for thread in readers + [writer]:
            thread.join(timeout=1)
    return {"status": reason or ("succeeded" if proc.returncode == 0 else "failed"),
            "exit_code": proc.returncode,
            **{name: "".join(parts) for name, parts in buffers.items()}}
