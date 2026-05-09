import {
  Building2,
  CheckCircle2,
  FileText,
  KeyRound,
  Loader2,
  Mail,
  MapPin,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { ProviderConnectionRequestCreate, PublicAddress } from "./types";

type PublicCatalogProps = {
  canBootstrap: boolean;
  onLoginClick: () => void;
};

type CatalogFilters = {
  city: string;
  fnsNumber: string;
  termMonths: 6 | 11;
  correspondence: boolean;
};

type OwnerRequestForm = {
  company_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  city: string;
  address_count: string;
  comment: string;
};

const initialOwnerRequestForm: OwnerRequestForm = {
  company_name: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
  city: "",
  address_count: "",
  comment: ""
};

function formatMoney(value: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0
  }).format(amount);
}

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export default function PublicCatalog({ canBootstrap, onLoginClick }: PublicCatalogProps) {
  const [filters, setFilters] = useState<CatalogFilters>({
    city: "",
    fnsNumber: "",
    termMonths: 11,
    correspondence: false
  });
  const [addresses, setAddresses] = useState<PublicAddress[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ownerForm, setOwnerForm] = useState<OwnerRequestForm>(initialOwnerRequestForm);
  const [ownerBusy, setOwnerBusy] = useState(false);
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [ownerSuccess, setOwnerSuccess] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .publicAddresses({
        city: filters.city.trim(),
        fns_number: filters.fnsNumber ? Number(filters.fnsNumber) : "",
        term_months: filters.termMonths,
        correspondence: filters.correspondence
      })
      .then((result) => {
        if (alive) setAddresses(result);
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [filters.city, filters.fnsNumber, filters.termMonths, filters.correspondence]);

  const cities = useMemo(() => {
    const values = new Set<string>();
    for (const address of addresses) {
      const match = address.full_address.match(/г\.\s*([^,]+)/i);
      if (match?.[1]) values.add(match[1].trim());
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b, "ru"));
  }, [addresses]);

  const hasActiveFilters = Boolean(filters.city.trim() || filters.fnsNumber || filters.correspondence);

  async function submitOwnerRequest(event: FormEvent) {
    event.preventDefault();
    setOwnerBusy(true);
    setOwnerError(null);
    setOwnerSuccess(false);
    const payload: ProviderConnectionRequestCreate = {
      company_name: ownerForm.company_name.trim(),
      contact_name: ownerForm.contact_name.trim(),
      contact_email: ownerForm.contact_email.trim(),
      contact_phone: normalizeOptional(ownerForm.contact_phone),
      city: normalizeOptional(ownerForm.city),
      address_count: ownerForm.address_count ? Number(ownerForm.address_count) : null,
      comment: normalizeOptional(ownerForm.comment)
    };
    try {
      await api.createProviderConnectionRequest(payload);
      setOwnerForm(initialOwnerRequestForm);
      setOwnerSuccess(true);
    } catch (err) {
      setOwnerError((err as Error).message);
    } finally {
      setOwnerBusy(false);
    }
  }

  return (
    <main className="public-shell">
      <header className="public-topbar">
        <div className="brand">
          <div className="brand-mark">ЮА</div>
          <div>
            <strong>Юридический адрес</strong>
            <span>маркетплейс проверенных помещений</span>
          </div>
        </div>
        <button className="btn secondary" onClick={onLoginClick} type="button">
          <KeyRound size={16} />
          {canBootstrap ? "Первый вход" : "Войти"}
        </button>
      </header>

      <section className="catalog-layout">
        <div className="catalog-main">
          <div className="catalog-heading">
            <div>
              <span className="eyebrow">Каталог адресов</span>
              <h1>Юридические адреса для регистрации и смены адреса</h1>
            </div>
            <div className="catalog-counter">
              <Building2 size={18} />
              <strong>{addresses.length}</strong>
              <span>{addresses.length === 1 ? "адрес" : "адресов"}</span>
            </div>
          </div>

          <section className="catalog-filters" aria-label="Фильтры каталога">
            <label className="field">
              <span>Город или улица</span>
              <div className="input-with-icon">
                <Search size={16} />
                <input
                  list="public-cities"
                  value={filters.city}
                  onChange={(event) => setFilters({ ...filters, city: event.target.value })}
                  placeholder="Москва"
                />
                <datalist id="public-cities">
                  {cities.map((city) => (
                    <option key={city} value={city} />
                  ))}
                </datalist>
              </div>
            </label>
            <label className="field">
              <span>ИФНС</span>
              <input
                min={1}
                value={filters.fnsNumber}
                onChange={(event) => setFilters({ ...filters, fnsNumber: event.target.value })}
                placeholder="46"
                type="number"
              />
            </label>
            <label className="field">
              <span>Срок</span>
              <div className="segmented public-segmented">
                <button
                  className={filters.termMonths === 6 ? "selected" : ""}
                  onClick={() => setFilters({ ...filters, termMonths: 6 })}
                  type="button"
                >
                  6 мес.
                </button>
                <button
                  className={filters.termMonths === 11 ? "selected" : ""}
                  onClick={() => setFilters({ ...filters, termMonths: 11 })}
                  type="button"
                >
                  11 мес.
                </button>
              </div>
            </label>
            <label className="toggle-field compact catalog-toggle">
              <input
                checked={filters.correspondence}
                onChange={(event) => setFilters({ ...filters, correspondence: event.target.checked })}
                type="checkbox"
              />
              <span>Корреспонденция</span>
            </label>
          </section>

          {error ? <div className="inline-error">{error}</div> : null}

          {loading ? (
            <div className="address-grid">
              {Array.from({ length: 4 }).map((_, index) => (
                <div className="address-card address-card-loading" key={index} />
              ))}
            </div>
          ) : addresses.length ? (
            <div className="address-grid">
              {addresses.map((address) => (
                <article className="address-card" key={address.id}>
                  <header>
                    <span className="address-card-icon">
                      <MapPin size={18} />
                    </span>
                    <div>
                      <strong>{address.full_address}</strong>
                      <span>{address.room_number || "помещение без отдельного номера"}</span>
                    </div>
                  </header>
                  <div className="address-meta">
                    <span>ИФНС {address.fns_number || "не указана"}</span>
                    <span>{address.fns_city || "город не указан"}</span>
                    <span>{address.provider_name}</span>
                  </div>
                  <div className="address-price-row">
                    <div>
                      <small>Стоимость</small>
                      <b>{formatMoney(address.selected_price)}</b>
                    </div>
                    <div>
                      <small>{filters.termMonths === 6 ? "11 мес." : "6 мес."}</small>
                      <span>{formatMoney(filters.termMonths === 6 ? address.price_11m : address.price_6m)}</span>
                    </div>
                  </div>
                  <div className="address-options">
                    {address.correspondence_price ? (
                      <span>
                        <Mail size={14} /> Корреспонденция {formatMoney(address.correspondence_price)}
                      </span>
                    ) : (
                      <span>Без корреспонденции</span>
                    )}
                    <span>
                      <ShieldCheck size={14} /> Опубликован
                    </span>
                  </div>
                  <button className="btn primary" onClick={onLoginClick} type="button">
                    <FileText size={16} />
                    Подать заявку
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state public-empty">
              <SlidersHorizontal size={28} strokeWidth={1.7} />
              <strong>Адреса не найдены</strong>
              <span>{hasActiveFilters ? "Измените фильтры каталога." : "Опубликованных адресов пока нет."}</span>
            </div>
          )}
        </div>

        <aside className="public-side">
          <section className="public-login-panel">
            <KeyRound size={22} strokeWidth={1.8} />
            <div>
              <strong>{canBootstrap ? "Создать администратора" : "Вход для участников"}</strong>
              <span>Клиенты, собственники и администраторы работают из личных кабинетов.</span>
            </div>
            <button className="btn secondary" onClick={onLoginClick} type="button">
              <KeyRound size={16} />
              {canBootstrap ? "Первый вход" : "Открыть вход"}
            </button>
          </section>

          <form className="owner-request-panel" onSubmit={submitOwnerRequest}>
            <div className="panel-title">
              <Building2 size={21} strokeWidth={1.8} />
              <div>
                <strong>Для собственников</strong>
                <span>Заявка на подключение адресов</span>
              </div>
            </div>

            <label className="field">
              <span>Компания</span>
              <input
                value={ownerForm.company_name}
                onChange={(event) => setOwnerForm({ ...ownerForm, company_name: event.target.value })}
                required
              />
            </label>
            <label className="field">
              <span>Контактное лицо</span>
              <input
                value={ownerForm.contact_name}
                onChange={(event) => setOwnerForm({ ...ownerForm, contact_name: event.target.value })}
                required
              />
            </label>
            <label className="field">
              <span>E-mail</span>
              <input
                value={ownerForm.contact_email}
                onChange={(event) => setOwnerForm({ ...ownerForm, contact_email: event.target.value })}
                required
                type="email"
              />
            </label>
            <div className="owner-request-row">
              <label className="field">
                <span>Телефон</span>
                <input
                  value={ownerForm.contact_phone}
                  onChange={(event) => setOwnerForm({ ...ownerForm, contact_phone: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Адресов</span>
                <input
                  min={0}
                  value={ownerForm.address_count}
                  onChange={(event) => setOwnerForm({ ...ownerForm, address_count: event.target.value })}
                  type="number"
                />
              </label>
            </div>
            <label className="field">
              <span>Город</span>
              <input value={ownerForm.city} onChange={(event) => setOwnerForm({ ...ownerForm, city: event.target.value })} />
            </label>
            <label className="field">
              <span>Комментарий</span>
              <textarea
                value={ownerForm.comment}
                onChange={(event) => setOwnerForm({ ...ownerForm, comment: event.target.value })}
                rows={4}
              />
            </label>

            {ownerError ? <div className="inline-error compact-error">{ownerError}</div> : null}
            {ownerSuccess ? (
              <div className="success-note">
                <CheckCircle2 size={16} />
                Заявка отправлена
              </div>
            ) : null}

            <button className="btn primary" disabled={ownerBusy} type="submit">
              {ownerBusy ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
              Отправить
            </button>
          </form>
        </aside>
      </section>
    </main>
  );
}
