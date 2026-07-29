/**
 * Ленивая загрузка JS API Яндекс.Карт — общая для модалки поиска на карте и
 * мини-карты в карточке адреса.
 *
 * Промис глобальный: скрипт подключается один раз на страницу, сколько бы
 * карт её ни открывало. Без этого открытие карточки после поиска на карте
 * тянуло бы api-maps второй раз.
 */
export const YANDEX_KEY = import.meta.env.VITE_YANDEX_MAPS_KEY as string | undefined;

let ymapsPromise: Promise<unknown> | null = null;

export function loadYandexMaps(): Promise<unknown> {
  if (ymapsPromise) return ymapsPromise;
  ymapsPromise = new Promise((resolve, reject) => {
    if (!YANDEX_KEY) {
      reject(new Error("no-key"));
      return;
    }
    const w = window as unknown as { ymaps?: { ready: (cb: () => void) => void } };
    if (w.ymaps) {
      w.ymaps.ready(() => resolve(w.ymaps));
      return;
    }
    const script = document.createElement("script");
    script.src = `https://api-maps.yandex.ru/2.1/?apikey=${YANDEX_KEY}&lang=ru_RU`;
    script.async = true;
    script.onload = () => {
      const ww = window as unknown as { ymaps?: { ready: (cb: () => void) => void } };
      if (ww.ymaps) ww.ymaps.ready(() => resolve(ww.ymaps));
      else reject(new Error("load-failed"));
    };
    script.onerror = () => reject(new Error("load-failed"));
    document.head.appendChild(script);
  });
  return ymapsPromise;
}
