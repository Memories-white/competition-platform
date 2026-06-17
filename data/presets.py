"""预设题目库 — OpenStack 云计算平台相关"""

PRESETS = [
    {
        "id": 1,
        "title": "keystone 安装",
        "description": "使用脚本安装 keystone 服务，在控制节点上完成 keystone 的安装与配置，包括创建数据库、配置连接、初始化 Fernet 密钥、同步数据库、配置 Apache WSGI 等操作。",
        "category": "OpenStack 安装部署",
        "difficulty": "基础",
    },
    {
        "id": 2,
        "title": "glance 安装",
        "description": "使用脚本安装 glance 服务。首先使用 iaas-install-glance.sh 脚本在控制节点安装 glance，然后配置 glance 与 keystone 的对接，创建 glance 服务实体、端点，最后上传测试镜像验证服务可用。",
        "category": "OpenStack 安装部署",
        "difficulty": "基础",
    },
    {
        "id": 3,
        "title": "nova 安装",
        "description": "根据平台安装步骤安装至 nova 计算服务，分别在控制节点安装 nova-api、nova-scheduler、nova-conductor 等服务，在计算节点安装 nova-compute，配置与控制节点的消息队列和数据库连接。",
        "category": "OpenStack 安装部署",
        "difficulty": "进阶",
    },
    {
        "id": 4,
        "title": "网络创建",
        "description": "使用脚本安装 neutron 服务，并配置 Linux Bridge 或 Open vSwitch 网络代理，创建外部网络（flat）和内部网络（VXLAN/GRE），配置安全组规则，确保云主机可以获取 IP 并访问外部网络。",
        "category": "OpenStack 安装部署",
        "difficulty": "进阶",
    },
    {
        "id": 5,
        "title": "dashboard 配置",
        "description": "通过脚本 iaas-install-dashboard.sh 安装 Horizon 控制面板，配置 dashboard 与 keystone 的集成，修改 Apache 配置使 dashboard 可以通过浏览器访问，汉化界面设置并验证各项管理功能。",
        "category": "OpenStack 安装部署",
        "difficulty": "基础",
    },
    {
        "id": 6,
        "title": "rabbitmq 管理",
        "description": "登录 IaaS 云主机。使用 rabbitmqctl 命令查看 RabbitMQ 服务状态、列出所有队列和交换机、查看连接数和通道数、创建新的虚拟主机和用户，测试消息队列在 OpenStack 各组件间通信中的工作情况。",
        "category": "OpenStack 运维管理",
        "difficulty": "基础",
    },
    {
        "id": 7,
        "title": "keystone 管理",
        "description": "登录 IaaS 云主机，在 keystone 中创建新项目和用户，为用户分配角色（admin/member），查看服务目录（catalog）和端点列表，创建新的角色并测试基于角色的访问控制策略是否生效。",
        "category": "OpenStack 运维管理",
        "difficulty": "基础",
    },
    {
        "id": 8,
        "title": "nova 管理",
        "description": "登录 IaaS 云主机，修改云平台中默认每个项目的实例配额（quota），包括最大实例数、最大 CPU 核心数、最大内存大小等，创建新的实例类型（flavor），验证配额限制是否生效。",
        "category": "OpenStack 运维管理",
        "difficulty": "进阶",
    },
    {
        "id": 9,
        "title": "块存储服务管理",
        "description": "使用 cinder 命令创建一个名字叫 block_volume 的云硬盘，大小为 10GB，将卷挂载到指定的云主机实例上，验证挂载成功后在实例中格式化并挂载文件系统，测试数据读写是否正常。",
        "category": "OpenStack 运维管理",
        "difficulty": "进阶",
    },
]
