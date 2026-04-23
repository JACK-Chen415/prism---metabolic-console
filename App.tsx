import React, { useCallback, useEffect, useState } from 'react';
import { View } from './types';
import SplashScreen from './components/SplashScreen';
import AppShell from './components/AppShell';
import HomeView from './components/views/HomeView';
import LogView from './components/views/LogView';
import ChatView from './components/views/ChatView';
import ProfileView from './components/views/ProfileView';
import CameraView from './components/views/CameraView';
import SettingsView from './components/views/SettingsView';
import MessageView from './components/views/MessageView';
import MedicalArchivesView from './components/views/MedicalArchivesView';
import HealthReportArchivesView from './components/views/HealthReportArchivesView';
import LoginView from './components/views/LoginView';
import RegisterView from './components/views/RegisterView';
import ForgotPasswordView from './components/views/ForgotPasswordView';
import { TokenManager } from './services/api';
import { syncScheduler } from './services/offline';
import { SPLASH_DURATION_MS, VIEW_TRANSITION_MS } from './constants/app';
import { useNavigation } from './hooks/useNavigation';
import { useAppData } from './hooks/useAppData';

const App: React.FC = () => {
  const { currentView, setCurrentView, navigate, isTransitioning, setIsTransitioning } = useNavigation();
  const [isAuthChecked, setIsAuthChecked] = useState(false);
  const {
    isGuest,
    currentUserId,
    userProfile,
    medicalConditions,
    meals,
    appMessages,
    dailyTargets,
    setMedicalConditions,
    loadUserData,
    enterGuestMode,
    logout,
    markAllMessagesRead,
    addMeal,
    refreshMeals,
    updateProfile,
    updateNickname,
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
      logout();
      setCurrentView(View.LOGIN);
      return;
    }

    navigate(view);
  }, [isGuest, logout, navigate, setCurrentView]);

  const handleAuthSuccess = useCallback(async () => {
    const result = await loadUserData();
    setCurrentView(result.success ? View.HOME : View.LOGIN);
  }, [loadUserData, setCurrentView]);

  const handleLogout = useCallback(() => {
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

  if (currentView === View.SPLASH) {
    return <SplashScreen isExiting={isTransitioning || isAuthChecked} />;
  }

  return (
    <AppShell currentView={currentView} onViewChange={handleNavChange}>
      {currentView === View.LOGIN && (
        <LoginView
          onViewChange={(view) => {
            logout();
            handleNavChange(view);
          }}
          onSkipLogin={() => {
            enterGuestMode();
            setCurrentView(View.HOME);
          }}
          onLoginSuccess={handleAuthSuccess}
        />
      )}

      {currentView === View.REGISTER && (
        <RegisterView
          onViewChange={(view) => {
            logout();
            handleNavChange(view);
          }}
          onRegisterSuccess={handleAuthSuccess}
        />
      )}

      {currentView === View.FORGOT_PASSWORD && (
        <ForgotPasswordView
          onViewChange={(view) => {
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
          meals={meals}
          dailyTargets={dailyTargets}
          onAddMeal={addMeal}
        />
      )}

      {currentView === View.CHAT && (
        <ChatView
          onViewChange={handleNavChange}
          onMealLogged={() => refreshMeals()}
        />
      )}

      {currentView === View.PROFILE && (
        <ProfileView
          onViewChange={handleNavChange}
          medicalConditions={medicalConditions}
          userProfile={userProfile}
          onUpdateNickname={updateNickname}
        />
      )}

      {currentView === View.CAMERA && <CameraView onViewChange={handleNavChange} />}

      {currentView === View.SETTINGS && (
        <SettingsView
          onViewChange={handleNavChange}
          userProfile={userProfile}
          currentUserId={currentUserId}
          onUpdateProfile={updateProfile}
          onLogout={handleLogout}
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
        />
      )}

      {currentView === View.HEALTH_REPORT_ARCHIVES && (
        <HealthReportArchivesView onViewChange={handleNavChange} />
      )}
    </AppShell>
  );
};

export default App;
