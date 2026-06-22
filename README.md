# 基于Docker的云计算竞赛环境自动构建系统

## 项目简介

本项目是一个 **Web 管理平台**，面向 **云计算技能竞赛** 场景，实现竞赛环境的**自动构建、一键部署、选手隔离与自动判题评分**。

选手在独立分配的 Docker 容器中完成 Linux 系统管理、服务搭建、运维配置等任务，系统自动检测任务完成情况并实时排名。

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | Python Flask + Flask-SocketIO |
| 前端 | Bootstrap 5 + 原生 JavaScript |
| 数据库 | SQLite (Flask-SQLAlchemy ORM) |
| 容器引擎 | Docker SDK for Python (docker-py) |
| 实时通信 | WebSocket (Flask-SocketIO) |
| 定时任务 | APScheduler |

## 功能特性

### 管理端 (Admin)
- **竞赛管理** — 创建/编辑/删除竞赛，设置时间窗口、CPU/内存资源限制
- **题目管理** — 编写 Dockerfile 或选用内置模板，系统自动构建 Docker 镜像
- **一键部署** — 为所有选手 × 所有题目批量创建独立容器，WebSocket 实时推送部署进度
- **环境监控** — 查看每个选手每个容器的运行状态，支持单独启动/停止/删除
- **成绩查看** — 按题目维度的得分矩阵和实时排名
- **日志查看** — 内置系统日志页面，支持级别筛选和自动刷新

### 选手端 (Contestant)
- **环境访问** — 查看分配给自己的容器列表，获取连接信息
- **手动判题** — 完成任务后点击提交，系统立即检测并返回结果
- **排行榜** — 实时查看所有选手的得分和排名

### 判题引擎 (3 种检测方式)
| 方式 | 说明 | 配置示例 |
|------|------|----------|
| 端口检测 | 检查容器内指定端口是否已监听 | `{"port": 80}` |
| 命令执行 | 在容器内执行命令并匹配输出 | `{"cmd": "curl -s localhost", "expected": "nginx"}` |
| 文件检测 | 检查指定文件是否存在 | `{"path": "/etc/nginx/nginx.conf"}` |

### 内置题目模板
| 模板 | 说明 |
|------|------|
| `nginx_setup` | Nginx 服务安装与启动 |
| `mysql_config` | MySQL 数据库安装与配置 |
| `docker_compose` | 使用 Docker Compose 部署多服务应用 |
| `system_admin` | Linux 系统管理（用户/SSH/防火墙） |

## 快速开始

### 环境要求

- **Python 3.10+**
- **Docker Desktop** (Windows/Mac) 或 **Docker Engine** (Linux)
- Windows 11 / macOS / Linux

### Linux 安装指南（Ubuntu/Debian）

#### 1. 安装 Python 3.10+

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
python3 --version   # 确认版本 >= 3.10
```

#### 2. 安装 Docker Engine

```bash
# 卸载旧版本（如有）
sudo apt remove -y docker docker-engine docker.io containerd runc

# 安装依赖
sudo apt install -y ca-certificates curl gnupg lsb-release

# 添加 Docker 官方 GPG 密钥
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 添加 Docker 仓库
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装 Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 将当前用户加入 docker 组（免 sudo）
sudo usermod -aG docker $USER
newgrp docker
docker ps   # 验证安装
```

#### 3. 配置 Docker 镜像加速器（国内环境）

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<-'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://registry.cn-hangzhou.aliyuncs.com"
  ]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

#### 4. 安装项目依赖

```bash
git clone https://github.com/Memories-white/competition-platform.git
cd competition-platform
pip install -r requirements.txt
```

#### 5. 启动

```bash
python app.py
```

浏览器访问 **http://服务器IP:5000**，首次启动将自动进入系统初始化引导页。

### Windows 安装指南

### 安装与运行

```bash
# 1. 克隆项目
git clone https://github.com/YOUR_USERNAME/competition-platform.git
cd competition-platform

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 确保 Docker 正在运行
docker ps

# 4. 启动应用
python app.py
```

浏览器访问 **http://localhost:5000**

### 测试账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | `admin` | `admin123` |
| 选手 | `player1` | `player123` |

> 选手账号可通过注册页面自行注册，也可以修改 `init_db.py` 添加更多测试账号后运行 `python init_db.py`

## 使用流程

### 管理员操作流程

```
1. 登录 → 管理面板
2. 创建竞赛 → 设置名称、时间、资源限制
3. 进入题目管理 → 添加题目
   - 方式A: 选择内置模板 → 自动填充 Dockerfile → 系统自动构建镜像
   - 方式B: 手动编写 Dockerfile → 系统自动构建镜像
4. 进入环境管理 → 点击「一键部署」→ 观察 WebSocket 实时部署日志
5. 等待选手完成比赛 → 查看成绩与排名
```

### 选手操作流程

```
1. 注册账号 → 登录 → 选手控制台
2. 查看已分配的竞赛环境
3. 点击「进入环境」→ 查看容器连接信息
4. 通过 docker exec 或 SSH 连接容器
5. 按照题目要求完成任务（安装服务、配置系统等）
6. 点击「提交判题」→ 查看结果
7. 在排行榜查看实时排名
```

## 项目结构

```
competition-platform/
├── app.py                        # Flask 入口、日志收集、定时调度
├── config.py                     # 全局配置
├── requirements.txt              # Python 依赖
├── init_db.py                    # 数据库初始化脚本
├── docker_engine/                # Docker 引擎层
│   ├── builder.py                # 镜像构建（Dockerfile / 模板）
│   └── manager.py                # 容器生命周期管理
├── models/
│   └── models.py                 # 6 张数据表 (ORM)
├── routes/
│   ├── auth.py                   # 登录 / 注册 / 登出
│   ├── admin.py                  # 管理端路由
│   └── contestant.py             # 选手端路由
├── services/
│   ├── environment_service.py    # 一键部署服务
│   └── judge_service.py          # 判题引擎
├── templates/
│   ├── base.html                 # 基础布局
│   ├── auth/                     # 登录注册页
│   ├── admin/                    # 5 个管理端页面
│   └── contestant/               # 3 个选手端页面
├── static/css/style.css          # 样式
└── docker_templates/             # 4 个内置题目模板
    ├── nginx_setup/Dockerfile
    ├── mysql_config/Dockerfile
    ├── docker_compose/Dockerfile
    └── system_admin/Dockerfile
```

## 数据库表结构

| 表 | 说明 |
|----|------|
| `users` | 用户账号（管理员/选手） |
| `competitions` | 竞赛配置（时间、资源限制） |
| `challenges` | 题目定义（Dockerfile、判题方式、分数） |
| `environments` | 选手环境实例（容器 ID、端口映射） |
| `scores` | 得分记录 |

## 配置文件说明

编辑 `config.py` 可调整系统参数：

```python
DEFAULT_CPU_LIMIT = 0.5        # 每个容器默认 CPU 限制（核）
DEFAULT_MEM_LIMIT = "512m"     # 每个容器默认内存限制
CONTAINER_NETWORK = "comp_network"  # Docker 网络名称
JUDGE_INTERVAL_SECONDS = 30    # 自动判题间隔（秒）
```

## 许可证

本项目仅用于学习与毕业设计用途。
