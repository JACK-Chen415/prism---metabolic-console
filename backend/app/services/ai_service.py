"""
豆包 AI 服务封装
包含对话和视觉识别功能
"""

import json
import base64
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator, Union

from app.core.config import settings
from app.models.user import User
from app.models.health_condition import HealthCondition
from app.schemas.chat import NutritionInfo, FoodRecognitionResult


# 系统提示词：健康顾问角色
SYSTEM_PROMPT = """你是「食鉴AI」，一位专业、可靠的智能健康饮食顾问。你融合了现代营养科学与大数据分析能力，为用户提供精准的饮食指导。

## 核心职责
1. 基于用户的健康档案（慢性病、过敏史、身体参数）提供个性化饮食建议
2. 分析用户的饮食记录，给出优化建议
3. 回答健康饮食相关问题
4. 识别食物图片并分析营养成分

## 沟通风格
- 使用文雅但不晦涩的语言
- 偶尔引用古籍养生名言
- 给出建议时要具体可执行
- 对危险食物搭配给予明确警告

## 注意事项
- 你不是医生，不能给出医疗诊断或处方
- 对于严重健康问题，建议用户咨询专业医生
- 所有建议仅供参考，需根据个人情况调整

## 用户健康档案
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
    
    def _build_user_context(
        self,
        user: User,
        conditions: List[HealthCondition]
    ) -> str:
        """构建用户健康上下文"""
        context_parts = []
        
        # 基本信息
        if user.gender and user.age and user.height and user.weight:
            gender_str = "男" if user.gender.value == "MALE" else "女"
            context_parts.append(
                f"- 基本信息：{gender_str}，{user.age}岁，身高{user.height}cm，体重{user.weight}kg"
            )
        
        # 健康状况
        chronic_conditions = [c for c in conditions if c.condition_type.value == "CHRONIC"]
        allergies = [c for c in conditions if c.condition_type.value == "ALLERGY"]
        
        if chronic_conditions:
            chronic_str = "、".join([c.title for c in chronic_conditions])
            context_parts.append(f"- 慢性病史：{chronic_str}")
        
        if allergies:
            allergy_str = "、".join([c.title for c in allergies])
            context_parts.append(f"- 过敏源：{allergy_str}（严格禁止！）")
        
        if not context_parts:
            return "用户尚未完善健康档案"
        
        return "\n".join(context_parts)
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        user: User,
        conditions: List[HealthCondition],
        stream: bool = False
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
        system_message = {
            "role": "system",
            "content": SYSTEM_PROMPT.format(user_context=user_context)
        }
        
        full_messages = [system_message] + messages
        
        if stream:
            return self._stream_chat(full_messages)
        else:
            return await self._sync_chat(full_messages)
    
    async def _sync_chat(self, messages: List[Dict[str, str]]) -> str:
        """同步对话"""
        try:
            response = self.client.chat.completions.create(
                model=settings.doubao_endpoint_id,
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"抱歉，服务暂时不可用：{str(e)}"
    
    async def _stream_chat(
        self,
        messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        """流式对话"""
        try:
            stream = self.client.chat.completions.create(
                model=settings.doubao_endpoint_id,
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"抱歉，服务暂时不可用：{str(e)}"
    
    async def recognize_food(
        self,
        image_base64: str,
        user: User,
        conditions: List[HealthCondition]
    ) -> tuple[List[FoodRecognitionResult], str]:
        """
        识别食物图片
        
        Args:
            image_base64: Base64 编码的图片
            user: 当前用户
            conditions: 用户健康状况
        
        Returns:
            (识别结果列表, AI 对话式回复)
        """
        await self._ensure_initialized()
        
        user_context = self._build_user_context(user, conditions)
        
        # 获取过敏源列表用于警告
        allergies = [c.title for c in conditions if c.condition_type.value == "ALLERGY"]
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
            "nutrition": {{
                "calories": 热量(kcal),
                "sodium": 钠含量(mg),
                "purine": 嘌呤含量(mg),
                "protein": 蛋白质(g),
                "carbs": 碳水化合物(g),
                "fat": 脂肪(g),
                "fiber": 膳食纤维(g)
            }},
            "category": "STAPLE/MEAT/VEG/DRINK/SNACK",
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
            response = self.client.chat.completions.create(
                model=settings.doubao_vision_endpoint_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": recognition_prompt
                            }
                        ]
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # 尝试解析 JSON
            try:
                # 移除可能的 markdown 代码块标记
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                result = json.loads(content.strip())
                
                foods = [
                    FoodRecognitionResult(
                        food_name=f["food_name"],
                        confidence=f.get("confidence", 0.8),
                        estimated_portion=f["estimated_portion"],
                        nutrition=NutritionInfo(**f["nutrition"]),
                        category=f["category"],
                        health_tips=f.get("health_tips"),
                        warnings=f.get("warnings", [])
                    )
                    for f in result.get("foods", [])
                ]
                
                ai_response = result.get("ai_response", "识别完成，请查看营养分析。")
                
                return foods, ai_response
                
            except json.JSONDecodeError:
                # JSON 解析失败，返回原始文本
                return [], content
                
        except Exception as e:
            return [], f"食物识别失败：{str(e)}"


# 单例实例
doubao_service = DoubaoAIService()
