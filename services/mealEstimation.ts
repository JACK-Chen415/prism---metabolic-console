import { FoodCategory, Meal } from '../types';

type MealInput = {
  name: string;
  portion: string;
  type: Meal['type'];
  category: FoodCategory;
  note: string;
};

const CATEGORY_BASELINE: Record<FoodCategory, { calories: number; sodium: number; purine: number }> = {
  STAPLE: { calories: 240, sodium: 90, purine: 28 },
  MEAT: { calories: 260, sodium: 180, purine: 130 },
  VEG: { calories: 95, sodium: 25, purine: 12 },
  DRINK: { calories: 75, sodium: 15, purine: 8 },
  SNACK: { calories: 210, sodium: 160, purine: 20 },
};

export function estimateMealNutrition(input: MealInput): Pick<Meal, 'calories' | 'sodium' | 'purine'> {
  const portionNum = Number.parseFloat((input.portion || '').replace(/[^\d.]/g, ''));
  const multiplier = !Number.isNaN(portionNum) && portionNum > 0 ? Math.min(Math.max(portionNum / 100, 0.5), 3) : 1;
  const baseline = CATEGORY_BASELINE[input.category];

  let calories = Math.round(baseline.calories * multiplier);
  let sodium = Math.round(baseline.sodium * multiplier);
  let purine = Math.round(baseline.purine * multiplier);

  if (input.note) {
    const note = input.note;
    if (note.includes('咸') || note.includes('盐') || note.includes('酱') || note.includes('卤')) sodium += 300;
    if (note.includes('油') || note.includes('炸') || note.includes('煎') || note.includes('肥')) calories += 100;
    if (note.includes('汤') || note.includes('内脏') || note.includes('海鲜')) purine += 80;
    if (note.includes('辣')) {
      sodium += 50;
      calories += 30;
    }
  }

  return { calories, sodium, purine };
}

