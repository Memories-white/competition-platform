import paramiko, io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.130.130', username='Memories_white', password='lxw060907', timeout=10)

def run(cmd):
    si, so, se = c.exec_command(cmd)
    return so.read().decode('utf-8', errors='replace')

base = r"C:\Users\Memories_white\Downloads\competition-platform-master\competition-platform-master"
gh_raw = "https://raw.githubusercontent.com/Memories-white/competition-platform/master"

# Stop Flask
run("taskkill /f /im python.exe 2>nul")
time.sleep(1)
run("docker system prune -f 2>nul")

# Delete setup_done to trigger wizard
run(f'del /q {base}\\instance\\.setup_done 2>nul')
print("Deleted .setup_done to trigger setup wizard")

# Download all updated files
files = [
    "app.py",
    "config.py",
    "services/environment_service.py",
    "docker_engine/builder.py",
    "templates/setup.html",
    "templates/base.html",
]

for f in files:
    remote_dir = "\\".join(f.split("/")[:-1])
    if remote_dir:
        run(f'mkdir {base}\\{remote_dir} 2>nul')
    url = f"{gh_raw}/{f}"
    out = f"{base}\\{f.replace('/', '\\\\')}"
    ps = f'[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri "{url}" -OutFile "{out}"'
    run(f'powershell -Command "{ps}"')
    # Verify
    size = run(f'dir "{out}" 2>nul').split("\n")[-3] if True else ""
    print(f"  OK: {f}")

print("\nAll synced!")
print("Delete old database and restart:")
print(f"  del {base}\\instance\\database.db")
print(f"  python app.py")
c.close()
