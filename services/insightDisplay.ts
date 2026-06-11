const SMART_INSIGHT_ATTRIBUTION_PREFIX = 'smart-insights:';

const CATEGORY_LABELS: Record<string, string> = {
  MISSING_MEAL: '补录提醒',
  CALORIES: '热量',
  SODIUM: '钠摄入',
  PURINE: '嘌呤',
  MACRO_BALANCE: '营养结构',
  FIBER: '膳食纤维',
  CONDITION_CAUTION: '健康档案',
  POSITIVE_FEEDBACK: '正向反馈',
};

const MESSAGE_TYPE_LABELS: Record<string, string> = {
  WARNING: '预警',
  ADVICE: '建议',
  BRIEF: '简报',
  INFO: '提示',
  insight: '洞察',
};

const MEAL_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

export function isSmartInsightAttribution(value?: string | null): boolean {
  return Boolean(value?.trim().startsWith(SMART_INSIGHT_ATTRIBUTION_PREFIX));
}

function getAttributionValue(attribution: string, key: string): string {
  const match = attribution.match(new RegExp(`(?:^|\\|)${key}=([^|]+)`));
  return match ? decodeURIComponent(match[1]) : '';
}

function formatInsightDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  return `${year}年${month}月${day}日`;
}

export function formatInsightAttribution(value?: string | null): string {
  const text = (value || '').trim();
  if (!text) return '来源：智能洞察';
  if (!isSmartInsightAttribution(text)) return text;

  const date = getAttributionValue(text, 'date');
  const category = getAttributionValue(text, 'category');
  const parts = ['来源：智能洞察'];
  if (date) parts.push(formatInsightDate(date));
  if (CATEGORY_LABELS[category]) parts.push(CATEGORY_LABELS[category]);
  return parts.join(' · ');
}

export function formatInsightTypeLabel(value?: string | null): string {
  const text = (value || '').trim();
  return MESSAGE_TYPE_LABELS[text] || MESSAGE_TYPE_LABELS[text.toUpperCase()] || '洞察';
}

function mealLabel(value?: string): string {
  const normalized = (value || '').trim().toLowerCase();
  return MEAL_LABELS[normalized] || '这一餐';
}

function isAlreadyChinese(value: string): boolean {
  return /[\u4e00-\u9fff]/.test(value);
}

export function formatSmartInsightTitle(title: string, attribution?: string | null): string {
  const text = (title || '').trim();
  if (!text || !isSmartInsightAttribution(attribution) || isAlreadyChinese(text)) return title;

  let match = text.match(/^Log (breakfast|lunch|dinner) before ([0-9:]+)$/i);
  if (match) return `请在 ${match[2]} 前记录${mealLabel(match[1])}`;

  match = text.match(/^Scale back this (breakfast|lunch|dinner)$/i);
  if (match) return `这顿${mealLabel(match[1])}热量偏高`;

  match = text.match(/^Round out this (breakfast|lunch|dinner) a bit more$/i);
  if (match) return `这顿${mealLabel(match[1])}可以再补足一些`;

  match = text.match(/^Add more fiber to (breakfast|lunch|dinner)$/i);
  if (match) return `这顿${mealLabel(match[1])}膳食纤维偏少`;

  match = text.match(/^Add more protein to this (breakfast|lunch|dinner|snack)$/i);
  if (match) return `这顿${mealLabel(match[1])}需要增加蛋白质`;

  match = text.match(/^Lighten the fattier parts of this (breakfast|lunch|dinner|snack)$/i);
  if (match) return `这顿${mealLabel(match[1])}油脂占比偏高`;

  match = text.match(/^Add a stronger protein source to this (breakfast|lunch|dinner|snack)$/i);
  if (match) return `这顿${mealLabel(match[1])}蛋白质偏少`;

  match = text.match(/^Remove flagged items from this (breakfast|lunch|dinner|snack)$/i);
  if (match) return `这顿${mealLabel(match[1])}包含需避开的风险食物`;

  match = text.match(/^Adjust this (breakfast|lunch|dinner|snack) for condition safety$/i);
  if (match) return `根据健康档案调整这顿${mealLabel(match[1])}`;

  const exactTitles: Record<string, string> = {
    'Keep snacks lighter for the rest of today': '今天后续加餐尽量清淡',
    'Lower sodium for the rest of today': '今天后续注意控钠',
    'Keep the rest of today lower purine': '今天后续注意降低嘌呤',
    'Keep this meal pattern going': '继续保持当前饮食节奏',
  };
  return exactTitles[text] || title;
}

