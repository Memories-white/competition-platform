import paramiko, io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.130.130', username='Memories_white', password='lxw060907', timeout=10)

def run(cmd):
    si, so, se = c.exec_command(cmd)
    return so.read().decode('utf-8',errors='replace')

base = r"C:\Users\Memories_white\Downloads\competition-platform-master\competition-platform-master"

# 1. Stop Flask
print("1. Stopping Flask...")
run("taskkill /f /im python.exe 2>nul")
time.sleep(1)
print("   Done")

# 2. Clean Docker
print("2. Cleaning Docker...")
run("docker stop $(docker ps -q) 2>nul")
run("docker system prune -af 2>nul")
print("   Done")

# 3. Delete database
print("3. Deleting database...")
run(f'del /q "{base}\\instance\\database.db" 2>nul')
print("   Done")

# 4. Delete setup done flag
print("4. Deleting setup flag...")
run(f'del /q "{base}\\instance\\.setup_done" 2>nul')
print("   Done")

# 5. Clean flask logs
print("5. Cleaning logs...")
run(f'del /q "{base}\\flask_stdout.log" 2>nul')
run(f'del /q "{base}\\flask_stderr.log" 2>nul')
print("   Done")

# 6. Verify clean state
print("\n=== Clean State ===")
print("DB exists:", "YES" if "database.db" in run(f'dir "{base}\\instance" 2>nul') else "NO")
print("Setup flag:", "YES" if ".setup_done" in run(f'dir "{base}\\instance" 2>nul') else "NO")
print("Docker containers:", run("docker ps -a --format '{{.Names}}'").strip() or "(none)")
print("Docker images:", run("docker images -q").strip() and "present" or "(none)")

print("\n=== READY for fresh setup ===")
print(f"Run: python app.py")
c.close()
