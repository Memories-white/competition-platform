# 基于Docker的云计算竞赛环境自动构建系统 — 系统架构文档

## 1. 系统概述

本系统实现了一个基于 Docker 的云计算竞赛平台，核心功能是**自动构建、部署和管理**竞赛所需的隔离容器环境。系统采用 B/S 架构，管理员通过 Web 界面创建竞赛、配置题目、触发自动构建，选手在浏览器中查看环境信息并完成题目。

### 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | Flask (Python) |
| 数据库 | SQLite (开发) / 可扩展至 PostgreSQL |
| ORM | SQLAlchemy |
| 容器引擎 | Docker (docker-py SDK) |
| 实时通信 | Flask-SocketIO (WebSocket) |
| 任务调度 | APScheduler |
| 前端 | Jinja2 + Bootstrap 5 + Vanilla JS |

---

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                    浏览器 (Browser)                       │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│   │ 管理员界面 │  │ 选手界面  │  │ WebSocket 部署日志    │  │
│   └─────┬────┘  └────┬─────┘  └──────────┬───────────┘  │
└─────────┼────────────┼───────────────────┼──────────────┘
          │ HTTP       │ HTTP              │ WS
┌─────────┼────────────┼───────────────────┼──────────────┐
│         ▼            ▼                   ▼               │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Flask 应用层 (app.py)                 │   │
│  │  ┌─────────┐ ┌─────────┐ ┌────────────────────┐  │   │
│  │  │ Auth BP │ │Admin BP │ │ Contestant BP      │  │   │
│  │  └────┬────┘ └────┬────┘ └────────┬───────────┘  │   │
│  └───────┼───────────┼──────────────┼───────────────┘   │
│          │           │              │                    │
│  ┌───────┼───────────┼──────────────┼───────────────┐   │
│  │       ▼           ▼              ▼                │   │
│  │              Service 层                           │   │
│  │  ┌─────────────┐  ┌──────────────┐              │   │
│  │  │ Environment │  │ Judge Service│              │   │
│  │  │ Service     │  │ (判题引擎)    │              │   │
│  │  └──────┬──────┘  └──────┬───────┘              │   │
│  └─────────┼────────────────┼──────────────────────┘   │
│            │                │                           │
│  ┌─────────┼────────────────┼──────────────────────┐   │
│  │         ▼                ▼                        │   │
│  │           Docker Engine 层                        │   │
│  │  ┌──────────────┐  ┌──────────────┐             │   │
│  │  │ builder.py   │  │ manager.py   │             │   │
│  │  │ (镜像构建)    │  │ (容器管理)    │             │   │
│  │  └──────┬───────┘  └──────┬───────┘             │   │
│  └─────────┼─────────────────┼─────────────────────┘   │
│            │                 │                          │
│  ┌─────────┼─────────────────┼─────────────────────┐   │
│  │         ▼                 ▼                        │   │
│  │     Models 层 (SQLAlchemy ORM) + SQLite           │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │     Docker Daemon        │
              │  ┌──────┐ ┌──────┐      │
              │  │镜像仓库│ │容器运行时│    │
              │  └──────┘ └──────┘      │
              │  ┌──────────────────┐   │
              │  │  comp_network    │   │
              │  │  (bridge 网络)    │   │
              │  └──────────────────┘   │
              └─────────────────────────┘
```

---

## 3. 核心模块设计

### 3.1 镜像构建引擎 (builder.py)

```
输入: Dockerfile 文本 / 模板名称
  │
  ▼
┌─────────────────────┐
│  Dockerfile 解析     │ ← 自动提取 EXPOSE 端口
│  (get_expose_port)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Docker SDK Build    │ ← 构建容器镜像
│  (docker.images.build)│
└────────┬────────────┘
         │
    ┌────┴────┐
    ▼         ▼
  成功       失败
    │         │
    ▼         ▼
  返回 tag   重试 (最多2次, 间隔3s)
             │
         ┌───┴───┐
         ▼       ▼
       成功     失败 → 返回错误
