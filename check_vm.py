import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('192.168.130.130', username='Memories_white', password='lxw060907', timeout=10)

def run(cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return (out + err).strip()

checks = [
    ("=== Git log ===", "cd /d C:\\Users\\Memories_white\\Downloads\\competition-platform-master\\competition-platform-master && git log --oneline -5"),
    ("=== Docker images ===", "docker images --format '{{.Repository}}:{{.Tag}}'"),
    ("=== Docker ps -a ===", "docker ps -a --format '{{.Names}} {{.Status}} {{.Ports}}'"),
    ("=== Database file ===", "dir C:\\Users\\Memories_white\\Downloads\\competition-platform-master\\competition-platform-master\\instance\\database.db"),
    ("=== Git fetch + remote log ===", "cd /d C:\\Users\\Memories_white\\Downloads\\competition-platform-master\\competition-platform-master && git fetch origin 2>&1 && git log --oneline origin/master -3"),
]

for title, cmd in checks:
    print(title)
    result = run(cmd)
    if result:
        print(result)
    else:
        print("(empty)")
    print()

client.close()
