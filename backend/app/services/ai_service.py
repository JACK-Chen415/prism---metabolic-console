"""
豆包 AI 服务封装
统一主多模态模型调用，支持文本、图片和图文混合输入
"""

import json
import asyncio
import logging
import re
import time
from typing import Optional, List, Dict, Any, AsyncGenerator, Union

from app.core.config import settings
from app.models.user import User
from app.models.health_condition import HealthCondition
from app.schemas.chat import NutritionInfo, FoodRecognitionResult
from app.services.target_service import calculate_bmi, calculate_daily_targets

logger = logging.getLogger(__name__)


# 食鉴AI prompt v3: compact default for lower cloud latency.

SYSTEM_PROMPT = """你是 PRISM 智能健康引擎（食鉴AI），专注饮食、代谢健康、慢病饮食约束和运动营养建议。

核心规则：
- 优先使用用户健康档案和本地规则约束；过敏、AVOID、LIMIT 等硬约束不得被放宽。
- 不做医疗诊断，不推荐处方药名称/剂量，不建议停药或换药；严重症状提示立即就医。
- 遇到胸痛、呼吸困难、意识模糊、持续高烧、剧烈红肿热痛等急症信号时，直接给急救提示。
- 针对食物/食谱/运动营养问题，给明确结论、关键数值、可执行份量或替代方案。
- 涉及慢病、多病共存、过敏或高风险食物时，先判定风险等级：安全 / 注意 / 高风险，并解释西医机制；必要时补充中医食疗角度。
- 普通低风险问题保持简洁；用户要求简短时严格简短。复杂饮食决策可用“感知、冲突检测、归因、决策”四段，但不要展开冗长推理。
- 使用清晰 Markdown。优先短段落、列表和表格；避免空泛鼓励和长篇模板化输出。

用户健康档案：

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
                import httpx

                timeout = httpx.Timeout(
                    timeout=settings.doubao_timeout_seconds,
                    connect=settings.doubao_connect_timeout_seconds,
                )
                self.client = Ark(
                    api_key=settings.ark_api_key,
                    timeout=timeout,
                    max_retries=settings.doubao_max_retries,
                )
                self._initialized = True
            except ImportError:
                raise RuntimeError("请安装 volcengine-python-sdk[ark]")

    @staticmethod
    def _enum_value(value: Any) -> Any:
        return getattr(value, "value", value)

    @staticmethod
    def _sanitize_cloud_error_detail(error: Exception) -> str:
        detail = str(error).strip() or error.__class__.__name__
        lowered = detail.lower()
        if any(marker in lowered for marker in ("api key", "apikey", "secret", "token", "password", "endpoint", "model id", "model_id")):
            return "上游错误细节已隐藏"
        detail = re.sub(r"ep-[A-Za-z0-9-]{6,}", "[redacted-endpoint]", detail)
        detail = re.sub(r"(?i)[0-9a-f]{16,}", "[redacted]", detail)
        return detail[:180]

    @classmethod
    def _format_cloud_error(cls, error: Exception) -> str:
        raw_detail = str(error).strip() or error.__class__.__name__
        lowered = raw_detail.lower()
        detail = cls._sanitize_cloud_error_detail(error)
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
        metrics: Optional[dict[str, Any]] = None,
    ) -> str:
        """Generate text with the main multimodal model."""
        await self._ensure_initialized()
        start = time.perf_counter()
        try:
            response = await asyncio.to_thread(
                self._create_chat_completion,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if metrics is not None:
                metrics["doubao_total_ms"] = round((time.perf_counter() - start) * 1000, 2)
                metrics["response_chars"] = len(content or "")
            return content
        except Exception as e:
            logger.warning("Doubao text generation request failed", extra={"error_type": e.__class__.__name__})
            message = self._format_cloud_error(e)
            if metrics is not None:
                metrics["doubao_total_ms"] = round((time.perf_counter() - start) * 1000, 2)
                metrics["response_chars"] = len(message)
                metrics["doubao_error"] = e.__class__.__name__
            return message

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
            response = await asyncio.to_thread(
                self._create_chat_completion,
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
            logger.warning("Doubao image generation request failed", extra={"error_type": e.__class__.__name__})
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

    @staticmethod
    def _normalize_chat_mode(value: Optional[str]) -> str:
        normalized = (value or "").strip().upper()
        return "GENTLE" if normalized == "GENTLE" else "STRICT"

    @staticmethod
    def _normalize_intervention_intensity(value: Optional[str]) -> str:
        normalized = (value or "").strip().upper()
        return normalized if normalized in {"LOW", "STANDARD", "HIGH"} else "STANDARD"

    @classmethod
    def _assistant_preference_context(cls, assistant_preferences: Optional[Dict[str, Any]]) -> str:
        if not assistant_preferences:
            return ""

        mode = cls._normalize_chat_mode(assistant_preferences.get("ai_mode"))
        intensity = cls._normalize_intervention_intensity(assistant_preferences.get("intervention_intensity"))
        mode_label = "分析师模式" if mode == "STRICT" else "教练模式"
        mode_note = "更偏结构化风险分析、结论明确、优先给出边界与替代方案。" if mode == "STRICT" else "更偏陪伴式解释与行动鼓励，但不能弱化风险和限制。"
        intensity_label = {
            "LOW": "轻提示",
            "STANDARD": "平衡",
            "HIGH": "强干预",
        }[intensity]
        intensity_note = {
            "LOW": "只在明显风险、缺口或偏离时提醒。",
            "STANDARD": "保持必要提醒，兼顾连续对话体验。",
            "HIGH": "更主动提示风险、趋势和下一步行动。",
        }[intensity]
        return (
            f"- 对话模式：{mode_label}。{mode_note}\n"
            f"- 干预强度：{intensity_label}。{intensity_note}\n"
            "- 以上仅影响表达方式和提醒频率，不改变本地规则、过敏/AVOID/LIMIT 约束或医疗边界。"
        )

    @staticmethod
    def _message_content_chars(message: Dict[str, Any]) -> int:
        content = message.get("content")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            total = 0
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        total += len(text)
            return total
        return len(str(content or ""))

    def _trim_messages_to_prompt_budget(
        self,
        system_message: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        prompt_limit = max(settings.chat_prompt_max_chars, len(system_message["content"]))
        remaining = prompt_limit - len(system_message["content"])
        if remaining <= 0:
            return []

        kept: list[Dict[str, Any]] = []
        used = 0
        for message in reversed(messages):
            chars = self._message_content_chars(message)
            if kept and used + chars > remaining:
                break
            if chars > remaining and not kept:
                content = str(message.get("content") or "")
                kept.append({**message, "content": content[-remaining:]})
                used = remaining
                break
            kept.append(message)
            used += chars
        kept.reverse()
        return kept

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        user: User,
        conditions: List[HealthCondition],
        stream: bool = False,
        assistant_preferences: Optional[Dict[str, Any]] = None,
        local_guardrail: Optional[str] = None,
        metrics: Optional[dict[str, Any]] = None,
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

        prompt_start = time.perf_counter()
        user_context = self._build_user_context(user, conditions)
        prompt = SYSTEM_PROMPT.format(user_context=user_context)
        assistant_preference_context = self._assistant_preference_context(assistant_preferences)
        if assistant_preference_context:
            prompt = (
                f"{prompt}\n\n"
                "## 用户对话偏好\n"
                f"{assistant_preference_context}"
            )
        if local_guardrail:
            prompt = (
                f"{prompt}\n\n"
                "## 七、本地规则与知识库优先约束\n"
                f"{local_guardrail}\n"
                "- 若本地命中 LIMIT 或 AVOID，绝不可放宽结论。\n"
                "- 你只能解释原因、补充替代建议或说明适用条件。"
            )
        system_message = {"role": "system", "content": prompt}

        trimmed_messages = self._trim_messages_to_prompt_budget(system_message, messages)
        full_messages = [system_message] + trimmed_messages
        if metrics is not None:
            metrics["prompt_build_ms"] = round((time.perf_counter() - prompt_start) * 1000, 2)
            metrics["prompt_chars"] = sum(self._message_content_chars(message) for message in full_messages)
            metrics["message_count"] = len(full_messages)

        if stream:
            return self._stream_chat(full_messages, metrics=metrics)
        else:
            return await self._sync_chat(full_messages, metrics=metrics)

    async def _sync_chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        metrics: Optional[dict[str, Any]] = None,
    ) -> str:
        """同步对话"""
        if metrics is not None:
            metrics["max_tokens"] = settings.doubao_chat_max_tokens
        return await self.generate_text(
            messages,
            temperature=0.7,
            max_tokens=settings.doubao_chat_max_tokens,
            metrics=metrics,
        )

    async def _stream_chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        metrics: Optional[dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """流式对话"""
        start = time.perf_counter()
        response_chars = 0
        first_chunk_seen = False
        if metrics is not None:
            metrics["max_tokens"] = settings.doubao_chat_max_tokens
        try:
            stream = await asyncio.to_thread(
                self._create_chat_completion,
                messages=messages,
                temperature=0.7,
                max_tokens=settings.doubao_chat_max_tokens,
                stream=True
            )

            while True:
                content = await asyncio.to_thread(self._next_stream_content, stream)
                if content is None:
                    break
                if not content:
                    continue
                response_chars += len(content)
                if content and not first_chunk_seen:
                    first_chunk_seen = True
                    if metrics is not None:
                        metrics["doubao_first_chunk_ms"] = round((time.perf_counter() - start) * 1000, 2)
                yield content
            if metrics is not None:
                metrics.setdefault("doubao_first_chunk_ms", None)
                metrics["doubao_total_ms"] = round((time.perf_counter() - start) * 1000, 2)
                metrics["response_chars"] = response_chars
        except Exception as e:
            logger.warning("Doubao streaming chat request failed", extra={"error_type": e.__class__.__name__})
            if metrics is not None:
                metrics.setdefault("doubao_first_chunk_ms", None)
                metrics["doubao_total_ms"] = round((time.perf_counter() - start) * 1000, 2)
                metrics["response_chars"] = response_chars
                metrics["doubao_error"] = e.__class__.__name__
            raise RuntimeError(self._format_cloud_error(e)) from e

    @staticmethod
    def _next_stream_content(stream) -> Optional[str]:
        try:
            chunk = next(stream)
        except StopIteration:
            return None
        if chunk.choices and chunk.choices[0].delta.content:
            return chunk.choices[0].delta.content
        return ""

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
        user_prompt: Optional[str] = None,
        fast: bool = False,
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
        user_prompt_block = (user_prompt or "").strip()
        user_prompt_section = f"\n用户随图片补充的提示词：{user_prompt_block}\n请优先结合这段提示词理解图片，例如食材名称、份量、烹饪方式、用户想重点分析的问题。" if user_prompt_block else ""

        if fast:
            recognition_prompt = f"""识别图片中的食物，并只返回可解析 JSON，不要输出 Markdown。

