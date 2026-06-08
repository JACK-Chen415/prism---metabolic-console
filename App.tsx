import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppMessage, ComplianceDocumentKey, IntakeDraftSession, View } from './types';
import SplashScreen from './components/SplashScreen';
import AppShell from './components/AppShell';
import HomeView from './components/views/HomeView';
import LogView from './components/views/LogView';
import ChatView from './components/views/ChatView';
import ProfileView from './components/views/ProfileView';
import PackagedFoodScanView from './components/views/PackagedFoodScanView';
import SettingsView from './components/views/SettingsView';
import MessageView from './components/views/MessageView';
import MedicalArchivesView from './components/views/MedicalArchivesView';
import HealthMetricsView from './components/views/HealthMetricsView';
import ReportsView from './components/views/ReportsView';
import BillingView from './components/views/BillingView';
import AdminView from './components/views/AdminView';
import LoginView from './components/views/LoginView';
import RegisterView from './components/views/RegisterView';
import ForgotPasswordView from './components/views/ForgotPasswordView';
import ComplianceView from './components/views/ComplianceView';
import { TokenManager } from './services/api';
import { syncScheduler } from './services/offline';
import { getLocalDateString } from './services/date';
import { SPLASH_DURATION_MS, VIEW_TRANSITION_MS } from './constants/app';
import { useNavigation } from './hooks/useNavigation';
import { useAppData } from './hooks/useAppData';

const SMART_INSIGHT_ATTRIBUTION_PREFIX = 'smart-insights:';

function isSmartInsightWarning(message: AppMessage): boolean {
  return (
    message.type === 'WARNING' &&
    !message.isRead &&
    typeof message.attribution === 'string' &&
    message.attribution.startsWith(SMART_INSIGHT_ATTRIBUTION_PREFIX)
  );
}

function getShortMessageBody(content: string): string {
  const trimmed = content.trim();
  return trimmed.length > 118 ? `${trimmed.slice(0, 118)}...` : trimmed;
}

interface SmartInsightWarningPopupProps {
  message: AppMessage | null;
  onDismiss: () => void;
  onViewInsights: () => void;
}

