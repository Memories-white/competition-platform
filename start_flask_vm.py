import paramiko, io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.130.130', username='Memories_white', password='lxw060907', timeout=10)

def run(cmd):
    si, so, se = c.exec_command(cmd)
    return so.read().decode('utf-8', errors='replace') + se.read().decode('utf-8', errors='replace')

base = r"C:\Users\Memories_white\Downloads\competition-platform-master\competition-platform-master"

# Upload batch file
print("Uploading batch file...")
sftp = c.open_sftp()
sftp.put(r"D:\competition-platform\start_flask.bat", f"{base}\\start_flask.bat")
sftp.close()
print("Done")

# Kill existing Python
print("Killing old Python processes...")
run("taskkill /f /im python.exe 2>nul")
time.sleep(1)

# Method: use PowerShell Start-Process to run batch file
print("Starting Flask...")
ps_cmd = f'Start-Process -FilePath "cmd.exe" -ArgumentList "/c {base}\\\\start_flask.bat" -WindowStyle Hidden'
print(f"PS: {ps_cmd}")
run(f'powershell -Command "{ps_cmd}"')

time.sleep(5)

# Verify
print("\n=== Python processes ===")
print(run('tasklist /fi "imagename eq python.exe"'))

# Check logs
print("\n=== Flask stderr ===")
log = run(f'type {base}\\flask_stderr.log 2>nul')
print(log[-2000:] if len(log) > 2000 else log)

print("\n=== Flask stdout (last 1000 chars) ===")
out = run(f'type {base}\\flask_stdout.log 2>nul')
print(out[-1000:] if len(out) > 1000 else out)

print("\n=== Verifying version ===")
print(run(f'findstr /c:"_sync_orphan_containers" "{base}\\app.py"'))
print(run(f'findstr /c:"result.get" "{base}\\app.py"'))

c.close()
