"""Sync latest code from D:\competition-platform to VM via SFTP"""
import paramiko, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.130.130', username='Memories_white', password='lxw060907', timeout=10)

# Check if VM code has _sync_orphan_containers
def run(cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace') + stderr.read().decode('utf-8', errors='replace')

vm_base = r"C:\Users\Memories_white\Downloads\competition-platform-master\competition-platform-master"

print("=== Checking VM code version ===")
result = run(f'findstr /c:"_sync_orphan_containers" "{vm_base}\\app.py"')
print("Has sync feature:", "YES" if "_sync_orphan_containers" in result else "NO")

result = run(f'findstr /c:"DOCKER_REGISTRY_MIRROR" "{vm_base}\\config.py"')
print("Has mirror config:", "YES" if "DOCKER_REGISTRY_MIRROR" in result else "NO")

result = run(f'findstr /c:"_rewrite_dockerfile_for_mirror" "{vm_base}\\docker_engine\\builder.py"')
print("Has mirror retry:", "YES" if "_rewrite_dockerfile_for_mirror" in result else "NO")

result = run(f'findstr /c:"auto_image_build_job" "{vm_base}\\app.py"')
print("Has image build job:", "YES" if "auto_image_build_job" in result else "NO")

print("\n=== Now syncing latest files via SFTP ===")
sftp = client.open_sftp()

local_base = r"D:\competition-platform"

# Files to sync (the modified ones from our fixes)
files_to_sync = [
    "app.py",
    "config.py",
    "docker_engine/builder.py",
    "docker_engine/manager.py",
    "routes/admin.py",
    "services/environment_service.py",
    "templates/base.html",
    "templates/admin/competitions.html",
    "templates/admin/challenges.html",
    "DOCKER_MIRROR_SETUP.md",
]

for f in files_to_sync:
    local_path = os.path.join(local_base, f)
    remote_path = f"{vm_base}\\{f.replace('/', '\\')}"
    try:
        sftp.put(local_path, remote_path)
        print(f"  OK: {f}")
    except Exception as e:
        print(f"  FAIL: {f} - {e}")

sftp.close()

# Also sync the models and services files that were updated
additional = [
    "models/models.py",
    "routes/contestant.py",
    "services/judge_service.py",
    "static/css/style.css",
    "templates/admin/competition_detail.html",
    "templates/admin/dashboard.html",
    "templates/admin/environments.html",
    "templates/admin/logs.html",
    "templates/admin/scores.html",
    "templates/admin/users.html",
    "templates/auth/login.html",
    "templates/auth/register.html",
    "templates/contestant/dashboard.html",
    "templates/contestant/environment.html",
    "templates/contestant/exam.html",
    "templates/contestant/scoreboard.html",
    "templates/presets.html",
]

print("\n=== Syncing additional files ===")
sftp = client.open_sftp()
for f in additional:
    local_path = os.path.join(local_base, f)
    remote_path = f"{vm_base}\\{f.replace('/', '\\')}"
    try:
        sftp.put(local_path, remote_path)
        print(f"  OK: {f}")
    except Exception as e:
        print(f"  FAIL: {f} - {e}")

sftp.close()

print("\n=== Restarting Flask ===")
# Kill existing python processes
run("taskkill /f /im python.exe 2>nul")
print("Killed old Python processes")

print("\nDone! VM code is now synced with latest.")
client.close()
