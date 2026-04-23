import React, { useState, useRef, useEffect } from 'react';
import { View } from '../../types';
import { ChatAPI, TokenManager } from '../../services/api';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { clearChatSessionId, consumeFoodScanResult, getChatSessionId, setChatSessionId } from '../../services/sessionState';

// 配置 marked：启用换行符支持，关闭不需要的功能
marked.setOptions({
  breaks: true,
  gfm: true,
});

// Markdown 渲染辅助函数
const renderMarkdown = (content: string): string => {
  try {
    const raw = marked.parse(content) as string;
    return DOMPurify.sanitize(raw);
  } catch {
    return DOMPurify.sanitize(content);
  }
};

const escapeText = (text: string): string => {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

interface ChatViewProps {
  onViewChange: (view: View) => void;
  onMealLogged?: () => void;
}

type MessageRole = 'USER' | 'AI' | 'SYSTEM';

interface Message {
  id: string;
  role: MessageRole;
  content: string;
  image?: string;
  // Specific properties for styling different AI personas
  aiMode?: 'GENTLE' | 'STRICT';
  aiName?: string;
  recognizedFoods?: RecognizedFood[];
  timestamp: number;
}

interface RecognizedFood {
  food_name: string;
  estimated_portion: string;
  category: string;
  nutrition: {
    calories: number;
    sodium: number;
    purine: number;
    protein?: number;
    carbs?: number;
    fat?: number;
    fiber?: number;
  };
}

interface RecognitionResponse {
  foods?: RecognizedFood[];
  ai_response?: string;
}

const ChatView: React.FC<ChatViewProps> = ({ onViewChange, onMealLogged }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [currentMode, setCurrentMode] = useState<'STRICT' | 'GENTLE'>('STRICT');
  const [sessionId, setSessionId] = useState<number | null>(() => {
    return getChatSessionId();
  });
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 创建或恢复会话，加载历史消息
  useEffect(() => {
    const initSession = async () => {
      if (!TokenManager.isAuthenticated()) return;

      // 1. 尝试复用已有会话
      const savedId = getChatSessionId();
      if (savedId) {
        try {
          setIsLoadingHistory(true);
          const session = await ChatAPI.getSession(savedId) as any;
          setSessionId(session.id);
          // 后端消息格式 → 前端 Message 格式
          const loadedMsgs: Message[] = (session.messages || []).map((m: any) => {
            const role = (m.role || '').toUpperCase(); // 后端返回小写 'user'/'assistant'
            const isUser = role === 'USER';
            return {
              id: m.id.toString(),
              role: isUser ? 'USER' as MessageRole : 'AI' as MessageRole,
              content: m.content,
              aiMode: !isUser ? 'STRICT' as const : undefined,
              aiName: !isUser ? '食鉴AI' : undefined,
              timestamp: new Date(m.created_at).getTime(),
            };
          });
          setMessages(loadedMsgs);
          setIsLoadingHistory(false);
          return;
        } catch {
          // 会话不存在或失效，清除并创建新的
          clearChatSessionId();
          setIsLoadingHistory(false);
        }
      }

      // 2. 创建新会话
      try {
        const res = await ChatAPI.createSession('食鉴AI对话') as any;
        if (res?.id) {
          setSessionId(res.id);
          setChatSessionId(res.id);
        }
      } catch (err) {
        console.error('创建会话失败:', err);
      }
    };
    initSession();
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  // Helper for time formatting
  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    // Format: 下午 6:42
    const timeStr = date.toLocaleTimeString('zh-CN', { hour: 'numeric', minute: '2-digit', hour12: true });

    if (isToday) {
      return `今天 ${timeStr}`;
    }
    // Simple date for non-today
    return `${date.getMonth() + 1}月${date.getDate()}日 ${timeStr}`;
  };

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const result = consumeFoodScanResult<RecognitionResponse>();
    if (!result) return;
      const foods = result.foods || [];
      const content = result.ai_response || '已识别食物图片，正在分析营养成分。';
      const aiMsg: Message = {
        id: Date.now().toString(),
        role: 'AI',
        aiMode: currentMode,
        aiName: '食鉴AI',
        content,
        recognizedFoods: foods,
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, aiMsg]);
  }, [currentMode]);

  const handleGalleryClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];

      // 显示用户上传的图片消息
      const imageUrl = URL.createObjectURL(file);
      const userMsg: Message = {
        id: Date.now().toString(),
        role: 'USER',
        content: '请识别这张食物图片',
        image: imageUrl,
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, userMsg]);

      // 调用食物识别API
      if (TokenManager.isAuthenticated()) {
        setIsSending(true);
        try {
          const result = await ChatAPI.recognizeFoodUpload(file) as RecognitionResponse;
          const aiMsg: Message = {
            id: (Date.now() + 1).toString(),
            role: 'AI',
            aiMode: currentMode,
            aiName: '食鉴AI',
            content: result?.ai_response || '已识别食物图片，正在分析营养成分...',
            recognizedFoods: result?.foods || [],
            timestamp: Date.now()
          };
          setMessages(prev => [...prev, aiMsg]);
        } catch (error) {
          console.error('食物识别失败:', error);
          const errorMsg: Message = {
            id: (Date.now() + 1).toString(),
            role: 'AI',
            aiMode: currentMode,
            aiName: '食鉴AI',
            content: '抱歉，食物识别服务暂时不可用。',
            timestamp: Date.now()
          };
          setMessages(prev => [...prev, errorMsg]);
        } finally {
          setIsSending(false);
        }
      }
    }
  };

  const handleModeSwitch = (mode: 'STRICT' | 'GENTLE') => {
    if (mode === currentMode) return;
    setCurrentMode(mode);
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'SYSTEM',
      content: `聊天风格已切换：${mode === 'STRICT' ? '分析师模式' : '教练模式'}`,
      timestamp: Date.now()
    }]);
  };

  const startListening = () => {
    if (isListening) return;

    // Check for browser support
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      // @ts-ignore
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();

      recognition.lang = 'zh-CN';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setInputValue(prev => prev ? prev + ' ' + transcript : transcript);
        setIsListening(false);
      };

      recognition.onerror = (event: any) => {
        console.error('Speech recognition error', event.error);
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
    } else {
      alert('您的浏览器暂不支持语音识别功能。');
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isSending) return;

    // 1. 添加用户消息
    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: 'USER',
      content: inputValue,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, newUserMsg]);
    const currentInput = inputValue;
    setInputValue('');
    setIsSending(true);

    // 2. 调用后端AI或降级到本地模拟
    if (TokenManager.isAuthenticated() && sessionId) {
      try {
        const response = await ChatAPI.sendMessage(sessionId, currentInput) as any;
        const aiContent = response?.ai_message?.content || response?.content || `已收到您的消息："${currentInput}"。`;
        const newAiMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: aiContent,
          timestamp: Date.now()
        };
        setMessages(prev => [...prev, newAiMsg]);
      } catch (error) {
        console.error('发送消息失败:', error);
        // 降级：显示错误提示
        const errorMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: '抱歉，AI服务暂时不可用，请稍后重试。',
          timestamp: Date.now()
        };
        setMessages(prev => [...prev, errorMsg]);
      } finally {
        setIsSending(false);
      }
    } else {
      // 游客模式：本地模拟
      setTimeout(() => {
        const newAiMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: `收到，已识别您的输入："${currentInput}"。请登录后体验完整AI分析功能。`,
          timestamp: Date.now()
        };
        setMessages(prev => [...prev, newAiMsg]);
        setIsSending(false);
      }, 800);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // textarea 自动增高
  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'; // 最大约4行
  };

  const handleQuickLog = async (food: RecognizedFood) => {
    if (!TokenManager.isAuthenticated()) return;
    try {
      const hour = new Date().getHours();
      const mealType = hour < 10 ? 'BREAKFAST' : hour < 14 ? 'LUNCH' : hour < 21 ? 'DINNER' : 'SNACK';
      await ChatAPI.quickLog(food, mealType, sessionId || undefined);
      await onMealLogged?.();
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'SYSTEM',
        content: `已记入${mealType === 'BREAKFAST' ? '早餐' : mealType === 'LUNCH' ? '午餐' : mealType === 'DINNER' ? '晚餐' : '加餐'}：${food.food_name}`,
        timestamp: Date.now()
      }]);
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'SYSTEM',
        content: `记日志失败：${error instanceof Error ? error.message : '未知错误'}`,
        timestamp: Date.now()
      }]);
    }
  };

  return (
    <div className="flex flex-col w-full min-h-[calc(100vh-100px)]">
      {/* Hidden File Input */}
      <input
        type="file"
        accept="image/*"
        className="hidden"
        ref={fileInputRef}
        onChange={handleFileChange}
      />

      {/* Header */}
      <div className="sticky top-0 z-20 flex items-center justify-between p-4 bg-background-dark/95 backdrop-blur border-b border-white/5">
        <button
          onClick={() => onViewChange(View.HOME)}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors"
        >
          <span className="material-symbols-outlined text-white">arrow_back</span>
        </button>
        <h2 className="text-lg font-bold text-white font-serif tracking-wide">食鉴AI</h2>
        <button
          onClick={() => onViewChange(View.SETTINGS)}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors"
        >
          <span className="material-symbols-outlined text-white">settings</span>
        </button>
      </div>

      {/* Mode Switcher */}
      <div className="px-4 py-3">
        <div className="flex rounded-xl bg-surface-dark border border-white/10 p-1">
          <button
            onClick={() => handleModeSwitch('STRICT')}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors font-serif tracking-wide ${currentMode === 'STRICT' ? 'bg-primary/10 text-primary font-bold shadow-sm' : 'text-slate-400 hover:bg-white/5'}`}
          >
            <span className="material-symbols-outlined text-sm">shield</span>
            分析师
          </button>
          <button
            onClick={() => handleModeSwitch('GENTLE')}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors font-serif tracking-wide ${currentMode === 'GENTLE' ? 'bg-primary/10 text-primary font-bold shadow-sm' : 'text-slate-400 hover:bg-white/5'}`}
          >
            <span className="material-symbols-outlined text-sm">spa</span>
            教练
          </button>
        </div>
      </div>

      <div className="flex-1 p-4 pb-28 flex flex-col gap-5">

        {messages.map((msg, index) => {
          const prevMsg = messages[index - 1];
          // Show timestamp if first message or if time difference > 5 minutes (300000ms)
          const showTimestamp = !prevMsg || (msg.timestamp - prevMsg.timestamp > 5 * 60 * 1000);

          return (
            <React.Fragment key={msg.id}>
              {showTimestamp && (
                <div className="text-center text-xs text-slate-500 my-4 font-serif font-bold tracking-wide">
                  {formatTime(msg.timestamp)}
                </div>
              )}

              {msg.role === 'SYSTEM' && (
                <div className="flex justify-center my-2 animate-fade-in">
                  <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-surface-dark border border-white/5">
                    <span className="material-symbols-outlined text-primary text-sm">compare_arrows</span>
                    <span className="text-xs text-primary/80 font-serif tracking-wide">{msg.content}</span>
                  </div>
                </div>
              )}

              {msg.role === 'USER' && (
                <div className="flex gap-2.5 flex-row-reverse animate-fade-in">
                  <div className="w-8 h-8 rounded-full bg-ochre/20 flex items-center justify-center shrink-0 border border-ochre/30 overflow-hidden mt-0.5">
                    <img src="/images/user-avatar.png" alt="User" className="w-full h-full object-cover" />
                  </div>
                  <div className="flex flex-col gap-1 items-end max-w-[85%]">
                    <div className="bg-white/10 border border-white/5 rounded-xl rounded-tr-none px-3.5 py-2.5 text-white text-sm leading-relaxed font-serif tracking-wide whitespace-pre-wrap break-words">
                      {msg.content}
                    </div>
                    {msg.image && (
                      <div className="rounded-xl overflow-hidden border border-white/10 w-48 h-32 relative mt-1">
                        <img src={msg.image} className="absolute inset-0 w-full h-full object-cover opacity-60" alt="Attachment" />
                      </div>
                    )}
                  </div>
                </div>
              )}

              {msg.role === 'AI' && (
                <div className="flex gap-2.5 animate-fade-in">
                  <div className={`w-8 h-8 rounded-full bg-surface-dark flex items-center justify-center shrink-0 mt-0.5 ${msg.aiMode === 'STRICT' ? 'border border-white/10 shadow-[0_0_10px_rgba(17,196,212,0.5)]' : 'border border-white/10 shadow-glow-cyan'}`}>
                    {msg.aiMode === 'STRICT' ? (
                      <span className="material-symbols-outlined text-primary text-sm">security</span>
                    ) : (
                      <div className="w-4 h-4 rounded-full border border-primary"></div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1 max-w-[85%]">
                    <span className={`text-xs ml-1 font-bold tracking-wide ${msg.aiMode === 'STRICT' ? 'text-primary font-serif' : 'text-slate-400 font-serif'}`}>{msg.aiName}</span>
                    <div
                      className={`rounded-xl rounded-tl-none px-3.5 py-2.5 text-white text-sm leading-relaxed shadow-sm font-serif tracking-wide ${msg.aiMode === 'STRICT'
                        ? 'bg-[#0f282d] border border-primary/20'
                        : 'bg-surface-dark border border-white/5'
                        }`}
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                    />
                    {msg.recognizedFoods && msg.recognizedFoods.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {msg.recognizedFoods.slice(0, 3).map((food, idx) => (
                          <button
                            key={`${food.food_name}-${idx}`}
                            onClick={() => handleQuickLog(food)}
                            className="px-2 py-1 rounded-lg text-xs bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 transition-colors"
                          >
                            记日志: {food.food_name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </React.Fragment>
          );
        })}

        {/* AI 思考中提示 */}
        {isSending && (
          <div className="flex gap-2.5 animate-fade-in">
            <div className={`w-8 h-8 rounded-full bg-surface-dark flex items-center justify-center shrink-0 mt-0.5 ${currentMode === 'STRICT' ? 'border border-white/10 shadow-[0_0_10px_rgba(17,196,212,0.5)]' : 'border border-white/10 shadow-glow-cyan'}`}>
              {currentMode === 'STRICT' ? (
                <span className="material-symbols-outlined text-primary text-sm">security</span>
              ) : (
                <div className="w-4 h-4 rounded-full border border-primary"></div>
              )}
            </div>
            <div className="flex flex-col gap-1 max-w-[85%]">
              <span className={`text-xs ml-1 font-bold tracking-wide ${currentMode === 'STRICT' ? 'text-primary font-serif' : 'text-slate-400 font-serif'}`}>食鉴AI</span>
              <div className={`rounded-xl rounded-tl-none px-4 py-3 text-sm leading-relaxed shadow-sm font-serif tracking-wide flex items-center gap-2 ${currentMode === 'STRICT' ? 'bg-[#0f282d] border border-primary/20' : 'bg-surface-dark border border-white/5'}`}>
                <div className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary/80 animate-bounce" style={{ animationDelay: '0ms', animationDuration: '1.2s' }}></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: '200ms', animationDuration: '1.2s' }}></span>
                  <span className="w-1.5 h-1.5 rounded-full bg-primary/40 animate-bounce" style={{ animationDelay: '400ms', animationDuration: '1.2s' }}></span>
                </div>
                <span className="text-white/50 text-xs tracking-wider">思考中...</span>
              </div>
            </div>
          </div>
        )}

        {/* Invisible element to scroll to */}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="sticky bottom-24 px-4 pb-2 z-30">
        <div className="flex items-center justify-start px-1 mb-2 gap-2">
          <button
            onClick={() => setInputValue("请基于我今天已记录的饮食和健康档案，说明当前需要注意的风险点和下一餐原则。")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#131b1d]/90 border border-white/10 backdrop-blur text-xs text-slate-300 hover:text-white hover:border-primary/40 hover:bg-[#162224] transition-all active:scale-95 shadow-lg group"
          >
            <div className="w-5 h-5 rounded-md bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
              <span className="material-symbols-outlined text-[14px] text-primary">assignment</span>
            </div>
            <span className="font-bold font-serif tracking-wide">今日风险解读</span>
          </button>

          <button
            onClick={() => setInputValue("一日三餐吃什么？")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#131b1d]/90 border border-white/10 backdrop-blur text-xs text-slate-300 hover:text-white hover:border-ochre/40 hover:bg-[#162224] transition-all active:scale-95 shadow-lg group"
          >
            <div className="w-5 h-5 rounded-md bg-ochre/10 flex items-center justify-center group-hover:bg-ochre/20 transition-colors">
              <span className="material-symbols-outlined text-[14px] text-ochre">restaurant_menu</span>
            </div>
            <span className="font-bold font-serif tracking-wide">一日三餐吃什么？</span>
          </button>
        </div>

        <div className="flex items-end gap-2 p-1.5 bg-surface-dark border border-white/10 rounded-2xl shadow-lg">
          <button
            onClick={handleGalleryClick}
            className="w-10 h-10 flex items-center justify-center text-slate-400 hover:text-white transition-colors shrink-0"
          >
            <span className="material-symbols-outlined">add_photo_alternate</span>
          </button>
          <textarea
            value={inputValue}
            onChange={handleTextareaInput}
            onKeyDown={handleKeyDown}
            placeholder={isListening ? "正在聆听..." : "咨询关于您的代谢健康..."}
            rows={1}
            className={`flex-1 bg-transparent border-none outline-none text-white placeholder-slate-500 text-sm focus:ring-0 caret-primary font-serif tracking-wide font-bold resize-none max-h-[120px] py-2.5 ${isListening ? 'animate-pulse' : ''}`}
          />
          <button
            onClick={startListening}
            disabled={isListening}
            className={`w-10 h-10 flex items-center justify-center transition-all duration-300 ${isListening ? 'text-primary scale-110' : 'text-slate-400 hover:text-white'}`}
          >
            <span className="material-symbols-outlined">mic</span>
          </button>
          <button
            onClick={handleSendMessage}
            className={`w-10 h-10 flex items-center justify-center rounded-full font-bold transition-all duration-300 ${inputValue.trim() ? 'bg-primary text-background-dark hover:bg-primary/90' : 'bg-white/10 text-white/20'}`}
            disabled={!inputValue.trim() || isSending}
          >
            <span className="material-symbols-outlined">arrow_upward</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatView;
