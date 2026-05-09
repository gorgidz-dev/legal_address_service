import {
  Building2,
  CheckCircle2,
  Copy,
  Database,
  Download,
  FileClock,
  FileArchive,
  FileCheck2,
  FileText,
  FolderOpen,
  Home,
  KeyRound,
  Loader2,
  LogOut,
  Plus,
  RefreshCw,
  ReceiptText,
  Search,
  Settings,
  ShieldCheck,
  Upload,
  UserPlus,
  XCircle
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, api, packageDownloadUrl, paymentDocumentDownloadUrl } from "./api";
import PublicCatalog from "./publicCatalog";
import type {
  ActiveClientRegistryItem,
  Address,
  Application,
  ApplicationType,
  ClientApplication,
  CurrentUser,
  DadataLookup,
  Invitation,
  InvitationCreateResult,
  NoticePeriod,
  OwnerApplication,
  OwnerDashboard,
  PaymentDocument,
  Provider
} from "./types";

type View = "applications" | "registry" | "new" | "providers" | "addresses" | "templates" | "access";

const baseNavItems: Array<{ id: View; label: string; icon: typeof Home }> = [
  { id: "applications", label: "Заявки", icon: FolderOpen },
  { id: "registry", label: "Действующие клиенты", icon: FileClock },
  { id: "new", label: "Новая заявка", icon: Plus },
  { id: "providers", label: "Собственники", icon: Building2 },
  { id: "addresses", label: "Помещения", icon: Home },
  { id: "templates", label: "Шаблоны", icon: Settings }
];

const adminNavItem: { id: View; label: string; icon: typeof Home } = {
  id: "access",
  label: "Доступ",
  icon: ShieldCheck
};

const statusLabels: Record<string, string> = {
  draft: "Черновик",
  guarantee_issued: "Гарантийка выдана",
  awaiting_contract: "Ожидает договор",
  contract_signed: "Договор подписан",
  active: "Активна",
  expired: "Истекла",
  terminated: "Расторгнута",
  awaiting_payment: "Ожидает оплату",
  paid: "Оплачена",
  admin_review: "Проверка администратора",
  needs_client_fix: "Нужны уточнения",
  assigned_to_owner: "Передана собственнику",
  accepted_by_owner: "Принята собственником",
  rejected_by_owner: "Отклонена собственником",
  documents_preparing: "Готовятся документы",
  documents_uploaded: "Документы загружены",
  documents_review: "Проверка документов",
  documents_revision: "Доработка документов",
  ready_for_client: "Готова к выдаче",
  completed: "Завершена",
  cancelled: "Отменена",
  dispute: "Спор",
  refund_pending: "Возврат готовится",
  refunded: "Возврат выполнен"
};

const typeLabels: Record<ApplicationType, string> = {
  initial_registration: "Первичная регистрация",
  address_change: "Смена адреса"
};

const ownerActionLabels: Record<string, string> = {
  accept: "Принять",
  reject: "Отклонить",
  start_documents: "Начать документы",
  upload_documents: "Загрузить документы"
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU").format(new Date(value));
}

function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0
  }).format(Number(value));
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

