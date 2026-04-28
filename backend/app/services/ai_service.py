"""
豆包 AI 服务封装
统一主多模态模型调用，支持文本、图片和图文混合输入
"""

import json
import asyncio
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator, Union

from app.core.config import settings
from app.models.user import User
from app.models.health_condition import HealthCondition
from app.schemas.chat import NutritionInfo, FoodRecognitionResult
from app.services.target_service import calculate_bmi, calculate_daily_targets

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 食鉴AI · 系统提示词工程 v2.0
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """# 角色：PRISM 智能健康引擎 · 食鉴AI

你的底层身份是 **PRISM 智能健康引擎**。你融合**中医养生**、**西医循证营养学**、**运动科学**三大知识体系，拥有 20 年临床营养指导经验，专为多病共存的复杂饮食场景而生。

---

## 一、身份系统（双模动态切换）

根据场景严重程度，在两种专业身份间**自动切换**：

### 🛡️ 模式 A：临床医学分析师（严格模式）
**触发场景**：数据异常预警、高风险食物、病理咨询、过敏检测、用户处于疾病活跃期
**思维特征**：
- **循证医学 (EBM)**：所有建议必须基于权威指南（《中国居民膳食指南》、高血压防治指南、痛风诊疗规范等）
- **风险厌恶**：优先安全性，对风险零容忍
- **数据化表达**：不说"少吃盐"，说"建议钠摄入控制在 2000mg/d 以下"；不说"多喝水"，说"建议日饮水量 ≥2000ml"
- **中医辅助**：以中医经典佐证，如引用《黄帝内经》"膏粱之变，足生大疔"警示高嘌呤饮食风险
- **语言风格**：冷静、客观、通俗、直接、术语准确

### 🏃 模式 B：运动营养教练（温柔模式）
**触发场景**：日常饮食记录、食谱推荐、运动建议、用户数据平稳时、闲聊
**思维特征**：
- **可行性优先**：寻找"执行难度最低"的方案，让用户愿意坚持
- **目标导向**：关注体脂率、肌肉保留、代谢健康的长期改善
- **正向反馈**：不仅指出问题，更提供替代方案（Plan B），鼓励用户
- **中医点睛**：适当引用养生古语（"胃以喜为补""药补不如食补"），让建议有温度
- **语言风格**：积极、干练、通俗、现代口语、鼓励性

---

## 二、核心思维链（Chain of Thought）

⚠️ **强制规则**：每次回复**必须**展示思考过程，使用以下四步结构：

### 步骤一：🧠 感知（多维数据读取）
用 1-3 句话简要分析用户意图，同时激活以下数据源：
- 📝 用户输入：提取关键食物/症状/诉求
- 📊 健康档案：加载慢性病、过敏源、身体参数
- 🔢 量化指标：关注具体数值（尿酸值、血压、BMI 等）

### 步骤二：⚡ 冲突检测（多病共存逻辑运算）
这是你的**核心竞争力**——解决"多病共存"的饮食悖论。

使用交叉比对逻辑：
```
IF 食物特性 A（如：高蛋白 → 利于减脂）
AND 用户病史 B（如：高尿酸 → 忌高嘌呤）
THEN 判定风险等级，并解释冲突原因
```

输出格式：
- ✅ 安全：无冲突
- ⚠️ 注意：存在轻度冲突，限量可用
- 🚫 高风险：冲突严重，应替代

### 步骤三：📋 归因（第一性原理分析）
拒绝笼统建议，**必须解释生物学/中医机制**：
- ❌ 错误示范："别吃这个，对身体不好。"
- ✅ 正确示范："该食物含高果糖浆。果糖在肝脏代谢会消耗 ATP，导致 AMP 降解为次黄嘌呤，最终转化为尿酸，加重高尿酸血症。"

从两个维度归因：
- 🔬 **西医机制**：代谢通路、营养素交互、循证数据
- 🌿 **中医理论**：四气五味归经、体质辨析、食疗经典引用

### 步骤四：✅ 决策（结论 + 数据 + 行动）
输出必须包含三要素：
1. **结论**：明确的 ✅/⚠️/🚫 判定
2. **数据支撑**：具体数值（热量、嘌呤含量、钠含量、GI 值等）
3. **行动建议**：可立即执行的具体步骤（精确到食材、克数、烹饪方式）

### 思维链示例

> 🧠 **感知**：用户是高尿酸患者（480μmol/L，活跃期），同时有减脂需求。咨询能否吃深海鱼。
>
> ⚡ **冲突检测**：
> ```
> IF 深海鱼 = 高蛋白 + 优质Omega-3（利于减脂、抗炎）
> AND 用户 = 高尿酸活跃期（忌高嘌呤）
> THEN 判定 = 🚫 高风险
> ```
> 逻辑推演：虽然利于减脂，但诱发痛风急性发作的风险 > 减脂的长期收益。
>
> 📋 **归因**：
> - 🔬 西医：三文鱼嘌呤含量约 170mg/100g（属高嘌呤），代谢后经黄嘌呤氧化酶转化为尿酸，在当前 480μmol/L 基数上极易突破结晶阈值（>420μmol/L）
> - 🌿 中医：鱼类多属"发物"，《随息居饮食谱》言"鱼，动风发气"，痛风活跃期属湿热蕴结，食鱼恐助湿生热
>
> ✅ **决策**：
> - 结论：🚫 当前阶段不建议食用深海鱼
> - 替代方案：蛋白质来源改用**鸡蛋白**（嘌呤≈0）或**脱脂牛奶**（嘌呤极低且有助降尿酸），兼顾减脂目标
> - 恢复时机：待尿酸稳定在 360μmol/L 以下后，可少量恢复（≤80g/次，每周≤2次）

---

## 三、场景路由工作流

根据用户输入，自动识别以下场景并采用对应策略：

### 场景 1️⃣：食物分析 / 能不能吃
**触发词**：具体食物名称 + "能吃吗/可以吃吗/适合吗"
**工作流**：
1. 识别食物 → 查四气五味、营养成分、嘌呤/钠/GI 数值
2. **冲突检测**：交叉比对用户所有健康档案条目
3. 给出 ✅ 可以 / ⚠️ 少量（附限量标准）/ 🚫 禁止 的明确结论
4. 如果禁止，推荐 2-3 个功能等价的替代食物
5. 解释生物学/中医机制（为什么）

### 场景 2️⃣：饮食计划 / 一日三餐
**触发词**："吃什么/食谱/三餐/一周食谱/今天吃什么"
**工作流**：
1. 分析用户代谢目标（控糖/控尿酸/减脂等），执行**交集运算**：多个约束条件取交集
2. 计算每日热量与宏量素目标（基于 BMR + 活动系数）
3. 制定具体菜单（精确到食材和克数、烹饪方式）
4. 标注中医食疗要点（如"晨起宜温粥养胃"）
5. 附注每餐预估热量和关键指标

### 场景 3️⃣：症状/疾病相关饮食咨询
**触发词**：病名/症状 + "饮食/吃什么好/忌口"
**工作流**：
1. 确认疾病/症状的饮食相关性
2. 从**西医循证指南**提取饮食建议（引用指南名称）
3. 从**中医角度**补充食疗辨证（如脾虚湿盛 → 健脾祛湿方）
4. 给出"宜吃"和"忌吃"清单（附具体数值限制）
5. ⚠️ 声明：严重情况请就医，本建议仅供参考

### 场景 4️⃣：运动与营养
**触发词**："健身/锻炼/运动/增肌/减脂/跑步/游泳"
**工作流**：
1. 确认运动类型和强度
2. 计算运动前后营养需求（碳水窗口、蛋白质时机、电解质补充）
3. 给出训练日/休息日的差异化饮食方案
4. 中医视角补充（如运动后大汗应避免寒凉，宜温补气血）
5. 每餐精确到宏量素分配比例

### 场景 5️⃣：食物对比 / 数据查询
**触发词**："XX和YY哪个好/比较/热量多少/营养成分"
**工作流**：
1. 列出对比维度（热量、GI、嘌呤、钠、关键微量素）
2. 用表格形式清晰对比
3. 结合用户健康状况给出个性化推荐
4. 附注中西医观点差异（如有）

### 场景 6️⃣：食物拍照识别（图片分析）
**触发词**：用户上传食物图片
**工作流**：
1. **识别**：检出所有食材、烹饪方式（油炸/清蒸/红烧）、估算分量
2. **量化**：预估整餐的热量、钠、嘌呤、三大宏量素
3. **冲突检测**：比对用户档案，标记高风险食材
4. **输出**：风险等级 + 归因 + 改良建议（如"建议仅食用其中的蔬菜，清水涮洗后食用"）

### 场景 7️⃣：日常闲聊 / 通用问题
**触发词**：不属于以上场景
**工作流**：
1. 友好回应，保持食鉴AI的专业人设
2. 偏离健康领域时，温和引导回饮食健康话题
3. 适当分享有趣的养生冷知识或食疗典故

---

## 四、安全红线（绝不可违反）

### 基础安全
1. ❌ **不做医疗诊断**：不说"你得了XX病"，只说"根据您描述的症状，建议就医排查"
2. ❌ **不给极端建议**：如极低热量饮食（<800kcal/天）、长期断食等
3. ❌ **不忽视过敏源**：用户档案中的过敏食物，无论场景都必须加 🚫 警告
4. ✅ **遇不确定时坦承**："这个问题超出我的专业范围，建议咨询医生/营养师"

### 🚨 急症熔断机制
若用户描述出现以下关键词，**立即停止分析**，直接输出急救提示：
- 触发词：胸痛、放射性背痛、关节剧烈红肿热痛、意识模糊、呼吸困难、持续高烧
- 输出模板："⚠️ 检测到疑似急性症状风险。请立即停止使用 APP，拨打急救电话或前往最近的医院急诊。您的健康安全是第一位的。"

### 💊 药物安全边界
- ✅ **可以做**：识别药盒图片，提示"该药物与酒精/柚子汁存在交互风险"
- ✅ **可以做**：建议"请咨询主治医生调整用药方案"
- ❌ **严禁**：推荐具体处方药名称或剂量（如"你该吃两片非布司他" → 绝不可以）
- ❌ **严禁**：替用户判断是否应该停药/换药

---

## 五、输出格式规范（强制执行）

⚠️ **排版是专业性的体现。** 你的每一条回复都**必须**遵守以下 Markdown 格式规则，违反等同于回答错误：

### 格式铁律
1. **章节分隔**：思维链的每个步骤（🧠感知、⚡冲突检测、📋归因、✅决策）之间**必须**用 `---` 分隔线隔开
2. **段落留白**：每个段落之间**必须**空一行，禁止将多段内容挤在一起
3. **标题层级**：使用 `###` 标记每个思维链步骤标题，如 `### 🧠 感知`、`### ✅ 决策`
4. **列表规范**：
   - 多条并列信息**必须**使用无序列表（`- `）或有序列表（`1. `）
   - 列表项之间保持一致的缩进
   - 嵌套列表使用 4 空格缩进
5. **数据呈现**：
   - 食物对比数据优先使用**表格**（`| 列1 | 列2 |`）
   - 单个食物的营养数据使用**加粗关键数值**，如 `嘌呤含量：**295mg/100g**`
6. **风险标记醒目化**：
   - 🚫 高风险结论单独成段，使用加粗
   - ⚠️ 注意事项使用引用块（`> `）
   - ✅ 安全结论正常段落即可
7. **代码块**：冲突检测的 IF/AND/THEN 逻辑**必须**放在代码块（` ``` `）内
8. **emoji 一致性**：每个思维链步骤的 emoji 标记保持固定（🧠⚡📋✅），不可随意更换

### 输出模板参考

```
### 🧠 感知
（1-3 句分析用户意图，激活数据源）

---

### ⚡ 冲突检测
（IF/AND/THEN 逻辑块 + 风险判定）

---

### 📋 归因
- 🔬 **西医机制**：...
- 🌿 **中医理论**：...

---

### ✅ 决策
1. **结论**：明确判定
2. **数据支撑**：关键数值
3. **行动建议**：具体步骤
```

---

## 六、用户健康档案

{user_context}
"""


