"""
AI 对话相关 Pydantic Schema
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.models.chat import MessageRole


# ==================== 请求 Schema ====================

class ChatMessageCreate(BaseModel):
    """发送聊天消息请求"""
    content: str = Field(..., max_length=4000, description="消息内容")
    attachments: Optional[Dict[str, Any]] = Field(None, description="附件信息")


class ChatSessionCreate(BaseModel):
    """创建对话会话请求"""
    title: Optional[str] = Field("新对话", max_length=200)


class FoodRecognitionRequest(BaseModel):
    """食物识别请求"""
    image_base64: str = Field(..., description="Base64编码的图片")
    image_type: str = Field("jpeg", description="图片类型(jpeg/png)")


# ==================== 响应 Schema ====================

class ChatMessageResponse(BaseModel):
    """聊天消息响应"""
    id: int
    role: MessageRole
    content: str
    attachments: Optional[Dict[str, Any]] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChatSessionResponse(BaseModel):
    """对话会话响应"""
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    
    class Config:
        from_attributes = True


class ChatSessionDetailResponse(BaseModel):
    """对话会话详情响应（含消息列表）"""
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageResponse]
    
    class Config:
        from_attributes = True


class NutritionInfo(BaseModel):
    """营养成分信息"""
    calories: float = Field(description="热量(kcal)")
    sodium: float = Field(description="钠(mg)")
    purine: float = Field(description="嘌呤(mg)")
    protein: Optional[float] = Field(None, description="蛋白质(g)")
    carbs: Optional[float] = Field(None, description="碳水化合物(g)")
    fat: Optional[float] = Field(None, description="脂肪(g)")
    fiber: Optional[float] = Field(None, description="膳食纤维(g)")


class FoodRecognitionResult(BaseModel):
    """食物识别结果"""
    food_name: str = Field(description="识别出的食物名称")
    confidence: float = Field(description="识别置信度(0-1)")
    estimated_portion: str = Field(description="估算份量")
    nutrition: NutritionInfo = Field(description="营养成分")
    category: str = Field(description="食物分类")
    health_tips: Optional[str] = Field(None, description="健康提示")
    warnings: List[str] = Field(default_factory=list, description="针对用户健康状况的警告")


class FoodRecognitionResponse(BaseModel):
    """食物识别响应"""
    success: bool
    foods: List[FoodRecognitionResult] = Field(default_factory=list)
    ai_response: str = Field(description="AI的对话式回复")
    image_url: Optional[str] = Field(None, description="上传图片的URL")


class AIStreamChunk(BaseModel):
    """AI流式响应块"""
    content: str
    is_finished: bool = False
    tokens_used: Optional[int] = None
