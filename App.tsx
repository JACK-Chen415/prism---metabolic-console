import React, { useState, useEffect, useMemo } from 'react';
import { View, ConditionData, UserProfile, Meal, DailyTargets, AppMessage } from './types';
import SplashScreen from './components/SplashScreen';
import BottomNav from './components/BottomNav';
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

// Initial Data moved from MedicalArchivesView
const INITIAL_MEDICAL_DATA: ConditionData[] = [
  {
    id: 'gout',
    title: '痛风',
    icon: 'rheumatology',
    status: 'ACTIVE',
    trend: 'WORSENING',
    value: '420',
    unit: 'μmol/L',
    dictum: '尿酸波动犹如山体微颤，需防微杜渐。',
    attribution: '归因：近期海鲜摄入频率较高，且饮水量未达标，导致血尿酸浓度出现锯齿状爬升。',
    type: 'CHRONIC'
  },
  {
    id: 'hypertension',
    title: '高血压',
    icon: 'cardiology',
    status: 'MONITORING',
    trend: 'STABLE',
    value: '128/82',
    unit: 'mmHg',
    dictum: '平稳如湖面微澜，守恒之道在于坚持。',
    attribution: '归因：由于您近期严格执行了“茶博士”的控盐建议，血压走势已从“惊涛”转为“微澜”。',
    type: 'CHRONIC'
  },
  {
    id: 'peanut',
    title: '花生过敏',
    icon: 'no_food',
    status: 'ALERT',
    trend: 'STABLE',
    dictum: '禁忌之地，切勿踏足。',
    attribution: '归因：免疫系统对花生蛋白保持高度敏感，需持续保持“绝对回避”策略。',
    type: 'ALLERGY'
  },
  {
    id: 'seafood',
    title: '海鲜过敏',
    icon: 'restaurant_menu',
    status: 'ALERT',
    trend: 'STABLE',
    dictum: '深海之味，以此为界。',
    attribution: '归因：IgE抗体检测显示对贝类及甲壳类蛋白呈强阳性反应。',
    type: 'ALLERGY'
  }
];

// Initial Meals Data
const INITIAL_MEALS: Meal[] = [
  { id: '1', name: '全麦吐司 & 煎蛋', portion: '2片 + 1个', calories: 350, sodium: 400, purine: 50, type: 'BREAKFAST', category: 'STAPLE' },
  { id: '2', name: '鸡胸肉藜麦沙拉', portion: '300g', calories: 420, sodium: 600, purine: 120, type: 'LUNCH', category: 'MEAT' },
  { id: '3', name: '坚果酸奶', portion: '1杯 (150g)', calories: 180, sodium: 80, purine: 20, type: 'SNACK', category: 'SNACK' },
];

// Initial Messages Data
const INITIAL_APP_MESSAGES: AppMessage[] = [
    {
      id: 0,
      type: 'ADVICE',
      title: '代谢状态良好',
      time: '现在',
      content: '今日各项摄入控制良好，请继续保持。建议晚餐后散步 20 分钟。',
      attribution: '归因：今日热量与钠摄入均在合理区间。',
      isRead: false,
    },
    {
      id: 2,
      type: 'ADVICE',
      title: '晚餐备选建议',
      time: '申时 16:45',
      content: '检测到今日蛋白质摄入不足。推荐晚餐包含清蒸鱼类或白灼虾。',
      attribution: '归因：早餐与午餐均为碳水主导，缺乏优质蛋白。',
      isRead: false,
    },
    {
      id: 1,
      type: 'WARNING',
      title: '钠摄入预警',
      time: '午时 13:20',
      content: '午餐钠摄入已达日限额 85%。建议额外补充 250ml 水分，促进排泄。',
      attribution: '归因：识别到午餐含有大量生抽与调味酱汁。',
      isRead: false,
    },
    {
      id: 3,
      type: 'BRIEF',
      title: '周代谢简报',
      time: '辰时 09:00',
      content: '本周血糖波动率下降 5%，尿酸水平维持在正常区间。',
      attribution: '归因：高纤维饮食干预初见成效。',
      isRead: true,
    }
  ];

