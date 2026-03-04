# Seedance Web 部署指南

## 文件结构

```
seedance-web/
├── main.py              # FastAPI 后端
├── seedance_client.py   # Seedance API 客户端（复用现有文件）
├── index.html           # 前端页面
├── requirements.txt     # Python 依赖
├── Dockerfile           # 容器镜像
├── docker-compose.yml   # 部署配置
└── data/                # 数据目录（自动创建）
    └── tasks.db         # SQLite 数据库
```

## 环境变量配置

复制 `.env.example` 为 `.env` 并填写：

```bash
# 访问密码（必需）
ACCESS_PASSWORD=your_secure_password

# Seedance API 配置（必需）
ARK_API_KEY=your_ark_api_key

# 腾讯云 COS 配置（必需）
COS_REGION=ap-guangzhou
COS_BUCKET_NAME=your-bucket
COS_ACCESS_KEY_ID=your-key-id
COS_ACCESS_KEY_SECRET=your-secret
COS_DOMAIN=https://cdn.yourdomain.com  # 可选，CDN 域名
```

## 部署步骤

### 1. 准备环境变量

```bash
# 在服务器上创建工作目录
mkdir -p ~/seedance-web && cd ~/seedance-web

# 创建环境变量文件
cat > .env << 'EOF'
ACCESS_PASSWORD=your_secure_password
ARK_API_KEY=your_ark_api_key
COS_REGION=ap-guangzhou
COS_BUCKET_NAME=your-bucket-name
COS_ACCESS_KEY_ID=your-access-key
COS_ACCESS_KEY_SECRET=your-secret
COS_DOMAIN=
EOF
```

### 2. 上传代码

```bash
# 方式1：git 拉取
git clone <your-repo> .

# 方式2：手动上传
# 使用 scp 或 SFTP 将以下文件上传到服务器：
# - main.py
# - seedance_client.py
# - index.html
# - requirements.txt
# - Dockerfile
# - docker-compose.yml
```

### 3. 启动服务

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

### 4. 配置 Nginx（可选，用于 HTTPS）

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

## 更新部署

```bash
cd ~/seedance-web

# 拉取最新代码
git pull

# 重建并重启
docker-compose down
docker-compose up -d --build
```

## 数据备份

```bash
# 备份数据库
cp data/tasks.db backup/tasks-$(date +%Y%m%d).db

# 或使用 cron 定时备份
0 2 * * * cp /root/seedance-web/data/tasks.db /backup/seedance/tasks-$(date +\%Y\%m\%d).db
```

## 故障排查

```bash
# 查看日志
docker-compose logs -f

# 进入容器
docker-compose exec seedance-web bash

# 检查数据库
sqlite3 data/tasks.db "SELECT * FROM tasks ORDER BY created_at DESC LIMIT 5;"
```
