import random
import logging
import docker
from config import Config

logger = logging.getLogger(__name__)

_client = None
_network_created = False


def get_client():
    global _client
    if _client is None:
        try:
            _client = docker.from_env(timeout=5)
            _client.ping()
        except Exception as e:
            _client = None
            logger.error(f"Docker 连接失败：{e} | Failed to connect to Docker: {e}")
            raise ConnectionError(f"Docker 服务未启动或无法连接: {e}")
    return _client


def _ensure_network():
    global _network_created
    if _network_created:
        return
    try:
        client = get_client()
        try:
            client.networks.get(Config.CONTAINER_NETWORK)
        except docker.errors.NotFound:
            client.networks.create(Config.CONTAINER_NETWORK, driver="bridge")
        _network_created = True
    except Exception as e:
        logger.warning(f"网络创建失败：{e} | Failed to ensure network: {e}")


def get_free_port(start=30000, end=40000, exclude_ports: set = None) -> int:
    try:
        client = get_client()
        used_ports = exclude_ports.copy() if exclude_ports else set()
        for container in client.containers.list(all=True):
            ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
            if ports:
                for mappings in ports.values():
                    if mappings:
                        for m in mappings:
                            if "HostPort" in m:
                                used_ports.add(int(m["HostPort"]))
        for port in range(start, end):
            if port not in used_ports:
                return port
    except Exception:
        pass
    return random.randint(start, end)


def create_container(image_tag: str, container_name: str, cpu_limit: float = 0.5,
                     mem_limit: str = "512m", expose_ports: list = None) -> dict:
    _ensure_network()
    if expose_ports is None:
        expose_ports = [80]
    try:
        client = get_client()
        # 创建前先清理同名残留容器
        try:
            old = client.containers.get(container_name)
            old.remove(force=True)
            logger.info(f"已清理残留容器：{container_name} | Removed leftover container: {container_name}")
        except docker.errors.NotFound:
            pass

        # 为每个容器端口分配宿主机端口（追踪已分配端口避免重复）
        port_bindings = {}
        host_ports = {}
        allocated = set()
        for port in expose_ports:
            hp = get_free_port(exclude_ports=allocated)
            allocated.add(hp)
            port_bindings[f"{port}/tcp"] = hp
            host_ports[port] = hp

        container = client.containers.run(
            image=image_tag,
            name=container_name,
            detach=True,
            ports=port_bindings,
            network=Config.CONTAINER_NETWORK,
            nano_cpus=int(cpu_limit * 1e9),
            mem_limit=mem_limit,
            memswap_limit=mem_limit,
            restart_policy={"Name": "no"},
            stdin_open=True,
            tty=True,
        )
        return {
            "success": True,
            "container_id": container.id,
            "container_name": container_name,
            "host_port": host_ports.get(22, host_ports.get(expose_ports[0], 0)),
            "web_port": host_ports.get(80) or host_ports.get(443) or host_ports.get(5000) or host_ports.get(3000) or 0,
            "host_ports": host_ports,
            "status": container.status,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def start_container(container_id: str) -> bool:
    try:
        client = get_client()
        c = client.containers.get(container_id)
        c.start()
        return True
    except Exception:
        return False


def stop_container(container_id: str) -> bool:
    try:
        client = get_client()
        c = client.containers.get(container_id)
        c.stop(timeout=10)
        return True
    except Exception:
        return False


def remove_container(container_id: str) -> bool:
    try:
        client = get_client()
        c = client.containers.get(container_id)
        c.remove(force=True)
        return True
    except Exception:
        return False


def get_container_status(container_id: str) -> dict | None:
    try:
        client = get_client()
        c = client.containers.get(container_id)
        return {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "image": c.image.tags[0] if c.image.tags else "",
            "created": c.attrs.get("Created", ""),
        }
    except docker.errors.NotFound:
        return None
    except Exception:
        return None


def get_container_logs(container_id: str, tail: int = 100) -> str:
    try:
        client = get_client()
        c = client.containers.get(container_id)
        return c.logs(tail=tail).decode("utf-8", errors="replace")
    except Exception:
        return ""


def exec_in_container(container_id: str, command: str) -> tuple:
    try:
        client = get_client()
        c = client.containers.get(container_id)
        if c.status != "running":
            return -1, "container not running"
        result = c.exec_run(command, tty=False)
        output = result.output.decode("utf-8", errors="replace").strip()
        return result.exit_code, output
    except docker.errors.NotFound:
        return -1, "container not found"
    except Exception as e:
        return -1, str(e)


def check_port_in_container(container_id: str, port: int) -> bool:
    exit_code, _ = exec_in_container(
        container_id,
        f"bash -c 'ss -tlnp 2>/dev/null | grep -q \":{port} \" || netstat -tlnp 2>/dev/null | grep -q \":{port} \"'"
    )
    return exit_code == 0


def check_file_in_container(container_id: str, path: str) -> bool:
    exit_code, _ = exec_in_container(container_id, f"test -f {path}")
    return exit_code == 0


def list_all_containers() -> list:
    try:
        client = get_client()
        containers = []
        for c in client.containers.list(all=True):
            if c.name.startswith("comp-"):
                containers.append({
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "",
                })
        return containers
    except Exception:
        return []
