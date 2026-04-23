import React from 'react';
import BottomNav from './BottomNav';
import { View } from '../types';

interface AppShellProps {
  currentView: View;
  onViewChange: (view: View) => void;
  children: React.ReactNode;
}

const HIDE_BOTTOM_NAV = new Set<View>([
  View.SPLASH,
  View.LOGIN,
  View.REGISTER,
  View.FORGOT_PASSWORD,
  View.CAMERA,
  View.SETTINGS,
  View.MESSAGES,
  View.HEALTH_REPORT_ARCHIVES,
]);

const AppShell: React.FC<AppShellProps> = ({ currentView, onViewChange, children }) => {
  return (
    <div className="relative min-h-screen w-full max-w-md mx-auto bg-gradient-to-b from-[#0c1416] to-[#132320] overflow-hidden flex flex-col">
      <div
        className="fixed inset-0 z-0 pointer-events-none opacity-30 mix-blend-overlay"
        style={{ backgroundImage: 'url("/images/bg-texture.png")' }}
      />
      <div className="fixed bottom-0 left-0 right-0 h-1/3 bg-[url('/images/bg-texture.png')] bg-cover bg-bottom opacity-20 pointer-events-none z-0 mix-blend-soft-light" />

      <main className="flex-1 relative z-10 overflow-y-auto scroll-smooth no-scrollbar h-full">
        {children}
      </main>

      {!HIDE_BOTTOM_NAV.has(currentView) && (
        <BottomNav currentView={currentView} onViewChange={onViewChange} />
      )}
    </div>
  );
};

export default AppShell;

