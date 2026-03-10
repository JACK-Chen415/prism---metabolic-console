# 🌈 Prism Metabolic Console

<div align="center">

**智能健康饮食管理应用** | AI-Powered Health & Diet Management

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

</div>

---

## ✨ 功能特性

### 🍎 饮食管理
- **AI 食物识别** - 拍照即可识别食物并分析营养成分
- **每日摄入追踪** - 记录卡路里、钠、嘌呤等关键指标
- **离线优先** - 无网络时自动本地缓存，联网后自动同步

### 🤖 AI 健康顾问
- **食鉴AI** - 基于豆包大模型的智能对话助手
- **个性化建议** - 根据用户健康档案定制饮食建议
- **冲突检测** - 自动识别食物与慢性病、过敏的冲突

### 📊 健康档案
- 支持记录高血压、糖尿病、痛风等慢性病
- 管理食物过敏史
- 动态调整每日摄入目标

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                     │
│  TypeScript + Vite + IndexedDB (离线缓存)                │
└─────────────────────────┬───────────────────────────────┘
                          │ REST API
┌─────────────────────────▼───────────────────────────────┐
│                  Backend (FastAPI)                       │
│  Python 3.9+ | JWT 认证 | SQLAlchemy 2.0                │
└─────────────────────────┬───────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
┌─────────────────┐             ┌─────────────────┐
│  PostgreSQL 16  │             │   豆包大模型    │
│   (数据存储)    │             │   (AI 服务)     │
└─────────────────┘             └─────────────────┘
```

---

## 🚀 快速开始

### 前置要求

- Node.js 18+
- Python 3.9+
- Docker Desktop
- 豆包 API Key ([火山引擎](https://console.volcengine.com/))

### 1. 克隆项目

```bash
git clone https://github.com/YOUR_USERNAME/prism---metabolic-console.git
cd prism---metabolic-console
```

### 2. 启动数据库

```bash
docker run -d --name prism-postgres \
  -e POSTGRES_USER=prism \
  -e POSTGRES_PASSWORD=prism123 \
  -e POSTGRES_DB=prism_metabolic \
  -p 5432:5432 \
  postgres:16-alpine
```

### 3. 启动后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的豆包 API Key

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd ..  # 返回项目根目录

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 5. 访问应用

- **前端**: http://localhost:3000
- **API 文档**: http://localhost:8000/api/docs

---

## 🧪 本地一键运行（推荐）

```bash
# 1) 启动数据库与后端（Docker）
docker compose up -d db backend

# 2) 启动前端（本机）
npm install
npm run dev
```

默认访问：
- 前端：`http://localhost:3000`
- 后端健康检查：`http://localhost:8000/api/health`
- API 文档：`http://localhost:8000/api/docs`

---

## 🔍 功能实现说明（本次更新）

### 1) 饮食 AI 估算：确定性规则（非随机）

位置：`components/views/LogView.tsx`

- 先按 `category` 给固定基线值（热量/钠/嘌呤）
- 再从 `portion` 中提取数字作为乘数（限制在 `0.5 ~ 3`）
- 最后根据备注关键词做固定增量修正（例如“咸/酱/卤”增加钠，“炸/油/煎”增加热量）

这样同样输入会得到同样结果，便于追踪与测试。

### 2) 验证码登录与重置密码

后端接口：
- `POST /api/auth/send-code`
- `POST /api/auth/login-code`
- `POST /api/auth/reset-password`

位置：
- 路由：`backend/app/api/routes/auth.py`
- Schema：`backend/app/schemas/user.py`
- 验证码服务：`backend/app/services/verification_service.py`

当前是谁在“发送验证码”？
- **开发版由后端服务自己生成并返回验证码文本**（`message` 字段），用于本地调试。
- 还**没有接入真实短信网关**（如阿里云短信、腾讯云短信、Twilio）。

生产环境建议：
- 将 `VerificationService` 替换为外部短信服务适配器
- 验证码只记录日志，不回传给前端
- 增加频控、IP 限流、设备指纹、防刷策略

---

## 📁 项目结构

```
prism---metabolic-console/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── core/           # 核心配置
│   │   ├── models/         # 数据库模型
│   │   ├── schemas/        # Pydantic Schema
│   │   ├── services/       # 业务服务 (AI)
│   │   └── main.py         # 应用入口
│   ├── Dockerfile
│   └── requirements.txt
├── components/              # React 组件
├── services/                # 前端服务层
│   ├── api.ts              # API 客户端
│   └── offline.ts          # 离线缓存服务
├── docker-compose.yml       # Docker 编排
└── package.json
```

---

## 🔐 环境变量

### 后端 (`backend/.env`)

```env
DATABASE_URL=postgresql+asyncpg://prism:prism123@localhost:5432/prism_metabolic
JWT_SECRET_KEY=your-secret-key
ARK_API_KEY=your-volcengine-api-key
DOUBAO_ENDPOINT_ID=your-endpoint-id
DOUBAO_VISION_ENDPOINT_ID=your-vision-endpoint-id
```

### 前端 (`.env.local`)

```env
VITE_API_URL=http://localhost:8000/api
```

---

## 📝 API 模块

| 模块 | 端点 | 功能 |
|------|------|------|
| 认证 | `/api/auth/*` | 注册、登录、Token 刷新 |
| 饮食 | `/api/meals/*` | CRUD、摄入汇总、离线同步 |
| 对话 | `/api/chat/*` | AI 对话、食物识别 |
| 健康 | `/api/conditions/*` | 慢性病、过敏管理 |
| 消息 | `/api/messages/*` | 系统通知 |

---

## ⚠️ 免责声明

本应用仅提供健康饮食建议，**不构成医疗诊断**。如有健康问题，请咨询专业医生。

---

## 📄 许可证

MIT License
