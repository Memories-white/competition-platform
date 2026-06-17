# Docker 镜像加速器配置指南

## 问题说明

在中国大陆网络环境下，Docker 默认从 Docker Hub（`registry-1.docker.io`）拉取镜像时可能会失败，报错类似：

```
dial tcp 128.242.240.61:443: connectex: No connection could be made
because the target machine actively refused it.
```

这是因为 Docker Hub 在国内访问受限。解决方案有两种：

---

## 方案一：使用项目的镜像加速器（推荐，最简单）

项目已内置镜像加速器支持，只需设置一个配置即可。

### 步骤 1：设置镜像地址

**方式 A：环境变量（推荐）**

在启动 Flask 前设置：

```bash
# Linux / macOS
export DOCKER_REGISTRY_MIRROR="https://docker.m.daocloud.io"

# Windows PowerShell
$env:DOCKER_REGISTRY_MIRROR="https://docker.m.daocloud.io"

# Windows CMD
set DOCKER_REGISTRY_MIRROR=https://docker.m.daocloud.io
```

**方式 B：修改配置文件**

打开项目根目录的 `config.py`，修改第 44 行：

```python
DOCKER_REGISTRY_MIRROR = "https://docker.m.daocloud.io"
```

### 步骤 2：启动项目

```bash
python app.py
```

### 工作原理

1. 后台定时任务（每 30 秒）扫描未构建镜像的题目
2. 首次尝试直接从 Docker Hub 构建
3. 失败后自动将 Dockerfile 中的 `FROM ubuntu:22.04` 重写为 `FROM <镜像地址>/library/ubuntu:22.04`
4. 用镜像地址重试构建
5. 构建结果通过页面 Toast 弹窗通知

---

## 方案二：配置 Docker Desktop 全局镜像加速

如果你使用的是 Docker Desktop，可以直接在 Docker 引擎中配置全局镜像加速，这样所有镜像拉取都会走加速器。

### 步骤 1：打开 Docker Desktop

### 步骤 2：进入设置

点击右上角齿轮图标 → **Docker Engine**

### 步骤 3：编辑配置

在 JSON 中添加 `registry-mirrors` 字段：

```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://registry.cn-hangzhou.aliyuncs.com",
    "https://docker.mirrors.ustc.edu.cn"
  ]
}
```

### 步骤 4：应用并重启

点击 **Apply & Restart**，等待 Docker 重启完成。

### 步骤 5：验证

```bash
docker pull ubuntu:22.04
```

如果能正常拉取，说明配置成功。

---

## 国内常用镜像加速器地址

| 名称 | 地址 |
|---|---|
| **DaoCloud**（推荐） | `https://docker.m.daocloud.io` |
| **阿里云容器镜像服务** | `https://registry.cn-hangzhou.aliyuncs.com` |
| **中科大镜像站** | `https://docker.mirrors.ustc.edu.cn` |
| **网易镜像中心** | `https://hub-mirror.c.163.com` |
| **南京大学镜像站** | `https://docker.nju.edu.cn` |

> **注意**：镜像加速器地址可能随时间变动，如遇到 404 或超时，请更换其他地址尝试。

---

## 验证配置是否生效

启动项目后，查看终端日志。当构建失败时，会看到类似输出：

```
INFO:docker_engine.builder:Retrying build for challenge 1 with mirror: https://docker.m.daocloud.io
```

如果看到这条日志，说明镜像加速器已启用。

构建成功/失败的通知也会通过页面右上角的 Toast 弹窗实时显示。
