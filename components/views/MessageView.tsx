import React, { useState } from 'react';
import { View, AppMessage } from '../../types';

interface MessageViewProps {
  onViewChange: (view: View) => void;
  messages: AppMessage[];
}

type TabType = 'ALL' | 'WARNING' | 'ADVICE' | 'BRIEF';

const MessageView: React.FC<MessageViewProps> = ({ onViewChange, messages }) => {
  const [activeTab, setActiveTab] = useState<TabType>('ALL');

  const filteredMessages = activeTab === 'ALL' 
    ? messages 
    : messages.filter(m => m.type === activeTab);

  const getTabLabel = (tab: TabType) => {
    switch (tab) {
      case 'ALL': return '全部';
      case 'WARNING': return '预警';
      case 'ADVICE': return '建议';
      case 'BRIEF': return '简报';
    }
  };

  const getTypeStyles = (type: string) => {
    switch (type) {
      case 'WARNING':
        return {
          border: 'border-[#fa5c38]',
          iconBg: 'bg-[#fa5c38]/10',
          iconColor: 'text-[#fa5c38]',
          icon: 'notifications_active'
        };
      case 'ADVICE':
        return {
          border: 'border-emerald-500',
          iconBg: 'bg-emerald-500/10',
          iconColor: 'text-emerald-500',
          icon: 'water_drop'
        };
      case 'BRIEF':
        return {
          border: 'border-mineral',
          iconBg: 'bg-mineral/10',
          iconColor: 'text-mineral',
          icon: 'article'
        };
      default:
        return {
          border: 'border-white',
          iconBg: 'bg-white/10',
          iconColor: 'text-white',
          icon: 'info'
        };
    }
  };

  return (
    <div className="flex flex-col w-full h-full pb-20">
      {/* Header Area */}
      <div className="relative sticky top-0 z-20 pt-4 bg-gradient-to-b from-[#080c0d] via-[#0d1416] to-[#0d1416]/95 backdrop-blur-sm border-b border-white/5">
        
        {/* Top Nav & Title */}
        <div className="px-6 pb-4 flex items-start justify-between">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => onViewChange(View.HOME)}
              className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors -ml-2"
            >
              <span className="material-symbols-outlined text-white/80">arrow_back</span>
            </button>
            <div className="flex flex-col">
              <h1 className="text-white text-xl font-bold font-serif tracking-widest">消息中心</h1>
              <span className="text-[10px] text-primary/40 font-serif tracking-[0.3em] uppercase mt-0.5">Insights</span>
            </div>
          </div>
        </div>

        {/* Tabs with Mountain Silhouette Indicator */}
        <div className="flex items-end justify-between px-6 mt-2 relative">
          {(['ALL', 'WARNING', 'ADVICE', 'BRIEF'] as TabType[]).map((tab) => {
            const isActive = activeTab === tab;
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`relative pb-3 px-2 flex flex-col items-center transition-all duration-300 ${isActive ? 'text-white' : 'text-white/40 hover:text-white/60'}`}
              >
                <span className={`text-sm font-serif tracking-widest ${isActive ? 'font-bold' : 'font-medium'}`}>
                  {getTabLabel(tab)}
                </span>
                
                {/* Mountain Silhouette SVG for Active Tab */}
                {isActive && (
                  <div className="absolute bottom-0 left-0 right-0 h-[6px] text-primary w-full flex justify-center overflow-hidden">
                     <svg viewBox="0 0 40 6" className="w-10 h-full fill-current opacity-80" preserveAspectRatio="none">
                        <path d="M0,6 L40,6 L35,2 C30,0 25,4 20,2 C15,0 10,4 5,2 L0,6 Z" />
                     </svg>
                  </div>
                )}
              </button>
            );
          })}
          {/* Bottom Line for entire tab bar */}
          <div className="absolute bottom-0 left-0 right-0 h-px bg-white/5 pointer-events-none"></div>
        </div>
      </div>

      {/* Message List - "Book Slips" */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {filteredMessages.map((msg) => {
          const styles = getTypeStyles(msg.type);
          return (
            <div 
              key={msg.id}
              className="group relative bg-[#162624]/90 border border-white/5 rounded-lg overflow-hidden backdrop-blur-sm shadow-lg transition-transform active:scale-[0.99]"
            >
              {/* Rice Paper Texture Overlay */}
              <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: 'url("https://www.transparenttextures.com/patterns/rice-paper.png")' }}></div>

              <div className="flex h-full">
                {/* Left Colored Bar */}
                <div className={`w-1.5 ${styles.border.replace('border', 'bg')} opacity-80`}></div>

                <div className="flex-1 p-5 pl-4">
                  {/* Card Header */}
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full ${styles.iconBg} flex items-center justify-center border border-white/5`}>
                        <span className={`material-symbols-outlined ${styles.iconColor} text-lg`}>{styles.icon}</span>
                      </div>
                      <h3 className="text-white text-lg font-bold font-serif tracking-wide">{msg.title}</h3>
                    </div>
                    <span className="text-white/30 text-xs font-serif tracking-wider font-light">{msg.time}</span>
                  </div>

                  {/* Content */}
                  <div className="pl-11">
                    <p className="text-slate-300 text-sm leading-relaxed font-serif text-justify">
                      {msg.content}
                    </p>
                    
                    {/* Attribution */}
                    <p className="mt-3 text-[10px] text-slate-500 font-serif border-l-2 border-white/10 pl-2 leading-tight">
                      {msg.attribution}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        
        {/* End of List Decoration */}
        <div className="py-8 flex justify-center opacity-30">
             <span className="text-xs font-serif text-slate-500 tracking-[0.5em]">— 完 —</span>
        </div>
      </div>
    </div>
  );
};

export default MessageView;