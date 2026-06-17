import paramiko, io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.130.130', username='Memories_white', password='lxw060907', timeout=10)

def run(cmd):
    si, so, se = c.exec_command(cmd)
    return so.read().decode('utf-8', errors='replace') + se.read().decode('utf-8', errors='replace')

# Stop Flask + clean Docker
print("=== Stopping Flask & cleaning ===")
run("taskkill /f /im python.exe 2>nul")
time.sleep(1)
run("docker stop $(docker ps -q) 2>nul")
run("docker system prune -f 2>nul")
print("Done")

# Download latest builder.py via PowerShell
print("=== Downloading latest builder.py ===")
base = r"C:\Users\Memories_white\Downloads\competition-platform-master\competition-platform-master"
url = "https://raw.githubusercontent.com/Memories-white/competition-platform/master/docker_engine/builder.py"
out_path = base + r"\docker_engine\builder.py"

ps_cmd = f'[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri "{url}" -OutFile "{out_path}"'
result = run(f'powershell -Command "{ps_cmd}"')
print(result)

# Verify the fix is there
print("=== Verifying stream.close() fix ===")
verify = run(f'findstr /c:"stream.close()" "{out_path}"')
if "stream.close()" in verify:
    print("FIX CONFIRMED: streaming timeout is in place")
else:
    print("WARNING: fix not found! Builder may still hang")

# Also update app.py
print("=== Downloading latest app.py ===")
app_path = base + r"\app.py"
url2 = "https://raw.githubusercontent.com/Memories-white/competition-platform/master/app.py"
ps_cmd2 = f'[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri "{url2}" -OutFile "{app_path}"'
run(f'powershell -Command "{ps_cmd2}"')
print("Done")

print()
print("=== File sizes ===")
print(run(f'dir "{out_path}" "{app_path}"'))

print()
print("All updated! Now run: python app.py")
c.close()
