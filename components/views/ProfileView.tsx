import React, { useState, useRef, useEffect } from 'react';
import { View, ConditionData, ConditionStatus } from '../../types';

interface ProfileViewProps {
    onViewChange?: (view: View) => void;
    medicalConditions: ConditionData[];
}

const ProfileView: React.FC<ProfileViewProps> = ({ onViewChange, medicalConditions }) => {
  const [avatar, setAvatar] = useState('/images/user-avatar.png');
  const [name, setName] = useState('Alex Chen');
  const [isEditingName, setIsEditingName] = useState(false);
  const [showCopyFeedback, setShowCopyFeedback] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditingName && nameInputRef.current) {
        nameInputRef.current.focus();
    }
  }, [isEditingName]);

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
        const reader = new FileReader();
        reader.onload = (e) => {
            if (e.target?.result) {
                setAvatar(e.target.result as string);
            }
        };
        reader.readAsDataURL(e.target.files[0]);
    }
  };

  const handleNameBlur = () => {
      setIsEditingName(false);
      if (name.trim() === '') setName('Alex Chen');
  };

  const handleNameKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
          handleNameBlur();
      }
  };

  const handleCopyId = () => {
      navigator.clipboard.writeText('#8829-XJ');
      setShowCopyFeedback(true);
      setTimeout(() => setShowCopyFeedback(false), 2000);
  };

  const getStatusLabel = (status: ConditionStatus) => {
    switch (status) {
      case 'ACTIVE': return '活跃';
      case 'MONITORING': return '监测中';
      case 'STABLE': return '平稳';
      case 'ALERT': return '过敏';
      default: return '未知';
    }
  };

  // Helper to determine visual style of cards
  const getCardStyle = (item: ConditionData) => {
    if (item.type === 'ALLERGY') {
         return { 
             bg: 'bg-red-500/10', 
             iconColor: 'text-red-400', 
             textColor: 'text-slate-400' 
         };
    }
    // Chronic conditions
    if (item.status === 'ACTIVE' || item.status === 'ALERT') {
        return { 
            bg: 'bg-ochre/10', 
            iconColor: 'text-ochre', 
            textColor: 'text-ochre' 
        };
    }
    // Stable/Monitoring
    return { 
        bg: 'bg-[#45b7aa]/10', 
        iconColor: 'text-[#45b7aa]', 
        textColor: 'text-[#45b7aa]' 
    };
  };

  return (
    <div className="flex flex-col w-full pb-24">
      {/* Hidden File Input */}
      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileChange} 
        className="hidden" 
        accept="image/*"
      />

      <div className="relative">
        {/* Glow blob decoration preserved */}
        <div className="absolute -top-20 -right-20 w-64 h-64 bg-primary/5 rounded-full blur-3xl pointer-events-none z-0"></div>
        
        {/* Nav Header */}
        <div className="relative z-10 flex items-center p-4 pb-2 justify-between">
            <button 
                onClick={() => onViewChange && onViewChange(View.HOME)}
                className="text-white flex size-10 shrink-0 items-center justify-center rounded-full hover:bg-white/5 transition-colors"
            >
            <span className="material-symbols-outlined">arrow_back</span>
            </button>
            <h2 className="text-white text-lg font-bold leading-tight tracking-wide flex-1 text-center font-serif">个人主页</h2>
            <button 
                onClick={() => onViewChange && onViewChange(View.SETTINGS)}
                className="text-white flex size-10 shrink-0 items-center justify-center rounded-full hover:bg-white/5 transition-colors"
            >
                <span className="material-symbols-outlined">settings</span>
            </button>
        </div>

        {/* Avatar Section */}
        <div className="relative z-10 px-6 py-6 flex flex-col items-center gap-4">
            <div className="relative group cursor-pointer" onClick={handleAvatarClick}>
                <div className="size-28 rounded-full p-1 bg-gradient-to-tr from-primary/30 to-ochre/30 transition-transform duration-300 group-active:scale-95">
                    <div 
                        className="w-full h-full rounded-full bg-cover bg-center border-4 border-background-dark relative overflow-hidden"
                        style={{ backgroundImage: `url("${avatar}")` }}
                    >
                         {/* Edit Overlay on Hover */}
                         <div className="absolute inset-0 bg-black/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                             <span className="material-symbols-outlined text-white text-2xl">photo_camera</span>
                         </div>
                    </div>
                </div>
                <div className="absolute -bottom-2 -right-2 bg-surface-dark border border-white/10 p-1.5 px-3 rounded-full flex items-center gap-1.5 shadow-lg pointer-events-none">
                    <span className="material-symbols-outlined text-primary text-[18px]">ecg_heart</span>
                    <span className="text-xs font-bold tracking-wide text-white font-serif">85</span>
                </div>
            </div>
            
            <div className="text-center flex flex-col items-center gap-1">
                {isEditingName ? (
                    <input 
                        ref={nameInputRef}
                        type="text" 
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onBlur={handleNameBlur}
                        onKeyDown={handleNameKeyDown}
                        className="text-2xl font-bold tracking-wide text-white font-serif bg-transparent border-b border-primary/50 outline-none text-center w-48 pb-1"
                    />
                ) : (
                    <h1 
                        onClick={() => setIsEditingName(true)}
                        className="text-2xl font-bold tracking-wide text-white font-serif cursor-pointer hover:text-white/90 flex items-center gap-2 group"
                    >
                        {name}
                        <span className="material-symbols-outlined text-white/20 text-sm group-hover:text-white/50 transition-colors">edit</span>
                    </h1>
                )}
                
                <div className="flex items-center gap-2 mt-1 relative">
                    <p className="text-slate-400 text-sm font-bold tracking-wide font-serif">Metabolic ID: #8829-XJ</p>
                    <button 
                        onClick={handleCopyId}
                        className="flex items-center justify-center w-6 h-6 rounded-md bg-white/5 text-slate-400 hover:text-white hover:bg-white/10 transition-all active:scale-95"
                        title="复制 ID"
                    >
                        <span className="material-symbols-outlined text-[14px]">
                            {showCopyFeedback ? 'check' : 'content_copy'}
                        </span>
                    </button>
                    {showCopyFeedback && (
                        <span className="text-[10px] text-[#45b7aa] animate-fade-in absolute -right-12 font-serif font-bold tracking-wide">已复制</span>
                    )}
                </div>
            </div>
        </div>
      </div>

      <div className="relative z-10 flex flex-col gap-6 px-4">
        {/* Medical History Grid */}
        <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between px-2">
                <h3 className="text-white text-base font-bold font-serif tracking-wide">病史背景</h3>
                <button 
                    onClick={() => onViewChange && onViewChange(View.MEDICAL_ARCHIVES)}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 hover:border-white/20 transition-all active:scale-95 group backdrop-blur-sm"
                >
                    <span className="text-xs text-slate-300 group-hover:text-white font-bold font-serif tracking-wide">编辑</span>
                    <span className="material-symbols-outlined text-[14px] text-slate-400 group-hover:text-primary transition-colors">edit</span>
                </button>
            </div>
            
            {medicalConditions.length > 0 ? (
                <div className="grid grid-cols-2 gap-3">
                    {medicalConditions.map(item => {
                        const style = getCardStyle(item);
                        return (
                             <div 
                                key={item.id}
                                className="flex items-start gap-3 p-3 rounded-xl bg-surface-dark border border-white/5 shadow-sm hover:bg-white/5 transition-colors cursor-pointer"
                             >
                                <div className={`shrink-0 size-8 rounded-lg ${style.bg} flex items-center justify-center ${style.iconColor}`}>
                                    <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                                </div>
                                <div className="flex flex-col">
                                    <span className="text-sm font-bold font-serif text-white tracking-wide">{item.title}</span>
                                    <span className={`text-[10px] uppercase font-bold font-serif tracking-wider mt-0.5 ${style.textColor}`}>
                                        {getStatusLabel(item.status)}
                                    </span>
                                </div>
                            </div>
                        );
                    })}
                </div>
            ) : (
                <div className="flex flex-col items-center justify-center py-6 border border-dashed border-white/10 rounded-xl bg-white/5">
                    <span className="text-xs text-slate-500 font-serif font-bold tracking-wide">暂无病史记录</span>
                </div>
            )}
        </div>

        {/* Scan Archives List */}
        <div className="flex flex-col gap-3 mt-4">
            <div className="flex items-center justify-between px-2">
                <h3 className="text-white text-base font-bold font-serif tracking-wide">体检档案</h3>
                {/* Filter button removed */}
            </div>
            <div className="flex flex-col gap-3">
                
                {/* File Item 1: Health Report */}
                <button 
                    onClick={() => onViewChange && onViewChange(View.HEALTH_REPORT_ARCHIVES)} 
                    className="group relative flex items-center gap-4 p-4 rounded-2xl bg-[#131b1d]/80 backdrop-blur-md border border-white/5 shadow-sm active:scale-[0.98] transition-all hover:border-primary/20 hover:bg-[#131b1d] cursor-pointer"
                >
                    <div className="relative shrink-0 size-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary border border-primary/10">
                        <span className="material-symbols-outlined text-[24px]">description</span>
                        <div className="absolute -top-1 -right-1 size-3 bg-[#10b981] rounded-full border-[3px] border-[#131b1d]"></div>
                    </div>
                    <div className="flex-1 min-w-0 text-left">
                        <h4 className="text-sm font-bold font-serif text-white truncate group-hover:text-primary transition-colors tracking-wide">体检报告</h4>
                        <p className="text-xs text-slate-400 mt-1 flex items-center gap-1.5 font-serif font-bold tracking-wide">
                            <span className="material-symbols-outlined text-[12px] opacity-70">calendar_today</span> 
                            2023年10月24日
                        </p>
                    </div>
                    <div className="shrink-0 flex items-center gap-3">
                        <div className="px-2.5 py-1 rounded-md bg-[#10b981]/10 border border-[#10b981]/20">
                            <span className="text-[10px] font-bold font-serif text-[#10b981] tracking-wide">已分析</span>
                        </div>
                        <span className="material-symbols-outlined text-slate-500 group-hover:text-white transition-colors text-xl">chevron_right</span>
                    </div>
                </button>

            </div>
        </div>
      </div>
    </div>
  );
};

export default ProfileView;