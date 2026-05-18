/**
 * Конфигуратор подбора адреса под задачу.
 *
 * Большая карточка под hero. Принимает все ключевые фильтры (ИФНС, бюджет,
 * срок, корреспонденция, премиум) и пишет их в общий `filters`-state главной.
 * Поэтому конфигуратор и filter-бар у грида работают на один state — рассинхрона
 * быть не может.
 *
 * Live-счётчик «N адресов» — это `totalCount`, который дёргается из
 * /marketplace/addresses/search с debounce.
 */
import { ArrowDown, Calendar, Search, Wallet } from "lucide-react";
import { useMemo } from "react";
import type { GeoRegion } from "../types";
import { GeoCascade, type GeoSelection } from "./GeoCascade";

export type ConfiguratorFilters = {
  query: string;
  region: string;
  geoCity: string;
  fnsOfficeId: string;
  withCorr: boolean;
  budgetUnder30k: boolean;
  premium11: boolean;
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
};

export function HomeConfigurator({
  filters,
  onChange,
  termMonths,
  onTermChange,
  geoTree,
  totalCount,
  loading,
  onShowResults,
}: ConfiguratorProps) {
  const resultLabel = useMemo(() => {
    if (loading) return "Считаем подходящие адреса…";
    if (totalCount === 0) return "По заданным параметрам ничего не нашлось";
    if (totalCount === 1) return "Найден 1 адрес";
    if (totalCount % 10 >= 2 && totalCount % 10 <= 4 && (totalCount % 100 < 12 || totalCount % 100 > 14))
      return `Найдено ${totalCount} адреса`;
    return `Найдено ${totalCount} адресов`;
  }, [totalCount, loading]);

  return (
    <section className="ds-configurator" aria-label="Подбор адреса под задачу">
      <header className="ds-configurator__head">
        <div>
          <h2 className="ds-configurator__title">Подберём адрес под задачу</h2>
          <p className="ds-configurator__sub">
            Расскажи параметры — покажем подходящие. Все адреса с гарантийным письмом и
            свежей выпиской ЕГРН.
          </p>
        </div>
      </header>

      <div className="ds-configurator__grid">
        {/* Текстовый поиск */}
        <label className="ds-configurator__field" data-span="2">
          <span className="ds-configurator__label">
            <Search size={14} /> По адресу или ИФНС
          </span>
          <input
            type="search"
            placeholder="Например: «Тверская» или «46»"
            value={filters.query}
            onChange={(e) => onChange({ ...filters, query: e.target.value })}
            className="ds-configurator__input"
            autoComplete="off"
            spellCheck={false}
          />
        </label>

        {/* Каскад Регион → Город → ИФНС */}
        <GeoCascade
          tree={geoTree}
          value={{
            region: filters.region,
            geoCity: filters.geoCity,
            fnsOfficeId: filters.fnsOfficeId,
          }}
          onChange={(geo: GeoSelection) => onChange({ ...filters, ...geo })}
        />

        {/* Срок */}
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

        {/* Бюджет — пресеты */}
        <fieldset className="ds-configurator__field" data-span="2">
          <legend className="ds-configurator__label">
            <Wallet size={14} /> Бюджет на 11 месяцев
          </legend>
          <div className="ds-configurator__budget">
            <button
              type="button"
              className={`ds-chip${
                filters.budgetUnder30k ? " ds-chip--active" : ""
              }`}
              onClick={() =>
                onChange({
                  ...filters,
                  budgetUnder30k: !filters.budgetUnder30k,
                  premium11: false,
                })
              }
            >
              До 30 000 ₽
            </button>
            <button
              type="button"
              className={`ds-chip${filters.premium11 ? " ds-chip--active" : ""}`}
              onClick={() =>
                onChange({
                  ...filters,
                  premium11: !filters.premium11,
                  budgetUnder30k: false,
                })
              }
            >
              Премиум от 25 000 ₽
            </button>
            <button
              type="button"
              className={`ds-chip${
                !filters.budgetUnder30k && !filters.premium11 ? " ds-chip--active" : ""
              }`}
              onClick={() =>
                onChange({ ...filters, budgetUnder30k: false, premium11: false })
              }
            >
              Любой
            </button>
          </div>
        </fieldset>

        {/* Опции */}
        <fieldset className="ds-configurator__field" data-span="2">
          <legend className="ds-configurator__label">Дополнительно</legend>
          <div className="ds-configurator__opts">
            <button
              type="button"
              className={`ds-chip${filters.withCorr ? " ds-chip--active" : ""}`}
              onClick={() => onChange({ ...filters, withCorr: !filters.withCorr })}
            >
              ✉ С корреспонденцией
            </button>
          </div>
        </fieldset>
      </div>

      <footer className="ds-configurator__foot">
        <span className="ds-configurator__count" aria-live="polite">
          {resultLabel}
        </span>
        <button
          type="button"
          className="ds-btn ds-btn--primary ds-btn--md"
          onClick={onShowResults}
          disabled={totalCount === 0 && !loading}
        >
          Показать все
          <ArrowDown size={14} />
        </button>
      </footer>
    </section>
  );
}