{allergy_warning}{user_prompt_section}

JSON 格式：
{{
  "foods": [
    {{
      "food_name": "食物名称",
      "confidence": 0.0,
      "estimated_portion": "约150g/1份",
      "amount_text": "约150g/1份",
      "ingredients": ["主要食材"],
      "cooking_method": "清蒸/清炒/油炸/未知",
      "nutrition": {{
        "calories": 0,
        "sodium": 0,
        "purine": 0,
        "protein": null,
        "carbs": null,
        "fat": null,
        "fiber": null,
        "sugar": null
      }},
      "category": "STAPLE/MEAT/VEG/DRINK/SNACK",
      "allergen_tags": [],
      "risk_tags": [],
      "health_tips": "一句话建议",
      "warnings": []
    }}
  ],
  "ai_response": "一句话总体评价"
}}

用户健康档案：
{user_context}
"""
        else:
            recognition_prompt = f"""请仔细分析这张食物图片，识别其中的所有食物，并提供详细的营养分析。

{allergy_warning}{user_prompt_section}

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
                temperature=0.2 if fast else 0.3,
                max_tokens=settings.doubao_vision_fast_max_tokens if fast else settings.doubao_vision_max_tokens,
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
            logger.warning("Doubao food recognition request failed", extra={"error_type": e.__class__.__name__})
            return [], f"食物识别失败：{self._format_cloud_error(e)}"


# 单例实例
doubao_service = DoubaoAIService()
