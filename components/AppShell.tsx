import React from 'react';
import BottomNav from './BottomNav';
import { View } from '../types';

interface AppShellProps {
  currentView: View;
  onViewChange: (view: View) => void;
  children: React.ReactNode;
  isOffline?: boolean;
  offlineQueueCount?: number;
  intakeDraftCount?: number;
}

const HIDE_BOTTOM_NAV = new Set<View>([
  View.SPLASH,
  View.LOGIN,
  View.REGISTER,
  View.FORGOT_PASSWORD,
  View.PACKAGED_FOOD_SCAN,
  View.CAMERA,
  View.SETTINGS,
  View.MESSAGES,
  View.HEALTH_METRICS,
  View.REPORTS,
  View.BILLING,
  View.ADMIN,
]);


const AppShell: React.FC<AppShellProps> = ({ currentView, onViewChange, children, isOffline = false, offlineQueueCount = 0, intakeDraftCount = 0 }) => {
  return (
    <div className="relative min-h-screen w-full max-w-md mx-auto bg-gradient-to-b from-[#0c1416] to-[#132320] overflow-hidden flex flex-col">
      <div
        className="fixed inset-0 z-0 pointer-events-none opacity-30 mix-blend-overlay"
        style={{ backgroundImage: 'url("/images/bg-texture.png")' }}
      />
      <div className="fixed bottom-0 left-0 right-0 h-1/3 bg-[url('/images/bg-texture.png')] bg-cover bg-bottom opacity-20 pointer-events-none z-0 mix-blend-soft-light" />

      {(isOffline || offlineQueueCount > 0 || intakeDraftCount > 0) && (
        <div className="relative z-20 border-b border-white/5 bg-[#0f1718]/95 px-4 py-2 text-[11px] font-serif tracking-wide text-slate-300">
          <div className="flex items-center justify-between gap-2">
            <span className="min-w-0 truncate">
              {isOffline ? '当前离线' : '本地队列可用'}
            </span>
            <span className="shrink-0 text-slate-500">
              {offlineQueueCount} 待同步 · {intakeDraftCount} 待复核
            </span>
          </div>
        </div>
      )}

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
