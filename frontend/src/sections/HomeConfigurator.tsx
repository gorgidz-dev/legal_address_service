/**
 * Конфигуратор подбора адреса под задачу.
 *
 * Раскладка: строка общего поиска → ряд Регион/Город/ИФНС → ряд Срок/Цена/Доп.
 * Пишет фильтры в общий `filters`-state главной (конфигуратор и filter-бар
 * работают на один state).
 */
import { ArrowDown, Calendar, Mail, MapPin, Search, Wallet, X } from "lucide-react";
import { useMemo } from "react";
import type { GeoRegion } from "../types";
import { GeoCascade, type GeoSelection } from "./GeoCascade";

export type ConfiguratorFilters = {
  query: string;
  region: string;
  geoCity: string;
  fnsOfficeId: string;
  priceFrom: string;
  priceTo: string;
  withCorr: boolean;
};

export type ConfiguratorProps = {
  filters: ConfiguratorFilters;
  onChange: (next: ConfiguratorFilters) => void;
  termMonths: 6 | 11;
  onTermChange: (term: 6 | 11) => void;
  geoTree: GeoRegion[];
  totalCount: number;
  loading: boolean;
  /** Скролл к гриду с результатами. */
  onShowResults: () => void;
  /** Сброс всех фильтров поиска. */
  onReset: () => void;
  /** Открыть модалку поиска на карте. */
  onOpenMap: () => void;
};

/** Оставляет в строке только цифры (для числовых инпутов цены). */
function digitsOnly(value: string): string {
  return value.replace(/\D/g, "");
}

export function HomeConfigurator({
  filters,
  onChange,
  termMonths,
  onTermChange,
  geoTree,
  totalCount,
  loading,
  onShowResults,
  onReset,
  onOpenMap,
}: ConfiguratorProps) {
  const hasAny = Boolean(
    filters.query.trim() ||
      filters.region ||
      filters.geoCity ||
      filters.fnsOfficeId ||
      filters.priceFrom ||
      filters.priceTo ||
      filters.withCorr,
  );
  const resultLabel = useMemo(() => {
    if (loading) return "Считаем подходящие адреса…";
    if (totalCount === 0) return "По заданным параметрам ничего не нашлось";
    if (totalCount === 1) return "Найден 1 адрес";
    if (
      totalCount % 10 >= 2 &&
      totalCount % 10 <= 4 &&
      (totalCount % 100 < 12 || totalCount % 100 > 14)
    )
      return `Найдено ${totalCount} адреса`;
    return `Найдено ${totalCount} адресов`;
  }, [totalCount, loading]);

  return (
    <section className="ds-configurator" aria-label="Подбор адреса под задачу">
      <header className="ds-configurator__head">
        <div>
          <h2 className="ds-configurator__title">Подберём адрес под задачу</h2>
          <p className="ds-configurator__sub">
            Расскажи параметры — покажем подходящие. Все адреса с гарантийным
            письмом и свежей выпиской ЕГРН.
          </p>
        </div>
      </header>

      <div className="ds-configurator__grid">
        {/* Строка общего поиска + кнопка поиска на карте */}
        <div className="ds-configurator__field" data-span="3">
          <span className="ds-configurator__label">
            <Search size={14} /> По адресу или ИФНС
          </span>
          <div className="ds-configurator__search-row">
            <input
              type="search"
              placeholder="Например: «Тверская» или «46»"
              value={filters.query}
              onChange={(e) => onChange({ ...filters, query: e.target.value })}
              className="ds-configurator__input"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="button"
              className="ds-configurator__map-btn"
              onClick={onOpenMap}
            >
              <MapPin size={16} /> На карте
            </button>
          </div>
        </div>

        {/* Ряд: Регион → Город → ИФНС */}
        <GeoCascade
          tree={geoTree}
          value={{
            region: filters.region,
            geoCity: filters.geoCity,
            fnsOfficeId: filters.fnsOfficeId,
          }}
          onChange={(geo: GeoSelection) => onChange({ ...filters, ...geo })}
        />

        {/* Ряд: Срок → Цена → Дополнительно */}
        <fieldset className="ds-configurator__field">
          <legend className="ds-configurator__label">
            <Calendar size={14} /> Срок аренды
          </legend>
          <div className="ds-configurator__segmented" role="group">
            <button
              type="button"
              className={`ds-configurator__seg${termMonths === 6 ? " ds-configurator__seg--active" : ""}`}
              onClick={() => onTermChange(6)}
            >
              6 мес.
            </button>
            <button
              type="button"
              className={`ds-configurator__seg${termMonths === 11 ? " ds-configurator__seg--active" : ""}`}
              onClick={() => onTermChange(11)}
            >
              11 мес.
            </button>
          </div>
        </fieldset>

        <fieldset className="ds-configurator__field">
          <legend className="ds-configurator__label">
            <Wallet size={14} /> Цена за 11 месяцев, ₽
          </legend>
          <div className="ds-configurator__price">
            <input
              type="text"
              inputMode="numeric"
              placeholder="от"
              className="ds-configurator__input"
              value={filters.priceFrom}
              onChange={(e) =>
                onChange({ ...filters, priceFrom: digitsOnly(e.target.value) })
              }
            />
            <span className="ds-configurator__price-dash">—</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="до"
              className="ds-configurator__input"
              value={filters.priceTo}
              onChange={(e) =>
                onChange({ ...filters, priceTo: digitsOnly(e.target.value) })
              }
            />
          </div>
        </fieldset>

        <fieldset className="ds-configurator__field">
          <legend className="ds-configurator__label">Дополнительно</legend>
          <div className="ds-configurator__opts">
            <button
              type="button"
              className={`ds-chip${filters.withCorr ? " ds-chip--active" : ""}`}
              onClick={() => onChange({ ...filters, withCorr: !filters.withCorr })}
            >
              <Mail size={18} /> С почтой
            </button>
          </div>
        </fieldset>
      </div>

      <footer className="ds-configurator__foot">
        <span className="ds-configurator__count" aria-live="polite">
          {resultLabel}
        </span>
        <div className="ds-configurator__foot-actions">
          {hasAny && (
            <button
              type="button"
              className="ds-btn ds-btn--ghost ds-btn--md"
              onClick={onReset}
            >
              <X size={14} /> Сбросить
            </button>
          )}
          <button
            type="button"
            className="ds-btn ds-btn--primary ds-btn--md"
            onClick={onShowResults}
            disabled={totalCount === 0 && !loading}
          >
            Показать все
            <ArrowDown size={14} />
          </button>
        </div>
      </footer>
    </section>
  );
}
