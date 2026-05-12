import {
  AlertTriangle,
  ArrowRight,
  Building2,
  Camera,
  CheckCircle2,
  ChevronRight,
  FileText,
  KeyRound,
  Loader2,
  Mail,
  MapPin,
  Search,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { motion, useReducedMotion, type Variants } from "framer-motion";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { PhoneInput } from "./PhoneInput";
import type {
  CurrentUser,
  ProviderConnectionRequestCreate,
  PublicAddress,
  PublicClientApplicationCreate,
} from "./types";

type PublicCatalogProps = {
  canBootstrap: boolean;
  onAuthenticated: (user: CurrentUser) => void;
  onLoginClick: () => void;
};

type CatalogFilters = {
  query: string;
  city: string;
  fnsNumber: string;
  termMonths: 6 | 11;
  correspondence: boolean;
};

const initialFilters: CatalogFilters = {
  query: "",
  city: "Москва",
  fnsNumber: "",
  termMonths: 11,
  correspondence: false,
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
  comment: "",
};

type ClientApplicationForm = {
  type: "initial_registration" | "address_change";
  planned_client_name: string;
  client_inn: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  password: string;
  term_months: 6 | 11;
  has_correspondence_service: boolean;
};

const initialClientApplicationForm: ClientApplicationForm = {
  type: "initial_registration",
  planned_client_name: "",
  client_inn: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
  password: "",
  term_months: 11,
  has_correspondence_service: false,
};

const NEW_ADDRESS_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(amount);
}

function normalizeOptional(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function streetInitials(fullAddress: string): string {
  const match = fullAddress.match(
    /(?:ул\.|улица|просп\.|проспект|пр\.|пер\.|переулок|наб\.|набережная|пл\.|площадь|ш\.|шоссе|бул\.|бульвар)\s*([А-Яа-яЁё-]+)/i,
  );
  const word = match?.[1] ?? fullAddress.replace(/^[^А-Яа-яЁё]+/, "").split(/[\s,]/)[0] ?? "АД";
  return word.slice(0, 2).toUpperCase();
}

function isRecent(createdAt: string): boolean {
  const ts = Date.parse(createdAt);
  if (!Number.isFinite(ts)) return false;
  return Date.now() - ts <= NEW_ADDRESS_WINDOW_MS;
}

const heroStaggerVariants: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.08, delayChildren: 0.05 },
  },
};

const heroChildVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.32, ease: [0.2, 0.8, 0.2, 1] } },
};

const gridStaggerVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05 } },
};

const cardVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.2, ease: "easeOut" } },
};