```

**关键特性：**
- 支持从 Dockerfile 文本直接构建
- 支持从预置模板目录构建
- **构建失败自动重试**（最多 2 次，间隔 3 秒）
- 带镜像加速下载提示的错误格式化
- 连接超时控制（5 秒）

### 3.2 容器管理引擎 (manager.py)

```
┌────────────────────────────────────────────┐
│            容器生命周期管理                    │
│                                            │
│  create_container()                        │
│    ├─ 申请空闲端口 (30000-40000)             │
│    ├─ 清理同名旧容器                         │
│    ├─ 设置资源限制 (CPU/Memory)             │
│    ├─ 挂载网络 (comp_network)               │
│    └─ 创建容器                              │
│                                            │
│  start_container() / stop_container()       │
│  remove_container()                         │
│  get_container_status() / get_container_logs() │
│  exec_in_container() — 用于判题             │
└────────────────────────────────────────────┘
```

**端口分配算法：**
1. 扫描所有现有容器，收集已占用 HostPort
2. 在 [30000, 40000) 区间内返回第一个未占用的端口
3. 若扫描失败，随机返回区间内端口

**资源隔离策略：**
- CPU: `--nano-cpus` 限制（如 0.5 核 = 500000000 nano CPUs）
- 内存: `--mem_limit` + `--memswap_limit` 双重限制（防止 swap 逃逸）
- 网络: 独立 bridge 网络 `comp_network`，容器间网络隔离

### 3.3 环境部署服务 (environment_service.py)

```
deploy_competition_environments(comp_id)
  │
  ├─ 获取竞赛信息 + 资源限制参数
  ├─ 获取所有选手 + Docker 题目 (跳过试卷)
  │
  ├─ for 选手 × 题目:  (双重循环)
  │    ├─ 检查是否已有运行中的容器 → 跳过
  │    ├─ 构建容器名: comp-{comp_id}-u{user_id}-c{chal_id}
  │    ├─ 提取 EXPOSE 端口
  │    ├─ 检查镜像是否已构建 → 未构建则标记失败
  │    ├─ create_container() → 创建容器
  │    └─ 写入 Environment 记录
  │
  ├─ 记录部署指标 (总耗时、成功/失败数、平均耗时)
  └─ 通过 SocketIO 实时推送进度
```

### 3.4 判题引擎 (judge_service.py)

```
判题方式:
  ├─ port 检测: ss/netstat 检查容器内端口监听
  ├─ command 检测: docker exec 执行命令，比对输出
  ├─ file 检测: test -f 检查文件是否存在
  └─ exam 判题: 逐题比对答案，60% 正确率通过

自动调度:
  ├─ 每 30s: 自动判题 active 竞赛的所有环境
  └─ 每 120s: 自动判题+停止+清理 finished 竞赛
```

### 3.5 自动构建调度器

```
┌──────────────────────────────────────────────────────┐
│                 APScheduler 定时任务                    │
│                                                      │
│  auto_build_job (每 15s)                              │
│    └─ 查找 active 且 auto_deployed=false 的竞赛       │
│       └─ deploy_competition_environments()            │
│          └─ 标记 auto_deployed=true                   │
│                                                      │
│  auto_judge_job (每 30s)                              │
│    └─ 遍历 active 竞赛的所有 Docker 环境              │
│       └─ judge_environment() 逐个判题                │
│                                                      │
│  auto_cleanup_job (每 120s)                           │
│    └─ 遍历 finished 竞赛                              │
│       ├─ 最后一批判题                                  │
│       ├─ 停止所有容器                                  │
│       └─ 删除所有容器 + 环境记录                       │
└──────────────────────────────────────────────────────┘
```

---

## 4. 数据模型 (ER 图)

```
┌─────────────┐       ┌───────────────┐       ┌─────────────┐
│    User     │       │  Competition  │       │  Challenge  │
├─────────────┤       ├───────────────┤       ├─────────────┤
│ id          │       │ id            │       │ id          │
│ username    │       │ name          │       │ comp_id FK  │
│ password    │       │ description   │       │ title       │
│ role        │       │ start_time    │       │ type        │─ docker|exam
│ team_name   │       │ end_time      │       │ dockerfile  │
│ created_at  │       │ status        │─ draft│ judge_type  │
└──────┬──────┘       │ cpu/mem_limit │  active│ image_tag   │
       │              │ auto_deployed │  fin.  │ points      │
       │              │ deployed_at   │       └──────┬──────┘
       │              └───────┬───────┘              │
       │                      │                      │
       │    ┌─────────────────┼──────────────────────┤
       │    │                 │                      │
       ▼    ▼                 ▼                      ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Environment  │    │    Score     │    │ ExamQuestion │
