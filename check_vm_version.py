import paramiko, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('192.168.130.130', username='Memories_white', password='lxw060907', timeout=10)

def run(cmd):
    si, so, se = c.exec_command(cmd)
    return so.read().decode('utf-8', errors='replace')

base = r"C:\Users\Memories_white\Downloads\competition-platform-master\competition-platform-master"

checks = [
    ("sync containers", "app.py", "_sync_orphan_containers"),
    ("mirror config", "config.py", "DOCKER_REGISTRY_MIRROR"),
    ("mirror retry", "docker_engine\\builder.py", "_rewrite_dockerfile_for_mirror"),
    ("build_challenge_image", "docker_engine\\builder.py", "build_challenge_image"),
    ("image build job", "app.py", "auto_image_build_job"),
    ("async create_competition", "routes\\admin.py", "镜像由后台定时任务异步构建"),
    ("Toast fix (error check)", "app.py", 'result.get("error")'),
    ("Toast fix (success===false)", "templates\\base.html", "success === false"),
    ("loading timeout", "templates\\admin\\competitions.html", "_createLoadingTimer"),
    ("loading timeout challenges", "templates\\admin\\challenges.html", "_createChalTimer"),
]

for name, path, pattern in checks:
    result = run(f'findstr /c:"{pattern}" "{base}\\{path}"')
    found = pattern in result
    print(f"{'[OK]' if found else '[MISS]'} {name}")

c.close()
