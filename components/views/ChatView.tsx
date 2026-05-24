import React, { useState, useRef, useEffect } from 'react';
import { ChatStreamEvent, IntakeCandidate, IntakeDraftSession, KnowledgeFallbackStatus, KnowledgeOrigin, View } from '../../types';
import { ChatAPI, IntakeAPI, TokenManager } from '../../services/api';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { clearChatSessionId, getChatSessionId, setChatSessionId } from '../../services/sessionState';
import IntakeConfirmationSheet from '../intake/IntakeConfirmationSheet';

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

interface ChatViewProps {
  onViewChange: (view: View) => void;
  onMealLogged?: (recordDate?: string) => void | Promise<void>;
  pendingIntakeSession: IntakeDraftSession | null;
  onPendingIntakeSessionChange: (session: IntakeDraftSession | null) => void;
}

type MessageRole = 'USER' | 'AI' | 'SYSTEM';

interface Message {
  id: string;
  serverId?: number;
  role: MessageRole;
  content: string;
  image?: string;
  aiMode?: 'GENTLE' | 'STRICT';
  aiName?: string;
  recognizedFoods?: RecognizedFood[];
  attachments?: Record<string, unknown>;
  origin?: KnowledgeOrigin;
  fallbackStatus?: KnowledgeFallbackStatus;
  statusText?: string;
  isStreaming?: boolean;
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

interface PendingImage {
  file: File;
  url: string;
}

interface PendingTextClarification {
  contextText: string;
  latestFollowUpPrompt: string;
}

const ChatView: React.FC<ChatViewProps> = ({
  onViewChange,
  onMealLogged,
  pendingIntakeSession,
  onPendingIntakeSessionChange,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [pendingImage, setPendingImage] = useState<PendingImage | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isParsingIntake, setIsParsingIntake] = useState(false);
  const [explicitTextLogMode, setExplicitTextLogMode] = useState(false);
  const [pendingTextClarification, setPendingTextClarification] = useState<PendingTextClarification | null>(null);
  const [isSubmittingIntake, setIsSubmittingIntake] = useState(false);
  const [intakeError, setIntakeError] = useState<string | null>(null);
  const [reevaluatingDraftIds, setReevaluatingDraftIds] = useState<string[]>([]);
  const [staleEvaluationDraftIds, setStaleEvaluationDraftIds] = useState<string[]>([]);
  const [currentMode, setCurrentMode] = useState<'STRICT' | 'GENTLE'>('STRICT');
  const [sessionId, setSessionId] = useState<number | null>(() => {
    return getChatSessionId();
  });
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingIntakeSessionRef = useRef<IntakeDraftSession | null>(pendingIntakeSession);

  useEffect(() => {
    pendingIntakeSessionRef.current = pendingIntakeSession;

    if (pendingIntakeSession) {
      setPendingTextClarification(null);
    }

    if (!pendingIntakeSession) {
      setReevaluatingDraftIds([]);
      setStaleEvaluationDraftIds([]);
      return;
    }

    const activeDraftIds = new Set(pendingIntakeSession.candidates.map(candidate => candidate.draft_id));
    const keepActiveIds = (ids: string[]) => {
      const nextIds = ids.filter(id => activeDraftIds.has(id));
      return nextIds.length === ids.length ? ids : nextIds;
    };

    setReevaluatingDraftIds(keepActiveIds);
    setStaleEvaluationDraftIds(keepActiveIds);
  }, [pendingIntakeSession]);

  // 创建或恢复会话，加载历史消息
  useEffect(() => {
    const initSession = async () => {
      if (!TokenManager.isAuthenticated()) return;

      const savedId = getChatSessionId();
      if (savedId) {
        try {
          setIsLoadingHistory(true);
          const session = await ChatAPI.getSession(savedId) as any;
          setSessionId(session.id);

          const loadedMsgs: Message[] = (session.messages || []).map((m: any) => {
            const role = (m.role || '').toUpperCase();
            const isUser = role === 'USER';
            return {
              id: m.id.toString(),
              serverId: m.id,
              role: isUser ? 'USER' as MessageRole : 'AI' as MessageRole,
              content: m.content,
              aiMode: !isUser ? 'STRICT' as const : undefined,
              aiName: !isUser ? '食鉴AI' : undefined,
              attachments: m.attachments,
              origin: m.attachments?.knowledge?.origin,
              fallbackStatus: m.attachments?.knowledge?.fallback_status,
              timestamp: new Date(m.created_at).getTime(),
            };
          });

          setMessages(loadedMsgs);
          setIsLoadingHistory(false);
          return;
        } catch {
          clearChatSessionId();
          setIsLoadingHistory(false);
        }
      }

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    const timeStr = date.toLocaleTimeString('zh-CN', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });

    if (isToday) {
      return `今天 ${timeStr}`;
    }

    return `${date.getMonth() + 1}月${date.getDate()}日 ${timeStr}`;
  };

  const getSystemNoticePresentation = (content: string) => {
    if (content.includes('失败')) {
      return {
        icon: 'error',
        label: '系统提醒',
        shellClass: 'border-red-400/15 bg-red-500/5 text-red-100',
        iconClass: 'text-red-300',
        labelClass: 'text-red-300/75',
      };
    }

    if (content.includes('已记入') || content.includes('已生成')) {
      return {
        icon: 'task_alt',
        label: '流程更新',
        shellClass: 'border-emerald-400/15 bg-emerald-500/5 text-emerald-100',
        iconClass: 'text-emerald-300',
        labelClass: 'text-emerald-300/75',
      };
    }

    if (content.includes('切换')) {
      return {
        icon: 'tune',
        label: '模式更新',
        shellClass: 'border-white/10 bg-white/[0.03] text-slate-300',
        iconClass: 'text-slate-400',
        labelClass: 'text-slate-500',
      };
    }

    return {
      icon: 'info',
      label: '系统提示',
      shellClass: 'border-white/10 bg-white/[0.03] text-slate-300',
      iconClass: 'text-slate-400',
      labelClass: 'text-slate-500',
    };
  };

  const formatRecognizedFoodMeta = (food: RecognizedFood) => {
    const nutrition = food.nutrition || {};
    const details = [
      food.estimated_portion,
      nutrition.calories ? `${Math.round(nutrition.calories)} kcal` : '',
      nutrition.sodium ? `钠 ${Math.round(nutrition.sodium)}mg` : '',
      nutrition.purine ? `嘌呤 ${Math.round(nutrition.purine)}mg` : '',
    ].filter(Boolean);

    return details.join(' · ');
  };

  const handleGalleryClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const imageUrl = URL.createObjectURL(file);
    setPendingImage(prev => {
      if (prev) {
        URL.revokeObjectURL(prev.url);
      }
      return { file, url: imageUrl };
    });
    e.target.value = '';
  };

  const clearPendingImage = () => {
    setPendingImage(prev => {
      if (prev) {
        URL.revokeObjectURL(prev.url);
      }
      return null;
    });
  };

  const handleModeSwitch = (mode: 'STRICT' | 'GENTLE') => {
    if (mode === currentMode) return;

    setCurrentMode(mode);
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'SYSTEM',
      content: `聊天风格已切换：${mode === 'STRICT' ? '分析师模式' : '教练模式'}`,
      timestamp: Date.now(),
    }]);
  };

  const autoLogVoiceTranscript = async (transcript: string) => {
    const cleanTranscript = transcript.trim();
    if (!cleanTranscript) return;

    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'USER',
      content: `语音录入：${cleanTranscript}`,
      timestamp: Date.now(),
    }]);

    if (!TokenManager.isAuthenticated()) {
      setInputValue(prev => prev ? `${prev} ${cleanTranscript}` : cleanTranscript);
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'AI',
        aiMode: currentMode,
        aiName: '食鉴AI',
        content: '已完成语音转文字。请登录后使用自动饮食记录功能。',
        timestamp: Date.now(),
      }]);
      return;
    }

    setIsParsingIntake(true);
    setIntakeError(null);

    try {
      const session = await IntakeAPI.parseVoice(cleanTranscript);

      if (!session.candidates?.length) {
        setInputValue(cleanTranscript);
        setMessages(prev => [...prev, {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: '我听到了你的语音，但没有识别出可记录的饮食内容。你可以补充“吃了什么、分量、口味、时间”等信息后再试一次。',
          timestamp: Date.now(),
        }]);
        return;
      }

      const result = await IntakeAPI.confirm({
        source: session.source,
        raw_input_text: session.raw_input_text || cleanTranscript,
        raw_summary: session.raw_summary || null,
        record_date: session.record_date,
        candidates: session.candidates,
      });

      if (result.failed_items?.length) {
        const failedDraftIds = new Set(result.failed_items.map(item => item.draft_id));
        const remainingCandidates = session.candidates.filter(candidate => failedDraftIds.has(candidate.draft_id));

        onPendingIntakeSessionChange({
          ...session,
          candidates: remainingCandidates,
        });

        setIntakeError(result.failed_items.map(item => `${item.food_name}: ${item.reason}`).join('；'));

        setMessages(prev => [...prev, {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: `语音已解析，但有 ${result.failed_items.length} 项没有自动写入。请在下方候选卡片里检查后手动确认。`,
          timestamp: Date.now(),
        }]);
      }

      if (result.meal_ids?.length) {
        await onMealLogged?.(session.record_date);

        const loggedNames = session.candidates
          .filter(candidate => !result.failed_items?.some(item => item.draft_id === candidate.draft_id))
          .map(candidate => `${candidate.food_name}${candidate.amount_text ? `（${candidate.amount_text}）` : ''}`)
          .join('、');

        setMessages(prev => [...prev, {
          id: (Date.now() + 2).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: `已根据语音自动记录到今天的饮食日志：${loggedNames || `${result.meal_ids.length} 项饮食`}。`,
          timestamp: Date.now(),
        }]);
      }
    } catch (error) {
      console.error('语音自动记录失败', error);
      setInputValue(cleanTranscript);
      setIntakeError(error instanceof Error ? error.message : '语音自动记录失败，请稍后重试。');

      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'AI',
        aiMode: currentMode,
        aiName: '食鉴AI',
        content: '语音转文字已完成，但自动记录失败。我已把识别到的文字放回输入框，你可以修改后重新发送或稍后再试。',
        timestamp: Date.now(),
      }]);
    } finally {
      setIsParsingIntake(false);
    }
  };

  const startListening = () => {
    if (isListening || isParsingIntake || isSubmittingIntake) return;

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
        const transcript = event.results?.[0]?.[0]?.transcript || '';
        setIsListening(false);
        void autoLogVoiceTranscript(transcript);
      };

      recognition.onerror = (event: any) => {
        console.error('Speech recognition error', event.error);
        setIsListening(false);

        const message = event?.error === 'not-allowed'
          ? '浏览器没有麦克风权限，请允许麦克风后重试。'
          : '语音识别失败，请稍后重试。';

        setIntakeError(message);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
    } else {
      alert('您的浏览器暂不支持语音识别功能。建议使用最新版 Chrome 或 Edge。');
    }
  };

  const updateMessage = (messageId: string, patch: Partial<Message> | ((message: Message) => Partial<Message>)) => {
    setMessages(prev => prev.map(message => {
      if (message.id !== messageId) return message;
      const nextPatch = typeof patch === 'function' ? patch(message) : patch;
      return { ...message, ...nextPatch };
    }));
  };

  const shouldFallbackToJson = (error: unknown): boolean => {
    const message = error instanceof Error ? error.message : String(error);
    return (
      message.includes('404') ||
      message.includes('405') ||
      message.includes('不支持流式响应') ||
      message.includes('Failed to fetch')
    );
  };

  const sendJsonFallback = async (assistantMessageId: string, sessionIdValue: number, content: string) => {
    updateMessage(assistantMessageId, {
      statusText: '正在使用普通模式生成回复...',
      isStreaming: true,
    });

    const response = await ChatAPI.sendMessage(sessionIdValue, content) as any;
    const knowledge = response?.attachments?.knowledge;
    const aiContent = response?.ai_message?.content || response?.content || `已收到您的消息："${content}"。`;

    updateMessage(assistantMessageId, {
      serverId: response?.id,
      content: aiContent,
      attachments: response?.attachments,
      origin: knowledge?.origin,
      fallbackStatus: knowledge?.fallback_status,
      statusText: '回复完成',
      isStreaming: false,
      timestamp: Date.now(),
    });
  };

  const logStreamPerf = (metrics: Record<string, unknown>) => {
    console.info('chat_stream_perf', metrics);
  };

  const appendStreamDelta = (assistantMessageId: string, chunk: string) => {
    updateMessage(assistantMessageId, message => ({
      content: `${message.content}${chunk}`,
      statusText: '正在生成回复...',
      isStreaming: true,
      timestamp: Date.now(),
    }));
  };

  const pushAiMessage = (content: string) => {
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'AI',
      aiMode: currentMode,
      aiName: '食鉴AI',
      content,
      timestamp: Date.now(),
    }]);
  };

  const pushSystemMessage = (content: string) => {
    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'SYSTEM',
      content,
      timestamp: Date.now(),
    }]);
  };

  const appendClarificationContext = (contextText: string, answerText: string) => {
    return [contextText.trim(), answerText.trim()].filter(Boolean).join('\n');
  };

  const handleSendMessage = async () => {
    if ((!inputValue.trim() && !pendingImage) || isSending || isParsingIntake) return;

    const clickAt = performance.now();
    const currentInput = inputValue.trim();
    const isAuthenticated = TokenManager.isAuthenticated();
    const isExplicitTextLogSend = explicitTextLogMode;

    if (pendingImage) {
      const imageToSend = pendingImage;
      const messageContent = currentInput || '请识别这张食物图片';

      const newUserMsg: Message = {
        id: Date.now().toString(),
        role: 'USER',
        content: messageContent,
        image: imageToSend.url,
        timestamp: Date.now(),
      };

      setMessages(prev => [...prev, newUserMsg]);
      setInputValue('');
      setPendingImage(null);

      if (!TokenManager.isAuthenticated()) {
        setMessages(prev => [...prev, {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: '已收到图片和提示词。请登录后体验完整图片识别与营养分析功能。',
          timestamp: Date.now(),
        }]);
        return;
      }

      setIsParsingIntake(true);
      setIntakeError(null);

      try {
        const result = await ChatAPI.recognizeFoodUpload(imageToSend.file, currentInput) as RecognitionResponse;

        setMessages(prev => [...prev, {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: result?.ai_response || '已完成图片识别。',
          recognizedFoods: result?.foods || [],
          timestamp: Date.now(),
        }]);

        const session = await IntakeAPI.parsePhotoResult({
          recognized_foods: result?.foods || [],
          ai_response: result?.ai_response || '已完成图片识别。',
        });

        onPendingIntakeSessionChange(session);

        setMessages(prev => [...prev, {
          id: (Date.now() + 2).toString(),
          role: 'SYSTEM',
          content: '已生成拍照候选，请确认后再写入生命日志。',
          timestamp: Date.now(),
        }]);
      } catch (error) {
        console.error('食物识别失败:', error);
        setIntakeError(error instanceof Error ? error.message : '抱歉，食物识别服务暂时不可用。');
      } finally {
        setIsParsingIntake(false);
      }

      return;
    }

    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: 'USER',
      content: currentInput,
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, newUserMsg]);
    setInputValue('');

    if (!isAuthenticated && isExplicitTextLogSend) {
      setExplicitTextLogMode(false);
      pushAiMessage('请登录后使用文本记餐。我不会把这条内容当作普通聊天处理。');
      return;
    }

    if (isAuthenticated) {
      setIsParsingIntake(true);
      setIntakeError(null);

      const activeClarification = pendingTextClarification;

      try {
        const intakeSession = await IntakeAPI.parseText(
          currentInput,
          activeClarification?.contextText,
        );

        if (intakeSession.status === 'ready' && intakeSession.candidates?.length) {
          if (isExplicitTextLogSend) {
            setExplicitTextLogMode(false);
          }
          setPendingTextClarification(null);
          onPendingIntakeSessionChange(intakeSession);
          pushSystemMessage(
            activeClarification
              ? '已根据你补充的信息生成待确认的饮食草稿，请检查后确认写入日志。'
              : '已生成待确认的饮食草稿，请检查后确认写入日志。'
          );
          return;
        }

        if (intakeSession.status === 'needs_clarification') {
          const followUpPrompt = intakeSession.follow_up_prompt || '请再补充一些饮食细节，我再帮你整理成待确认记录。';
          const nextContextText = activeClarification
            ? appendClarificationContext(activeClarification.contextText, currentInput)
            : intakeSession.raw_input_text?.trim() || currentInput;

          setPendingTextClarification({
            contextText: nextContextText,
            latestFollowUpPrompt: followUpPrompt,
          });
          pushAiMessage(isExplicitTextLogSend ? `文本记餐还需要补充一点信息：${followUpPrompt}` : followUpPrompt);
          return;
        }

        if (intakeSession.status === 'refused') {
          setPendingTextClarification(null);

          if (isExplicitTextLogSend) {
            setExplicitTextLogMode(false);
            pushAiMessage(
              intakeSession.refusal_reason
                ? `这段文字暂时无法整理成饮食记录。${intakeSession.refusal_reason} 请补充吃了什么、什么时候吃的，以及大致分量后再试一次。`
                : '这段文字暂时无法整理成饮食记录。请补充吃了什么、什么时候吃的，以及大致分量后再试一次。'
            );
            return;
          }

          if (activeClarification) {
            pushAiMessage(intakeSession.refusal_reason || '这条消息暂时无法整理成可记录的饮食内容。');
            return;
          }
        }
      } catch (error) {
        console.error('文本饮食解析失败:', error);
        if (activeClarification) {
          setIntakeError(error instanceof Error ? error.message : '补充信息解析失败，请稍后重试。');
          pushAiMessage('刚才的补充信息暂时没有处理成功。当前待补充记录我还保留着，请稍后再试一次。');
          return;
        }

        if (isExplicitTextLogSend) {
          setExplicitTextLogMode(false);
          setIntakeError(error instanceof Error ? error.message : '文本记餐解析失败，请稍后重试。');
          pushAiMessage('文本记餐暂时没有处理成功。我不会把这条内容当作普通聊天处理，请稍后补充食物、时间和分量后再试一次。');
          return;
        }
      } finally {
        setIsParsingIntake(false);
      }
    }

    setIsSending(true);

    if (isAuthenticated && sessionId) {
      const assistantMessageId = (Date.now() + 1).toString();
      let streamStarted = false;
      let serverStreamError: string | null = null;
      let requestId: string | undefined;
      let requestStartAt = 0;
      let firstDeltaAt: number | null = null;
      let fallbackUsed = false;
      let streamInterrupted = false;

      const streamingMessage: Message = {
        id: assistantMessageId,
        role: 'AI',
        aiMode: currentMode,
        aiName: '食鉴AI',
        content: '',
        statusText: '正在检查本地规则...',
        isStreaming: true,
        timestamp: Date.now(),
      };

      setMessages(prev => [...prev, streamingMessage]);

      try {
        requestStartAt = performance.now();
        await ChatAPI.sendMessageStream(
          sessionId,
          currentInput,
          undefined,
          (event: ChatStreamEvent) => {
            streamStarted = true;
            if (event.event === 'meta') {
              requestId = event.data.request_id;
              logStreamPerf({
                request_id: requestId,
                session_id: event.data.session_id,
                send_click_to_request_ms: Math.round((requestStartAt - clickAt) * 100) / 100,
              });
              return;
            }

            if (event.event === 'status') {
              updateMessage(assistantMessageId, {
                statusText: event.data.message || '正在生成回复...',
                isStreaming: true,
              });
              return;
            }

            if (event.event === 'delta' && event.data.content) {
              if (firstDeltaAt === null) {
                firstDeltaAt = performance.now();
                logStreamPerf({
                  request_id: requestId,
                  request_to_first_delta_ms: Math.round((firstDeltaAt - requestStartAt) * 100) / 100,
                  fallback: false,
                  interrupted: false,
                });
              }
              appendStreamDelta(assistantMessageId, event.data.content);
              return;
            }

            if (event.event === 'done') {
              const doneAt = performance.now();
              updateMessage(assistantMessageId, {
                serverId: event.data.message_id,
                attachments: event.data.attachments,
                origin: event.data.origin,
                fallbackStatus: event.data.fallback_status,
                statusText: '回复完成',
                isStreaming: false,
                timestamp: Date.now(),
              });
              window.requestAnimationFrame(() => {
                logStreamPerf({
                  request_id: event.data.request_id || requestId,
                  request_to_done_ms: Math.round((doneAt - requestStartAt) * 100) / 100,
                  render_done_ms: Math.round((performance.now() - requestStartAt) * 100) / 100,
                  fallback: fallbackUsed,
                  interrupted: streamInterrupted,
                  origin: event.data.origin,
                  fallback_status: event.data.fallback_status,
                });
              });
              return;
            }

            if (event.event === 'error') {
              serverStreamError = event.data.message || '生成失败，请重试。';
              streamInterrupted = true;
              updateMessage(assistantMessageId, {
                content: serverStreamError || '生成失败，请重试。',
                statusText: '生成失败，请重试',
                isStreaming: false,
                timestamp: Date.now(),
              });
            }
          }
        );

        if (serverStreamError) {
          console.warn('流式消息返回错误:', serverStreamError);
        }
      } catch (error) {
        console.error('流式发送失败:', error);

        if (!streamStarted && shouldFallbackToJson(error)) {
          try {
            fallbackUsed = true;
            const fallbackStartAt = performance.now();
            await sendJsonFallback(assistantMessageId, sessionId, currentInput);
            logStreamPerf({
              request_id: requestId,
              request_to_done_ms: Math.round((performance.now() - fallbackStartAt) * 100) / 100,
              fallback: true,
              interrupted: false,
            });
          } catch (fallbackError) {
            console.error('普通消息 fallback 失败:', fallbackError);
            updateMessage(assistantMessageId, {
              content: '抱歉，AI服务暂时不可用，请稍后重试。',
              statusText: '生成失败，请重试',
              isStreaming: false,
              timestamp: Date.now(),
            });
          }
        } else {
          updateMessage(assistantMessageId, {
            content: '抱歉，AI服务暂时不可用，请稍后重试。',
            statusText: '生成失败，请重试',
            isStreaming: false,
            timestamp: Date.now(),
          });
        }
      } finally {
        setIsSending(false);
      }
    } else {
      setTimeout(() => {
        const newAiMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: 'AI',
          aiMode: currentMode,
          aiName: '食鉴AI',
          content: `收到，已识别您的输入："${currentInput}"。请登录后体验完整AI分析功能。`,
          timestamp: Date.now(),
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

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
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
        timestamp: Date.now(),
      }]);
    } catch (error) {
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'SYSTEM',
        content: `记日志失败：${error instanceof Error ? error.message : '未知错误'}`,
        timestamp: Date.now(),
      }]);
    }
  };

  const handlePendingCandidateChange = (draftId: string, patch: Partial<IntakeCandidate>) => {
    if (!pendingIntakeSession) return;

    if (
      Object.prototype.hasOwnProperty.call(patch, 'food_name') ||
      Object.prototype.hasOwnProperty.call(patch, 'food_code') ||
      Object.prototype.hasOwnProperty.call(patch, 'category') ||
      Object.prototype.hasOwnProperty.call(patch, 'normalized_amount') ||
      Object.prototype.hasOwnProperty.call(patch, 'unit')
    ) {
      setStaleEvaluationDraftIds(prev => prev.includes(draftId) ? prev : [...prev, draftId]);
    }

    onPendingIntakeSessionChange({
      ...pendingIntakeSession,
      candidates: pendingIntakeSession.candidates.map((candidate) => {
        if (candidate.draft_id !== draftId) return candidate;

        const nextCandidate = { ...candidate, ...patch };

        if (patch.normalized_amount !== undefined || patch.unit !== undefined) {
          const amount = nextCandidate.normalized_amount;
          const unit = nextCandidate.unit || '份';
          nextCandidate.amount_text = amount ? `${amount}${unit}` : candidate.amount_text;
        }

        return nextCandidate;
      }),
    });
  };

  const handleDeletePendingCandidate = (draftId: string) => {
    if (!pendingIntakeSession) return;

    setReevaluatingDraftIds(prev => prev.filter(id => id !== draftId));
    setStaleEvaluationDraftIds(prev => prev.filter(id => id !== draftId));

    onPendingIntakeSessionChange({
      ...pendingIntakeSession,
      candidates: pendingIntakeSession.candidates.filter(candidate => candidate.draft_id !== draftId),
    });
  };

  const handleReevaluatePendingCandidate = async (draftId: string) => {
    const session = pendingIntakeSessionRef.current;
    if (!session || reevaluatingDraftIds.includes(draftId)) return;

    const candidate = session.candidates.find(item => item.draft_id === draftId);
    const foodName = candidate?.food_name.trim();
    if (!candidate || !foodName) return;

    setReevaluatingDraftIds(prev => prev.includes(draftId) ? prev : [...prev, draftId]);
    setIntakeError(null);

    try {
      const reevaluatedCandidate = await IntakeAPI.reevaluateCandidate(candidate);

      const latestSession = pendingIntakeSessionRef.current;
      if (!latestSession) return;

      onPendingIntakeSessionChange({
        ...latestSession,
        candidates: latestSession.candidates.map((item) => {
          if (item.draft_id !== draftId) return item;

          return {
            ...item,
            ...reevaluatedCandidate,
            draft_id: item.draft_id,
          };
        }),
      });

      setStaleEvaluationDraftIds(prev => prev.filter(id => id !== draftId));
    } catch (error) {
      console.error('候选重新评估失败', error);
      setIntakeError(`${candidate.food_name}: ${error instanceof Error ? error.message : '重新评估失败，请稍后重试。'}`);
    } finally {
      setReevaluatingDraftIds(prev => prev.filter(id => id !== draftId));
    }
  };

  const handleAddPendingCandidate = () => {
    const fallbackMealType = pendingIntakeSession?.candidates[0]?.meal_type || 'DINNER';
    const source = pendingIntakeSession?.source || 'voice';

    const nextCandidate: IntakeCandidate = {
      draft_id: crypto.randomUUID(),
      source,
      meal_type: fallbackMealType,
      category: 'STAPLE',
      food_name: '',
      food_code: null,
      amount_text: '1份',
      normalized_amount: 1,
      unit: '份',
      time_hint: pendingIntakeSession?.meal_time_hint || null,
      note: '',
      confidence: 0.2,
      ingredients: [],
      cooking_method: null,
      calories: null,
      protein: null,
      carbs: null,
      fat: null,
      fiber: null,
      sodium: null,
      sugar: null,
      purine: null,
      allergen_tags: [],
      risk_tags: [],
      estimated_fields: [],
      estimated_notes: [],
      local_rule_hit: false,
      matched_disease_codes: [],
      recommendation_level: null,
      warnings: [],
      citations: [],
      origin: 'LOCAL_KNOWLEDGE',
      fallback_status: 'NO_LOCAL_MATCH_ALLOW_CLOUD',
      conflict_note: null,
      caution_note: null,
    };

    onPendingIntakeSessionChange({
      source,
      raw_input_text: pendingIntakeSession?.raw_input_text || null,
      raw_summary: pendingIntakeSession?.raw_summary || null,
      record_date: pendingIntakeSession?.record_date || new Date().toISOString().slice(0, 10),
      meal_time_hint: pendingIntakeSession?.meal_time_hint || null,
      summary_warning: pendingIntakeSession?.summary_warning || null,
      candidates: [...(pendingIntakeSession?.candidates || []), nextCandidate],
    });
  };

  const handleConfirmIntake = async () => {
    if (!pendingIntakeSession || isSubmittingIntake) return;
    if (staleEvaluationDraftIds.length > 0) {
      setIntakeError('候选项已修改，请先点击“重新评估”，再确认写入日志。');
      return;
    }

    setIsSubmittingIntake(true);
    setIntakeError(null);

    try {
      const result = await IntakeAPI.confirm({
        source: pendingIntakeSession.source,
        raw_input_text: pendingIntakeSession.raw_input_text || null,
        raw_summary: pendingIntakeSession.raw_summary || null,
        record_date: pendingIntakeSession.record_date,
        candidates: pendingIntakeSession.candidates,
      });

      if (result.failed_items?.length) {
        setIntakeError(result.failed_items.map(item => `${item.food_name}: ${item.reason}`).join('；'));

        const failedDraftIds = new Set(result.failed_items.map(item => item.draft_id));

        onPendingIntakeSessionChange({
          ...pendingIntakeSession,
          candidates: pendingIntakeSession.candidates.filter(candidate => failedDraftIds.has(candidate.draft_id)),
        });
      }

      if (result.meal_ids?.length && !result.failed_items?.length) {
        onPendingIntakeSessionChange(null);
        await onMealLogged?.(pendingIntakeSession.record_date);
        onViewChange(View.LOG);
      } else if (result.meal_ids?.length) {
        await onMealLogged?.(pendingIntakeSession.record_date);
      }
    } catch (error) {
      console.error('确认写入失败', error);
      setIntakeError(error instanceof Error ? error.message : '确认写入失败，请稍后重试。');
    } finally {
      setIsSubmittingIntake(false);
    }
  };

  const canSendComposer = Boolean(inputValue.trim() || pendingImage);
  const sendButtonLabel = pendingImage
    ? inputValue.trim()
      ? '发送图片'
      : '直接发送'
    : explicitTextLogMode
      ? '记餐'
      : '发送';
  const composerBusyMessage = isSubmittingIntake
    ? '正在写入饮食日志，请稍候。'
    : isParsingIntake
      ? pendingImage
        ? '正在识别图片并整理饮食候选。'
        : '正在解析饮食内容并尝试写入日志。'
      : isSending
        ? '正在发送给食鉴AI，请稍候。'
        : isListening
          ? '正在听你说，结束后会自动整理。'
          : null;
  const composerPlaceholder = isListening
    ? '正在聆听，请说出你吃了什么、分量和口味...'
    : isParsingIntake
      ? '正在解析饮食内容...'
      : isSubmittingIntake
        ? '正在写入饮食日志...'
        : pendingImage
          ? '可补充：半份、少油、重点看嘌呤...'
          : pendingTextClarification
            ? '请补充上面的记餐问题...'
            : explicitTextLogMode
              ? '文本记餐：写下食物、时间和大致分量...'
              : '输入问题，或描述刚吃了什么...';

  return (
    <div className="flex flex-col w-full min-h-[calc(100vh-100px)]">
      <input
        type="file"
        accept="image/*"
        className="hidden"
        ref={fileInputRef}
        onChange={handleFileChange}
      />

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
        {isLoadingHistory && (
          <div className="text-center text-xs text-slate-500 my-4 font-serif font-bold tracking-wide">
            正在加载历史消息...
          </div>
        )}

        {messages.map((msg, index) => {
          const prevMsg = messages[index - 1];
          const showTimestamp = !prevMsg || (msg.timestamp - prevMsg.timestamp > 5 * 60 * 1000);

          return (
            <React.Fragment key={msg.id}>
              {showTimestamp && (
                <div className="text-center text-xs text-slate-500 my-4 font-serif font-bold tracking-wide">
                  {formatTime(msg.timestamp)}
                </div>
              )}

              {msg.role === 'SYSTEM' && (() => {
                const notice = getSystemNoticePresentation(msg.content);

                return (
                  <div className="flex justify-center my-1.5 animate-fade-in px-2">
                    <div className={`w-full max-w-[20rem] rounded-xl border px-3 py-2 ${notice.shellClass}`}>
                      <div className="flex items-start gap-2">
                        <span className={`material-symbols-outlined mt-0.5 text-[15px] ${notice.iconClass}`}>{notice.icon}</span>
                        <div className="min-w-0">
                          <div className={`text-[10px] font-bold tracking-[0.18em] ${notice.labelClass}`}>
                            {notice.label}
                          </div>
                          <div className="mt-0.5 text-xs leading-relaxed font-serif tracking-wide break-words">
                            {msg.content}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}

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

                  <div className="flex flex-col gap-2 max-w-[88%] sm:max-w-[34rem]">
                    <div className="ml-1 flex items-center gap-2">
                      <span className={`text-xs font-bold tracking-wide ${msg.aiMode === 'STRICT' ? 'text-primary font-serif' : 'text-slate-400 font-serif'}`}>
                        {msg.aiName}
                      </span>
                      <span className="rounded-full border border-white/10 bg-white/[0.03] px-1.5 py-0.5 text-[10px] text-slate-500 font-serif font-bold tracking-wide">
                        {msg.aiMode === 'STRICT' ? '风险分析' : '饮食教练'}
                      </span>
                      {msg.content && msg.isStreaming && (
                        <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-primary/75 font-serif tracking-wide">
                          <span className="h-1.5 w-1.5 rounded-full bg-primary/70 animate-pulse"></span>
                          {msg.statusText || '生成中'}
                        </span>
                      )}
                    </div>

                    {msg.content ? (
                      <div
                        className={`rounded-xl rounded-tl-none px-3.5 py-3 text-white text-sm leading-7 shadow-sm font-serif tracking-wide break-words [&_p]:my-1.5 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ul]:my-2 [&_ul]:pl-4 [&_ol]:my-2 [&_ol]:pl-4 [&_li]:my-1 [&_strong]:text-white [&_strong]:font-bold ${msg.aiMode === 'STRICT'
                          ? 'bg-[#0f282d] border border-primary/20'
                          : 'bg-surface-dark border border-white/5'
                          }`}
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                      />
                    ) : (
                      <div className={`rounded-xl rounded-tl-none px-4 py-3 text-sm leading-relaxed shadow-sm font-serif tracking-wide flex items-center gap-2 ${msg.aiMode === 'STRICT' ? 'bg-[#0f282d] border border-primary/20' : 'bg-surface-dark border border-white/5'}`}>
                        <div className="flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-primary/80 animate-bounce" style={{ animationDelay: '0ms', animationDuration: '1.2s' }}></span>
                          <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: '200ms', animationDuration: '1.2s' }}></span>
                          <span className="w-1.5 h-1.5 rounded-full bg-primary/40 animate-bounce" style={{ animationDelay: '400ms', animationDuration: '1.2s' }}></span>
                        </div>
                        <span className="text-white/50 text-xs tracking-wider">{msg.statusText || '正在生成回复...'}</span>
                      </div>
                    )}

                    {msg.recognizedFoods && msg.recognizedFoods.length > 0 && !pendingIntakeSession && (
                      <div className="mt-1 rounded-2xl border border-primary/20 bg-primary/[0.06] p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-xs font-serif font-bold tracking-wide text-primary">
                              下一步：确认要写入日志的食物
                            </p>
                            <p className="mt-1 text-[11px] leading-relaxed text-slate-400 font-serif tracking-wide">
                              点选后会直接按当前时间归入对应餐次。
                            </p>
                          </div>
                          <span className="material-symbols-outlined shrink-0 text-[18px] text-primary/80">add_task</span>
                        </div>

                        <div className="mt-3 flex flex-col gap-2">
                          {msg.recognizedFoods.slice(0, 3).map((food, idx) => (
                            <button
                              key={`${food.food_name}-${idx}`}
                              onClick={() => handleQuickLog(food)}
                              className="flex w-full items-center justify-between gap-3 rounded-xl border border-primary/25 bg-[#0f282d]/80 px-3 py-2.5 text-left transition-colors hover:bg-primary/10 active:scale-[0.99]"
                            >
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-serif font-bold tracking-wide text-white">
                                  {food.food_name}
                                </span>
                                <span className="mt-0.5 block truncate text-[11px] font-serif tracking-wide text-slate-400">
                                  {formatRecognizedFoodMeta(food) || '识别结果待补充分量'}
                                </span>
                              </span>
                              <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-primary px-2.5 py-1 text-[11px] font-serif font-bold tracking-wide text-background-dark">
                                写入
                                <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </React.Fragment>
          );
        })}

        {isSending && !messages.some(message => message.isStreaming) && (
          <div className="flex gap-2.5 animate-fade-in">
            <div className={`w-8 h-8 rounded-full bg-surface-dark flex items-center justify-center shrink-0 mt-0.5 ${currentMode === 'STRICT' ? 'border border-white/10 shadow-[0_0_10px_rgba(17,196,212,0.5)]' : 'border border-white/10 shadow-glow-cyan'}`}>
              {currentMode === 'STRICT' ? (
                <span className="material-symbols-outlined text-primary text-sm">security</span>
              ) : (
                <div className="w-4 h-4 rounded-full border border-primary"></div>
              )}
            </div>

            <div className="flex flex-col gap-1 max-w-[85%]">
              <span className={`text-xs ml-1 font-bold tracking-wide ${currentMode === 'STRICT' ? 'text-primary font-serif' : 'text-slate-400 font-serif'}`}>
                食鉴AI
              </span>

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

        <div ref={messagesEndRef} />
      </div>

      <div className="sticky bottom-24 px-3 sm:px-4 pb-2 z-30">
        {composerBusyMessage && (
          <div className="mb-2 flex items-start gap-2 rounded-2xl border border-primary/25 bg-[#0f282d]/95 px-3 py-2.5 text-xs text-primary font-serif tracking-wide shadow-lg">
            <span className="material-symbols-outlined mt-0.5 text-[16px] animate-pulse">progress_activity</span>
            <span className="leading-relaxed">{composerBusyMessage}</span>
          </div>
        )}

        {intakeError && (
          <div className="mb-2 rounded-2xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200 font-serif tracking-wide">
            {intakeError}
          </div>
        )}

        <div className="mb-2 flex items-center justify-between gap-2 px-1">
          <button
            type="button"
            onClick={() => setExplicitTextLogMode(prev => !prev)}
            disabled={isParsingIntake || isSubmittingIntake}
            aria-pressed={explicitTextLogMode}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] font-bold font-serif tracking-wide transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 ${explicitTextLogMode ? 'border-primary/60 bg-primary/15 text-primary shadow-[0_0_14px_rgba(17,196,212,0.18)]' : 'border-white/10 bg-[#101719]/75 text-slate-400 hover:border-primary/30 hover:text-slate-200'}`}
          >
            <span className="material-symbols-outlined text-[16px]">edit_note</span>
            文本记餐
          </button>

          {explicitTextLogMode && (
            <span className="min-w-0 flex-1 text-right text-[11px] leading-relaxed text-primary/80 font-serif tracking-wide">
              下一条文字将整理为饮食记录
            </span>
          )}
        </div>

        <div className="flex items-center justify-start px-1 mb-2 gap-1.5 overflow-x-auto">
          <button
            onClick={() => setInputValue('请基于我今天已记录的饮食和健康档案，说明当前需要注意的风险点和下一餐原则。')}
            className="flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-[#101719]/75 px-2.5 py-1 text-[11px] text-slate-500 backdrop-blur transition-all active:scale-95 hover:border-primary/30 hover:text-slate-300 group"
          >
            <span className="material-symbols-outlined text-[14px] text-primary/70 group-hover:text-primary">assignment</span>
            <span className="font-serif tracking-wide">今日风险</span>
          </button>

          <button
            onClick={() => setInputValue('一日三餐吃什么？')}
            className="flex shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-[#101719]/75 px-2.5 py-1 text-[11px] text-slate-500 backdrop-blur transition-all active:scale-95 hover:border-ochre/30 hover:text-slate-300 group"
          >
            <span className="material-symbols-outlined text-[14px] text-ochre/70 group-hover:text-ochre">restaurant_menu</span>
            <span className="font-serif tracking-wide">三餐建议</span>
          </button>
        </div>

        {pendingImage && (
          <div className="mb-2 flex items-center gap-3 rounded-2xl border border-primary/20 bg-surface-dark/95 p-2.5 shadow-lg">
            <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl border border-white/10">
              <img src={pendingImage.url} alt="待发送图片" className="h-full w-full object-cover" />
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[16px] text-primary">image</span>
                <p className="text-xs font-bold text-white font-serif tracking-wide">图片已准备好</p>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-400 font-serif">
                可先补充提示词，也可直接发送识别。
              </p>
              <p className="mt-0.5 truncate text-[11px] text-slate-600 font-serif">{pendingImage.file.name}</p>
            </div>

            <button
              onClick={clearPendingImage}
              disabled={isParsingIntake || isSubmittingIntake}
              className="h-8 w-8 rounded-full bg-white/10 text-slate-300 hover:bg-white/20 hover:text-white disabled:opacity-50"
              aria-label="移除图片"
            >
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          </div>
        )}

        <div className="flex items-end gap-1.5 rounded-2xl border border-white/10 bg-surface-dark p-1.5 shadow-lg">
          <button
            onClick={handleGalleryClick}
            disabled={isParsingIntake || isSubmittingIntake}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-slate-400 transition-colors hover:bg-white/5 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="添加图片"
          >
            <span className="material-symbols-outlined">add_photo_alternate</span>
          </button>

          <textarea
            value={inputValue}
            onChange={handleTextareaInput}
            onKeyDown={handleKeyDown}
            placeholder={composerPlaceholder}
            rows={1}
            className={`min-w-0 flex-1 resize-none bg-transparent py-2.5 text-sm font-bold tracking-wide text-white caret-primary outline-none placeholder:text-slate-500 focus:ring-0 font-serif max-h-[120px] ${isListening ? 'animate-pulse' : ''}`}
          />

          <button
            onClick={startListening}
            disabled={isListening || isParsingIntake || isSubmittingIntake}
            className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-300 ${isListening ? 'scale-110 bg-primary/10 text-primary' : 'text-slate-400 hover:bg-white/5 hover:text-white'} ${(isParsingIntake || isSubmittingIntake) ? 'opacity-50 cursor-not-allowed' : ''}`}
            title="语音录入饮食"
            aria-label="语音录入饮食"
          >
            <span className="material-symbols-outlined">mic</span>
          </button>

          <button
            onClick={handleSendMessage}
            className={`flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-xl px-3 font-bold transition-all duration-300 font-serif ${canSendComposer ? 'min-w-[4.5rem] bg-primary text-background-dark shadow-[0_0_18px_rgba(17,196,212,0.25)] hover:bg-primary/90' : 'w-10 bg-white/10 px-0 text-white/20'}`}
            disabled={!canSendComposer || isSending || isParsingIntake || isSubmittingIntake}
            aria-label={sendButtonLabel}
          >
            <span className="material-symbols-outlined text-[18px]">arrow_upward</span>
            {canSendComposer && (
              <span className="text-xs tracking-wide">{sendButtonLabel}</span>
            )}
          </button>
        </div>
      </div>

      {pendingIntakeSession && (
        <IntakeConfirmationSheet
          session={pendingIntakeSession}
          isSubmitting={isSubmittingIntake}
          error={intakeError}
          reevaluatingDraftIds={reevaluatingDraftIds}
          staleEvaluationDraftIds={staleEvaluationDraftIds}
          onClose={() => {
            setIntakeError(null);
            setReevaluatingDraftIds([]);
            setStaleEvaluationDraftIds([]);
            onPendingIntakeSessionChange(null);
          }}
          onChangeCandidate={handlePendingCandidateChange}
          onDeleteCandidate={handleDeletePendingCandidate}
          onAddCandidate={handleAddPendingCandidate}
          onReevaluateCandidate={handleReevaluatePendingCandidate}
          onConfirm={handleConfirmIntake}
        />
      )}
    </div>
  );
};

export default ChatView;
