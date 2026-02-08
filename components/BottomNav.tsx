import React from 'react';
import { View } from '../types';

interface BottomNavProps {
  currentView: View;
  onViewChange: (view: View) => void;
}

const BottomNav: React.FC<BottomNavProps> = ({ currentView, onViewChange }) => {
  
  const NavItem = ({ view, icon, label }: { view: View; icon: string; label: string }) => {
    const isActive = currentView === view;
    return (
      <button 
        onClick={() => onViewChange(view)}
        className={`flex flex-col items-center gap-1 transition-colors duration-300 ${isActive ? 'text-primary' : 'text-white/40 hover:text-white'}`}
      >
        <span className={`material-symbols-outlined ${isActive ? 'icon-filled' : ''}`}>{icon}</span>
        <span className="text-[10px] font-medium font-serif">{label}</span>
      </button>
    );
  };

  return (
    <nav className="fixed bottom-0 left-0 right-0 max-w-md mx-auto z-50">
      {/* Glassmorphism Background */}
      <div className="absolute inset-0 bg-[#080c0d]/90 backdrop-blur-xl border-t border-white/5"></div>
      
      <div className="relative flex justify-between items-center h-20 px-8 pb-2">
        <NavItem view={View.HOME} icon="home_app_logo" label="首页" />
        <NavItem view={View.LOG} icon="edit_note" label="日志" />
        
        {/* Spacer for the central button */}
        <div className="w-12"></div>
        
        <NavItem view={View.CHAT} icon="chat_bubble" label="AI" />
        <NavItem view={View.PROFILE} icon="person" label="我的" />
      </div>

      {/* Floating Central Prism Button */}
      <div className="absolute -top-8 left-1/2 -translate-x-1/2 p-1.5 rounded-full bg-gradient-to-b from-mineral/20 to-transparent backdrop-blur-sm border-t border-white/5">
        <button 
          onClick={() => onViewChange(View.CAMERA)}
          className="relative flex items-center justify-center w-16 h-16 rounded-full bg-[#0d1416] shadow-[0_0_20px_rgba(17,196,212,0.3),inset_0_0_15px_rgba(122,160,160,0.1)] hover:shadow-[0_0_30px_rgba(17,196,212,0.5),inset_0_0_20px_rgba(17,196,212,0.2)] transition-all duration-500 active:scale-95 border border-white/10 group overflow-hidden"
        >
          {/* Internal Glows */}
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(122,160,160,0.15),transparent_60%)]"></div>
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_70%,rgba(17,196,212,0.05),transparent_60%)]"></div>
          
          {/* SVG Prism Icon */}
          <svg className="w-8 h-8 relative z-10 transition-transform duration-700 ease-out group-hover:rotate-[120deg] drop-shadow-[0_0_10px_rgba(17,196,212,0.6)]" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
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
    </nav>
  );
};

export default BottomNav;