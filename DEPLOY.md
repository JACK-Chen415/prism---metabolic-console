# 🚀 Prism 云端部署指南（免费方案）

## 架构总览

```
[用户浏览器]
     ↓
[Vercel 前端] ← prism-metabolic-console.vercel.app
     ↓  (HTTPS API 请求)
[Render 后端] ← prism-backend-xxx.onrender.com
     ↓  (PostgreSQL 连接)
[Neon 数据库] ← xxx.neon.tech
```

---

## 第一步：创建免费 PostgreSQL 数据库（Neon）

1. 访问 **https://neon.tech** 并注册账号（支持 GitHub 登录）
2. 点击 **"Create a project"**
3. 设置：
   - **Project name**: `prism-metabolic`
   - **Postgres version**: 默认即可（16）
   - **Region**: 选离你最近的（如 `Singapore` 或 `US East`）
4. 创建后，在 **Dashboard** 页面找到 **Connection string**
5. 复制连接字符串，格式类似：
   ```
   postgresql://username:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
   ```
6. **⚠️ 重要**：需要将驱动改为 `asyncpg` 格式：
   ```
   postgresql+asyncpg://username:password@ep-xxx.region.aws.neon.tech/neondb?ssl=require
   ```
   即：把 `postgresql://` 改为 `postgresql+asyncpg://`，把 `sslmode=require` 改为 `ssl=require`

---

## 第二步：部署后端到 Render

1. 访问 **https://render.com** 并注册账号（支持 GitHub 登录）
2. 将代码推送到 GitHub 仓库（如果还没有的话）
3. 在 Render 控制台点击 **"New +"** → **"Web Service"**
4. 连接你的 GitHub 仓库 `prism---metabolic-console`
5. 配置服务：
   - **Name**: `prism-backend`
   - **Region**: 选和 Neon 数据库同区域的
   - **Branch**: `main`（或你的主分支）
   - **Runtime**: **Docker**
   - **Dockerfile Path**: `./backend/Dockerfile`
   - **Docker Context Directory**: `./backend`
   - **Instance Type**: **Free**

6. 在 **"Environment Variables"** 中添加以下变量：

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | `postgresql+asyncpg://...?ssl=require`（第一步获取的 Neon 连接字符串） |
   | `JWT_SECRET_KEY` | 一个随机强密码（如用 `openssl rand -hex 32` 生成） |
   | `ARK_API_KEY` | 你的豆包 AI API Key |
   | `DOUBAO_ENDPOINT_ID` | 你的豆包对话模型 endpoint |
   | `DOUBAO_VISION_ENDPOINT_ID` | 你的豆包视觉模型 endpoint |
   | `CORS_ORIGINS` | `["https://prism-metabolic-console.vercel.app","http://localhost:3000"]` |
   | `DEBUG` | `false` |

7. 点击 **"Create Web Service"** 开始部署
8. 等待部署完成（首次约 5-10 分钟）
9. 部署完成后会获得一个 URL，类似：`https://prism-backend-xxxx.onrender.com`
10. 验证：访问 `https://prism-backend-xxxx.onrender.com/api/health` 应返回 JSON

---

## 第三步：更新 Vercel 前端 API 地址

1. 登录 **https://vercel.com**，进入 `prism-metabolic-console` 项目
2. 进入 **Settings** → **Environment Variables**
3. 添加环境变量：
   - **Key**: `VITE_API_URL`
   - **Value**: `https://prism-backend-xxxx.onrender.com/api`（替换为你的 Render 后端地址）
   - **Environment**: 勾选 Production, Preview, Development
4. 点击 **Save**
5. 回到 **Deployments** → 点击最新部署旁的 **"..."** → **"Redeploy"**
6. 等待重新部署完成

---

## 第四步：验证

1. 访问 https://prism-metabolic-console.vercel.app
2. 尝试注册一个新账号
3. 尝试登录

---

## ⚠️ 注意事项

### Render 免费版限制
- 服务会在 **15 分钟无活动后自动休眠**
- 首次唤醒需要 **30-60 秒**（用户会感受到第一次请求较慢）
- 每月有 750 小时免费额度

### Neon 免费版限制
- 存储：0.5 GB
- 计算：每月 191 小时活跃时间
- 对个人项目完全够用

### 安全提醒
- ❌ 不要将 `.env` 文件提交到 Git
- ✅ 确保 `.gitignore` 中包含 `.env`
- ✅ 生产环境使用强随机 `JWT_SECRET_KEY`
