export interface DiseaseEntity {
  code: string;
  name: string;
  category: 'chronic' | 'allergy' | 'metabolic' | 'other';
}

export interface DietaryConstraint {
  diseaseCode: string;
  nutrientCode?: string;
  foodId?: string;
  level: 'avoid' | 'limit' | 'prefer' | 'monitor';
  rationale?: string;
  source?: string;
}

