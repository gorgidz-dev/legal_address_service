/**
 * Модалка «Поиск на карте» — показывает адреса каталога метками на Яндекс.Карте.
 *
 * JS API Яндекс.Карт грузится лениво (один раз на страницу) с ключом из
 * VITE_YANDEX_MAPS_KEY. Клик по метке выбирает адрес (onSelectAddress) —
 * родитель открывает карточку адреса.
 *
 * Адреса без координат (latitude/longitude === null) на карту не попадают.
 */
import { Loader2, MapPin, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { PublicAddress } from "../types";

type Props = {
  open: boolean;
  addresses: PublicAddress[];
  onClose: () => void;
  onSelectAddress: (address: PublicAddress) => void;
};

const YANDEX_KEY = import.meta.env.VITE_YANDEX_MAPS_KEY as string | undefined;

// Глобальный промис загрузки JS API — чтобы скрипт подключался один раз.
let ymapsPromise: Promise<unknown> | null = null;

function loadYandexMaps(): Promise<unknown> {
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

function formatPrice(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return `${Math.round(n).toLocaleString("ru-RU")} ₽`;
}

export function AddressMapModal({
  open,
  addresses,
  onClose,
  onSelectAddress,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mapRef = useRef<any>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "no-key" | "error">(
    "loading",
  );

  const located = addresses.filter(
    (a) => a.latitude != null && a.longitude != null,
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setStatus("loading");

    loadYandexMaps()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .then((ymaps: any) => {
        if (cancelled || !containerRef.current) return;
        // Пересоздаём карту при каждом открытии — контейнер новый.
        const map = new ymaps.Map(containerRef.current, {
          center: [55.751244, 37.618423], // Москва — дефолт
          zoom: 5,
          controls: ["zoomControl", "geolocationControl"],
        });
        mapRef.current = map;

        const collection = new ymaps.GeoObjectCollection();
        located.forEach((address) => {
          const placemark = new ymaps.Placemark(
            [address.latitude, address.longitude],
            {
              hintContent: address.full_address,
              balloonContentHeader: address.full_address,
              balloonContentBody: `Цена за 11 мес.: <b>${formatPrice(
                address.price_11m,
              )}</b>`,
              balloonContentFooter:
                "<span style='color:#4F46E5'>Клик по метке — открыть карточку</span>",
            },
            { preset: "islands#violetDotIcon" },
          );
          placemark.events.add("click", () => {
            onSelectAddress(address);
          });
          collection.add(placemark);
        });
        map.geoObjects.add(collection);

        // Подгоняем масштаб под все метки.
        if (located.length > 0) {
          const bounds = collection.getBounds();
          if (bounds) {
            map.setBounds(bounds, { checkZoomRange: true, zoomMargin: 40 });
          }
        }
        setStatus("ready");
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setStatus(err.message === "no-key" ? "no-key" : "error");
      });

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
    };
    // located пересчитывается из addresses; open триггерит re-init.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, addresses]);

  // Esc закрывает модалку.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="ds-mapmodal__overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Поиск адресов на карте"
      onClick={onClose}
    >
      <div className="ds-mapmodal" onClick={(e) => e.stopPropagation()}>
        <header className="ds-mapmodal__head">
          <h3 className="ds-mapmodal__title">
            <MapPin size={18} /> Адреса на карте
          </h3>
          <span className="ds-mapmodal__count">
            {located.length} из {addresses.length} с координатами
          </span>
          <button
            type="button"
            className="ds-mapmodal__close"
            onClick={onClose}
            aria-label="Закрыть"
          >
            <X size={18} />
          </button>
        </header>

        <div className="ds-mapmodal__body">
          <div ref={containerRef} className="ds-mapmodal__map" />
          {status !== "ready" && (
            <div className="ds-mapmodal__state">
              {status === "loading" && (
                <>
                  <Loader2 className="spin" size={22} />
                  <span>Загружаем карту…</span>
                </>
              )}
              {status === "no-key" && (
                <span>
                  Карта недоступна: не задан ключ Яндекс.Карт
                  (VITE_YANDEX_MAPS_KEY).
                </span>
              )}
              {status === "error" && (
                <span>Не удалось загрузить Яндекс.Карты. Попробуйте позже.</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
