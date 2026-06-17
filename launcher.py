"""Flask launcher - detaches from parent process so it survives SSH disconnect"""
import subprocess, os, sys

base = r"C:\Users\Memories_white\Downloads\competition-platform-master\competition-platform-master"
python = r"C:\Program Files\Python313\python.exe"

os.chdir(base)

# DETACHED_PROCESS (0x00000008) + CREATE_NEW_PROCESS_GROUP (0x00000200)
DETACHED = 0x00000008
CREATE_NEW_GROUP = 0x00000200

with open("flask_stdout.log", "w") as out, open("flask_stderr.log", "w") as err:
    proc = subprocess.Popen(
        [python, "app.py"],
        stdout=out,
        stderr=err,
        creationflags=DETACHED | CREATE_NEW_GROUP,
        close_fds=True,
    )
    print(f"Flask started with PID: {proc.pid}")
