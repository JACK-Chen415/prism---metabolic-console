# Prism Metabolic Console - Backend

## 技术栈

- **框架**: FastAPI (Python 3.9+)
- **数据库**: PostgreSQL 16 + SQLAlchemy 2.0 (异步)
- **认证**: JWT (python-jose + passlib + bcrypt)
- **AI服务**: 豆包主多模态大模型 (Volcengine ARK SDK)
- **PDF生成**: WeasyPrint
- **部署**: Docker + Docker Compose

## 快速开始

### 1. 环境准备

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 填入你的配置
# 特别是豆包 API 密钥
```

### 2. 本地开发

推荐直接从仓库根目录运行一键脚本：

```bash
npm run dev:local
```

这会自动完成：
- 启动工作区内隔离 PostgreSQL（端口 `5433`）
- 执行 `alembic upgrade head`
- 执行知识库 seed
- 启动后端和前端

停止：

```bash
npm run dev:local:stop
```

如果你只想手动跑后端，再使用下面的方式。

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 执行迁移
python -m alembic upgrade head

# 执行知识库 seed
python -m app.seed.knowledge_seed --dataset core_v1

# 启动开发服务器
uvicorn app.main:app --reload --port 8000
```

### 3. Docker 部署

```bash
# 返回项目根目录
cd ..

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f backend
```

## API 文档

启动后访问:
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

## 项目结构

```
backend/
├── app/
│   ├── api/              # API 路由
│   │   ├── deps.py       # 依赖注入 (认证、数据库)
│   │   └── routes/       # 各模块路由
│   │       ├── auth.py   # 认证 API
│   │       ├── meals.py  # 饮食记录 API
│   │       ├── chat.py   # AI 对话 API
│   │       ├── conditions.py  # 健康档案 API
│   │       └── messages.py    # 消息通知 API
│   ├── core/             # 核心配置
│   │   ├── config.py     # 环境变量
│   │   ├── database.py   # 数据库连接
│   │   └── security.py   # JWT 认证工具
│   ├── models/           # SQLAlchemy 数据模型
│   ├── schemas/          # Pydantic 请求/响应 Schema
│   ├── services/         # 业务服务层
│   │   └── ai_service.py # 豆包 AI 服务
│   └── main.py           # 应用入口
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## 数据库表

| 表名 | 用途 |
|------|------|
| `users` | 用户账号 |
| `meals` | 饮食记录 |
| `health_conditions` | 健康档案 |
| `chat_sessions` | 对话会话 |
| `chat_messages` | 对话消息 |
| `app_messages` | 系统通知 |

## 豆包 AI 配置

1. 访问 [火山引擎控制台](https://console.volcengine.com/)
2. 开通「火山方舟」服务
3. 创建 API Key
4. 创建支持文本和图片输入的主多模态模型端点 (Endpoint)，获取 Endpoint ID
5. 填入 `.env` 文件对应字段：
   - `ARK_API_KEY`
   - `DOUBAO_MODEL`

`DOUBAO_MODEL` 同时用于 AI 对话、饮食建议和拍照识别；不再单独配置图片识别 endpoint。

## 常用命令

```bash
# 查看数据库
docker exec prism-postgres psql -U prism -d prism_metabolic -c "\dt"

# 查看用户
docker exec prism-postgres psql -U prism -d prism_metabolic -c "SELECT * FROM users;"

# 重启后端
uvicorn app.main:app --reload --port 8000
```

