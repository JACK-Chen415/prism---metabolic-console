import { AppMessage, ConditionData, Meal, UserProfile } from '../types';

export const GUEST_USER_PROFILE: UserProfile = {
  gender: 'MALE',
  age: 28,
  height: 175,
  weight: 70,
  nickname: '游客',
};

export const GUEST_MEDICAL_DATA: ConditionData[] = [
  {
    id: 'demo-hypertension',
    conditionCode: 'hypertension',
    title: '高血压',
    icon: 'cardiology',
    status: 'MONITORING',
    trend: 'STABLE',
    value: '128/82',
    unit: 'mmHg',
    dictum: '演示档案仅用于游客预览。',
    attribution: '登录后请维护真实健康档案，AI 建议才会结合个人约束。',
    type: 'CHRONIC',
  },
];

export const GUEST_MEALS: Meal[] = [
  {
    id: 'guest-breakfast',
    clientId: 'guest-breakfast',
    name: '全麦吐司和鸡蛋',
    portion: '1份',
    calories: 350,
    sodium: 360,
    purine: 45,
    type: 'BREAKFAST',
    category: 'STAPLE',
    note: '游客演示数据',
  },
];

export const GUEST_APP_MESSAGES: AppMessage[] = [
  {
    id: 0,
    type: 'ADVICE',
    title: '游客模式',
    time: '现在',
    content: '当前展示的是演示数据。登录后会读取你的真实饮食记录、健康档案和 AI 消息。',
    attribution: '演示数据不会保存，也不会参与真实健康建议。',
    isRead: false,
  },
];

