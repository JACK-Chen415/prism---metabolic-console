# Prism 代码风险审查清单

生成日期：2026-05-30
适用范围：Prism Metabolic Console 前端、后端、AI、数据和部署风险审查。
审查立场：面向移动端优先 AI 代谢健康产品，优先发现会影响真实用户安全、隐私、账号、数据完整性和健康建议边界的问题。

## 1. 审查总原则

- 不把 AI 输出当成事实：图片识别、语音解析、营养值和健康建议必须可确认、可纠错、可审计。
- 不绕过本地规则：过敏、AVOID、LIMIT、显式忌口等高风险场景必须由本地规则优先约束。
- 不暴露敏感数据：手机号、验证码、健康档案、聊天内容、图片、密钥、模型 endpoint 和数据库 URL 不应出现在日志或前端包中。
- 不让移动端流程断路：真实用户首先在手机端完成注册、记餐、拍照、聊天、报告和设置。
- 不把测试能力误认为生产能力：mock billing、dev OTP、mock device provider 必须在 UI 和 readiness 中明确标识。

## 2. 前端风险清单

| 检查项 | 风险 | 重点文件/区域 | 验收口径 |
|---|---|---|---|
| 移动端布局 | 按钮遮挡、底部导航覆盖、长文案溢出 | `components/views/*`、`components/BottomNav.tsx`、`index.css` | 375px/390px/430px 宽度核心路径无遮挡 |
| 协议和免责声明入口 | 用户未理解健康边界即使用 AI | `RegisterView`、`ComplianceView`、`ChatView`、`CameraView`、`ReportsView` | 注册前可查看，AI/报告/拍照处有短提示 |
| AI 候选确认 | 误识别直接入库污染数据 | `components/intake/IntakeConfirmationSheet.tsx`、`ChatView`、`CameraView` | 所有 AI/语音/图片候选需用户确认；编辑后重新评估 |
| 低置信度候选 | 用户误信 AI 估算 | 候选卡、风险标签、置信度展示 | 低置信度、高风险、规则不足候选禁止自动确认 |
| XSS 和 Markdown | AI 回复或用户内容注入脚本 | `ChatView`、Markdown 渲染、`DOMPurify` | 渲染前净化；链接策略安全；测试恶意 Markdown |
| token 存储 | `localStorage` 受 XSS 影响 | `constants/storage.ts`、`services/api.ts`、`sessionState` | 明确残余风险；强化 XSS 防护；设备会话可撤销 |
| 前端生产 API | 生产误连 localhost 或 HTTP | `services/api.ts`、`.env*`、`vite.config.ts` | production 必须显式 `VITE_API_URL`，拒绝 localhost fallback |
| 离线队列 | 本地记录丢失、重复、冲突不可见 | `services/offline.ts`、`SettingsView`、`LogView` | PENDING/FAILED/CONFLICT/SYNCED 可见，可重试/丢弃 |
| 退出登录 | 未同步数据被误删 | `useAppData.ts`、`offline.ts` | 退出前提示未同步记录；用户明确确认 |
| 图片上传 UX | 大图、失败、取消、重试处理不清 | `CameraView`、`ChatView`、`imageOptimization.ts` | 进度、取消、重试和错误原因清楚 |
| 语音兼容 | 浏览器不支持 SpeechRecognition | `ChatView` | 无能力时降级为文本输入，不阻断记餐 |
| 设置页数据权利 | 用户找不到导出/删除/注销 | `SettingsView`、`api.ts` | 数据权利入口清晰；高危操作二次确认 |
| 管理台脱敏 | 后台泄露手机号或健康文本 | `AdminView` | raw phone、验证码、密钥、原图不展示 |
| 前端测试 | UI 变更破坏核心路径 | `tests/*.mjs`、未来 Playwright | 至少覆盖登录、记餐、聊天、报告、设置 |

## 3. 后端风险清单