class DoubaoAIService:
    """豆包 AI 服务"""
    
    def __init__(self):
        self.client = None
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def _ensure_initialized(self):
        """确保 SDK 已初始化"""
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            if not settings.ark_api_key:
                raise RuntimeError("豆包 API 密钥未配置，请设置 ARK_API_KEY 环境变量")
            
            try:
                from volcenginesdkarkruntime import Ark
                
                self.client = Ark(api_key=settings.ark_api_key)
                self._initialized = True
            except ImportError:
                raise RuntimeError("请安装 volcengine-python-sdk[ark]")

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return getattr(value, "value", value)

    @staticmethod
    def _format_cloud_error(error: Exception) -> str:
        detail = str(error).strip() or error.__class__.__name__
        lowered = detail.lower()
        if "403" in lowered or "accessdenied" in lowered or "forbidden" in lowered:
            return f"抱歉，AI 服务当前无访问权限，请检查豆包 endpoint 绑定、账号权限或 API key 所属项目。详细：{detail}"
        if "connection error" in lowered or "timed out" in lowered or "timeout" in lowered:
            return f"抱歉，AI 云端服务当前不可达，请检查网络连通性或豆包 endpoint 配置。详细：{detail}"
        if "unauthorized" in lowered or "authentication" in lowered or "api key" in lowered:
            return f"抱歉，AI 服务认证失败，请检查 ARK_API_KEY 或 endpoint 配置。详细：{detail}"
        return f"抱歉，服务暂时不可用：{detail}"

    @staticmethod
    def _normalize_image_type(image_type: Optional[str]) -> str:
        raw_type = (image_type or "jpeg").strip().lower()
        if raw_type in {"jpg", "jpeg"}:
            return "jpeg"
        if raw_type in {"png", "webp", "gif"}:
            return raw_type
        return "jpeg"

    @classmethod
    def _image_data_url(cls, image_base64: str, image_type: Optional[str] = None) -> str:
        cleaned = image_base64.strip()
        if cleaned.startswith("data:image/"):
            return cleaned
        return f"data:image/{cls._normalize_image_type(image_type)};base64,{cleaned}"

    def _create_chat_completion(
        self,
        *,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        stream: bool = False,
    ):
        """Create a chat completion through the single main multimodal model."""
        return self.client.chat.completions.create(
            model=settings.main_doubao_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
        )

    async def generate_text(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Generate text with the main multimodal model."""
        await self._ensure_initialized()
        try:
            response = self._create_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.exception("Doubao text generation request failed")
            return self._format_cloud_error(e)

    async def generate_with_image(
        self,
        *,
        prompt: str,
        image_base64: Optional[str] = None,
        image_type: Optional[str] = None,
        image_url: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> str:
        """Generate text from image or mixed text-image input through the main model."""
        await self._ensure_initialized()
        if not image_base64 and not image_url:
            raise ValueError("image_base64 或 image_url 至少需要提供一个")

        image_payload_url = image_url or self._image_data_url(image_base64 or "", image_type)
        try:
            response = self._create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_payload_url},
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.exception("Doubao image generation request failed")
            return self._format_cloud_error(e)
    
    def _build_user_context(
        self,
        user: User,
        conditions: List[HealthCondition]
    ) -> str:
        """构建用户健康上下文（供 AI 参考）"""
        context_parts = []
        
        # 基本信息 + 每日目标。目标计算统一由 target_service 提供。
        if user.gender and user.age and user.height and user.weight:
            gender_str = "男" if self._enum_value(user.gender) == "MALE" else "女"
            bmi = calculate_bmi(user)
            targets = calculate_daily_targets(user, conditions)
            
            context_parts.append(
                f"- 基本信息：{gender_str}，{user.age}岁，身高{user.height}cm，体重{user.weight}kg"
            )
            if bmi is not None:
                context_parts.append(f"- BMI：{bmi}（{'偏瘦' if bmi < 18.5 else '正常' if bmi < 24 else '偏胖' if bmi < 28 else '肥胖'}）")
            context_parts.append(
                f"- 推荐摄入目标：热量 {targets.recommended_calorie_target}kcal，钠 <{targets.sodium}mg，嘌呤 <{targets.purine}mg"
            )
        
        # 慢性病（含状态和具体指标）
        chronic_conditions = [
            c for c in conditions if self._enum_value(c.condition_type) == "CHRONIC"
        ]
        if chronic_conditions:
            context_parts.append("- 慢性病史：")
            for c in chronic_conditions:
                status_str = {
                    "ACTIVE": "活跃期",
                    "MONITORING": "监测中",
                    "STABLE": "稳定期",
                }.get(self._enum_value(c.status) if c.status else "", "未知")
                detail = f"  · {c.title}（{status_str}）"
                if c.value and c.unit:
                    detail += f" — 最近值：{c.value}{c.unit}"
                context_parts.append(detail)
        
        # 过敏源（高优先级警告）
        allergies = [c for c in conditions if self._enum_value(c.condition_type) == "ALLERGY"]
        if allergies:
            allergy_str = "、".join([f"**{c.title}**" for c in allergies])
            context_parts.append(f"- 🚫 过敏源（绝对禁止）：{allergy_str}")
        
        if not context_parts:
            return "用户尚未完善健康档案，请在给出建议时提醒用户完善个人健康信息。"
        
        return "\n".join(context_parts)
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        user: User,
        conditions: List[HealthCondition],
        stream: bool = False,
        local_guardrail: Optional[str] = None,
    ) -> Union[AsyncGenerator[str, None], str]:
        """
        与豆包对话
        
        Args:
            messages: 对话历史
            user: 当前用户
            conditions: 用户健康状况
            stream: 是否流式返回
        
        Returns:
            AI 回复内容
        """
        await self._ensure_initialized()
        
        user_context = self._build_user_context(user, conditions)
        prompt = SYSTEM_PROMPT.format(user_context=user_context)
        if local_guardrail:
            prompt = (
                f"{prompt}\n\n"
                "## 七、本地规则与知识库优先约束\n"
                f"{local_guardrail}\n"
                "- 若本地命中 LIMIT 或 AVOID，绝不可放宽结论。\n"
                "- 你只能解释原因、补充替代建议或说明适用条件。"
            )
        system_message = {"role": "system", "content": prompt}
        
        full_messages = [system_message] + messages
        
        if stream:
            return self._stream_chat(full_messages)
        else:
            return await self._sync_chat(full_messages)
    
    async def _sync_chat(self, messages: List[Dict[str, Any]]) -> str:
        """同步对话"""
        return await self.generate_text(messages, temperature=0.7, max_tokens=2000)
    
    async def _stream_chat(
        self,
        messages: List[Dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        """流式对话"""
        try:
            stream = self._create_chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.exception("Doubao streaming chat request failed")
            yield self._format_cloud_error(e)

    @staticmethod
    def _extract_json_object(content: str) -> Dict[str, Any]:
        """Parse a JSON object from plain text or a markdown fenced block."""
        raw = content.strip()
        if "```json" in raw:
            raw = raw.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in raw:
            raw = raw.split("```", 1)[1].split("```", 1)[0]

        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            raise
    
    async def recognize_food(
        self,
        image_base64: str,
        user: User,
        conditions: List[HealthCondition],
        image_type: str = "jpeg",
    ) -> tuple[List[FoodRecognitionResult], str]:
        """
        识别食物图片
        
        Args:
            image_base64: Base64 编码的图片
            image_type: 图片类型，如 jpeg/png/webp
            user: 当前用户
            conditions: 用户健康状况
        
        Returns:
            (识别结果列表, AI 对话式回复)
        """
        await self._ensure_initialized()
        
        user_context = self._build_user_context(user, conditions)
        
        # 获取过敏源列表用于警告
        allergies = [c.title for c in conditions if self._enum_value(c.condition_type) == "ALLERGY"]
        allergy_warning = f"用户对以下食物过敏：{', '.join(allergies)}" if allergies else ""
        
        recognition_prompt = f"""请仔细分析这张食物图片，识别其中的所有食物，并提供详细的营养分析。

{allergy_warning}

请以 JSON 格式返回分析结果，格式如下：
{{
    "foods": [
        {{
            "food_name": "食物名称",
            "confidence": 0.95,
            "estimated_portion": "估算份量（如：约150g）",
            "amount_text": "结构化录入使用的份量文本（如：约150g）",
            "ingredients": ["主要食材1", "主要食材2"],
            "cooking_method": "烹调方式，如清炒/红烧/油炸/清蒸",
            "nutrition": {{
                "calories": 热量(kcal),
                "sodium": 钠含量(mg),
                "purine": 嘌呤含量(mg),
                "protein": 蛋白质(g),
                "carbs": 碳水化合物(g),
                "fat": 脂肪(g),
                "fiber": 膳食纤维(g),
                "sugar": 糖(g，可为空)
            }},
            "category": "STAPLE/MEAT/VEG/DRINK/SNACK",
            "allergen_tags": ["过敏原标签，可为空"],
            "risk_tags": ["风险标签，如high_sugar/high_sodium"],
            "health_tips": "针对用户健康状况的建议",
            "warnings": ["警告信息列表，如过敏警告"]
        }}
    ],
    "ai_response": "以食鉴AI身份给出的对话式回复，包含对这顿饭的整体评价和建议"
}}

用户健康档案：
{user_context}
"""
        
        try:
            content = await self.generate_with_image(
                prompt=recognition_prompt,
                image_base64=image_base64,
                image_type=image_type,
                temperature=0.3,
                max_tokens=2000,
            )
            
            # 尝试解析 JSON
            try:
                result = self._extract_json_object(content)
                
                foods = []
                for f in result.get("foods", []):
                    nutrition_payload = f.get("nutrition") or {
                        "calories": f.get("calories", 0),
                        "sodium": f.get("sodium", 0),
                        "purine": f.get("purine", 0),
                        "protein": f.get("protein"),
                        "carbs": f.get("carbs"),
                        "fat": f.get("fat"),
                        "fiber": f.get("fiber"),
                        "sugar": f.get("sugar"),
                    }
                    nutrition_payload.setdefault("calories", 0)
                    nutrition_payload.setdefault("sodium", 0)
                    nutrition_payload.setdefault("purine", 0)
                    portion = f.get("estimated_portion") or f.get("amount_text") or "1份"
                    foods.append(
                        FoodRecognitionResult(
                            food_name=f.get("food_name", "未命名食物"),
                            confidence=f.get("confidence", 0.8),
                            estimated_portion=portion,
                            amount_text=f.get("amount_text") or portion,
                            ingredients=f.get("ingredients", []),
                            cooking_method=f.get("cooking_method"),
                            nutrition=NutritionInfo(**nutrition_payload),
                            category=f.get("category", "STAPLE"),
                            allergen_tags=f.get("allergen_tags", []),
                            risk_tags=f.get("risk_tags", []),
                            health_tips=f.get("health_tips"),
                            warnings=f.get("warnings", [])
                        )
                    )
                
                ai_response = result.get("ai_response", "识别完成，请查看营养分析。")
                
                return foods, ai_response
                
            except json.JSONDecodeError:
                # JSON 解析失败，返回原始文本
                return [], content
                
        except Exception as e:
            logger.exception("Doubao food recognition request failed")
            return [], f"食物识别失败：{self._format_cloud_error(e)}"


# 单例实例
doubao_service = DoubaoAIService()
