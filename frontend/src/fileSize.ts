/** Размер файла человеку. Один на кабинет и на переписку — иначе «1.5 МБ» в
 *  одном месте и «1,5 MB» в другом появятся сами собой. */
export function formatFileSize(value: number): string {
  if (value < 1024) return `${value} Б`;
  if (value < 1024 * 1024) return `${Math.round(value / 102.4) / 10} КБ`;
  return `${Math.round(value / 1024 / 102.4) / 10} МБ`;
}
