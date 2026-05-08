import {
  Building2,
  CheckCircle2,
  Database,
  Download,
  FileArchive,
  FileCheck2,
  FileText,
  FolderOpen,
  Home,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Upload
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, packageDownloadUrl } from "./api";
import type { Address, Application, ApplicationType, DadataLookup, NoticePeriod, Provider } from "./types";

type View = "applications" | "new" | "providers" | "addresses" | "templates";

const navItems: Array<{ id: View; label: string; icon: typeof Home }> = [
  { id: "applications", label: "Заявки", icon: FolderOpen },
  { id: "new", label: "Новая заявка", icon: Plus },
  { id: "providers", label: "Собственники", icon: Building2 },
  { id: "addresses", label: "Помещения", icon: Home },
  { id: "templates", label: "Шаблоны", icon: Settings }
];

const statusLabels: Record<string, string> = {
  draft: "Черновик",
  guarantee_issued: "Гарантийка выдана",
  awaiting_contract: "Ожидает договор",
  contract_signed: "Договор подписан",
  active: "Активна",
  expired: "Истекла",
  terminated: "Расторгнута"
};

const typeLabels: Record<ApplicationType, string> = {
  initial_registration: "Первичная регистрация",
  address_change: "Смена адреса"
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU").format(new Date(value));
}