export default function PublicCatalog({ canBootstrap, onAuthenticated, onLoginClick }: PublicCatalogProps) {
  const reduceMotion = useReducedMotion();
  const motionVariants = reduceMotion ? undefined : heroStaggerVariants;
  const childMotion = reduceMotion ? undefined : heroChildVariants;
  const gridMotion = reduceMotion ? undefined : gridStaggerVariants;
  const cardMotion = reduceMotion ? undefined : cardVariants;

  const [filters, setFilters] = useState<CatalogFilters>(initialFilters);
  const [addresses, setAddresses] = useState<PublicAddress[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [ownerOpen, setOwnerOpen] = useState(false);
  const [ownerForm, setOwnerForm] = useState<OwnerRequestForm>(initialOwnerRequestForm);
  const [ownerBusy, setOwnerBusy] = useState(false);
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [ownerSuccess, setOwnerSuccess] = useState(false);

  const [selectedAddress, setSelectedAddress] = useState<PublicAddress | null>(null);
  const [applicationForm, setApplicationForm] = useState<ClientApplicationForm>(initialClientApplicationForm);
  const [applicationBusy, setApplicationBusy] = useState(false);
  const [applicationError, setApplicationError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .publicAddresses({
        city: filters.city.trim(),
        fns_number: filters.fnsNumber ? Number(filters.fnsNumber) : "",
        term_months: filters.termMonths,
        correspondence: filters.correspondence,
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
  }, [filters.city, filters.fnsNumber, filters.termMonths, filters.correspondence, reloadKey]);

  const filteredAddresses = useMemo(() => {
    const q = filters.query.trim().toLowerCase();
    if (!q) return addresses;
    return addresses.filter((address) => {
      const haystack = `${address.full_address} ${address.fns_number ?? ""} ${address.fns_city ?? ""} ${address.provider_name}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [addresses, filters.query]);

  const ifnsCount = useMemo(() => {
    const set = new Set<number>();
    for (const a of addresses) {
      if (a.fns_number) set.add(a.fns_number);
    }
    return set.size;
  }, [addresses]);

  const cities = useMemo(() => {
    const values = new Set<string>(["Москва"]);
    for (const address of addresses) {
      const match = address.full_address.match(/г\.\s*([^,]+)/i);
      if (match?.[1]) values.add(match[1].trim());
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b, "ru"));
  }, [addresses]);

  const hasActiveFilters = Boolean(
    filters.query.trim() ||
      filters.fnsNumber ||
      filters.correspondence ||
      filters.termMonths !== initialFilters.termMonths ||
      filters.city !== initialFilters.city,
  );

  function resetFilters() {
    setFilters(initialFilters);
  }

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
      comment: normalizeOptional(ownerForm.comment),
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

  function openApplicationForm(address: PublicAddress) {
    setSelectedAddress(address);
    setApplicationError(null);
    setApplicationForm({
      ...initialClientApplicationForm,
      term_months: filters.termMonths,
      has_correspondence_service: filters.correspondence && Boolean(address.correspondence_price),
    });
  }

  async function submitClientApplication(event: FormEvent) {
    event.preventDefault();
    if (!selectedAddress) return;
    setApplicationBusy(true);
    setApplicationError(null);
    const basePayload = {
      address_id: selectedAddress.id,
      contact_name: applicationForm.contact_name.trim(),
      contact_email: applicationForm.contact_email.trim(),
      contact_phone: normalizeOptional(applicationForm.contact_phone),
      password: applicationForm.password,
      term_months: applicationForm.term_months,
      has_correspondence_service: applicationForm.has_correspondence_service,
      contract_city: null,
    };
    const payload: PublicClientApplicationCreate =
      applicationForm.type === "initial_registration"
        ? {
            ...basePayload,
            type: "initial_registration",
            planned_client_name: applicationForm.planned_client_name.trim(),
          }
        : {
            ...basePayload,
            type: "address_change",
            client_inn: applicationForm.client_inn.trim(),
            notice_period: "1m",
          };
    try {
      const result = await api.createPublicApplication(payload);
      setSelectedAddress(null);
      setApplicationForm(initialClientApplicationForm);
      onAuthenticated(result.user);
    } catch (err) {
      setApplicationError((err as Error).message);
    } finally {
      setApplicationBusy(false);
    }
  }

  return (
    <main className="ds-catalog">
      <header className="ds-topnav">
        <div className="ds-topnav__brand">
          <span className="ds-topnav__brand-mark">UR</span>
          <span>UrAdres</span>
        </div>
        <nav className="ds-topnav__links" aria-label="Главное меню">
          <a href="#catalog">Каталог</a>
          <a href="#how">Как это работает</a>
          <a
            href="#owners"
            onClick={(e) => {
              e.preventDefault();
              setOwnerOpen(true);
            }}
          >
            Для собственников
          </a>
        </nav>
        <div className="ds-topnav__actions">
          <button className="ds-btn ds-btn--ghost ds-btn--md" onClick={onLoginClick} type="button">
            <KeyRound size={14} />
            {canBootstrap ? "Первый вход" : "Войти"}
          </button>
          <button
            className="ds-btn ds-btn--primary ds-btn--md"
            type="button"
            onClick={() => {
              const grid = document.getElementById("catalog-grid");
              grid?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          >
            Подобрать адрес
            <ArrowRight size={14} />
          </button>
        </div>
      </header>

      <motion.section
        id="catalog"
        className="ds-hero"
        initial={reduceMotion ? false : "hidden"}
        animate="visible"
        variants={motionVariants}
      >
        <motion.h1 className="ds-hero__h1" variants={childMotion}>
          Юридический адрес для бизнеса.<br />
          <em>За 1 день.</em>
        </motion.h1>
        <motion.p className="ds-hero__sub" variants={childMotion}>
          Проверенные собственники, готовый комплект документов с гарантийным письмом и выпиской ЕГРН.
          Подходит и для регистрации новой компании, и для смены адреса действующей.
        </motion.p>
        <motion.div className="ds-hero__stats ds-stat-row" variants={childMotion}>
          <div className="ds-stat">
            <div className="ds-stat__num">{addresses.length || "—"}</div>
            <div className="ds-stat__lbl">{addresses.length === 1 ? "адрес в каталоге" : "адресов в каталоге"}</div>
          </div>
          <div className="ds-stat">
            <div className="ds-stat__num">{ifnsCount || "—"}</div>
            <div className="ds-stat__lbl">ИФНС в выборке</div>
          </div>
          <div className="ds-stat">
            <div className="ds-stat__num">98%</div>
            <div className="ds-stat__lbl">одобрений ФНС</div>
          </div>
          <div className="ds-stat">
            <div className="ds-stat__num">1 день</div>
            <div className="ds-stat__lbl">средний срок выдачи</div>
          </div>
        </motion.div>
      </motion.section>

      <section className="ds-filterbar" aria-label="Фильтры каталога">
        <label className="ds-input">
          <span className="ds-input__icon">
            <Search size={14} />
          </span>
          <input
            list="ds-public-cities"
            placeholder="Найти адрес, ИФНС или собственника"
            value={filters.query}
            onChange={(event) => setFilters({ ...filters, query: event.target.value })}
          />
          <datalist id="ds-public-cities">
            {cities.map((city) => (
              <option key={city} value={city} />
            ))}
          </datalist>
        </label>
        <button
          type="button"
          className={`ds-chip${filters.city === "Москва" ? " ds-chip--active" : ""}`}
          onClick={() =>
            setFilters({ ...filters, city: filters.city === "Москва" ? "" : "Москва" })
          }
        >
          Москва
          {filters.city === "Москва" && <span className="ds-chip__x" aria-hidden>×</span>}
        </button>
        <select
          className="ds-select"
          value={filters.termMonths}
          onChange={(event) => setFilters({ ...filters, termMonths: Number(event.target.value) as 6 | 11 })}
          aria-label="Срок"
        >
          <option value={6}>Срок: 6 мес.</option>
          <option value={11}>Срок: 11 мес.</option>
        </select>
        <label className="ds-input" style={{ minWidth: 160, flex: "0 0 auto" }}>
          <span className="ds-input__icon">№</span>
          <input
            type="number"
            min={1}
            placeholder="ИФНС"
            value={filters.fnsNumber}
            onChange={(event) => setFilters({ ...filters, fnsNumber: event.target.value })}
          />
        </label>
        <button
          type="button"
          className={`ds-chip${filters.correspondence ? " ds-chip--active" : ""}`}
          onClick={() => setFilters({ ...filters, correspondence: !filters.correspondence })}
        >
          + корреспонденция
          {filters.correspondence && <span className="ds-chip__x" aria-hidden>×</span>}
        </button>
        {hasActiveFilters && (
          <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm ds-filterbar__reset" onClick={resetFilters}>
            Сбросить
          </button>
        )}
      </section>

      <div className="ds-resultbar" id="catalog-grid">
        <div>
          {loading ? (
            "Загружаем каталог…"
          ) : (
            <>
              Показано <b>{filteredAddresses.length}</b> из <b>{addresses.length}</b> {addresses.length === 1 ? "адреса" : "адресов"}
            </>
          )}
        </div>
      </div>

      <div className="ds-gridwrap">
        {error ? (
          <div className="ds-emptystate">
            <div className="ds-emptystate__icon ds-emptystate__icon--danger">
              <AlertTriangle size={26} strokeWidth={1.8} />
            </div>
            <h3>Не удалось загрузить каталог</h3>
            <p>Что-то пошло не так на нашей стороне. Попробуй обновить страницу через минуту — если ошибка повторится, напиши нам.</p>
            <div className="ds-emptystate__actions">
              <button
                className="ds-btn ds-btn--secondary ds-btn--md"
                type="button"
                onClick={() => setOwnerOpen(true)}
              >
                <Mail size={14} />
                Связаться с поддержкой
              </button>
              <button
                className="ds-btn ds-btn--primary ds-btn--md"
                type="button"
                onClick={() => setReloadKey((key) => key + 1)}
              >
                Обновить
              </button>
            </div>
          </div>
        ) : loading ? (
          <div className="ds-grid">
            {Array.from({ length: 6 }).map((_, index) => (
              <div className="ds-skel-card" key={index}>
                <div className="ds-skel ds-skel-card__media" />
                <div className="ds-skel-card__body">
                  <div className="ds-skel" style={{ height: 14, width: "70%" }} />
                  <div className="ds-skel" style={{ height: 11, width: "55%" }} />
                  <div className="ds-skel" style={{ height: 18, width: "40%", marginTop: 6 }} />
                </div>
              </div>
            ))}
          </div>
        ) : filteredAddresses.length === 0 ? (
          <div className="ds-emptystate">
            <div className="ds-emptystate__icon">
              <Search size={26} strokeWidth={1.8} />
            </div>
            <h3>{hasActiveFilters ? "По заданным фильтрам адресов нет" : "Опубликованных адресов пока нет"}</h3>
            <p>
              {hasActiveFilters
                ? `Попробуй расширить срок или выбрать другую ИФНС. У нас ${addresses.length} адресов в ${ifnsCount} ИФНС.`
                : "Скоро появятся первые адреса от верифицированных собственников."}
            </p>
            {hasActiveFilters && (
              <div className="ds-emptystate__actions">
                <button className="ds-btn ds-btn--primary ds-btn--md" type="button" onClick={resetFilters}>
                  Сбросить фильтры
                </button>
              </div>
            )}
          </div>
        ) : (
          <motion.div
            className="ds-grid"
            initial={reduceMotion ? false : "hidden"}
            animate="visible"
            variants={gridMotion}
            key={`${filters.city}-${filters.termMonths}-${filters.correspondence}-${filteredAddresses.length}`}
          >
            {filteredAddresses.map((address) => {
              const initials = streetInitials(address.full_address);
              const fresh = isRecent(address.created_at);
              const price = filters.termMonths === 6 ? address.price_6m : address.price_11m;
              return (
                <motion.button
                  type="button"
                  className="ds-card"
                  variants={cardMotion}
                  onClick={() => openApplicationForm(address)}
                  key={address.id}
                >
                  <div className="ds-card__media">
                    {fresh && (
                      <span className="ds-card__media-overlay ds-badge ds-badge--new">
                        <span className="ds-badge__dot" />
                        Новый адрес
                      </span>
                    )}
                    <div className="ds-card__media-fallback">
                      <div>
                        <div className="ds-card__media-fallback-initials">{initials}</div>
                        <div className="ds-card__media-fallback-meta">
                          {address.fns_number ? `ИФНС № ${address.fns_number}` : "ИФНС не указана"}
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="ds-card__body">
                    <h3 className="ds-card__title">{address.full_address}</h3>
                    <div className="ds-card__sub">
                      {address.room_number ? `${address.room_number} · ` : ""}
                      {address.fns_number ? `ИФНС № ${address.fns_number}` : ""}
                      {address.fns_number && filters.termMonths ? " · " : ""}
                      {filters.termMonths} мес
                    </div>
                    <div className="ds-card__row">
                      <div className="ds-card__price">
                        <span className="ds-card__price-from">от</span>
                        {formatMoney(price)}
                      </div>
                      <span className="ds-btn ds-btn--ghost ds-btn--sm" aria-hidden>
                        Подробнее
                        <ChevronRight size={14} />
                      </span>
                    </div>
                  </div>
                </motion.button>
              );
            })}
          </motion.div>
        )}
      </div>

      {selectedAddress && (
        <div className="modal-backdrop">
          <form className="modal-panel public-application-modal" onSubmit={submitClientApplication}>
            <header>
              <div>
                <span className="eyebrow">Заявка клиента</span>
                <h2>Подать заявку на адрес</h2>
              </div>
              <button className="text-action" onClick={() => setSelectedAddress(null)} type="button">
                <X size={16} /> Закрыть
              </button>
            </header>

            <div className="selected-address-strip">
              <MapPin size={18} />
              <div>
                <strong>{selectedAddress.full_address}</strong>
                <span>
                  {selectedAddress.provider_name} · ИФНС {selectedAddress.fns_number || "не указана"} ·{" "}
                  {formatMoney(applicationForm.term_months === 6 ? selectedAddress.price_6m : selectedAddress.price_11m)}
                </span>
              </div>
            </div>

            <div className="segmented">
              <button
                className={applicationForm.type === "initial_registration" ? "selected" : ""}
                onClick={() => setApplicationForm({ ...applicationForm, type: "initial_registration" })}
                type="button"
              >
                Первичная регистрация
              </button>
              <button
                className={applicationForm.type === "address_change" ? "selected" : ""}
                onClick={() => setApplicationForm({ ...applicationForm, type: "address_change" })}
                type="button"
              >
                Смена адреса
              </button>
            </div>

            {applicationForm.type === "initial_registration" ? (
              <label className="field">
                <span>Название будущей компании</span>
                <input
                  value={applicationForm.planned_client_name}
                  onChange={(event) => setApplicationForm({ ...applicationForm, planned_client_name: event.target.value })}
                  required
                />
              </label>
            ) : (
              <label className="field">
                <span>ИНН компании</span>
                <input
                  inputMode="numeric"
                  maxLength={10}
                  value={applicationForm.client_inn}
                  onChange={(event) => setApplicationForm({ ...applicationForm, client_inn: event.target.value })}
                  required
                />
              </label>
            )}

            <div className="client-application-grid">
              <label className="field">
                <span>Контактное лицо</span>
                <input
                  value={applicationForm.contact_name}
                  onChange={(event) => setApplicationForm({ ...applicationForm, contact_name: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>E-mail для аккаунта</span>
                <input
                  inputMode="email"
                  value={applicationForm.contact_email}
                  onChange={(event) => setApplicationForm({ ...applicationForm, contact_email: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Телефон</span>
                <PhoneInput
                  value={applicationForm.contact_phone}
                  onChange={(value) => setApplicationForm({ ...applicationForm, contact_phone: value })}
                />
              </label>
              <label className="field">
                <span>Пароль</span>
                <input
                  minLength={8}
                  value={applicationForm.password}
                  onChange={(event) => setApplicationForm({ ...applicationForm, password: event.target.value })}
                  required
                  type="password"
                />
              </label>
            </div>

            <div className="client-application-options">
              <label className="field">
                <span>Срок</span>
                <div className="segmented public-segmented">
                  <button
                    className={applicationForm.term_months === 6 ? "selected" : ""}
                    onClick={() => setApplicationForm({ ...applicationForm, term_months: 6 })}
                    type="button"
                  >
                    6 мес.
                  </button>
                  <button
                    className={applicationForm.term_months === 11 ? "selected" : ""}
                    onClick={() => setApplicationForm({ ...applicationForm, term_months: 11 })}
                    type="button"
                  >
                    11 мес.
                  </button>
                </div>
              </label>
              <label className="toggle-field compact catalog-toggle">
                <input
                  checked={applicationForm.has_correspondence_service}
                  disabled={!selectedAddress.correspondence_price}
                  onChange={(event) =>
                    setApplicationForm({ ...applicationForm, has_correspondence_service: event.target.checked })
                  }
                  type="checkbox"
                />
                <span>Корреспонденция</span>
              </label>
            </div>

            {applicationError ? <div className="inline-error compact-error">{applicationError}</div> : null}

            <div className="actions">
              <button className="ds-btn ds-btn--primary ds-btn--lg" disabled={applicationBusy} type="submit">
                {applicationBusy ? <Loader2 className="spin" size={16} /> : <FileText size={16} />}
                Создать заявку и аккаунт
              </button>
            </div>
          </form>
        </div>
      )}

      {ownerOpen && (
        <div className="modal-backdrop" onClick={() => setOwnerOpen(false)}>
          <form className="modal-panel public-application-modal" onSubmit={submitOwnerRequest} onClick={(e) => e.stopPropagation()}>
            <header>
              <div>
                <span className="eyebrow">Для собственников</span>
                <h2>Подключить адреса в каталог</h2>
              </div>
              <button className="text-action" onClick={() => setOwnerOpen(false)} type="button">
                <X size={16} /> Закрыть
              </button>
            </header>
            <p style={{ fontSize: 13, color: "var(--ds-slate-500)", marginTop: 0 }}>
              <Sparkles size={14} style={{ verticalAlign: "-2px" }} /> Расскажи о компании и адресах — мы свяжемся в течение рабочего дня и пришлём приглашение в админку.
            </p>

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
            <div className="client-application-grid">
              <label className="field">
                <span>E-mail</span>
                <input
                  type="email"
                  value={ownerForm.contact_email}
                  onChange={(event) => setOwnerForm({ ...ownerForm, contact_email: event.target.value })}
                  required
                />
              </label>
              <label className="field">
                <span>Телефон</span>
                <PhoneInput
                  value={ownerForm.contact_phone}
                  onChange={(value) => setOwnerForm({ ...ownerForm, contact_phone: value })}
                />
              </label>
              <label className="field">
                <span>Город</span>
                <input
                  value={ownerForm.city}
                  onChange={(event) => setOwnerForm({ ...ownerForm, city: event.target.value })}
                />
              </label>
              <label className="field">
                <span>Адресов</span>
                <input
                  type="number"
                  min={0}
                  value={ownerForm.address_count}
                  onChange={(event) => setOwnerForm({ ...ownerForm, address_count: event.target.value })}
                />
              </label>
            </div>
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
                Заявка отправлена. Проверь почту — мы напишем в течение рабочего дня.
              </div>
            ) : null}

            <div className="actions">
              <button className="ds-btn ds-btn--primary ds-btn--lg" disabled={ownerBusy} type="submit">
                {ownerBusy ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
                Отправить заявку
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

// Сохраняем именованный экспорт неиспользуемых иконок чтобы tree-shake не выкинул нужные.
// (Building2/Camera импортированы для будущих фаз.)
export const _DS_ICONS_PROBE = { Building2, Camera };