function AuthView({
  canBootstrap,
  onAuthenticated,
  onBack
}: {
  canBootstrap: boolean;
  onAuthenticated: (user: CurrentUser) => void;
  onBack?: () => void;
}) {
  const inviteFromPath = window.location.pathname.startsWith("/invite/")
    ? decodeURIComponent(window.location.pathname.replace("/invite/", ""))
    : "";
  const [mode, setMode] = useState<"login" | "bootstrap" | "invite">(canBootstrap ? "bootstrap" : inviteFromPath ? "invite" : "login");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [inviteToken, setInviteToken] = useState(inviteFromPath);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response =
        mode === "bootstrap"
          ? await api.bootstrapAdmin({ email, full_name: fullName, password })
          : mode === "invite"
            ? await api.acceptInvitation(inviteToken.trim(), { full_name: fullName, password })
            : await api.login({ email, password });
      onAuthenticated(response.user);
      window.history.replaceState(null, "", "/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <form className="auth-panel" onSubmit={submit}>
        <div className="brand auth-brand">
          <div className="brand-mark">ЮА</div>
          <div>
            <strong>Юридический адрес</strong>
            <span>онлайн-доступ к сервису</span>
          </div>
        </div>

        {onBack ? (
          <button className="text-action auth-back" onClick={onBack} type="button">
            Вернуться в каталог
          </button>
        ) : null}

        <div className="segmented">
          <button className={mode === "login" ? "selected" : ""} onClick={() => setMode("login")} type="button">
            Вход
          </button>
          <button className={mode === "invite" ? "selected" : ""} onClick={() => setMode("invite")} type="button">
            Приглашение
          </button>
          {canBootstrap ? (
            <button
              className={mode === "bootstrap" ? "selected" : ""}
              onClick={() => setMode("bootstrap")}
              type="button"
            >
              Первый вход
            </button>
          ) : null}
        </div>

        {mode !== "invite" ? (
          <Field label="E-mail">
            <input
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </Field>
        ) : (
          <Field label="Токен или ссылка приглашения">
            <input
              value={inviteToken}
              onChange={(event) => setInviteToken(event.target.value.replace(/^.*\/invite\//, ""))}
              required
            />
          </Field>
        )}

        {mode !== "login" ? (
          <Field label="ФИО пользователя">
            <input value={fullName} onChange={(event) => setFullName(event.target.value)} required />
          </Field>
        ) : null}

        <Field label="Пароль">
          <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required />
        </Field>

        <InlineError message={error} />

        <Button disabled={busy} type="submit">
          {busy ? <Loader2 className="spin" size={16} /> : <KeyRound size={16} />}
          {mode === "login" ? "Войти" : mode === "invite" ? "Принять приглашение" : "Создать администратора"}
        </Button>
      </form>
    </main>
  );
}

function AccessView() {
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [form, setForm] = useState({ email: "", full_name: "", role: "manager" });
  const [created, setCreated] = useState<InvitationCreateResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .invitations()
      .then(setInvitations)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const result = await api.createInvitation({
        email: form.email,
        full_name: form.full_name || null,
        role: form.role
      });
      setCreated(result);
      setForm({ email: "", full_name: "", role: "manager" });
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const inviteUrl = created ? `${window.location.origin}${created.invitation_path}` : "";

  return (
    <section className="stack">
      <form className="compact-form access-form" onSubmit={submit}>
        <Field label="E-mail">
          <input value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} type="email" required />
        </Field>
        <Field label="ФИО">
          <input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
        </Field>
        <Field label="Роль">
          <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
            <option value="manager">Менеджер</option>
            <option value="lawyer">Юрист</option>
            <option value="admin">Администратор</option>
          </select>
        </Field>
        <Button disabled={busy} type="submit">
          {busy ? <Loader2 className="spin" size={16} /> : <UserPlus size={16} />}
          Пригласить
        </Button>
      </form>

      {created ? (
        <div className="invite-result">
          <div>
            <strong>Ссылка приглашения</strong>
            <span>{inviteUrl}</span>
          </div>
          <button className="text-action" onClick={() => navigator.clipboard?.writeText(inviteUrl)} type="button">
            <Copy size={15} /> Копировать
          </button>
        </div>
      ) : null}

      <InlineError message={error} />

      {loading ? (
        <LoadingRows />
      ) : (
        <SimpleList
          items={invitations}
          render={(invitation) => (
            <>
              <strong>{invitation.email}</strong>
              <span>
                {invitation.full_name || "без ФИО"} · {invitation.role} · до {formatDate(invitation.expires_at)}
                {invitation.accepted_at ? ` · принято ${formatDate(invitation.accepted_at)}` : ""}
              </span>
            </>
          )}
        />
      )}
    </section>
  );
}

export default function App() {
  const [view, setView] = useState<View>("applications");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [canBootstrap, setCanBootstrap] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [showAuth, setShowAuth] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((user) => {
        if (!alive) return;
        setCurrentUser(user);
        setShowAuth(false);
      })
      .catch(async () => {
        if (!alive) return;
        setCurrentUser(null);
        try {
          const state = await api.bootstrapState();
          if (alive) setCanBootstrap(state.can_bootstrap);
        } catch {
          if (alive) setCanBootstrap(false);
        }
      })
      .finally(() => alive && setAuthChecked(true));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!currentUser) {
      setLoading(false);
      return;
    }
    if (currentUser.role === "client" || currentUser.role === "owner") {
      setLoading(false);
      return;
    }
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
      .catch((err: Error) => {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 401) {
          setCurrentUser(null);
          return;
        }
        setError(err.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [currentUser, refreshKey]);

  const navItems = currentUser?.role === "admin" ? [...baseNavItems, adminNavItem] : baseNavItems;
  const selectedTitle = navItems.find((item) => item.id === view)?.label || "Сервис";

  async function handleLogout() {
    await api.logout().catch(() => undefined);
    setCurrentUser(null);
    setShowAuth(false);
    setProviders([]);
    setAddresses([]);
    setApplications([]);
  }

  if (!authChecked) {
    return (
      <div className="auth-shell">
        <LoadingRows />
      </div>
    );
  }

  if (!currentUser) {
    if (showAuth) {
      return (
        <AuthView
          canBootstrap={canBootstrap}
          onAuthenticated={(user) => {
            setCurrentUser(user);
            setShowAuth(false);
          }}
          onBack={() => setShowAuth(false)}
        />
      );
    }

    return (
      <PublicCatalog
        canBootstrap={canBootstrap}
        onAuthenticated={(user) => setCurrentUser(user)}
        onLoginClick={() => setShowAuth(true)}
      />
    );
  }

  if (currentUser.role === "client") {
    return <ClientDashboardView user={currentUser} onLogout={handleLogout} />;
  }

  if (currentUser.role === "owner") {
    return <OwnerDashboardView user={currentUser} onLogout={handleLogout} />;
  }

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
          <span>{currentUser.role === "admin" ? "Администратор" : "Пользователь"}</span>
          <strong>{currentUser.email}</strong>
          <button className="text-action" onClick={handleLogout} type="button">
            <LogOut size={15} /> Выйти
          </button>
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
              <ApplicationsView
                applications={applications}
                providers={providers}
                addresses={addresses}
                onChanged={() => setRefreshKey((value) => value + 1)}
              />
            )}
            {view === "registry" && <RegistryView />}
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
            {view === "access" && currentUser.role === "admin" && <AccessView />}
          </>
        )}
      </main>
    </div>
  );
}

