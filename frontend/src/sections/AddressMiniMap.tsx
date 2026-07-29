/**
 * Мини-карта одного адреса — вкладка «На карте» в карточке.
 *
 * Отдельной вкладкой, а не полосой под фото: JS API Яндекс.Карт весит больше,
 * чем вся остальная страница, и грузить его при каждом открытии карточки ради
 * блока, который увидят не все, — плохой размен. Здесь скрипт подключается
 * только когда вкладку открыли (`active`).
 *
 * Координат нет у части адресов (geocode_addresses.py прогоняется отдельно) —
 * в этом случае вкладка не показывается вовсе, решение принимает родитель.
 */
import { Loader2, MapPin } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { loadYandexMaps } from "./yandexMaps";

type Props = {
  latitude: number;
  longitude: number;
  /** Подпись метки — полный адрес. */
  title: string;
  /** Вкладка открыта. Пока false, карта не инициализируется. */
  active: boolean;
};

export function AddressMiniMap({ latitude, longitude, title, active }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mapRef = useRef<any>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "no-key" | "error">(
    "loading",
  );

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setStatus("loading");

    loadYandexMaps()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .then((ymaps: any) => {
        if (cancelled || !containerRef.current) return;
        const map = new ymaps.Map(containerRef.current, {
          center: [latitude, longitude],
          zoom: 16,
          controls: ["zoomControl"],
        });
        // Скролл страницы важнее зума: карточка длинная, и «залипание»
        // колеса на карте мешало бы дочитать её до конца.
        map.behaviors.disable("scrollZoom");
        map.geoObjects.add(
          new ymaps.Placemark(
            [latitude, longitude],
            { hintContent: title, balloonContent: title },
            { preset: "islands#violetDotIconWithCaption" },
          ),
        );
        mapRef.current = map;
        setStatus("ready");
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setStatus(error.message === "no-key" ? "no-key" : "error");
      });

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
    };
  }, [active, latitude, longitude, title]);

  if (!active) return null;

  return (
    <div className="ds-address-detail__map">
      <div className="ds-address-detail__map-canvas" ref={containerRef} />
      {status !== "ready" && (
        <div className="ds-address-detail__map-state">
          {status === "loading" ? (
            <>
              <Loader2 className="spin" size={18} /> Загружаем карту…
            </>
          ) : status === "no-key" ? (
            <>
              <MapPin size={18} /> Карта недоступна — не настроен ключ Яндекс.Карт.
            </>
          ) : (
            <>
              <MapPin size={18} /> Карта не загрузилась. Адрес: {title}
            </>
          )}
        </div>
      )}
    </div>
  );
}
