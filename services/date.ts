export function getLocalDateString(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function formatChineseDate(dateString: string): string {
  const [year, month, day] = dateString.split('-').map(Number);
  if (!year || !month || !day) return dateString;
  return `${year}年${month}月${day}日`;
}