| 检查项 | 风险 | 重点文件/区域 | 验收口径 |
|---|---|---|---|
| OTP provider | dev 验证码回传到生产 | `verification_service.py`、`auth.py`、`config.py` | production 禁止 dev provider 和 debug_code |
| OTP 频控 | 短信轰炸、撞库、成本失控 | `auth_security.py`、`verification_service.py` | 手机号/IP/设备维度限流、失败锁定、审计 |
| refresh token | 登出后 token 仍有效 | `security.py`、`auth.py`、`security.py` model | 设备会话、`sid`/`jti`、撤销和复用检测 |
| user scope | 越权访问他人数据 | routes、schemas、models | 所有查询带 `user_id` 约束；测试覆盖 403/404 |
| RBAC/admin | 普通用户访问后台 | `admin.py`、deps | admin allowlist/role 双重控制；操作审计 |
| 数据权利 | 导出/删除/注销漏数据或越权 | `account.py`、models | 导出完整且限本人；删除后不可访问；保留必要审计 |
| 上传校验 | 恶意文件、超大图片、EXIF 泄露 | `upload_security.py`、`chat.py` | MIME、文件头、像素、大小、EXIF 清理、错误日志脱敏 |
| CORS | 通配来源导致 token 风险 | `config.py`、`main.py` | production 只允许明确 HTTPS origin |
| 密钥配置 | 默认 JWT/占位 AI key 上线 | `config.py`、`.env.example` | readiness 启动 gate 拒绝默认和占位值 |
| 错误响应 | 暴露堆栈、SQL、密钥、手机号 | exception handlers、logs | 用户响应通用化，服务端结构化脱敏 |
| Alembic 迁移 | 灰度数据库不可复现 | `backend/alembic/versions` | 迁移顺序清晰；升级可重复；有回滚策略说明 |
| DB 约束 | 重复档案、重复离线记录 | models、migrations | 关键唯一约束或服务层幂等测试 |
| API schema | 前后端字段漂移 | `schemas/*`、`services/api.ts` | contract tests 覆盖新增字段 |
| 测试可靠性 | 后端功能被回归破坏 | `backend/tests` | 安全、AI、知识、上传、数据权利、离线同步均有测试 |

## 4. AI 风险清单

| 检查项 | 风险 | 重点文件/区域 | 验收口径 |
|---|---|---|---|
| 本地规则优先 | LLM 放宽慢病/过敏风险 | `knowledge/service.py`、`ai_service.py`、`chat.py` | LOCAL_BLOCKED_NO_CLOUD 时不调用云端放宽 |
| 输出后复核 | 云端生成与本地规则冲突 | `ai_service.py`、`intake.py`、`knowledge` | 云端建议回流本地规则；冲突时改写/阻断 |
| prompt 注入 | 用户诱导 AI 忽略健康边界 | system prompt、chat route | 提示词不暴露内部规则；高风险拒答稳定 |
| 图片识别误差 | 食物、份量、营养估算错误 | 多模态调用、候选确认 | 结果标识估算和置信度；用户确认后入库 |
| 自动确认 | 错误候选静默写入 | `intake.py`、确认接口 | 低置信度、高风险、规则不足不自动确认 |
| 医疗建议越界 | 诊断、治疗、处方、药物调整 | prompt、安全模板、测试集 | 触发拒答和就医引导 |
| 引用和来源 | 用户误以为 AI 有医学依据 | knowledge citations | 本地来源可追溯；云端补充不伪造引用 |
| fallback 状态 | 运营无法判断规则命中 | knowledge audit | 记录 fallback、cloud_call_reason、blocked_reason |
| AI 失败态 | 模型超时、限额、网络失败 | `ai_service.py`、前端状态 | 用户得到可操作降级，不重复提交 |
| 成本和延迟 | 灰度成本不可控 | telemetry、admin | 记录模型调用耗时、失败率、占位成本 |
| 用户反馈 | 错误建议无法闭环 | feedback API、AdminView | 有风险反馈进入 open 队列并可关闭 |

## 5. 数据风险清单