├──────────────┤    ├──────────────┤    ├──────────────┤
│ id           │    │ id           │    │ id           │
│ comp_id FK   │    │ comp_id FK   │    │ chal_id FK   │
│ user_id FK   │    │ user_id FK   │    │ question_type│
│ chal_id FK   │    │ chal_id FK   │    │ question_text│
│ container_id │    │ score        │    │ options(JSON)│
│ name         │    │ passed       │    │ answer       │
│ host_port    │    │ judged_at    │    │ points       │
│ status       │    │ answers(JSON)│    │ order        │
│ created_at   │    └──────────────┘    └──────────────┘
└──────────────┘
```

---

## 5. 自动化构建流水线 (核心论文素材)

### 5.1 完整自动化流程

```
[管理员创建竞赛] → [添加 Docker 题目] → [编写 Dockerfile / 选模板]
                                              │
                                              ▼
                                     [构建镜像] (带重试)
                                              │
                    ┌─────────────────────────┤
                    │                         │
              [管理员点"开始"]           [到达 start_time]
                    │                         │
                    ▼                         ▼
          ┌─────────────────────────────────────────┐
          │        自动构建调度器触发                  │
          │  deploy_competition_environments()       │
          │                                         │
          │  for 选手:                               │
          │    for 题目:                             │
          │      ① 分配端口 (30000-40000 扫描)        │
          │      ② 设置资源限制 (CPU / Memory)        │
          │      ③ 创建容器 (bridge 网络隔离)          │
          │      ④ 写入 Environment 记录              │
          │      ⑤ SocketIO 推送进度                  │
          │                                         │
          │  标记 auto_deployed = true               │
          │  记录部署指标 (耗时、成功率)                │
          └─────────────────────────────────────────┘
                    │
                    ▼
          [选手操作容器完成题目]
                    │
                    ▼
          ┌─────────────────┐
          │  自动判题 (30s)   │
          │  - 端口检测       │
          │  - 命令执行       │
          │  - 文件检测       │
          └─────────────────┘
                    │
                    ▼
          [竞赛结束 → 自动清理]
          ┌─────────────────┐
          │  自动清理 (120s)  │
          │  ① 最后一轮判题   │
          │  ② 停止所有容器   │
          │  ③ 删除所有容器   │
          └─────────────────┘
```

### 5.2 自动化程度对照

| 环节 | 传统方式 | 本系统 |
|------|---------|--------|
| 环境搭建 | 手动为每个选手配置 VM | **自动为 N 个选手 × M 个题目创建 M×N 个容器** |
| 端口分配 | 手动指定/冲突排查 | **自动扫描空闲端口 (30000-40000)** |
| 资源限制 | 依赖人工配置 | **CPU/Memory 自动限制，防止资源争抢** |
| 判题评分 | 人工检查 | **每 30s 自动判题，结果写入数据库** |
| 环境回收 | 手动清理 | **竞赛结束后自动停止+删除容器** |
| 构建失败 | 手动重试 | **自动重试 2 次，带日志** |

---

## 6. API 接口清单

### 6.1 管理端 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /admin/ | 仪表盘 |
| GET | /admin/competitions | 竞赛列表 |
| POST | /admin/competitions/create | 创建竞赛 |
| POST | /admin/competitions/{id}/edit | 编辑竞赛 |
| POST | /admin/competitions/{id}/status | 切换状态（自动触发部署） |
| GET | /admin/competitions/{id} | 竞赛详情（题目/环境/成绩） |
| POST | /admin/competitions/{id}/challenges/create | 创建题目 |
| POST | /challenges/{id}/edit | 编辑题目 |
| POST | /challenges/{id}/delete | 删除题目 |
| POST | /admin/competitions/{id}/deploy | 一键部署（手动触发） |
| POST | /admin/challenges/{id}/exam-questions | 添加试卷试题 |
| POST | /admin/exam-questions/{id}/edit | 编辑试卷试题 |
| POST | /admin/exam-questions/{id}/delete | 删除试卷试题 |
| GET | /admin/metrics | 部署指标数据 |

### 6.2 选手端 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /contestant/ | 我的环境 + 试卷列表 |
| GET | /contestant/environment/{id} | 容器操作界面 |
| POST | /contestant/environment/{id}/submit | 提交判题 |
| GET | /contestant/exam/{id} | 试卷答题页 |
| POST | /contestant/exam/{id}/submit | 提交试卷 |
| GET | /contestant/scoreboard | 排行榜 |

---

## 7. 部署模板库

| 模板 | 用途 | 默认端口 |
|------|------|---------|
| nginx_setup | Nginx Web 服务器配置 | 80 |
| mysql_config | MySQL 数据库配置 | 3306 |
| docker_compose | Docker Compose 编排 | — |
| system_admin | Linux 系统管理 | — |
| redis_server | Redis 缓存服务配置 | 6379 |
| python_flask | Python Flask 应用开发 | 5000 |
| node_express | Node.js Express 应用开发 | 3000 |
| ssh_admin | SSH 服务器管理 | 22 |

---

## 8. 关键性能指标

系统应记录以下指标供论文使用：

- **并发部署能力**: 同时为 P 个选手 × C 个题目创建 P×C 个容器
- **平均部署耗时**: 单容器创建时间 + 端口分配开销
- **端口利用率**: [30000, 40000] 区间可支持最多 10000 个并发容器
- **判题延迟**: 单次判题从触发到返回结果的时间
- **资源开销**: 每个容器的 CPU/Memory 占用基线