function ClientDashboardView({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) {
  const [applications, setApplications] = useState<ClientApplication[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .clientApplications()
      .then((result) => {
        if (!alive) return;
        setApplications(result);
        setSelectedId((current) => {
          if (current && result.some((application) => application.id === current)) return current;
          return result[0]?.id || null;
        });
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  const selectedApplication = useMemo(
    () => applications.find((application) => application.id === selectedId) || applications[0] || null,
    [applications, selectedId]
  );

  return (
    <main className="client-shell">
      <header className="client-topbar">
        <div className="brand">
          <div className="brand-mark">ЮА</div>
          <div>
            <strong>Личный кабинет клиента</strong>
            <span>{user.email}</span>
          </div>
        </div>
        <div className="actions">
          <Button variant="secondary" onClick={() => setRefreshKey((value) => value + 1)}>
            <RefreshCw size={16} /> Обновить
          </Button>
          <Button variant="secondary" onClick={onLogout}>
            <LogOut size={16} /> Выйти
          </Button>
        </div>
      </header>

      <section className="client-heading">
        <span className="eyebrow">Мои заявки</span>
        <h1>Статус и адрес по заявке на юридический адрес</h1>
      </section>

      <InlineError message={error} />

      {loading ? (
        <LoadingRows />
      ) : applications.length === 0 ? (
        <EmptyState title="Заявок пока нет" text="После отправки заявки она появится в этом кабинете." />
      ) : (
        <section className="client-dashboard">
          <div className="client-list">
            {applications.map((application) => (
              <button
                className={application.id === selectedApplication?.id ? "client-application active" : "client-application"}
                key={application.id}
                onClick={() => setSelectedId(application.id)}
                type="button"
              >
                <span className={`status ${application.status}`}>
                  {statusLabels[application.status] || application.status}
                </span>
                <strong>{application.company_name || application.planned_client_name || "Компания"}</strong>
                <small>{application.full_address}</small>
                <b>{formatMoney(application.selected_price)}</b>
              </button>
            ))}
          </div>

          {selectedApplication ? (
            <div className="client-detail">
              <div className="client-detail-header">
                <div>
                  <span className="eyebrow">{typeLabels[selectedApplication.type]}</span>
                  <h2>{selectedApplication.company_name || selectedApplication.planned_client_name || "Заявка"}</h2>
                </div>
                <span className={`status ${selectedApplication.status}`}>
                  {statusLabels[selectedApplication.status] || selectedApplication.status}
                </span>
              </div>

              <div className="client-metrics">
                <div>
                  <ReceiptText size={18} />
                  <span>Стоимость</span>
                  <strong>{formatMoney(selectedApplication.selected_price)}</strong>
                </div>
                <div>
                  <FileClock size={18} />
                  <span>Срок</span>
                  <strong>{selectedApplication.term_months ? `${selectedApplication.term_months} мес.` : "—"}</strong>
                </div>
                <div>
                  <Home size={18} />
                  <span>ИФНС</span>
                  <strong>{selectedApplication.fns_number ? `№ ${selectedApplication.fns_number}` : "—"}</strong>
                </div>
              </div>

              <div className="client-info-grid">
                <div>
                  <span>Адрес</span>
                  <strong>{selectedApplication.full_address}</strong>
                  {selectedApplication.room_number ? <small>{selectedApplication.room_number}</small> : null}
                </div>
                <div>
                  <span>Собственник</span>
                  <strong>{selectedApplication.provider_name}</strong>
                </div>
                <div>
                  <span>Контакт</span>
                  <strong>{selectedApplication.contact_name || "—"}</strong>
                  <small>{[selectedApplication.contact_phone, selectedApplication.contact_email].filter(Boolean).join(" · ")}</small>
                </div>
                <div>
                  <span>Корреспонденция</span>
                  <strong>{selectedApplication.has_correspondence_service ? "Подключена" : "Не подключена"}</strong>
                  {selectedApplication.correspondence_price ? <small>{formatMoney(selectedApplication.correspondence_price)}</small> : null}
                </div>
              </div>

              <div className="timeline-panel">
                <div className="timeline-title">
                  <FileText size={18} />
                  <strong>Лента заявки</strong>
                </div>
                {selectedApplication.events.length ? (
                  <div className="timeline">
                    {selectedApplication.events.map((event) => (
                      <div className="timeline-item" key={event.id}>
                        <span>{formatDate(event.created_at)}</span>
                        <strong>{event.title}</strong>
                        <p>{event.message}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="Событий пока нет" text="Обновления по заявке появятся после проверки." />
                )}
              </div>
            </div>
          ) : null}
        </section>
      )}
    </main>
  );
}

function OwnerDashboardView({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) {
  const [dashboard, setDashboard] = useState<OwnerDashboard | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .ownerDashboard()
      .then((result) => {
        if (!alive) return;
        setDashboard(result);
        setSelectedId((current) => {
          if (current && result.applications.some((application) => application.id === current)) return current;
          return result.applications[0]?.id || null;
        });
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  const applications = dashboard?.applications || [];
  const addresses = dashboard?.addresses || [];
  const selectedApplication = useMemo<OwnerApplication | null>(
    () => applications.find((application) => application.id === selectedId) || applications[0] || null,
    [applications, selectedId]
  );
  const publishedCount = addresses.filter((address) => address.publication_status === "published").length;
  const availableCount = addresses.filter((address) => address.is_available).length;
  const actionableCount = applications.filter((application) => application.available_actions.length > 0).length;

  async function runOwnerAction(action: string) {
    if (!selectedApplication) return;
    setActionBusy(action);
    setActionError(null);
    try {
      await api.runApplicationAction(selectedApplication.id, action);
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <main className="owner-shell">
      <header className="owner-topbar">
        <div className="brand">
          <div className="brand-mark">ЮА</div>
          <div>
            <strong>Кабинет исполнителя</strong>
            <span>{user.email}</span>
          </div>
        </div>
        <div className="actions">
          <Button variant="secondary" onClick={() => setRefreshKey((value) => value + 1)}>
            <RefreshCw size={16} /> Обновить
          </Button>
          <Button variant="secondary" onClick={onLogout}>
            <LogOut size={16} /> Выйти
          </Button>
        </div>
      </header>

      <section className="owner-heading">
        <span className="eyebrow">Собственник адреса</span>
        <h1>Заявки и адреса, назначенные вашей организации</h1>
      </section>

      <InlineError message={error} />

      {loading ? (
        <LoadingRows />
      ) : !dashboard ? (
        <EmptyState title="Кабинет недоступен" text="Проверьте привязку пользователя к организации исполнителя." />
      ) : (
        <section className="owner-layout">
          <aside className="owner-side">
            <div className="owner-provider-card">
              <Building2 size={22} />
              <span>Организация</span>
              <strong>{dashboard.provider.short_name}</strong>
              <small>{dashboard.provider.phone || dashboard.provider.full_name}</small>
            </div>

            <div className="owner-metrics">
              <div>
                <Home size={17} />
                <span>Адресов</span>
                <strong>{addresses.length}</strong>
              </div>
              <div>
                <CheckCircle2 size={17} />
                <span>Опубликовано</span>
                <strong>{publishedCount}</strong>
              </div>
              <div>
                <FileClock size={17} />
                <span>Требуют внимания</span>
                <strong>{actionableCount}</strong>
              </div>
            </div>

            <div className="owner-addresses">
              <div className="timeline-title">
                <Database size={18} />
                <strong>Мои адреса</strong>
              </div>
              {addresses.length ? (
                addresses.map((address) => (
                  <div className="owner-address-item" key={address.id}>
                    <strong>{address.full_address}</strong>
                    <span>
                      {address.fns_number ? `ИФНС ${address.fns_number}` : "ИФНС не указана"} ·{" "}
                      {address.is_available ? "доступен" : "недоступен"}
                    </span>
                    <small>{formatMoney(address.price_11m)} за 11 мес.</small>
                  </div>
                ))
              ) : (
                <EmptyState title="Адресов нет" text="Администратор еще не привязал адреса к организации." />
              )}
            </div>
          </aside>

          <div className="owner-main">
            {applications.length ? (
              <div className="owner-application-list">
                {applications.map((application) => (
                  <button
                    className={application.id === selectedApplication?.id ? "owner-application active" : "owner-application"}
                    key={application.id}
                    onClick={() => setSelectedId(application.id)}
                    type="button"
                  >
                    <span className={`status ${application.status}`}>
                      {statusLabels[application.status] || application.status}
                    </span>
                    <strong>{application.company_name || application.planned_client_name || "Компания"}</strong>
                    <small>{application.full_address}</small>
                    <b>{formatMoney(application.selected_price)}</b>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState title="Заявок пока нет" text="Когда администратор назначит заявку на ваш адрес, она появится здесь." />
            )}

            {selectedApplication ? (
              <div className="owner-detail">
                <div className="client-detail-header">
                  <div>
                    <span className="eyebrow">{typeLabels[selectedApplication.type]}</span>
                    <h2>{selectedApplication.company_name || selectedApplication.planned_client_name || "Заявка"}</h2>
                  </div>
                  <span className={`status ${selectedApplication.status}`}>
                    {statusLabels[selectedApplication.status] || selectedApplication.status}
                  </span>
                </div>

                <div className="client-metrics">
                  <div>
                    <ReceiptText size={18} />
                    <span>Сумма адреса</span>
                    <strong>{formatMoney(selectedApplication.selected_price)}</strong>
                  </div>
                  <div>
                    <FileClock size={18} />
                    <span>Срок</span>
                    <strong>{selectedApplication.term_months ? `${selectedApplication.term_months} мес.` : "—"}</strong>
                  </div>
                  <div>
                    <Home size={18} />
                    <span>ИФНС</span>
                    <strong>{selectedApplication.fns_number ? `№ ${selectedApplication.fns_number}` : "—"}</strong>
                  </div>
                </div>

                <div className="client-info-grid">
                  <div>
                    <span>Адрес</span>
                    <strong>{selectedApplication.full_address}</strong>
                  </div>
                  <div>
                    <span>Контакт клиента</span>
                    <strong>{selectedApplication.contact_name || "—"}</strong>
                    <small>{[selectedApplication.contact_phone, selectedApplication.contact_email].filter(Boolean).join(" · ")}</small>
                  </div>
                  <div>
                    <span>Следующий шаг</span>
                    <strong>
                      {selectedApplication.available_actions.length
                        ? selectedApplication.available_actions.map((action) => ownerActionLabels[action] || action).join(", ")
                        : "Ожидает другой роли"}
                    </strong>
                  </div>
                  <div>
                    <span>Корреспонденция</span>
                    <strong>{selectedApplication.has_correspondence_service ? "Подключена" : "Не подключена"}</strong>
                    {selectedApplication.correspondence_price ? <small>{formatMoney(selectedApplication.correspondence_price)}</small> : null}
                  </div>
                </div>

                {selectedApplication.available_actions.length ? (
                  <div className="owner-action-strip">
                    {selectedApplication.available_actions.map((action) => {
                      const Icon =
                        action === "accept"
                          ? CheckCircle2
                          : action === "reject"
                            ? XCircle
                            : action === "start_documents"
                              ? FileText
                              : Upload;
                      return (
                        <Button
                          disabled={actionBusy !== null}
                          key={action}
                          onClick={() => runOwnerAction(action)}
                          variant={action === "reject" ? "secondary" : "primary"}
                        >
                          {actionBusy === action ? <Loader2 className="spin" size={16} /> : <Icon size={16} />}
                          {ownerActionLabels[action] || action}
                        </Button>
                      );
                    })}
                  </div>
                ) : null}
                <InlineError message={actionError} />

                <div className="timeline-panel">
                  <div className="timeline-title">
                    <FileText size={18} />
                    <strong>Лента исполнителя</strong>
                  </div>
                  {selectedApplication.events.length ? (
                    <div className="timeline">
                      {selectedApplication.events.map((event) => (
                        <div className="timeline-item" key={event.id}>
                          <span>{formatDate(event.created_at)}</span>
                          <strong>{event.title}</strong>
                          <p>{event.message}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="Событий пока нет" text="События для исполнителя появятся после назначения заявки." />
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </section>
      )}
    </main>
  );
}

function ApplicationsView({
  applications,
  providers,
  addresses,
  onChanged
}: {
  applications: Application[];
  providers: Provider[];
  addresses: Address[];
  onChanged: () => void;
}) {
  const [promotingId, setPromotingId] = useState<string | null>(null);

  if (!applications.length) {
    return <EmptyState title="Заявок пока нет" text="Создайте первичную регистрацию или смену адреса." />;
  }

  const providerById = new Map(providers.map((provider) => [provider.id, provider]));
  const addressById = new Map(addresses.map((address) => [address.id, address]));

  return (
    <section className="table-panel">
      <div className="table-header">
        <span>Тип</span>
        <span>Компания</span>
        <span>Контакты</span>
        <span>Статус</span>
        <span>Собственник</span>
        <span>Адрес</span>
        <span>Дата</span>
        <span />
      </div>
      {applications.map((application) => (
        <div className="table-row" key={application.id}>
          <span>{typeLabels[application.type]}</span>
          <span>{application.company_name || application.planned_client_name || "—"}</span>
          <span className="contact-cell">
            <b>{application.contact_name || "—"}</b>
            <small>{[application.contact_phone, application.contact_email].filter(Boolean).join(" · ") || "нет контактов"}</small>
          </span>
          <span className={`status ${application.status}`}>{statusLabels[application.status] || application.status}</span>
          <span>{providerById.get(application.provider_id)?.short_name || "—"}</span>
          <span>{addressById.get(application.address_id)?.full_address || "—"}</span>
          <span>{formatDate(application.created_at)}</span>
          <div className="row-actions">
            {application.type === "initial_registration" ? (
              <button className="text-action" onClick={() => setPromotingId(application.id)} type="button">
                <FileCheck2 size={15} /> Договор
              </button>
            ) : null}
            <a className="download-link" href={packageDownloadUrl(application.id)}>
              <Download size={16} /> ZIP
            </a>
          </div>
        </div>
      ))}
      {promotingId ? (
        <PromoteContractPanel
          application={applications.find((item) => item.id === promotingId) || null}
          onClose={() => setPromotingId(null)}
          onDone={onChanged}
        />
      ) : null}
    </section>
  );
}

function PromoteContractPanel({
  application,
  onClose,
  onDone
}: {
  application: Application | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [inn, setInn] = useState("");
  const [termMonths, setTermMonths] = useState<6 | 11>(11);
  const [noticePeriod, setNoticePeriod] = useState<NoticePeriod>("1m");
  const [hasCorrespondence, setHasCorrespondence] = useState(false);
  const [contactName, setContactName] = useState(application?.contact_name || "");
  const [contactPhone, setContactPhone] = useState(application?.contact_phone || "");
  const [contactEmail, setContactEmail] = useState(application?.contact_email || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  if (!application) return null;
  const currentApplication = application;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDownloadUrl(null);
    try {
      const child = await api.promoteToContract(currentApplication.id, {
        client_inn: inn,
        term_months: termMonths,
        notice_period: noticePeriod,
        has_correspondence_service: hasCorrespondence,
        contact_name: contactName || null,
        contact_phone: contactPhone || null,
        contact_email: contactEmail || null
      });
      await api.generatePackage(child.id);
      setDownloadUrl(packageDownloadUrl(child.id));
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <form className="modal-panel" onSubmit={submit}>
        <header>
          <div>
            <span className="eyebrow">После регистрации</span>
            <h2>Создать договор аренды</h2>
          </div>
          <button className="text-action" onClick={onClose} type="button">
            Закрыть
          </button>
        </header>
        <p>
          Для первичной заявки «{application.company_name || application.planned_client_name}» будет создана дочерняя
          договорная заявка по ИНН, а затем сформирован ZIP-комплект.
        </p>
        <div className="form-grid">
          <Field label="ИНН зарегистрированной компании">
            <input value={inn} onChange={(event) => setInn(event.target.value)} inputMode="numeric" required />
          </Field>
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
          <label className="toggle-field compact">
            <input
              checked={hasCorrespondence}
              onChange={(event) => setHasCorrespondence(event.target.checked)}
              type="checkbox"
            />
            <span>Корреспонденция</span>
          </label>
        </div>
        <div className="form-grid three">
          <Field label="Контактное лицо">
            <input value={contactName} onChange={(event) => setContactName(event.target.value)} />
          </Field>
          <Field label="Телефон">
            <input value={contactPhone} onChange={(event) => setContactPhone(event.target.value)} />
          </Field>
          <Field label="E-mail">
            <input value={contactEmail} onChange={(event) => setContactEmail(event.target.value)} type="email" />
          </Field>
        </div>
        <InlineError message={error} />
        <div className="actions">
          <Button disabled={busy || inn.length !== 10} type="submit">
            {busy ? <Loader2 className="spin" size={16} /> : <FileArchive size={16} />}
            Создать договор
          </Button>
          {downloadUrl ? (
            <a className="btn secondary" href={downloadUrl}>
              <Download size={16} /> Скачать ZIP
            </a>
          ) : null}
        </div>
      </form>
    </div>
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
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [contactEmail, setContactEmail] = useState("");
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
              planned_client_name: plannedClientName,
              contact_name: contactName || null,
              contact_phone: contactPhone || null,
              contact_email: contactEmail || null
            }
          : {
              type,
              provider_id: providerId,
              address_id: addressId,
              client_inn: inn,
              term_months: termMonths,
              notice_period: noticePeriod,
              has_correspondence_service: hasCorrespondence,
              contact_name: contactName || null,
              contact_phone: contactPhone || null,
              contact_email: contactEmail || null
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

        <div className="form-grid three">
          <Field label="Контактное лицо">
            <input
              value={contactName}
              onChange={(event) => setContactName(event.target.value)}
              placeholder="Менеджер клиента"
            />
          </Field>
          <Field label="Телефон">
            <input
              value={contactPhone}
              onChange={(event) => setContactPhone(event.target.value)}
              placeholder="+7 900 000-00-00"
            />
          </Field>
          <Field label="E-mail">
            <input
              value={contactEmail}
              onChange={(event) => setContactEmail(event.target.value)}
              placeholder="mail@example.ru"
              type="email"
            />
          </Field>
        </div>

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

function RegistryView() {
  const [items, setItems] = useState<ActiveClientRegistryItem[]>([]);
  const [dueOnly, setDueOnly] = useState(false);
  const [paymentClient, setPaymentClient] = useState<ActiveClientRegistryItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .activeClients(dueOnly ? 30 : undefined)
      .then((result) => {
        if (alive) setItems(result);
      })
      .catch((err: Error) => alive && setError(err.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [dueOnly]);

  const totals = useMemo(() => {
    const overdue = items.filter((item) => item.renewal_status === "overdue").length;
    const dueSoon = items.filter((item) => item.renewal_status === "due_soon").length;
    return { all: items.length, overdue, dueSoon };
  }, [items]);

  return (
    <section className="registry-view">
      <div className="registry-toolbar">
        <div className="metric-line">
          <div>
            <span>Всего</span>
            <strong>{totals.all}</strong>
          </div>
          <div>
            <span>На пролонгацию</span>
            <strong>{totals.dueSoon}</strong>
          </div>
          <div>
            <span>Просрочены</span>
            <strong>{totals.overdue}</strong>
          </div>
        </div>
        <label className="toggle-field compact registry-filter">
          <input checked={dueOnly} onChange={(event) => setDueOnly(event.target.checked)} type="checkbox" />
          <span>Только ближайшие 30 дней</span>
        </label>
      </div>

      <InlineError message={error} />

      {loading ? (
        <LoadingRows />
      ) : items.length ? (
        <div className="registry-table">
          <div className="registry-header">
            <span>Компания</span>
            <span>Контакты</span>
            <span>Договор</span>
            <span>Срок</span>
            <span>Пролонгация</span>
            <span>Адрес</span>
            <span />
          </div>
          {items.map((item) => (
            <div className="registry-row" key={item.contract_id}>
              <span>
                <b>{item.company_name}</b>
                <small>ИНН {item.client_inn}</small>
              </span>
              <span className="contact-cell">
                <b>{item.contact_name || "—"}</b>
                <small>{[item.contact_phone, item.contact_email].filter(Boolean).join(" · ") || "нет контактов"}</small>
              </span>
              <span>
                <b>{item.contract_number}</b>
                <small>{formatDate(item.contract_date)}</small>
              </span>
              <span>
                <b>{item.term_months} мес.</b>
                <small>
                  {formatDate(item.start_date)} — {formatDate(item.end_date)}
                </small>
              </span>
              <span>
                <b className={`renewal ${item.renewal_status}`}>
                  {item.days_until_renewal < 0
                    ? `${Math.abs(item.days_until_renewal)} дн. проср.`
                    : `${item.days_until_renewal} дн.`}
                </b>
                <small>{formatDate(item.renewal_date)}</small>
              </span>
              <span>
                <b>{item.provider_name}</b>
                <small>{item.address_full}</small>
              </span>
              <div className="row-actions">
                <button className="text-action" onClick={() => setPaymentClient(item)} type="button">
                  <ReceiptText size={15} /> Оплата
                </button>
                <a className="download-link" href={packageDownloadUrl(item.application_id)}>
                  <Download size={16} /> ZIP
                </a>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState title="Действующих договоров нет" text="Реестр появится после формирования договоров по смене адреса." />
      )}
      {paymentClient ? <PaymentDocumentsPanel client={paymentClient} onClose={() => setPaymentClient(null)} /> : null}
    </section>
  );
}

function PaymentDocumentsPanel({
  client,
  onClose
}: {
  client: ActiveClientRegistryItem;
  onClose: () => void;
}) {
  const [documents, setDocuments] = useState<PaymentDocument[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [amount, setAmount] = useState("");
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10));
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .paymentDocuments(client.client_id)
      .then(setDocuments)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [client.client_id]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const formData = new FormData();
    formData.append("file", file);
    if (paymentDate) formData.append("payment_date", paymentDate);
    if (amount) formData.append("amount", amount);
    if (comment) formData.append("comment", comment);
    try {
      await api.uploadPaymentDocument(client.client_id, formData);
      setFile(null);
      setAmount("");
      setComment("");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <section className="modal-panel payment-panel">
        <header>
          <div>
            <span className="eyebrow">Карточка клиента</span>
            <h2>{client.company_name}</h2>
          </div>
          <button className="text-action" onClick={onClose} type="button">
            Закрыть
          </button>
        </header>

        <form className="payment-upload" onSubmit={submit}>
          <Field label="Документ">
            <input onChange={(event) => setFile(event.target.files?.[0] || null)} type="file" />
          </Field>
          <Field label="Дата оплаты">
            <input value={paymentDate} onChange={(event) => setPaymentDate(event.target.value)} type="date" />
          </Field>
          <Field label="Сумма">
            <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" />
          </Field>
          <Field label="Комментарий">
            <input value={comment} onChange={(event) => setComment(event.target.value)} />
          </Field>
          <Button disabled={!file || busy} type="submit">
            {busy ? <Loader2 className="spin" size={16} /> : <Upload size={16} />}
            Добавить
          </Button>
        </form>

        <InlineError message={error} />

        {loading ? (
          <LoadingRows />
        ) : documents.length ? (
          <div className="payment-list">
            {documents.map((document) => (
              <div className="payment-item" key={document.id}>
                <div>
                  <strong>{document.original_filename}</strong>
                  <span>
                    {formatDate(document.payment_date)} · {document.amount ? `${document.amount} руб.` : "сумма не указана"}
                    {document.comment ? ` · ${document.comment}` : ""}
                  </span>
                </div>
                <a className="download-link" href={paymentDocumentDownloadUrl(document.download_url)}>
                  <Download size={16} /> Скачать
                </a>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="Документов об оплате нет" text="Добавьте чек, платёжное поручение или счёт при необходимости." />
        )}
      </section>
    </div>
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
