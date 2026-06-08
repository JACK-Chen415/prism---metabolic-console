import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path) => readFileSync(resolve(repoRoot, path), 'utf8');

test('favorite meals expose typed API client methods and shared type', () => {
  const typeSource = read('types.ts');
  const apiSource = read('services/api.ts');

  for (const required of [
    'export interface FavoriteMeal',
    'source_meal_id?: number | null',
    "meal_type: Meal['type']",
    'usage_count: number',
    'last_used_at?: string | null',
  ]) {
    assert.ok(typeSource.includes(required), `Missing FavoriteMeal type contract: ${required}`);
  }

  for (const required of [
    'listFavorites: (limit = 20)',
    'apiClient.get<FavoriteMeal[]>(`/meals/favorites?limit=${limit}`)',
    'favoriteMeal: (mealId: string | number)',
    'apiClient.post<FavoriteMeal>(`/meals/${mealId}/favorite`, {})',
    'useFavorite: (favoriteId: number)',
    'apiClient.post<FavoriteMeal>(`/meals/favorites/${favoriteId}/use`, {})',
    'deleteFavorite: (favoriteId: number)',
    'apiClient.delete(`/meals/favorites/${favoriteId}`)',
  ]) {
    assert.ok(apiSource.includes(required), `Missing FavoriteMeal API contract: ${required}`);
  }
});

test('log view lets users save and reuse favorite meals without bypassing confirmation', () => {
  const logSource = read('components/views/LogView.tsx');

  for (const required of [
    'FavoriteMeal',
    'normalizeFavoriteMealList',
    'favoriteMealToInput',
    'upsertFavoriteMeal',
    'loadFavoriteMealTemplates',
    'MealsAPI.listFavorites(20)',
    'favoriteMeals',
    'isLoadingFavoriteMeals',
    'favoriteMealsError',
    'saveMealAsFavorite',
    'MealsAPI.favoriteMeal(meal.id)',
    'useFavoriteMealTemplate',
    'MealsAPI.useFavorite(favorite.id)',
    'deleteFavoriteMealTemplate',
    'MealsAPI.deleteFavorite(favorite.id)',
    '收藏餐',
    '加入收藏餐',
    '移除收藏餐',
    '一键复记并编辑',
    '已填入收藏餐，可继续编辑后保存。',
    '暂未收藏餐',
  ]) {
    if (required === '暂未收藏餐') continue;
    assert.ok(logSource.includes(required), `Missing favorite meal log-view contract: ${required}`);
  }

  assert.ok(logSource.includes('暂无收藏餐，可在已记录餐食卡片点击收藏。'), 'Favorite empty state should tell users where to save templates');
  assert.ok(logSource.includes("disabled={!canFavoriteThisMeal || Boolean(favoriteActionId)}"), 'Unsynced/offline meals should not be sent to server favorite endpoint');
  assert.ok(logSource.includes("return syncStatus === 'SYNCED' && Number.isFinite(Number(meal.id));"), 'Favorite save should require synced numeric backend meal id');

  const useStart = logSource.indexOf('const useFavoriteMealTemplate');
  const useEnd = logSource.indexOf('const deleteFavoriteMealTemplate', useStart);
  const useSource = logSource.slice(useStart, useEnd);
  for (const required of [
    'setMealInput(favoriteMealToInput(favorite))',
    'setPreMealSimulation(EMPTY_PRE_MEAL_SIMULATION)',
    'MealsAPI.useFavorite(favorite.id)',
    'setFavoriteMeals(previous => upsertFavoriteMeal(previous, updatedFavorite))',
  ]) {
    assert.ok(useSource.includes(required), `Favorite use should preserve editable confirmation flow: ${required}`);
  }
  assert.equal(useSource.includes('onAddMeal'), false, 'Favorite use must not create a meal directly');
  assert.equal(useSource.includes('setIsAdding(false)'), false, 'Favorite use should keep the add modal open for editing before save');

  const helperStart = logSource.indexOf('const favoriteMealToInput');
  const helperEnd = logSource.indexOf('const upsertFavoriteMeal', helperStart);
  const helperSource = logSource.slice(helperStart, helperEnd);
  for (const field of ['name: favorite.name', "portion: favorite.portion || '1份'", 'type: favorite.meal_type', 'category: favorite.category', "note: favorite.note || ''"]) {
    assert.ok(helperSource.includes(field), `Favorite template should map editable field: ${field}`);
  }

  const deleteStart = logSource.indexOf('const deleteFavoriteMealTemplate');
  const deleteEnd = logSource.indexOf('const runPreMealSimulation', deleteStart);
  const deleteSource = logSource.slice(deleteStart, deleteEnd);
  assert.ok(deleteSource.includes('event.stopPropagation()'), 'Deleting a favorite should not also trigger template use');
});

test('backend favorite meal routes are user scoped and audit metadata is allowlisted', () => {
  const routeSource = read('backend/app/api/routes/meals.py');
  const modelSource = read('backend/app/models/meal.py');
  const schemaSource = read('backend/app/schemas/meal.py');

  for (const required of [
    'class FavoriteMeal',
    '__tablename__ = "favorite_meals"',
    'UniqueConstraint("user_id", "name", "portion", "meal_type"',
    'usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)',
    'last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)',
  ]) {
    assert.ok(modelSource.includes(required), `Missing favorite meal model contract: ${required}`);
  }

  assert.ok(schemaSource.includes('class FavoriteMealResponse'), 'FavoriteMealResponse schema should exist');

  for (const required of [
    '@router.get("/favorites", response_model=List[FavoriteMealResponse])',
    '@router.post("/{meal_id}/favorite", response_model=FavoriteMealResponse, status_code=status.HTTP_201_CREATED)',
    '@router.post("/favorites/{favorite_id}/use", response_model=FavoriteMealResponse)',
    '@router.delete("/favorites/{favorite_id}")',
    'FavoriteMeal.user_id == current_user.id',
    'favorite.usage_count += 1',
    'favorite.last_used_at = datetime.now(timezone.utc)',
    'audit_security_event(',
  ]) {
    assert.ok(routeSource.includes(required), `Missing favorite meal route contract: ${required}`);
  }

  const auditStart = routeSource.indexOf('def _favorite_audit_metadata');
  const auditEnd = routeSource.indexOf('@router.get("/favorites"', auditStart);
  const auditSource = routeSource.slice(auditStart, auditEnd);
  for (const allowed of ['"favorite_id"', '"source_meal_id"', '"meal_type"', '"category"', '"usage_count"']) {
    assert.ok(auditSource.includes(allowed), `Favorite audit metadata should include allowlisted key: ${allowed}`);
  }
  for (const forbidden of ['"name"', '"note"']) {
    assert.equal(auditSource.includes(forbidden), false, `Favorite audit metadata must not include raw sensitive field: ${forbidden}`);
  }
});
