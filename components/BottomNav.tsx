import React from 'react';
import { View } from '../types';

interface BottomNavProps {
  currentView: View;
  onViewChange: (view: View) => void;
}

const BottomNav: React.FC<BottomNavProps> = ({ currentView, onViewChange }) => {
  const isCameraActive = currentView === View.CAMERA;
  
  const NavItem = ({ view, icon, label }: { view: View; icon: string; label: string }) => {
    const isActive = currentView === view;
    return (
      <button 
        type="button"
        onClick={() => onViewChange(view)}
        aria-current={isActive ? 'page' : undefined}
        className={`relative flex h-14 w-12 flex-col items-center justify-center gap-1 rounded-2xl transition-all duration-300 ${isActive ? 'bg-white/[0.07] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]' : 'text-white/30 hover:bg-white/[0.04] hover:text-white/65'}`}
      >
        <span className={`material-symbols-outlined text-[23px] transition-transform duration-300 ${isActive ? 'icon-filled text-primary drop-shadow-[0_0_10px_rgba(17,196,212,0.35)]' : 'scale-95'}`}>{icon}</span>
        <span className={`text-[10px] font-medium font-serif leading-none ${isActive ? 'text-white/90' : 'text-white/35'}`}>{label}</span>
        {isActive && (
          <span className="absolute -bottom-1 h-0.5 w-5 rounded-full bg-primary shadow-[0_0_10px_rgba(17,196,212,0.6)]" />
        )}
      </button>
    );
  };

  return (
    <nav className="fixed bottom-0 left-0 right-0 max-w-md mx-auto z-50" aria-label="底部导航">
      {/* Glassmorphism Background */}
      <div className="absolute inset-0 bg-[#080c0d]/95 backdrop-blur-xl border-t border-white/5"></div>
      
      <div className="relative flex h-20 items-center justify-between px-7 pb-2">
        <NavItem view={View.HOME} icon="home_app_logo" label="首页" />
        <NavItem view={View.LOG} icon="edit_note" label="日志" />
        
        {/* Spacer for the central button */}
        <div className="w-20"></div>
        
        <NavItem view={View.CHAT} icon="chat_bubble" label="AI" />
        <NavItem view={View.PROFILE} icon="person" label="我的" />
      </div>

      {/* Floating Central Prism Button */}
      <div className="absolute -top-10 left-1/2 flex -translate-x-1/2 flex-col items-center gap-1.5">
        <div className={`rounded-full p-1.5 backdrop-blur-sm transition-all duration-500 ${isCameraActive ? 'bg-primary/20 shadow-[0_0_34px_rgba(17,196,212,0.45)]' : 'bg-gradient-to-b from-primary/25 via-mineral/10 to-transparent shadow-[0_14px_36px_rgba(0,0,0,0.35)]'} border-t border-white/10`}>
          <button 
            type="button"
            onClick={() => onViewChange(View.CAMERA)}
            aria-label="拍照或从相册记录饮食"
            className="group relative flex h-[72px] w-[72px] items-center justify-center overflow-hidden rounded-full border border-primary/45 bg-[#0d1416] shadow-[0_0_26px_rgba(17,196,212,0.42),0_18px_30px_rgba(0,0,0,0.4),inset_0_0_18px_rgba(122,160,160,0.13)] transition-all duration-500 hover:shadow-[0_0_36px_rgba(17,196,212,0.58),0_18px_30px_rgba(0,0,0,0.4),inset_0_0_22px_rgba(17,196,212,0.22)] active:scale-95"
          >
            {/* Internal Glows */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(122,160,160,0.22),transparent_60%)]"></div>
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_70%,rgba(17,196,212,0.16),transparent_60%)]"></div>
            <div className="absolute inset-x-4 top-2 h-px bg-white/40"></div>
            
            {/* SVG Prism Icon */}
            <svg className="relative z-10 h-9 w-9 drop-shadow-[0_0_12px_rgba(17,196,212,0.75)] transition-transform duration-700 ease-out group-hover:rotate-[120deg]" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient gradientUnits="userSpaceOnUse" id="prism_grad_1" x1="12" x2="2" y1="2" y2="19">
                  <stop stopColor="#11c4d4" stopOpacity="0.9"></stop>
                  <stop offset="1" stopColor="#11c4d4" stopOpacity="0.1"></stop>
                </linearGradient>
                <linearGradient gradientUnits="userSpaceOnUse" id="prism_grad_2" x1="12" x2="22" y1="2" y2="19">
                  <stop stopColor="#7aa0a0" stopOpacity="0.9"></stop>
                  <stop offset="1" stopColor="#7aa0a0" stopOpacity="0.1"></stop>
                </linearGradient>
                <linearGradient id="prism_shine" x1="0" x2="1" y1="0" y2="1">
                  <stop stopColor="white" stopOpacity="0.8"></stop>
                  <stop offset="1" stopColor="transparent"></stop>
                </linearGradient>
              </defs>
              <path d="M12 2L2 19L12 14L12 2Z" fill="url(#prism_grad_1)" stroke="rgba(17,196,212,0.3)" strokeWidth="0.5"></path>
              <path d="M12 2L22 19L12 14L12 2Z" fill="url(#prism_grad_2)" stroke="rgba(122,160,160,0.3)" strokeWidth="0.5"></path>
              <path d="M2 19L12 14L22 19" fill="rgba(8,12,13,0.5)"></path>
              <path d="M12 2L2 19" stroke="url(#prism_shine)" strokeOpacity="0.5" strokeWidth="0.5"></path>
              <path d="M12 2L22 19" stroke="url(#prism_shine)" strokeOpacity="0.5" strokeWidth="0.5"></path>
              <path d="M12 14L12 2" stroke="rgba(255,255,255,0.4)" strokeWidth="0.5"></path>
            </svg>
            
            {/* Glass reflection overlay */}
            <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-white/10 to-transparent pointer-events-none"></div>
          </button>
        </div>
        <div className="text-center leading-none">
          <div className="text-[11px] font-semibold font-serif text-primary drop-shadow-[0_0_10px_rgba(17,196,212,0.45)]">记录饮食</div>
          <div className="mt-0.5 text-[8px] font-medium tracking-[0.08em] text-white/50">拍照 / 相册</div>
        </div>
      </div>
    </nav>
  );
};

export default BottomNav;