const SmartInsightWarningPopup: React.FC<SmartInsightWarningPopupProps> = ({
  message,
  onDismiss,
  onViewInsights,
}) => {
  if (!message) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center px-4 pb-5 pt-10 sm:items-center sm:pb-10">
      <button
        type="button"
        aria-label="关闭智能预警"
        className="absolute inset-0 w-full h-full bg-black/55 backdrop-blur-[2px]"
        onClick={onDismiss}
      />

      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="smart-insight-warning-title"
        className="relative w-full max-w-md overflow-hidden rounded-2xl border border-[#fa5c38]/35 bg-[#111c1d]/95 shadow-2xl shadow-black/45"
      >
        <div className="absolute inset-0 pointer-events-none bg-[url('/images/bg-texture.png')] bg-cover opacity-10 mix-blend-soft-light" />
        <div className="absolute left-0 top-0 h-full w-1 bg-[#fa5c38]" />

        <div className="relative p-5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#fa5c38]/25 bg-[#fa5c38]/10">
              <span className="material-symbols-outlined icon-filled text-[#fa5c38]">notifications_active</span>
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-serif tracking-[0.28em] text-[#fa5c38]/80">智能预警</p>
              <h2
                id="smart-insight-warning-title"
                className="mt-1 text-lg font-bold leading-snug tracking-wide text-white font-serif"
              >
                {message.title}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-300 font-serif">
                {getShortMessageBody(message.content)}
              </p>
            </div>

            <button
              type="button"
              aria-label="关闭"
              onClick={onDismiss}
              className="-mr-1 -mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white/55 transition-colors hover:bg-white/10 hover:text-white"
            >
              <span className="material-symbols-outlined text-xl">close</span>
            </button>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={onDismiss}
              className="h-11 rounded-lg border border-white/10 bg-white/5 text-sm font-bold tracking-widest text-slate-300 transition-colors hover:bg-white/10"
            >
              稍后
            </button>
            <button
              type="button"
              onClick={onViewInsights}
              className="h-11 rounded-lg bg-primary text-sm font-bold tracking-widest text-[#062326] shadow-glow-cyan transition-transform active:scale-[0.98]"
            >
              查看洞察
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};

const App: React.FC = () => {
  const { currentView, setCurrentView, navigate, isTransitioning, setIsTransitioning } = useNavigation();
  const [isAuthChecked, setIsAuthChecked] = useState(false);
  const [pendingIntakeSession, setPendingIntakeSession] = useState<IntakeDraftSession | null>(null);
  const [smartInsightWarningPopup, setSmartInsightWarningPopup] = useState<AppMessage | null>(null);
  const [activeComplianceDocument, setActiveComplianceDocument] = useState<ComplianceDocumentKey | null>(null);
  const shownSmartInsightWarningIdsRef = useRef<Set<number>>(new Set());
  const {
    isGuest,
    currentUserId,
    userProfile,
    medicalConditions,
    meals,
    currentMealDate,
    appMessages,
    dailyTargets,
    setMedicalConditions,
    loadUserData,
    enterGuestMode,
    exitGuestMode,
    logout,
    markAllMessagesRead,
    addMeal,
    updateMeal,
    deleteMeal,
    refreshMeals,
    refreshAfterMealChange,
    refreshSmartInsightsAndMessages,
    updateProfile,
    updateNickname,
    clearUserContent,
  } = useAppData();

  const handleNavChange = useCallback((view: View) => {
    if (
      isGuest &&
      view !== View.HOME &&
      view !== View.LOGIN &&
      view !== View.REGISTER &&
      view !== View.FORGOT_PASSWORD &&
      view !== View.SPLASH
    ) {
      exitGuestMode();
      setCurrentView(View.LOGIN);
      return;
    }

    navigate(view);
  }, [exitGuestMode, isGuest, navigate, setCurrentView]);

  const handleAuthSuccess = useCallback(async () => {
    const result = await loadUserData();
    setPendingIntakeSession(null);
    setCurrentView(result.success ? View.HOME : View.LOGIN);
  }, [loadUserData, setCurrentView]);

  const handleLogout = useCallback(() => {
    setPendingIntakeSession(null);
    setSmartInsightWarningPopup(null);
    shownSmartInsightWarningIdsRef.current.clear();
    logout();
    setCurrentView(View.LOGIN);
  }, [logout, setCurrentView]);

  useEffect(() => {
    const onAuthLogout = () => handleLogout();
    window.addEventListener('auth:logout', onAuthLogout);
    return () => window.removeEventListener('auth:logout', onAuthLogout);
  }, [handleLogout]);

  useEffect(() => {
    if (currentView !== View.SPLASH) return;

    const timer = window.setTimeout(async () => {
      setIsTransitioning(true);

      if (TokenManager.isAuthenticated()) {
        const result = await loadUserData();
        if (result.success) {
          window.setTimeout(() => {
            setCurrentView(View.HOME);
            setIsTransitioning(false);
            setIsAuthChecked(true);
          }, VIEW_TRANSITION_MS);
          return;
        }
      }

      window.setTimeout(() => {
        setCurrentView(View.LOGIN);
        setIsTransitioning(false);
        setIsAuthChecked(true);
      }, VIEW_TRANSITION_MS);
    }, SPLASH_DURATION_MS);

    return () => window.clearTimeout(timer);
  }, [currentView, loadUserData, setCurrentView, setIsTransitioning]);

  useEffect(() => {
    return () => {
      syncScheduler.stop();
    };
  }, []);

  useEffect(() => {
    if (isGuest || currentView === View.MESSAGES || appMessages.length === 0) {
      setSmartInsightWarningPopup(null);
      return;
    }

    if (smartInsightWarningPopup) return;

    const nextSmartInsightWarning = appMessages.find((message) => (
      isSmartInsightWarning(message) && !shownSmartInsightWarningIdsRef.current.has(message.id)
    ));

    if (!nextSmartInsightWarning) return;

    shownSmartInsightWarningIdsRef.current.add(nextSmartInsightWarning.id);
    setSmartInsightWarningPopup(nextSmartInsightWarning);
  }, [appMessages, currentView, isGuest, smartInsightWarningPopup]);

  const handleDismissSmartInsightWarning = useCallback(() => {
    setSmartInsightWarningPopup(null);
  }, []);

  const handleViewSmartInsightWarning = useCallback(() => {
    setSmartInsightWarningPopup(null);
    handleNavChange(View.MESSAGES);
  }, [handleNavChange]);

  const openComplianceDocument = useCallback((documentKey: ComplianceDocumentKey) => {
    setActiveComplianceDocument(documentKey);
  }, []);

  if (currentView === View.SPLASH) {
    return <SplashScreen isExiting={isTransitioning || isAuthChecked} />;
  }

  return (
    <AppShell currentView={currentView} onViewChange={handleNavChange}>
      {currentView === View.LOGIN && (
        <LoginView
          onViewChange={(view) => {
            shownSmartInsightWarningIdsRef.current.clear();
            logout();
            handleNavChange(view);
          }}
          onSkipLogin={() => {
            enterGuestMode();
            setPendingIntakeSession(null);
            setCurrentView(View.HOME);
          }}
          onLoginSuccess={handleAuthSuccess}
        />
      )}

      {currentView === View.REGISTER && (
        <RegisterView
          onViewChange={(view) => {
            shownSmartInsightWarningIdsRef.current.clear();
            logout();
            handleNavChange(view);
          }}
          onRegisterSuccess={handleAuthSuccess}
          onOpenCompliance={openComplianceDocument}
        />
      )}

      {currentView === View.FORGOT_PASSWORD && (
        <ForgotPasswordView
          onViewChange={(view) => {
            shownSmartInsightWarningIdsRef.current.clear();
            logout();
            handleNavChange(view);
          }}
        />
      )}

      {currentView === View.HOME && (
        <HomeView
          onViewChange={handleNavChange}
          meals={meals}
          dailyTargets={dailyTargets}
          latestMessage={appMessages[0]}
          appMessages={appMessages}
        />
      )}

      {currentView === View.LOG && (
        <LogView
          userProfile={userProfile}
          medicalConditions={medicalConditions}
          meals={meals}
          currentDate={currentMealDate}
          dailyTargets={dailyTargets}
          onAddMeal={addMeal}
          onUpdateMeal={updateMeal}
          onDeleteMeal={deleteMeal}
          onDateChange={refreshMeals}
        />
      )}

      {currentView === View.CHAT && (
        <ChatView
          onViewChange={handleNavChange}
          onMealLogged={(recordDate) => refreshAfterMealChange(recordDate || getLocalDateString())}
          pendingIntakeSession={pendingIntakeSession}
          onPendingIntakeSessionChange={setPendingIntakeSession}
          currentUserId={currentUserId}
        />
      )}

      {currentView === View.PACKAGED_FOOD_SCAN && (
        <PackagedFoodScanView onViewChange={handleNavChange} />
      )}

      {currentView === View.PROFILE && (
        <ProfileView
          onViewChange={handleNavChange}
          medicalConditions={medicalConditions}
          userProfile={userProfile}
          onUpdateNickname={updateNickname}
        />
      )}

      {currentView === View.CAMERA && (
        <CameraView
          onViewChange={handleNavChange}
          onPendingIntakeSessionChange={setPendingIntakeSession}
        />
      )}

      {currentView === View.SETTINGS && (
        <SettingsView
          onViewChange={handleNavChange}
          userProfile={userProfile}
          currentUserId={currentUserId}
          onUpdateProfile={updateProfile}
          onLogout={handleLogout}
          onOpenCompliance={openComplianceDocument}
          onDataDeleted={() => {
            setPendingIntakeSession(null);
            setSmartInsightWarningPopup(null);
            shownSmartInsightWarningIdsRef.current.clear();
            clearUserContent();
          }}
          onOpenLogDate={async (date) => {
            await refreshMeals(date);
            handleNavChange(View.LOG);
          }}
        />
      )}

      {currentView === View.MESSAGES && (
        <MessageView
          onViewChange={handleNavChange}
          messages={appMessages}
          onMarkAllRead={markAllMessagesRead}
        />
      )}

      {currentView === View.MEDICAL_ARCHIVES && (
        <MedicalArchivesView
          onViewChange={handleNavChange}
          conditions={medicalConditions}
          setConditions={setMedicalConditions}
          onConditionsChanged={refreshSmartInsightsAndMessages}
        />
      )}

      {currentView === View.HEALTH_METRICS && (
        <HealthMetricsView onViewChange={handleNavChange} />
      )}

      {currentView === View.REPORTS && (
        <ReportsView onViewChange={handleNavChange} />
      )}

      {currentView === View.BILLING && (
        <BillingView onViewChange={handleNavChange} />
      )}

      {currentView === View.ADMIN && (
        <AdminView onViewChange={handleNavChange} />
      )}

      <SmartInsightWarningPopup
        message={smartInsightWarningPopup}
        onDismiss={handleDismissSmartInsightWarning}
        onViewInsights={handleViewSmartInsightWarning}
      />
      {activeComplianceDocument && (
        <ComplianceView
          activeDocument={activeComplianceDocument}
          onDocumentChange={setActiveComplianceDocument}
          onClose={() => setActiveComplianceDocument(null)}
        />
      )}
    </AppShell>
  );
};

export default App;