export function formatSmartInsightContent(content: string, attribution?: string | null): string {
  const text = (content || '').trim();
  if (!text || !isSmartInsightAttribution(attribution) || isAlreadyChinese(text)) return content;

  let match = text.match(/^The (breakfast|lunch|dinner) window is open until ([0-9:]+)\. Add it now so today's coaching stays accurate\.$/i);
  if (match) return `${mealLabel(match[1])}记录窗口会持续到 ${match[2]}。现在补充这一餐，今天的建议会更准确。`;

  match = text.match(/^This snack logged ([0-9.]+) kcal, above your ([0-9.]+) kcal snack threshold\. Next step: skip one extra add-on or choose a lighter option later today\.$/i);
  if (match) return `加餐已记录约 ${match[1]} kcal，高于 ${match[2]} kcal 的加餐参考线。下一步：今天后续少加一项高热量配料，或选择更清淡的食物。`;

  match = text.match(/^This (breakfast|lunch|dinner) logged ([0-9.]+) kcal, above your ([0-9.]+)-([0-9.]+) kcal target band\. Next step: trim one calorie-dense item or portion next time\.$/i);
  if (match) return `这顿${mealLabel(match[1])}记录约 ${match[2]} kcal，高于 ${match[3]}-${match[4]} kcal 的目标区间。下一步：下次减少一项高热量食物或适当减量。`;

  match = text.match(/^This (breakfast|lunch|dinner) logged ([0-9.]+) kcal, below your ([0-9.]+)-([0-9.]+) kcal target band\. Next step: add a balanced side like protein, fruit, or a staple portion\.$/i);
  if (match) return `这顿${mealLabel(match[1])}记录约 ${match[2]} kcal，低于 ${match[3]}-${match[4]} kcal 的目标区间。下一步：可补充一份优质蛋白、水果或适量主食。`;

  match = text.match(/^You've logged ([0-9.]+) mg sodium, above your ([0-9.]+) mg daily limit\. Next step: skip extra sauces and choose lower-sodium foods for later meals\.$/i);
  if (match) return `今天已记录约 ${match[1]} mg 钠，高于 ${match[2]} mg 的每日上限。下一步：后续餐食少放酱料和汤汁，优先选择低钠食物。`;

  match = text.match(/^You've logged ([0-9.]+) mg purine, above your gout-focused ([0-9.]+) mg limit\. Next step: avoid more high-purine choices like beer or organ meats in later meals\.$/i);
  if (match) return `今天已记录约 ${match[1]} mg 嘌呤，高于痛风管理参考上限 ${match[2]} mg。下一步：后续餐食避开啤酒、动物内脏、浓肉汤等高嘌呤选择。`;

  match = text.match(/^This (breakfast|lunch|dinner) logged ([0-9.]+) g fiber\. Next step: add vegetables, beans, fruit, or whole grains to bring it up\.$/i);
  if (match) return `这顿${mealLabel(match[1])}记录约 ${match[2]} g 膳食纤维。下一步：可增加蔬菜、豆类、水果或全谷物。`;

  match = text.match(/^This (breakfast|lunch|dinner|snack) skews carb heavy\. Next step: pair the starch-heavy items with lean protein or extra vegetables\.$/i);
  if (match) return `这顿${mealLabel(match[1])}主食或碳水占比偏高。下一步：把主食搭配优质蛋白或更多蔬菜。`;

  match = text.match(/^This (breakfast|lunch|dinner|snack) skews fat heavy\. Next step: swap one fried, oily, or creamy item for a leaner choice\.$/i);
  if (match) return `这顿${mealLabel(match[1])}油脂占比偏高。下一步：把一项油炸、重油或奶油类食物换成更清淡的选择。`;

  match = text.match(/^This (breakfast|lunch|dinner|snack) is light on protein\. Next step: add eggs, tofu, dairy, fish, or another protein source\.$/i);
  if (match) return `这顿${mealLabel(match[1])}蛋白质偏少。下一步：可加入鸡蛋、豆腐、奶制品、鱼肉或其他蛋白来源。`;

  if (text === "Today's logged meals stayed within current rules. Repeat similar portions and meal choices next time.") {
    return '今天已记录餐食均在当前规则范围内。下次可以延续类似份量和食物搭配。';
  }

  match = text.match(/^Check .+ before repeating this (breakfast|lunch|dinner|snack)\. Next step: avoid the flagged items and choose a safer swap\..*$/i);
  if (match) return `再次选择前，请先确认这顿${mealLabel(match[1])}中的风险食物。下一步：避开已标记食物，并选择更安全的替代项。请以健康档案中的过敏和慢病规则为准。`;

  match = text.match(/^Check .+ before repeating this (breakfast|lunch|dinner|snack)\. Next step: limit or swap the flagged items\..*$/i);
  if (match) return `再次选择前，请先确认这顿${mealLabel(match[1])}中的风险食物。下一步：减少份量或替换已标记食物。请以健康档案中的过敏和慢病规则为准。`;

  return content;
}