function Field({
  label,
  children,
  hint
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}

function Button({
  children,
  variant = "primary",
  disabled,
  onClick,
  type = "button"
}: {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button className={`btn ${variant}`} disabled={disabled} onClick={onClick} type={type}>
      {children}
    </button>
  );
}

function InlineError({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="inline-error">{message}</div>;
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty-state">
      <FileText size={28} strokeWidth={1.7} />
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="skeleton-list">
      {Array.from({ length: 5 }).map((_, index) => (
        <div className="skeleton-row" key={index} />
      ))}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("applications");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    Promise.all([api.providers(), api.addresses(), api.applications()])
      .then(([providersResult, addressesResult, applicationsResult]) => {
        if (!alive) return;
        setProviders(providersResult);
        setAddresses(addressesResult);
        setApplications(applicationsResult);
      })
      .catch((err: Error) => alive && setError(err.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  const selectedTitle = navItems.find((item) => item.id === view)?.label || "Сервис";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">ЮА</div>
          <div>
            <strong>Юридический адрес</strong>
            <span>договоры и гарантийки</span>
          </div>
        </div>

        <nav className="nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={view === item.id ? "nav-item active" : "nav-item"}
                key={item.id}
                onClick={() => setView(item.id)}
              >
                <Icon size={18} strokeWidth={1.8} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <span>API</span>
          <strong>127.0.0.1:8000</strong>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">Рабочая область</span>
            <h1>{selectedTitle}</h1>
          </div>
          <Button variant="secondary" onClick={() => setRefreshKey((value) => value + 1)}>
            <RefreshCw size={16} /> Обновить
          </Button>
        </header>

        <InlineError message={error} />

        {loading ? (
          <LoadingRows />
        ) : (
          <>
            {view === "applications" && (
              <ApplicationsView applications={applications} providers={providers} addresses={addresses} />
            )}
            {view === "new" && (
              <NewApplicationView
                providers={providers}
                addresses={addresses}
                onCreated={() => {
                  setRefreshKey((value) => value + 1);
                  setView("applications");
                }}
              />
            )}
            {view === "providers" && (
              <ProvidersView providers={providers} onChanged={() => setRefreshKey((value) => value + 1)} />
            )}
            {view === "addresses" && (
              <AddressesView
                providers={providers}
                addresses={addresses}
                onChanged={() => setRefreshKey((value) => value + 1)}
              />
            )}
            {view === "templates" && <TemplatesView />}
          </>
        )}
      </main>
    </div>
  );
}

function ApplicationsView({
  applications,
  providers,
  addresses
}: {
  applications: Application[];
  providers: Provider[];
  addresses: Address[];
}) {
  if (!applications.length) {
    return <EmptyState title="Заявок пока нет" text="Создайте первичную регистрацию или смену адреса." />;
  }

  const providerById = new Map(providers.map((provider) => [provider.id, provider]));
  const addressById = new Map(addresses.map((address) => [address.id, address]));

  return (
    <section className="table-panel">
      <div className="table-header">
        <span>Тип</span>
        <span>Статус</span>
        <span>Собственник</span>
        <span>Адрес</span>
        <span>Дата</span>
        <span />
      </div>
      {applications.map((application) => (
        <div className="table-row" key={application.id}>
          <span>{typeLabels[application.type]}</span>
          <span className={`status ${application.status}`}>{statusLabels[application.status] || application.status}</span>
          <span>{providerById.get(application.provider_id)?.short_name || "—"}</span>
          <span>{addressById.get(application.address_id)?.full_address || "—"}</span>
          <span>{formatDate(application.created_at)}</span>
          <a className="download-link" href={packageDownloadUrl(application.id)}>
            <Download size={16} /> ZIP
          </a>
        </div>
      ))}
    </section>
  );
}

function NewApplicationView({
  providers,
  addresses,
  onCreated
}: {
  providers: Provider[];
  addresses: Address[];
  onCreated: () => void;
}) {
  const [type, setType] = useState<ApplicationType>("initial_registration");
  const [providerId, setProviderId] = useState(providers[0]?.id || "");
  const [addressId, setAddressId] = useState("");
  const [plannedClientName, setPlannedClientName] = useState("");
  const [inn, setInn] = useState("");
  const [lookup, setLookup] = useState<DadataLookup | null>(null);
  const [termMonths, setTermMonths] = useState<6 | 11>(11);
  const [noticePeriod, setNoticePeriod] = useState<NoticePeriod>("1m");
  const [hasCorrespondence, setHasCorrespondence] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);

  const availableAddresses = useMemo(
    () => addresses.filter((address) => address.provider_id === providerId),
    [addresses, providerId]
  );

  useEffect(() => {
    setAddressId(availableAddresses[0]?.id || "");
  }, [availableAddresses]);

  async function handleLookup() {
    setBusy(true);
    setError(null);
    setLookup(null);
    try {
      const result = await api.lookupInn(inn);
      setLookup(result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResultUrl(null);
    try {
      const payload =
        type === "initial_registration"
          ? {
              type,
              provider_id: providerId,
              address_id: addressId,
              planned_client_name: plannedClientName
            }
          : {
              type,
              provider_id: providerId,
              address_id: addressId,
              client_inn: inn,
              term_months: termMonths,
              notice_period: noticePeriod,
              has_correspondence_service: hasCorrespondence
            };
      const application = await api.createApplication(payload);
      await api.generatePackage(application.id);
      setResultUrl(packageDownloadUrl(application.id));
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const lookupBlocked =
    lookup &&
    (lookup.blockers.bankrupt ||
      lookup.blockers.is_branch ||
      lookup.blockers.liquidating_or_liquidated ||
      lookup.blockers.signatory_disqualified);

  return (
    <form className="split-form" onSubmit={handleSubmit}>
      <section className="form-main">
        <div className="segmented">
          <button
            className={type === "initial_registration" ? "selected" : ""}
            onClick={() => setType("initial_registration")}
            type="button"
          >
            Первичная регистрация
          </button>
          <button
            className={type === "address_change" ? "selected" : ""}
            onClick={() => setType("address_change")}
            type="button"
          >
            Смена адреса
          </button>
        </div>

        <div className="form-grid">
          <Field label="Собственник">
            <select value={providerId} onChange={(event) => setProviderId(event.target.value)} required>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.short_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Помещение">
            <select value={addressId} onChange={(event) => setAddressId(event.target.value)} required>
              {availableAddresses.map((address) => (
                <option key={address.id} value={address.id}>
                  {address.full_address}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {type === "initial_registration" ? (
          <Field label="Название будущей компании" hint="Без ОПФ, например: Альфа">
            <input
              value={plannedClientName}
              onChange={(event) => setPlannedClientName(event.target.value)}
              placeholder="Название компании"
              required
            />
          </Field>
        ) : (
          <>
            <div className="lookup-row">
              <Field label="ИНН клиента">
                <input
                  value={inn}
                  onChange={(event) => setInn(event.target.value)}
                  inputMode="numeric"
                  placeholder="7704217370"
                  required
                />
              </Field>
              <Button variant="secondary" disabled={busy || inn.length !== 10} onClick={handleLookup}>
                <Search size={16} /> Проверить
              </Button>
            </div>

            {lookup ? (
              <div className={lookupBlocked ? "lookup danger" : "lookup"}>
                <div>
                  <strong>{lookup.short_name}</strong>
                  <span>{lookup.full_name}</span>
                </div>
                <div>
                  <small>Статус</small>
                  <b>{lookup.egrul_status}</b>
                </div>
                <div>
                  <small>Руководитель</small>
                  <b>{lookup.signatory_name || "—"}</b>
                </div>
              </div>
            ) : null}

            <div className="form-grid three">
              <Field label="Срок">
                <select value={termMonths} onChange={(event) => setTermMonths(Number(event.target.value) as 6 | 11)}>
                  <option value={11}>11 месяцев</option>
                  <option value={6}>6 месяцев</option>
                </select>
              </Field>
              <Field label="Уведомление">
                <select value={noticePeriod} onChange={(event) => setNoticePeriod(event.target.value as NoticePeriod)}>
                  <option value="1m">1 месяц</option>
                  <option value="7d">7 дней</option>
                  <option value="1d">1 день</option>
                </select>
              </Field>
              <label className="toggle-field">
                <input
                  checked={hasCorrespondence}
                  onChange={(event) => setHasCorrespondence(event.target.checked)}
                  type="checkbox"
                />
                <span>Корреспонденция</span>
              </label>
            </div>
          </>
        )}

        <InlineError message={error} />

        <div className="actions">
          <Button disabled={busy || !providerId || !addressId || Boolean(lookupBlocked)} type="submit">
            {busy ? <Loader2 className="spin" size={16} /> : <FileArchive size={16} />}
            Сформировать комплект
          </Button>
          {resultUrl ? (
            <a className="btn secondary" href={resultUrl}>
              <Download size={16} /> Скачать ZIP
            </a>
          ) : null}
        </div>
      </section>

      <aside className="summary-panel">
        <FileCheck2 size={24} strokeWidth={1.7} />
        <strong>{type === "initial_registration" ? "Гарантийное письмо" : "Договор и гарантийное письмо"}</strong>
        <span>
          {type === "initial_registration"
            ? "Компания ещё не создана, поэтому договор не формируется."
            : "Реквизиты клиента подтягиваются из DaData по ИНН."}
        </span>
      </aside>
    </form>
  );
}

function ProvidersView({ providers, onChanged }: { providers: Provider[]; onChanged: () => void }) {
  const [form, setForm] = useState({
    code: "",
    full_name: "",
    short_name: "",
    inn: "",
    ogrn: "",
    legal_address: "",
    signatory_name: "",
    signatory_position: "Индивидуальный предприниматель",
    signatory_initials: "",
    phone: ""
  });
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.createProvider({ ...form, inn: form.inn || null, ogrn: form.ogrn || null });
      setForm({
        code: "",
        full_name: "",
        short_name: "",
        inn: "",
        ogrn: "",
        legal_address: "",
        signatory_name: "",
        signatory_position: "Индивидуальный предприниматель",
        signatory_initials: "",
        phone: ""
      });
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="stack">
      <form className="compact-form" onSubmit={submit}>
        <Field label="Код">
          <input value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} required />
        </Field>
        <Field label="Краткое имя">
          <input
            value={form.short_name}
            onChange={(event) => setForm({ ...form, short_name: event.target.value })}
            required
          />
        </Field>
        <Field label="Полное имя">
          <input
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            required
          />
        </Field>
        <Field label="ИНН">
          <input value={form.inn} onChange={(event) => setForm({ ...form, inn: event.target.value })} />
        </Field>
        <Field label="ОГРНИП">
          <input value={form.ogrn} onChange={(event) => setForm({ ...form, ogrn: event.target.value })} />
        </Field>
        <Field label="Адрес">
          <input
            value={form.legal_address}
            onChange={(event) => setForm({ ...form, legal_address: event.target.value })}
          />
        </Field>
        <Field label="Подписант">
          <input
            value={form.signatory_name}
            onChange={(event) => setForm({ ...form, signatory_name: event.target.value })}
          />
        </Field>
        <Field label="Инициалы">
          <input
            value={form.signatory_initials}
            onChange={(event) => setForm({ ...form, signatory_initials: event.target.value })}
          />
        </Field>
        <Field label="Телефон">
          <input value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} />
        </Field>
        <Button type="submit">
          <Plus size={16} /> Добавить
        </Button>
      </form>
      <InlineError message={error} />
      <SimpleList
        items={providers}
        render={(provider) => (
          <>
            <strong>{provider.short_name}</strong>
            <span>{provider.legal_address || provider.full_name}</span>
          </>
        )}
      />
    </div>
  );
}

function AddressesView({
  providers,
  addresses,
  onChanged
}: {
  providers: Provider[];
  addresses: Address[];
  onChanged: () => void;
}) {
  const [providerId, setProviderId] = useState(providers[0]?.id || "");
  const [selectedAddressId, setSelectedAddressId] = useState(addresses[0]?.id || "");
  const [issueDate, setIssueDate] = useState(new Date().toISOString().slice(0, 10));
  const [extractNumber, setExtractNumber] = useState("");
  const [pdf, setPdf] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    full_address: "",
    cadastral_number: "",
    ownership_doc: "Выписка из ЕГРН",
    ownership_doc_short: "Выписки из ЕГРН",
    ownership_doc_pages: 3,
    price_6m: "15000",
    price_11m: "25000",
    fns_number: "46",
    fns_city: "Москве"
  });

  async function createAddress(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.createAddress({
        ...form,
        provider_id: providerId,
        ownership_doc_pages: Number(form.ownership_doc_pages),
        price_6m: form.price_6m,
        price_11m: form.price_11m,
        fns_number: Number(form.fns_number)
      });
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function uploadEgrn(event: FormEvent) {
    event.preventDefault();
    if (!pdf || !selectedAddressId) return;
    setError(null);
    const formData = new FormData();
    formData.append("pdf_file", pdf);
    formData.append("issue_date", issueDate);
    if (extractNumber) formData.append("extract_number", extractNumber);
    try {
      await api.uploadEgrn(selectedAddressId, formData);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="stack">
      <form className="compact-form" onSubmit={createAddress}>
        <Field label="Собственник">
          <select value={providerId} onChange={(event) => setProviderId(event.target.value)} required>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.short_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Адрес помещения">
          <input
            value={form.full_address}
            onChange={(event) => setForm({ ...form, full_address: event.target.value })}
            required
          />
        </Field>
        <Field label="Кадастровый номер">
          <input
            value={form.cadastral_number}
            onChange={(event) => setForm({ ...form, cadastral_number: event.target.value })}
            placeholder="77:01:0001001:1234"
            required
          />
        </Field>
        <Field label="Цена 6 мес">
          <input value={form.price_6m} onChange={(event) => setForm({ ...form, price_6m: event.target.value })} />
        </Field>
        <Field label="Цена 11 мес">
          <input value={form.price_11m} onChange={(event) => setForm({ ...form, price_11m: event.target.value })} />
        </Field>
        <Field label="ИФНС">
          <input value={form.fns_number} onChange={(event) => setForm({ ...form, fns_number: event.target.value })} />
        </Field>
        <Button type="submit">
          <Plus size={16} /> Добавить помещение
        </Button>
      </form>

      <form className="upload-form" onSubmit={uploadEgrn}>
        <Field label="Помещение для выписки">
          <select value={selectedAddressId} onChange={(event) => setSelectedAddressId(event.target.value)}>
            {addresses.map((address) => (
              <option key={address.id} value={address.id}>
                {address.full_address}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Дата выписки">
          <input value={issueDate} onChange={(event) => setIssueDate(event.target.value)} type="date" />
        </Field>
        <Field label="Номер выписки">
          <input value={extractNumber} onChange={(event) => setExtractNumber(event.target.value)} />
        </Field>
        <Field label="PDF">
          <input accept="application/pdf" onChange={(event) => setPdf(event.target.files?.[0] || null)} type="file" />
        </Field>
        <Button disabled={!pdf || !selectedAddressId} type="submit">
          <Upload size={16} /> Загрузить ЕГРН
        </Button>
      </form>

      <InlineError message={error} />
      <SimpleList
        items={addresses}
        render={(address) => (
          <>
            <strong>{address.full_address}</strong>
            <span>
              {address.cadastral_number} · {address.price_6m} / {address.price_11m} руб.
            </span>
          </>
        )}
      />
    </div>
  );
}

function TemplatesView() {
  return (
    <div className="templates-panel">
      <Database size={26} strokeWidth={1.7} />
      <strong>Шаблоны .docx подключены</strong>
      <span>Активные версии можно добавить следующим шагом: загрузка, тестовый рендер и активация.</span>
    </div>
  );
}

function SimpleList<T>({ items, render }: { items: T[]; render: (item: T) => React.ReactNode }) {
  if (!items.length) return <EmptyState title="Список пуст" text="Добавьте первую запись через форму выше." />;
  return (
    <div className="simple-list">
      {items.map((item, index) => (
        <div className="simple-item" key={index}>
          {render(item)}
        </div>
      ))}
    </div>
  );
}
