export type NutrientCode = 'calories' | 'protein' | 'carbs' | 'fat' | 'fiber' | 'sodium' | 'purine';

export interface FoodEntity {
  id: string;
  name: string;
  aliases?: string[];
  defaultUnit?: 'g' | 'ml' | 'serving' | 'piece';
  source?: string;
}

export interface NutrientProfile {
  foodId: string;
  perAmount: number;
  unit: 'g' | 'ml' | 'serving' | 'piece';
  nutrients: Partial<Record<NutrientCode, number>>;
  source?: string;
}