| 检查项 | 风险 | 重点文件/区域 | 验收口径 |
|---|---|---|---|
| 数据分类 | 健康数据未按敏感数据处理 | models、privacy docs | 健康档案、指标、图片、聊天列入敏感范围 |
| 日志脱敏 | 手机号、验证码、健康文本泄露 | logging、audit services | 日志只含哈希、ID、类型、状态，不含验证码 |
| 审计边界 | 审计不足或过度采集 | `security_audit_logs`、knowledge audit | 记录必要安全事件，不记录原始图片和密钥 |
| 数据导出完整性 | 用户拿不到自己的数据 | account export | 覆盖用户资料、饮食、健康档案、聊天、指标、反馈 |
| 删除一致性 | 删除后残留在前端或关联表 | account delete、offline cache | 服务端删除，前端清缓存，关联数据策略明确 |
| 备份和保留 | 删除权与备份冲突 | 部署/隐私政策 | 说明备份滞后和审计保留周期 |
| 离线 client_id | 重复同步或覆盖 | `offline.ts`、`meals.py` | client_id 幂等；冲突不静默丢失 |
| 知识库版本 | 用户不知道规则来源 | seed、knowledge models | 规则有来源、版本、审核状态或待审核标记 |
| 健康指标来源 | mock/手动/设备混淆 | health metrics provider | 来源明确，不把 mock 数据当真实设备 |
| 分析埋点 | 过度采集健康行为 | future analytics | 仅采集必要事件；默认脱敏聚合 |

## 6. 部署风险清单

| 检查项 | 风险 | 重点文件/区域 | 验收口径 |
|---|---|---|---|
| 环境变量 | 密钥提交或占位上线 | `.env.example`、deployment config | 仓库无真实密钥；生产拒绝占位 |
| HTTPS | 健康数据明文传输 | Vercel/Render/CORS/API URL | 前后端均 HTTPS；HTTP 仅本地开发 |
| readiness | 配置错误仍可放量 | `/api/ready`、admin release readiness | 灰度前红/黄/绿 gate 可用 |
| CI | 未跑测试直接部署 | package scripts、backend pytest | test/typecheck/build/backend tests 作为 gate |
| 数据迁移 | 上线迁移失败 | Alembic、DB backup | 部署前备份；迁移失败可回滚应用 |
| 监控告警 | AI、短信、上传、登录异常不可见 | logs、admin telemetry | OTP lockout、AI error、upload rejection 有监控 |
| 回滚 | 事故时无法降级 | deployment runbook | 先关前端入口，再关后端功能，保留审计和数据 |
| 支付 provider | mock 被误当真实收费 | billing providers | UI 和 readiness 明确 mock；真实支付前签名/幂等/退款/发票齐全 |
| 管理员 bootstrap | 管理权限丢失或滥用 | `ADMIN_PHONE_HASHES`、User.role | 至少一个 break-glass 管理员；操作审计 |
| 第三方模型 | key 泄露、endpoint 失效、模型变更 | Doubao/Ark config | key 轮换策略；失败降级；模型变更前回归测试 |

## 7. 推荐审查节奏

- 每次灰度前：运行前端 contract tests、typecheck、build、后端 pytest，并检查 readiness。
- 每周：审查 AI 风险反馈、知识缺口、OTP 异常、上传拒绝、数据权利事件。
- 每个功能切片合入前：补一条对应风险测试或手工验收记录。
- 每次知识库扩容：检查来源、别名、过敏标签、疾病规则、fallback 状态和审计输出。
- 每次涉及健康文案：检查是否出现诊断、治疗、处方、保证效果、替代医生等表达。

## 8. P0 阻断判定

出现以下任一情况，不建议扩大内测：

- AI 放宽过敏、AVOID、LIMIT 或显式忌口。
- AI 给出个体化诊断、处方、药物调整或急救指导。
- 生产环境回传验证码或允许 dev OTP provider。
- 用户可访问、导出、删除他人数据。
- 图片上传泄露原图、EXIF、密钥或可执行恶意文件被接收。
- 生产包使用 localhost API、默认 JWT secret、通配 CORS 或占位模型配置。
- 数据删除、注销、设备会话撤销不可用。