const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<View>(View.SPLASH);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [isGuest, setIsGuest] = useState(false);
  
  // Shared State for Medical Conditions
  const [medicalConditions, setMedicalConditions] = useState<ConditionData[]>(INITIAL_MEDICAL_DATA);

  // Shared State for User Profile
  const [userProfile, setUserProfile] = useState<UserProfile>({
    gender: 'MALE',
    age: 28,
    height: 181,
    weight: 72.5
  });

  // Shared State for Meals (Lifted from LogView)
  const [meals, setMeals] = useState<Meal[]>(INITIAL_MEALS);

  // Shared State for Messages
  const [appMessages, setAppMessages] = useState<AppMessage[]>(INITIAL_APP_MESSAGES);

  // Auto-transition from Splash to Login
  useEffect(() => {
    if (currentView === View.SPLASH) {
      const timer = setTimeout(() => {
        setIsTransitioning(true);
        setTimeout(() => {
          setCurrentView(View.LOGIN);
          setIsTransitioning(false);
        }, 500); // Wait for fade out
      }, 3500);
      return () => clearTimeout(timer);
    }
  }, [currentView]);

  // AI Logic: Calculate Daily Targets based on Profile & Conditions
  const dailyTargets: DailyTargets = useMemo(() => {
    // 1. Calculate BMR (Mifflin-St Jeor)
    const s = userProfile.gender === 'MALE' ? 5 : -161;
    const bmr = (10 * userProfile.weight) + (6.25 * userProfile.height) - (5 * userProfile.age) + s;
    const calories = Math.round(bmr * 1.375); // Sedentary/Light activity

    // 2. Calculate Sodium Target
    // Default: 2300mg. Hypertension: 1500mg.
    const hasHypertension = medicalConditions.some(c => c.id === 'hypertension' && (c.status === 'ACTIVE' || c.status === 'MONITORING'));
    const sodium = hasHypertension ? 1500 : 2300;

    // 3. Calculate Purine Target
    // Normal: 600-1000mg tolerance (but low purine diet is <400). Gout: 200mg.
    const hasGout = medicalConditions.some(c => c.id === 'gout' && (c.status === 'ACTIVE' || c.status === 'MONITORING'));
    const purine = hasGout ? 300 : 600;

    return { calories, sodium, purine };
  }, [userProfile, medicalConditions]);

  // Real-time Message Generation based on Intake
  useEffect(() => {
    const totalSodium = meals.reduce((sum, item) => sum + item.sodium, 0);
    const sodiumLimit = dailyTargets.sodium;

    if (totalSodium > sodiumLimit) {
        // Check if latest message is already a warning to avoid duplicates
        if (appMessages[0].type !== 'WARNING') {
            const warningMsg: AppMessage = {
                id: Date.now(),
                type: 'WARNING',
                title: '钠摄入超标预警',
                time: new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute:'2-digit'}),
                content: `今日钠摄入已超出 ${totalSodium - sodiumLimit}mg。建议接下来大量饮水（至少500ml）并食用含钾食物（如香蕉）以促进代谢。`,
                attribution: '归因：最新饮食记录显示钠含量较高。',
                isRead: false
            };
            setAppMessages(prev => [warningMsg, ...prev]);
        }
    }
  }, [meals, dailyTargets.sodium]);

  const handleNavChange = (view: View) => {
    // Guest Mode Guard: Redirect to Login if accessing restricted features
    if (isGuest && view !== View.HOME && view !== View.LOGIN && view !== View.REGISTER && view !== View.FORGOT_PASSWORD && view !== View.SPLASH) {
      setIsGuest(false); // Reset guest mode so user lands on login page freshly
      setCurrentView(View.LOGIN);
      return;
    }
    setCurrentView(view);
  };

  const handleAddMeal = (meal: Meal) => {
    setMeals(prev => [...prev, meal]);
  };

  if (currentView === View.SPLASH) {
    return <SplashScreen isExiting={isTransitioning} />;
  }

  return (
    <div className="relative min-h-screen w-full max-w-md mx-auto bg-gradient-to-b from-[#0c1416] to-[#132320] overflow-hidden flex flex-col">
      {/* Background Overlay Texture */}
      <div 
        className="fixed inset-0 z-0 pointer-events-none opacity-30 mix-blend-overlay"
        style={{
          backgroundImage: 'url("/images/bg-texture.png")'
        }}
      />
      {/* Bottom Mountain Silhouette */}
      <div className="fixed bottom-0 left-0 right-0 h-1/3 bg-[url('/images/bg-texture.png')] bg-cover bg-bottom opacity-20 pointer-events-none z-0 mix-blend-soft-light"></div>

      {/* Main Content Area */}
      <main className="flex-1 relative z-10 overflow-y-auto scroll-smooth no-scrollbar h-full">
        {currentView === View.LOGIN && (
          <LoginView 
            onViewChange={(view) => {
              setIsGuest(false); // Real login
              handleNavChange(view);
            }} 
            onSkipLogin={() => {
              setIsGuest(true);
              setCurrentView(View.HOME);
            }}
          />
        )}
        {currentView === View.REGISTER && (
          <RegisterView 
            onViewChange={(view) => {
              setIsGuest(false); // Real registration
              handleNavChange(view);
            }} 
          />
        )}
        {currentView === View.FORGOT_PASSWORD && (
          <ForgotPasswordView 
            onViewChange={(view) => {
              setIsGuest(false);
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
          />
        )}
        {currentView === View.LOG && (
          <LogView 
            userProfile={userProfile} 
            meals={meals}
            dailyTargets={dailyTargets}
            onAddMeal={handleAddMeal}
          />
        )}
        {currentView === View.CHAT && <ChatView onViewChange={handleNavChange} />}
        {currentView === View.PROFILE && (
          <ProfileView 
            onViewChange={handleNavChange} 
            medicalConditions={medicalConditions}
          />
        )}
        {currentView === View.CAMERA && <CameraView onViewChange={handleNavChange} />}
        {currentView === View.SETTINGS && (
          <SettingsView 
            onViewChange={handleNavChange} 
            userProfile={userProfile}
            onUpdateProfile={setUserProfile}
          />
        )}
        {currentView === View.MESSAGES && (
          <MessageView 
            onViewChange={handleNavChange} 
            messages={appMessages}
          />
        )}
        {currentView === View.MEDICAL_ARCHIVES && (
          <MedicalArchivesView 
            onViewChange={handleNavChange}
            conditions={medicalConditions}
            setConditions={setMedicalConditions}
          />
        )}
        {currentView === View.HEALTH_REPORT_ARCHIVES && <HealthReportArchivesView onViewChange={handleNavChange} />}
      </main>

      {/* Unified Bottom Navigation - Hidden when in auth, camera or specific sub-views */}
      {(
        currentView !== View.SPLASH &&
        currentView !== View.LOGIN &&
        currentView !== View.REGISTER &&
        currentView !== View.FORGOT_PASSWORD &&
        currentView !== View.CAMERA && 
        currentView !== View.SETTINGS && 
        currentView !== View.MESSAGES &&
        currentView !== View.HEALTH_REPORT_ARCHIVES
      ) && (
        <BottomNav currentView={currentView} onViewChange={handleNavChange} />
      )}
    </div>
  );
};

export default App;