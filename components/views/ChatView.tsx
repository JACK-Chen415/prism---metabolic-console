import React, { useState, useRef, useEffect } from 'react';
import { View } from '../../types';

interface ChatViewProps {
  onViewChange: (view: View) => void;
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
  timestamp: number;
}

// Initial time reference for demo purposes
const NOW = Date.now();

const INITIAL_MESSAGES: Message[] = [
  {
    id: '3',
    role: 'SYSTEM',
    content: '聊天风格已切换：严格模式',
    timestamp: NOW - 1000 * 60 * 30 // 30 minutes ago
  },
  {
    id: '4',
    role: 'AI',
    aiMode: 'STRICT',
    aiName: '食鉴AI',
    content: '正在切换协议。请立即上传菜单照片。<span class="text-primary font-bold">绝对禁止点油条。</span>',
    timestamp: NOW - 1000 * 60 * 29 // 29 minutes ago
  },
  {
    id: '5',
    role: 'USER',
    content: '明白了，这是菜单。',
    image: '/images/menu-sample.png',
    timestamp: NOW - 1000 * 60 * 2 // 2 minutes ago
  }
];

const ChatView: React.FC<ChatViewProps> = ({ onViewChange }) => {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [currentMode, setCurrentMode] = useState<'STRICT' | 'GENTLE'>('STRICT');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

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

  // Check for auto-send message from other views (e.g. Health Archives)
  useEffect(() => {
    const autoMsg = sessionStorage.getItem('PRISM_AUTO_SEND_MESSAGE');
    if (autoMsg) {
      sessionStorage.removeItem('PRISM_AUTO_SEND_MESSAGE');
      
      // Add User Message
      const userMsg: Message = {
        id: Date.now().toString(),
        role: 'USER',
        content: autoMsg.replace(/\n/g, '<br/>'), // Simple formatting for display
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, userMsg]);

      // Trigger AI Response
      setTimeout(() => {
        const aiMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: 'STRICT',
          aiName: '食鉴AI',
          content: `已深度分析您的 ${autoMsg.match(/【.*?】/g)?.length || 3} 份体检档案。
          <br/><br/>
          <strong class="text-primary">趋势解读：</strong><br/>
          1. <strong>尿酸控制成效显著</strong>：从 480 降至 342 μmol/L，已回到安全区间。这表明您当前的低嘌呤饮食策略（如减少海鲜摄入）非常成功。<br/>
          2. <strong>血脂风险浮现</strong>：虽然尿酸改善，但甘油三酯近期升至 1.85 mmol/L，提示可能存在"碳水代偿"现象（即少吃肉多吃了主食）。<br/><br/>
          <strong class="text-ochre">干预建议：</strong><br/>
          建议将晚餐主食替换为粗粮（如荞麦面或红薯），并增加抗阻力训练。是否需要为您生成针对甘油三酯控制的一周食谱？`,
          timestamp: Date.now()
        };
        setMessages(prev => [...prev, aiMsg]);
      }, 2500);
    }
  }, []);

  const handleGalleryClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      // Logic to handle selected file (Simulated for now)
      console.log('Selected file:', e.target.files[0]);
    }
  };

  const handleModeSwitch = (mode: 'STRICT' | 'GENTLE') => {
    if (mode === currentMode) return;
    setCurrentMode(mode);
    setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'SYSTEM',
        content: `聊天风格已切换：${mode === 'STRICT' ? '严格模式' : '温柔模式'}`,
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

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;

    // 1. Add User Message
    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: 'USER',
      content: inputValue,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, newUserMsg]);
    const currentInput = inputValue; // Capture for AI response
    setInputValue('');

    // 2. Simulate AI Response
    setTimeout(() => {
      const newAiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'AI',
        aiMode: currentMode, // Keeping consistent context from previous messages
        aiName: '食鉴AI',
        content: `收到，已识别您的输入："${currentInput}"。正在基于您的代谢数据进行风险评估...`,
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, newAiMsg]);
    }, 1000);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSendMessage();
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
            严格
          </button>
          <button 
             onClick={() => handleModeSwitch('GENTLE')}
             className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors font-serif tracking-wide ${currentMode === 'GENTLE' ? 'bg-primary/10 text-primary font-bold shadow-sm' : 'text-slate-400 hover:bg-white/5'}`}
          >
            <span className="material-symbols-outlined text-sm">spa</span>
            温柔
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
                    <div 
                      className="bg-white/10 border border-white/5 rounded-xl rounded-tr-none px-3.5 py-2.5 text-white text-sm leading-relaxed font-serif tracking-wide"
                      dangerouslySetInnerHTML={{ __html: msg.content }}
                    />
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
                      className={`rounded-xl rounded-tl-none px-3.5 py-2.5 text-white text-sm leading-relaxed shadow-sm font-serif tracking-wide ${
                        msg.aiMode === 'STRICT' 
                        ? 'bg-[#0f282d] border border-primary/20' 
                        : 'bg-surface-dark border border-white/5'
                      }`}
                      dangerouslySetInnerHTML={{ __html: msg.content }} // Allow HTML for bolding/coloring
                    />
                  </div>
                </div>
              )}
            </React.Fragment>
          );
        })}
        
        {/* Invisible element to scroll to */}
        <div ref={messagesEndRef} />
      </div>
        
      {/* Input Area */}
      <div className="sticky bottom-24 px-4 pb-2 z-30">
        <div className="flex items-center justify-start px-1 mb-2 gap-2">
            <button 
                onClick={() => setInputValue("生成体检报告")}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#131b1d]/90 border border-white/10 backdrop-blur text-xs text-slate-300 hover:text-white hover:border-primary/40 hover:bg-[#162224] transition-all active:scale-95 shadow-lg group"
            >
                <div className="w-5 h-5 rounded-md bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                    <span className="material-symbols-outlined text-[14px] text-primary">assignment</span>
                </div>
                <span className="font-bold font-serif tracking-wide">生成体检报告</span>
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

        <div className="flex items-center gap-2 p-1.5 bg-surface-dark border border-white/10 rounded-full shadow-lg">
            <button 
                onClick={handleGalleryClick}
                className="w-10 h-10 flex items-center justify-center text-slate-400 hover:text-white transition-colors"
            >
                <span className="material-symbols-outlined">add_photo_alternate</span>
            </button>
            <input 
                type="text" 
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isListening ? "正在聆听..." : "咨询关于您的代谢健康..."} 
                className={`flex-1 bg-transparent border-none outline-none text-white placeholder-slate-500 text-sm focus:ring-0 caret-primary font-serif tracking-wide font-bold ${isListening ? 'animate-pulse' : ''}`}
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
                disabled={!inputValue.trim()}
            >
                <span className="material-symbols-outlined">arrow_upward</span>
            </button>
        </div>
      </div>
    </div>
  );
};

export default ChatView;