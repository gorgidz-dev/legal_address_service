import {
  Bell,
  Building2,
  Camera,
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
  Image as ImageIcon,
  KeyRound,
  MessageSquare,
  Loader2,
  LogOut,
  Monitor,
  Plus,
  RefreshCw,
  Smartphone,
  ReceiptText,
  Search,
  Settings,
  ShieldCheck,
  Star,
  Trash2,
  Upload,
  UserPlus,
  X,
  XCircle
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, api, packageDownloadUrl, paymentDocumentDownloadUrl } from "./api";
import { PhoneInput, formatRuPhone } from "./PhoneInput";
import PublicCatalog from "./publicCatalog";
import { ChatsListPanel } from "./ChatsListPanel";
import { OwnerAddressEditor } from "./OwnerAddressEditor";
import { PushToggle } from "./PushToggle";
import { AdminReviewModeration } from "./sections/AdminReviewModeration";
import type {
  ActiveClientRegistryItem,
  Address,
  AddressPhotoAdmin,
  AddressServiceAdmin,
  OwnerAddress,
  AddressPublicationStatus,
  Application,
  ApplicationDocumentModeration,
  ApplicationDocument,
  ApplicationType,
  ClientApplication,
  CurrentUser,
  DadataLookup,
  DemoSeedResult,
  DocumentFileKind,
  Invitation,
  InvitationCreateResult,
  NoticePeriod,
  AppNotification,
  NotificationInbox,
  OwnerApplication,
  OwnerConnectionRequestStatus,
  OwnerDashboard,
  Payment,
  PaymentDocument,
  Provider,
  ProviderConnectionRequest,
  ProviderConnectionRequestApproveResult,
  UserSessionInfo
} from "./types";

type View =
  | "applications"
  | "registry"
  | "new"
  | "providers"
  | "addresses"
  | "templates"
  | "access"
  | "photos"
  | "provider-requests"
  | "address-moderation"
  | "address-services"
  | "address-chats"
  | "review-moderation";

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

const adminPhotosNavItem: { id: View; label: string; icon: typeof Home } = {
  id: "photos",
  label: "Фото на модерацию",
  icon: ImageIcon
};

const adminProviderRequestsNavItem: { id: View; label: string; icon: typeof Home } = {
  id: "provider-requests",
  label: "Заявки собственников",
  icon: Building2
};

const adminAddressModerationNavItem: { id: View; label: string; icon: typeof Home } = {
  id: "address-moderation",
  label: "Модерация адресов",
  icon: Home
};

const adminAddressServicesNavItem: { id: View; label: string; icon: typeof Home } = {
  id: "address-services",
  label: "Услуги адресов",
  icon: Settings
};

const adminAddressChatsNavItem: { id: View; label: string; icon: typeof Home } = {
  id: "address-chats",
  label: "Чаты",
  icon: MessageSquare
};

const adminReviewModerationNavItem: { id: View; label: string; icon: typeof Home } = {
  id: "review-moderation",
  label: "Отзывы на модерацию",
  icon: MessageSquare
};

const ownerRequestStatusLabels: Record<string, string> = {
  new: "Новая",
  reviewing: "В работе",
  invited: "Приглашение отправлено",
  rejected: "Отклонена"
};

const photoModerationStatusLabels: Record<string, string> = {
  pending: "На модерации",
  approved: "Одобрено",
  rejected: "Отклонено"
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

const roleLabels: Record<string, string> = {
  admin: "Администратор",
  manager: "Менеджер",
  lawyer: "Юрист",
  client: "Клиент",
  owner: "Собственник"
};

const adminDocumentActionLabels: Record<string, string> = {
  approve_documents: "Одобрить комплект",
  request_document_revision: "На доработку"
};

const adminWorkflowActionLabels: Record<string, string> = {
  start_admin_review: "Взять в проверку",
  assign_owner: "Передать собственнику",
  request_client_fix: "Запросить уточнения",
  cancel: "Отменить",
  resolve_dispute: "Закрыть спор",
  complete: "Завершить"
};

const documentModerationActions = new Set(["approve_documents", "request_document_revision"]);

const ownerDocumentKinds: DocumentFileKind[] = [
  "owner_consent",
  "contract",
  "act",
  "postal_service",
  "ownership_proof",
  "guarantee_letter"
];

const documentKindLabels: Record<DocumentFileKind, string> = {
  client_requisites: "Реквизиты клиента",
  company_details: "Карточка компании",
  ownership_proof: "Подтверждение собственности",
  guarantee_letter: "Гарантийное письмо",
  contract: "Договор",
  act: "Акт",
  owner_consent: "Согласие собственника",
  postal_service: "Почтовое обслуживание",
  admin_review_file: "Файл проверки"
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU").format(new Date(value));
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0
  }).format(Number(value));
}

function formatFileSize(value: number): string {
  if (value < 1024) return `${value} Б`;
  if (value < 1024 * 1024) return `${Math.round(value / 102.4) / 10} КБ`;
  return `${Math.round(value / 1024 / 102.4) / 10} МБ`;
}

function ownerCanUploadDocuments(application: OwnerApplication | null): boolean {
  return application?.status === "documents_preparing" || application?.status === "documents_revision";
}

function ownerNextStepLabel(application: OwnerApplication): string {
  if (application.available_actions.length) {
    return application.available_actions.map((action) => ownerActionLabels[action] || action).join(", ");
  }
  if (ownerCanUploadDocuments(application)) return "Загрузить комплект документов";
  if (application.status === "documents_review") return "Проверка площадки";
  if (application.status === "ready_for_client") return "Документы готовы клиенту";
  if (application.status === "completed") return "Заявка завершена";
  return "Ожидает другой роли";
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

function NotificationCenter({
  refreshKey = 0,
  onNavigate,
}: {
  refreshKey?: number;
  /** Куда вести при клике. UI-роутинг наружу. */
  onNavigate?: (notification: AppNotification) => void;
}) {
  const [inbox, setInbox] = useState<NotificationInbox | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const unreadCount = inbox?.unread_count || 0;
  const items = inbox?.items || [];

  function load() {
    setLoading(true);
    setError(null);
    api
      .notifications({ limit: 20 })
      .then(setInbox)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [refreshKey]);

  // Лёгкий полл — раз в 30 сек подтянуть новые.
  useEffect(() => {
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, []);

  async function markRead(notification: AppNotification) {
    if (notification.is_read) return notification;
    try {
      const updated = await api.markNotificationRead(notification.id, notification.source);
      setInbox((current) => {
        if (!current) return current;
        return {
          unread_count: Math.max(0, current.unread_count - 1),
          items: current.items.map((item) => (item.id === updated.id ? updated : item))
        };
      });
      return updated;
    } catch (err) {
      setError((err as Error).message);
      return notification;
    }
  }

  async function handleClick(notification: AppNotification) {
    await markRead(notification);
    if (notification.link_type && onNavigate) {
      onNavigate(notification);
      setOpen(false);
    }
  }

  return (
    <div className="notification-center">
      <button
        aria-label="Уведомления"
        className={open ? "notification-button active" : "notification-button"}
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <Bell size={18} strokeWidth={1.8} />
        {unreadCount > 0 ? <span className="notification-badge">{unreadCount > 9 ? "9+" : unreadCount}</span> : null}
      </button>

      {open ? (
        <div className="notification-popover">
          <header>
            <div>
              <strong>Уведомления</strong>
              <span>{unreadCount ? `${unreadCount} непрочит.` : "Все прочитано"}</span>
            </div>
            <button className="text-action" onClick={load} type="button">
              <RefreshCw size={14} /> Обновить
            </button>
          </header>

          {error ? <div className="notification-error">{error}</div> : null}

          {loading ? (
            <div className="notification-skeleton">
              <div />
              <div />
              <div />
            </div>
          ) : items.length ? (
            <div className="notification-list">
              {items.map((notification) => {
                const isChat = notification.link_type === "chat";
                const statusLabel = notification.application_status
                  ? statusLabels[notification.application_status] || notification.application_status
                  : isChat ? "Чат" : "Уведомление";
                const subtitle = notification.application_title
                  ? `${notification.application_title} · ${formatDateTime(notification.created_at)}`
                  : formatDateTime(notification.created_at);
                return (
                  <button
                    className={notification.is_read ? "notification-item" : "notification-item unread"}
                    key={`${notification.source}-${notification.id}`}
                    onClick={() => handleClick(notification)}
                    type="button"
                  >
                    <span className={`status ${isChat ? "chat" : notification.application_status || ""}`}>
                      {statusLabel}
                    </span>
                    <strong>{notification.title}</strong>
                    <small>{subtitle}</small>
                    <p>{notification.message}</p>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="notification-empty">Новых уведомлений нет</div>
          )}
        </div>
      ) : null}
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

function SessionsView() {
  const [sessions, setSessions] = useState<UserSessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmKick, setConfirmKick] = useState(false);

  function load() {
    setLoading(true);
    setError(null);
    api
      .listSessions()
      .then(setSessions)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function logoutOthers() {
    setBusy(true);
    setError(null);
    try {
      await api.logoutAll();
      setConfirmKick(false);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const others = sessions.filter((s) => !s.is_current);

  return (
    <section className="stack">
      <div className="panel">
        <div className="panel-title">
          <Monitor size={20} />
          <div>
            <strong>Активные сессии</strong>
            <span>Устройства, где сейчас открыт аккаунт. Можно завершить все, кроме этого.</span>
          </div>
        </div>

        {error ? <p className="error">{error}</p> : null}

        {loading ? (
          <LoadingRows />
        ) : (
          <>
            <div className="sessions-list">
              {sessions.map((session) => (
                <div key={session.id} className={`session-row${session.is_current ? " session-row--current" : ""}`}>
                  <div className="session-icon">
                    {session.session_type === "mobile" ? <Smartphone size={18} /> : <Monitor size={18} />}
                  </div>
                  <div className="session-main">
                    <div className="session-title">
                      {session.device_name || (session.session_type === "mobile" ? "Мобильное устройство" : "Браузер")}
                      {session.is_current ? <span className="session-badge">эта сессия</span> : null}
                    </div>
                    <div className="session-meta">
                      {session.user_agent ? <span title={session.user_agent}>{session.user_agent.slice(0, 80)}</span> : null}
                    </div>
                    <div className="session-meta">
                      {session.ip_address ? <span>IP: {session.ip_address}</span> : null}
                      <span>Создана: {formatDateTime(session.created_at)}</span>
                      <span>Активность: {formatDateTime(session.last_seen_at)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {others.length > 0 ? (
              <div className="sessions-actions">
                {confirmKick ? (
                  <>
                    <span>Завершить {others.length} {others.length === 1 ? "сессию" : "сессий"}? Текущая останется активной.</span>
                    <Button disabled={busy} onClick={logoutOthers} variant="secondary">
                      {busy ? <Loader2 className="spin" size={16} /> : <LogOut size={16} />}
                      Подтвердить
                    </Button>
                    <Button onClick={() => setConfirmKick(false)} variant="ghost">
                      Отмена
                    </Button>
                  </>
                ) : (
                  <Button onClick={() => setConfirmKick(true)} variant="secondary">
                    <LogOut size={16} />
                    Завершить остальные сессии ({others.length})
                  </Button>
                )}
              </div>
            ) : (
              <p className="hint">Других активных сессий нет.</p>
            )}
          </>
        )}
      </div>
    </section>
  );
}

function AccessView() {
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [form, setForm] = useState({ email: "", full_name: "", role: "manager" });
  const [created, setCreated] = useState<InvitationCreateResult | null>(null);
  const [demoResult, setDemoResult] = useState<DemoSeedResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
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

  async function seedDemoData() {
    setDemoBusy(true);
    setError(null);
    try {
      const result = await api.seedDemoData();
      setDemoResult(result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDemoBusy(false);
    }
  }

  const inviteUrl = created ? `${window.location.origin}${created.invitation_path}` : "";
  const createdTotal = demoResult
    ? Object.values(demoResult.created).reduce((sum, value) => sum + value, 0)
    : 0;
  const updatedTotal = demoResult
    ? Object.values(demoResult.updated).reduce((sum, value) => sum + value, 0)
    : 0;

  return (
    <section className="stack">
      <div className="demo-seed-panel">
        <div className="panel-title">
          <Database size={20} />
          <div>
            <strong>Тестовые данные</strong>
            <span>Демо-аккаунты, адреса, заявки по статусам, документы и события.</span>
          </div>
        </div>
        <Button disabled={demoBusy} onClick={seedDemoData} variant="secondary">
          {demoBusy ? <Loader2 className="spin" size={16} /> : <Database size={16} />}
          Создать демо-набор
        </Button>
        {demoResult ? (
          <div className="demo-seed-result">
            <div className="demo-stat-grid">
              <div>
                <span>Создано</span>
                <strong>{createdTotal}</strong>
              </div>
              <div>
                <span>Обновлено</span>
                <strong>{updatedTotal}</strong>
              </div>
              <div>
                <span>Аккаунтов</span>
                <strong>{demoResult.credentials.length}</strong>
              </div>
            </div>
            <div className="demo-credentials">
              {demoResult.credentials.map((credential) => (
                <div key={credential.email}>
                  <strong>{credential.email}</strong>
                  <span>
                    {roleLabels[credential.role] || credential.role} · {credential.password}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>

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

function ProviderRequestsView() {
  const [statusFilter, setStatusFilter] = useState<OwnerConnectionRequestStatus | "all">("all");
  const [requests, setRequests] = useState<ProviderConnectionRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [approveTarget, setApproveTarget] = useState<ProviderConnectionRequest | null>(null);
  const [approved, setApproved] = useState<ProviderConnectionRequestApproveResult | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .adminListProviderRequests(statusFilter === "all" ? undefined : statusFilter)
      .then(setRequests)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [statusFilter]);

  async function changeStatus(req: ProviderConnectionRequest, status: "reviewing" | "rejected") {
    setBusyId(req.id);
    setError(null);
    try {
      const comment =
        status === "rejected"
          ? window.prompt("Комментарий (необязательно)") ?? undefined
          : undefined;
      await api.adminUpdateProviderRequestStatus(req.id, {
        status,
        admin_comment: comment ?? null
      });
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  const approveUrl = approved ? `${window.location.origin}${approved.invitation_path}` : "";

  return (
    <section className="stack">
      <Field label="Фильтр статусов">
        <select
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value as OwnerConnectionRequestStatus | "all")
          }
        >
          <option value="all">Все</option>
          <option value="new">Новые</option>
          <option value="reviewing">В работе</option>
          <option value="invited">Приглашение отправлено</option>
          <option value="rejected">Отклонены</option>
        </select>
      </Field>

      <InlineError message={error} />

      {approved ? (
        <div className="invite-result">
          <div>
            <strong>Приглашение собственника готово</strong>
            <span>{approveUrl}</span>
          </div>
          <button
            className="text-action"
            onClick={() => navigator.clipboard?.writeText(approveUrl)}
            type="button"
          >
            <Copy size={15} /> Копировать
          </button>
          <button className="text-action" onClick={() => setApproved(null)} type="button">
            <X size={15} /> Закрыть
          </button>
        </div>
      ) : null}

      {loading ? (
        <LoadingRows />
      ) : requests.length === 0 ? (
        <p className="hint">Заявок нет.</p>
      ) : (
        <SimpleList
          items={requests}
          render={(req) => (
            <>
              <strong>{req.company_name}</strong>
              <span>
                {req.contact_name} · {req.contact_email}
                {req.contact_phone ? ` · ${req.contact_phone}` : ""}
                {req.city ? ` · ${req.city}` : ""}
                {req.address_count !== null ? ` · ${req.address_count} адресов` : ""}
              </span>
              {req.comment ? <span>{req.comment}</span> : null}
              <span>
                Статус: <strong>{ownerRequestStatusLabels[req.status] || req.status}</strong>
                {req.admin_comment ? ` · ${req.admin_comment}` : ""}
              </span>
              {req.status === "new" || req.status === "reviewing" ? (
                <div className="row-actions">
                  {req.status === "new" ? (
                    <Button
                      disabled={busyId === req.id}
                      onClick={() => changeStatus(req, "reviewing")}
                      variant="secondary"
                    >
                      Взять в работу
                    </Button>
                  ) : null}
                  <Button
                    disabled={busyId === req.id}
                    onClick={() => setApproveTarget(req)}
                  >
                    Пригласить
                  </Button>
                  <Button
                    disabled={busyId === req.id}
                    onClick={() => changeStatus(req, "rejected")}
                    variant="secondary"
                  >
                    Отклонить
                  </Button>
                </div>
              ) : null}
            </>
          )}
        />
      )}

      {approveTarget ? (
        <ApproveProviderRequestModal
          request={approveTarget}
          onCancel={() => setApproveTarget(null)}
          onApproved={(result) => {
            setApproved(result);
            setApproveTarget(null);
            load();
          }}
        />
      ) : null}
    </section>
  );
}

function ApproveProviderRequestModal({
  request,
  onCancel,
  onApproved
}: {
  request: ProviderConnectionRequest;
  onCancel: () => void;
  onApproved: (result: ProviderConnectionRequestApproveResult) => void;
}) {
  const [code, setCode] = useState("");
  const [shortName, setShortName] = useState(request.company_name);
  const [fullName, setFullName] = useState(request.company_name);
  const [adminComment, setAdminComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.adminApproveProviderRequest(request.id, {
        code: code.trim(),
        short_name: shortName.trim(),
        full_name: fullName.trim(),
        admin_comment: adminComment.trim() || null
      });
      onApproved(result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <form className="modal-panel compact-form" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Создать собственника из заявки</h3>
        <p className="hint">{request.company_name} · {request.contact_email}</p>
        <Field label="Код собственника">
          <input value={code} onChange={(e) => setCode(e.target.value)} required />
        </Field>
        <Field label="Короткое наименование">
          <input value={shortName} onChange={(e) => setShortName(e.target.value)} required />
        </Field>
        <Field label="Полное наименование">
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        </Field>
        <Field label="Комментарий администратора">
          <textarea
            value={adminComment}
            onChange={(e) => setAdminComment(e.target.value)}
            rows={2}
          />
        </Field>
        <InlineError message={error} />
        <div className="row-actions">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
          <Button disabled={busy} type="submit">
            {busy ? <Loader2 className="spin" size={16} /> : <UserPlus size={16} />}
            Создать и пригласить
          </Button>
        </div>
      </form>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("applications");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [canBootstrap, setCanBootstrap] = useState(false);
  // viewMode = "catalog" → залогиненный юзер открыл публичный каталог из кабинета.
  // По умолчанию "dashboard" — после логина показываем кабинет.
  const [viewMode, setViewMode] = useState<"dashboard" | "catalog">("dashboard");
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

  const navItems =
    currentUser?.role === "admin"
      ? [
          ...baseNavItems,
          adminProviderRequestsNavItem,
          adminAddressModerationNavItem,
          adminAddressServicesNavItem,
          adminAddressChatsNavItem,
          adminReviewModerationNavItem,
          adminPhotosNavItem,
          adminNavItem
        ]
      : baseNavItems;
  const selectedTitle = navItems.find((item) => item.id === view)?.label || "Сервис";

  async function handleLogout() {
    await api.logout().catch(() => undefined);
    setCurrentUser(null);
    setShowAuth(false);
    setViewMode("dashboard");
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
        currentUser={currentUser}
        onAuthenticated={(user) => setCurrentUser(user)}
        onLoginClick={() => {
          // Запомнить, что юзер был на каталоге, — чтобы после логина
          // вернуться сюда (а не в кабинет). Используется auto-open чата.
          setViewMode("catalog");
          setShowAuth(true);
        }}
        onOpenDashboard={() => setViewMode("dashboard")}
      />
    );
  }

  // Авторизованный пользователь явно открыл публичный каталог.
  if (viewMode === "catalog") {
    return (
      <PublicCatalog
        canBootstrap={canBootstrap}
        currentUser={currentUser}
        onAuthenticated={(user) => setCurrentUser(user)}
        onLoginClick={() => setShowAuth(true)}
        onOpenDashboard={() => setViewMode("dashboard")}
      />
    );
  }

  if (currentUser.role === "client") {
    return (
      <ClientDashboardView
        user={currentUser}
        onLogout={handleLogout}
        onOpenCatalog={() => setViewMode("catalog")}
      />
    );
  }

  if (currentUser.role === "owner") {
    return (
      <OwnerDashboardView
        user={currentUser}
        onLogout={handleLogout}
        onOpenCatalog={() => setViewMode("catalog")}
      />
    );
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
          <button
            className="nav-item"
            type="button"
            onClick={() => setViewMode("catalog")}
            title="Открыть публичный каталог"
          >
            <Home size={18} strokeWidth={1.8} />
            <span>Каталог</span>
          </button>
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
          <div className="topbar-actions">
            <NotificationCenter
              refreshKey={refreshKey}
              onNavigate={(n) => {
                if (n.link_type === "application" && n.link_id) {
                  setView("applications");
                  // Админский список заявок сам управляет selected — внешнего
                  // пробрасывания selected пока нет; пользователь увидит список
                  // и сможет найти нужную. Линк хотя бы переключит раздел.
                } else if (n.link_type === "chat") {
                  setView("address-chats");
                }
              }}
            />
            <Button variant="secondary" onClick={() => setRefreshKey((value) => value + 1)}>
              <RefreshCw size={16} /> Обновить
            </Button>
          </div>
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
            {view === "photos" && currentUser.role === "admin" && <AdminPhotoModerationView />}
            {view === "provider-requests" && currentUser.role === "admin" && (
              <ProviderRequestsView />
            )}
            {view === "address-moderation" && currentUser.role === "admin" && (
              <AdminAddressModerationView />
            )}
            {view === "address-services" && currentUser.role === "admin" && (
              <AdminAddressServicesView />
            )}
            {view === "address-chats" && currentUser.role === "admin" && (
              <ChatsListPanel currentUser={currentUser} />
            )}
            {view === "review-moderation" && currentUser.role === "admin" && (
              <AdminReviewModeration />
            )}
            {view === "access" && currentUser.role === "admin" && (
              <>
                <SessionsView />
                <AccessView />
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function SbpPaymentPanel({
  applicationId,
  onPaid
}: {
  applicationId: string;
  onPaid: () => void;
}) {
  const [payment, setPayment] = useState<Payment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initiate (or fetch existing active) payment on mount.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .initiatePayment(applicationId)
      .then((p) => alive && setPayment(p))
      .catch((err: Error) => alive && setError(err.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [applicationId]);

  // Poll status every 3s while awaiting_user or pending.
  useEffect(() => {
    if (!payment) return;
    if (payment.status !== "awaiting_user" && payment.status !== "pending") return;
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const fresh = await api.getPayment(payment.id);
        if (!alive) return;
        setPayment(fresh);
        if (fresh.status === "succeeded") {
          clearInterval(timer);
          onPaid();
        }
      } catch (err) {
        if (alive) setError((err as Error).message);
      }
    }, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [payment?.id, payment?.status, onPaid]);

  const cardStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    padding: 16,
    border: "1px solid #dfe3dc",
    borderRadius: 12,
    background: "#fdfdfb"
  };

  if (loading) {
    return (
      <div style={cardStyle}>
        <Loader2 className="spin" size={18} /> Создаём платёж…
      </div>
    );
  }
  if (error) return <InlineError message={error} />;
  if (!payment) return null;

  if (payment.status === "succeeded") {
    return (
      <div style={{ ...cardStyle, background: "#eaf6ed", borderColor: "#3AB663" }}>
        <CheckCircle2 size={18} /> Оплата получена. Заявка ушла на проверку администратора.
      </div>
    );
  }

  const amountRub = (payment.amount_kopeks / 100).toLocaleString("ru-RU");

  if (payment.provider === "manual_invoice") {
    return (
      <div style={cardStyle}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <strong>Оплата по счёту от юридического лица</strong>
          <span>
            {amountRub} ₽ · статус: <b>{paymentStatusLabels[payment.status]}</b>
          </span>
        </div>
        <p style={{ margin: 0, color: "#596259" }}>
          Собственник загрузит счёт-фактуру в комплекте документов на адрес. После
          оплаты по реквизитам администратор подтвердит платёж вручную, и заявка
          перейдёт в проверку.
        </p>
        {payment.status === "failed" ? (
          <small style={{ color: "#c0392b" }}>
            Оплата не подтверждена. Свяжитесь с поддержкой.
          </small>
        ) : null}
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <strong>Оплата заявки через СБП</strong>
        <span>
          {amountRub} ₽ · CDEK Pay · статус: <b>{paymentStatusLabels[payment.status]}</b>
        </span>
      </div>
      {payment.qr_image_base64 ? (
        <img
          alt="QR для оплаты СБП"
          src={`data:image/png;base64,${payment.qr_image_base64}`}
          style={{ width: 240, height: 240, alignSelf: "center" }}
        />
      ) : null}
      {payment.qr_link ? (
        <a className="btn primary" href={payment.qr_link} rel="noreferrer" target="_blank">
          Открыть в банке
        </a>
      ) : null}
      {payment.expires_at ? (
        <small>Ссылка/QR действительны до {formatDate(payment.expires_at)}</small>
      ) : null}
    </div>
  );
}

const paymentStatusLabels: Record<string, string> = {
  pending: "создаётся",
  awaiting_user: "ждёт оплату",
  succeeded: "оплачено",
  failed: "ошибка",
  expired: "истёк",
  cancelled: "отменён",
  refund_requested: "ожидает возврата",
  refunded: "возвращён"
};

type ClientCabinetView = "applications" | "chats";

function ClientDashboardView({
  user,
  onLogout,
  onOpenCatalog,
}: {
  user: CurrentUser;
  onLogout: () => void;
  onOpenCatalog: () => void;
}) {
  const [view, setView] = useState<ClientCabinetView>("applications");
  const [applications, setApplications] = useState<ClientApplication[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pendingChatId, setPendingChatId] = useState<string | null>(null);
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
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">ЮА</div>
          <div>
            <strong>Личный кабинет</strong>
            <span>клиент</span>
          </div>
        </div>
        <nav className="nav">
          <button type="button" className="nav-item" onClick={onOpenCatalog} title="Открыть публичный каталог">
            <Home size={18} strokeWidth={1.8} />
            <span>Каталог</span>
          </button>
          <button
            type="button"
            className={view === "applications" ? "nav-item active" : "nav-item"}
            onClick={() => setView("applications")}
          >
            <FolderOpen size={18} strokeWidth={1.8} />
            <span>Заявки</span>
          </button>
          <button
            type="button"
            className={view === "chats" ? "nav-item active" : "nav-item"}
            onClick={() => setView("chats")}
          >
            <MessageSquare size={18} strokeWidth={1.8} />
            <span>Чаты</span>
          </button>
        </nav>
        <div className="sidebar-footer">
          <span>Клиент</span>
          <strong>{user.email}</strong>
          <button className="text-action" onClick={onLogout} type="button">
            <LogOut size={15} /> Выйти
          </button>
        </div>
      </aside>

      <main className="client-shell">
        <header className="client-topbar">
          <div className="brand" style={{ visibility: "hidden" }} />
          <div className="actions">
            <NotificationCenter
              refreshKey={refreshKey}
              onNavigate={(n) => {
                if (n.link_type === "application" && n.link_id) {
                  setView("applications");
                  setSelectedId(n.link_id);
                } else if (n.link_type === "chat" && n.link_id) {
                  setView("chats");
                  setPendingChatId(n.link_id);
                }
              }}
            />
            <PushToggle />
            <Button variant="secondary" onClick={() => setRefreshKey((value) => value + 1)}>
              <RefreshCw size={16} /> Обновить
            </Button>
          </div>
        </header>

        <section className="client-heading">
          <span className="eyebrow">
            {view === "applications" ? "Мои заявки" : "Сообщения"}
          </span>
          <h1>
            {view === "applications"
              ? "Статус и адрес по заявке на юридический адрес"
              : "Чаты с собственниками"}
          </h1>
        </section>

        <InlineError message={error} />

      {view === "applications" && (loading ? (
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

              {selectedApplication.status === "awaiting_payment" ? (
                <SbpPaymentPanel
                  applicationId={selectedApplication.id}
                  onPaid={() => setRefreshKey((value) => value + 1)}
                />
              ) : null}

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
      ))}

      {view === "chats" && (
        <ChatsListPanel
          currentUser={user}
          autoOpenChatId={pendingChatId}
          onChatOpened={() => setPendingChatId(null)}
        />
      )}
      </main>
    </div>
  );
}

type OwnerCabinetView = "applications" | "addresses" | "chats";

function OwnerDashboardView({
  user,
  onLogout,
  onOpenCatalog,
}: {
  user: CurrentUser;
  onLogout: () => void;
  onOpenCatalog: () => void;
}) {
  const [view, setView] = useState<OwnerCabinetView>("applications");
  const [pendingChatId, setPendingChatId] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<OwnerDashboard | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [documents, setDocuments] = useState<ApplicationDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [documentKind, setDocumentKind] = useState<DocumentFileKind>("owner_consent");
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [documentInputKey, setDocumentInputKey] = useState(0);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [documentsRefreshKey, setDocumentsRefreshKey] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [photoAddressId, setPhotoAddressId] = useState<string | null>(null);
  const [photoAddressLabel, setPhotoAddressLabel] = useState<string>("");
  const [editorAddress, setEditorAddress] = useState<OwnerAddress | null>(null);

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
  const actionableCount = applications.filter(
    (application) => application.available_actions.length > 0 || ownerCanUploadDocuments(application)
  ).length;

  useEffect(() => {
    if (!selectedApplication) {
      setDocuments([]);
      setDocumentsError(null);
      setDocumentsLoading(false);
      return;
    }
    let alive = true;
    setDocumentsLoading(true);
    setDocumentsError(null);
    api
      .applicationDocuments(selectedApplication.id)
      .then((result) => {
        if (alive) setDocuments(result);
      })
      .catch((err: Error) => {
        if (alive) setDocumentsError(err.message);
      })
      .finally(() => alive && setDocumentsLoading(false));
    return () => {
      alive = false;
    };
  }, [selectedApplication?.id, documentsRefreshKey]);

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

  async function uploadOwnerDocument(event: FormEvent) {
    event.preventDefault();
    if (!selectedApplication || !documentFile) return;
    setUploadBusy(true);
    setUploadError(null);
    const form = new FormData();
    form.append("kind", documentKind);
    form.append("file", documentFile);
    try {
      const result = await api.uploadApplicationDocument(selectedApplication.id, form);
      setDocuments((current) => [result.document, ...current.filter((item) => item.id !== result.document.id)]);
      setDocumentFile(null);
      setDocumentInputKey((value) => value + 1);
      setDocumentsRefreshKey((value) => value + 1);
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setUploadBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">ЮА</div>
          <div>
            <strong>Кабинет</strong>
            <span>исполнитель</span>
          </div>
        </div>
        <nav className="nav">
          <button type="button" className="nav-item" onClick={onOpenCatalog} title="Открыть публичный каталог">
            <Home size={18} strokeWidth={1.8} />
            <span>Каталог</span>
          </button>
          <button
            type="button"
            className={view === "applications" ? "nav-item active" : "nav-item"}
            onClick={() => setView("applications")}
          >
            <FolderOpen size={18} strokeWidth={1.8} />
            <span>Заявки</span>
          </button>
          <button
            type="button"
            className={view === "addresses" ? "nav-item active" : "nav-item"}
            onClick={() => setView("addresses")}
          >
            <Home size={18} strokeWidth={1.8} />
            <span>Адреса</span>
          </button>
          <button
            type="button"
            className={view === "chats" ? "nav-item active" : "nav-item"}
            onClick={() => setView("chats")}
          >
            <MessageSquare size={18} strokeWidth={1.8} />
            <span>Чаты</span>
          </button>
        </nav>
        <div className="sidebar-footer">
          <span>Собственник</span>
          <strong>{user.email}</strong>
          <button className="text-action" onClick={onLogout} type="button">
            <LogOut size={15} /> Выйти
          </button>
        </div>
      </aside>

      <main className="owner-shell">
        <header className="owner-topbar">
          <div className="brand" style={{ visibility: "hidden" }} />
          <div className="actions">
            <NotificationCenter
              refreshKey={refreshKey}
              onNavigate={(n) => {
                if (n.link_type === "application" && n.link_id) {
                  setView("applications");
                  setSelectedId(n.link_id);
                } else if (n.link_type === "chat" && n.link_id) {
                  setView("chats");
                  setPendingChatId(n.link_id);
                }
              }}
            />
            <PushToggle />
            <Button variant="secondary" onClick={() => setRefreshKey((value) => value + 1)}>
              <RefreshCw size={16} /> Обновить
            </Button>
          </div>
        </header>

        <section className="owner-heading">
          <span className="eyebrow">
            {view === "applications"
              ? "Заявки"
              : view === "addresses"
                ? "Адреса"
                : "Сообщения"}
          </span>
          <h1>
            {view === "applications"
              ? "Заявки, назначенные вашей организации"
              : view === "addresses"
                ? "Адреса, привязанные к вашей организации"
                : "Входящие сообщения по адресам"}
          </h1>
        </section>

        <InlineError message={error} />

        {(view === "applications" || view === "addresses") && (loading ? (
          <LoadingRows />
        ) : !dashboard ? (
          <EmptyState title="Кабинет недоступен" text="Проверьте привязку пользователя к организации исполнителя." />
        ) : (
          <section className={view === "applications" ? "owner-layout owner-layout--single" : "owner-layout owner-layout--single"}>
          {view === "addresses" && (
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
                    <div className="row-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button
                        className="text-action owner-address-photos-link"
                        onClick={() => {
                          setPhotoAddressId(address.id);
                          setPhotoAddressLabel(address.full_address);
                        }}
                        type="button"
                      >
                        <Camera size={14} /> Фотографии
                      </button>
                      <button
                        className="text-action owner-address-photos-link"
                        onClick={() => setEditorAddress(address)}
                        type="button"
                      >
                        <FileText size={14} /> Описание и услуги
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState title="Адресов нет" text="Администратор еще не привязал адреса к организации." />
              )}
            </div>
          </aside>
          )}

          {view === "applications" && (
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
                    <strong>{ownerNextStepLabel(selectedApplication)}</strong>
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

                <div className="owner-documents-panel">
                  <div className="timeline-title">
                    <FileArchive size={18} />
                    <strong>Документы заявки</strong>
                  </div>

                  {ownerCanUploadDocuments(selectedApplication) ? (
                    <form className="owner-upload-form" onSubmit={uploadOwnerDocument}>
                      <Field label="Тип документа">
                        <select value={documentKind} onChange={(event) => setDocumentKind(event.target.value as DocumentFileKind)}>
                          {ownerDocumentKinds.map((kind) => (
                            <option key={kind} value={kind}>
                              {documentKindLabels[kind]}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Файл">
                        <input
                          accept=".pdf,.doc,.docx,.zip,.jpg,.jpeg,.png"
                          key={documentInputKey}
                          onChange={(event) => setDocumentFile(event.target.files?.[0] || null)}
                          type="file"
                        />
                      </Field>
                      <Button disabled={uploadBusy || !documentFile} type="submit">
                        {uploadBusy ? <Loader2 className="spin" size={16} /> : <Upload size={16} />}
                        Отправить на проверку
                      </Button>
                    </form>
                  ) : null}

                  <InlineError message={uploadError || documentsError} />

                  {documentsLoading ? (
                    <LoadingRows />
                  ) : documents.length ? (
                    <div className="owner-document-list">
                      {documents.map((document) => (
                        <a className="owner-document-item" href={document.download_url} key={document.id}>
                          <FileText size={17} />
                          <span>
                            <strong>{document.original_filename}</strong>
                            <small>
                              {documentKindLabels[document.kind]} · {formatFileSize(document.size_bytes)} ·{" "}
                              {formatDate(document.created_at)}
                            </small>
                          </span>
                          <Download size={16} />
                        </a>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="Документы пока не загружены" text="После загрузки файлы появятся здесь." />
                  )}
                </div>

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
          )}
        </section>
        ))}

        {view === "chats" && (
          <ChatsListPanel
            currentUser={user}
            autoOpenChatId={pendingChatId}
            onChatOpened={() => setPendingChatId(null)}
          />
        )}

        {photoAddressId ? (
          <AddressPhotosModal
            addressId={photoAddressId}
            addressLabel={photoAddressLabel}
            mode="owner"
            onClose={() => setPhotoAddressId(null)}
          />
        ) : null}

        {editorAddress ? (
          <OwnerAddressEditor
            addressId={editorAddress.id}
            addressLabel={editorAddress.full_address}
            initialDescription={editorAddress.description ?? null}
            onClose={() => setEditorAddress(null)}
            onSaved={() => setRefreshKey((value) => value + 1)}
          />
        ) : null}
      </main>
    </div>
  );
}

function AddressPhotosModal({
  addressId,
  addressLabel,
  mode,
  onClose
}: {
  addressId: string;
  addressLabel: string;
  mode: "owner" | "admin";
  onClose: () => void;
}) {
  const [photos, setPhotos] = useState<AddressPhotoAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .ownerListAddressPhotos(addressId)
      .then((rows) => {
        if (alive) setPhotos(rows);
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [addressId, refreshKey]);

  async function handleUpload(event: FormEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    setUploadBusy(true);
    setUploadError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      await api.ownerUploadAddressPhoto(addressId, form);
      setRefreshKey((value) => value + 1);
      setFileInputKey((value) => value + 1);
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setUploadBusy(false);
    }
  }

  async function handleDelete(photoId: string) {
    if (!window.confirm("Удалить фотографию?")) return;
    setActionBusy(`delete-${photoId}`);
    try {
      await api.ownerDeletePhoto(photoId);
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setActionBusy(null);
    }
  }

  async function handleSetMain(photoId: string) {
    setActionBusy(`main-${photoId}`);
    try {
      await api.ownerSetMainPhoto(photoId);
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal-panel address-photos-modal" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <span className="eyebrow">Фотографии адреса</span>
            <h2>{addressLabel}</h2>
          </div>
          <button className="text-action" onClick={onClose} type="button">
            <X size={16} /> Закрыть
          </button>
        </header>

        {mode === "owner" ? (
          <label className="photo-uploader">
            <input
              key={fileInputKey}
              accept="image/jpeg,image/png,image/webp"
              type="file"
              onChange={handleUpload}
              disabled={uploadBusy}
            />
            <span>
              {uploadBusy ? <Loader2 className="spin" size={18} /> : <Upload size={18} />}
              {uploadBusy ? "Загружаем..." : "Загрузить фотографию"}
            </span>
            <small>JPEG, PNG или WebP — до 8 МБ. Перед публикацией админ проверит снимок.</small>
          </label>
        ) : null}

        <InlineError message={error || uploadError} />

        {loading ? (
          <LoadingRows />
        ) : photos.length === 0 ? (
          <EmptyState
            title="Фото нет"
            text={mode === "owner" ? "Добавьте хотя бы одну фотографию здания, чтобы клиенты её видели." : "Собственник ещё не загружал фото для этого адреса."}
          />
        ) : (
          <div className="photo-grid">
            {photos.map((photo) => (
              <div className={`photo-card photo-card--${photo.moderation_status}`} key={photo.id}>
                <div className="photo-card__media">
                  <img src={photo.url} alt={photo.original_filename} loading="lazy" />
                  {photo.is_main && photo.moderation_status === "approved" ? (
                    <span className="photo-card__main-badge">
                      <Star size={11} /> Главное
                    </span>
                  ) : null}
                </div>
                <div className="photo-card__body">
                  <span className={`photo-card__status photo-card__status--${photo.moderation_status}`}>
                    {photoModerationStatusLabels[photo.moderation_status] || photo.moderation_status}
                  </span>
                  {photo.moderation_comment ? <p>{photo.moderation_comment}</p> : null}
                  <small>
                    {photo.width}×{photo.height} · {formatFileSize(photo.size_bytes)}
                  </small>
                  {mode === "owner" ? (
                    <div className="photo-card__actions">
                      {photo.moderation_status === "approved" && !photo.is_main ? (
                        <Button
                          variant="secondary"
                          onClick={() => handleSetMain(photo.id)}
                          disabled={actionBusy === `main-${photo.id}`}
                        >
                          {actionBusy === `main-${photo.id}` ? (
                            <Loader2 className="spin" size={14} />
                          ) : (
                            <Star size={14} />
                          )}
                          Сделать главным
                        </Button>
                      ) : null}
                      <Button
                        variant="secondary"
                        onClick={() => handleDelete(photo.id)}
                        disabled={actionBusy === `delete-${photo.id}`}
                      >
                        {actionBusy === `delete-${photo.id}` ? (
                          <Loader2 className="spin" size={14} />
                        ) : (
                          <Trash2 size={14} />
                        )}
                        Удалить
                      </Button>
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AdminPhotoModerationView() {
  const [photos, setPhotos] = useState<AddressPhotoAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [rejectingPhotoId, setRejectingPhotoId] = useState<string | null>(null);
  const [rejectComment, setRejectComment] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .adminPendingPhotos()
      .then((rows) => {
        if (alive) setPhotos(rows);
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  async function handleApprove(photoId: string) {
    setActionBusy(`approve-${photoId}`);
    try {
      await api.adminApprovePhoto(photoId);
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionBusy(null);
    }
  }

  async function handleReject(photoId: string) {
    if (rejectComment.trim().length < 2) {
      setError("Укажите причину отказа (минимум 2 символа)");
      return;
    }
    setActionBusy(`reject-${photoId}`);
    try {
      await api.adminRejectPhoto(photoId, rejectComment.trim());
      setRejectingPhotoId(null);
      setRejectComment("");
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <section className="admin-photos-view">
      <div className="view-heading">
        <span className="eyebrow">Модерация контента</span>
        <h2>Фотографии адресов на проверке</h2>
        <p>Подтвердите снимки от собственников, чтобы они появились в публичном каталоге.</p>
      </div>

      <InlineError message={error} />

      {loading ? (
        <LoadingRows />
      ) : photos.length === 0 ? (
        <EmptyState
          title="Очередь пуста"
          text="Все загруженные собственниками фотографии уже промодерированы."
        />
      ) : (
        <div className="photo-grid">
          {photos.map((photo) => (
            <div className="photo-card photo-card--pending" key={photo.id}>
              <div className="photo-card__media">
                <img src={photo.url} alt={photo.original_filename} loading="lazy" />
              </div>
              <div className="photo-card__body">
                <span className="photo-card__status photo-card__status--pending">На модерации</span>
                <small>
                  {photo.width}×{photo.height} · {formatFileSize(photo.size_bytes)} · {photo.content_type}
                </small>
                <small>Загружено {formatDateTime(photo.created_at)}</small>
                <div className="photo-card__actions">
                  <Button
                    onClick={() => handleApprove(photo.id)}
                    disabled={actionBusy?.startsWith(`approve-${photo.id}`)}
                  >
                    {actionBusy === `approve-${photo.id}` ? (
                      <Loader2 className="spin" size={14} />
                    ) : (
                      <CheckCircle2 size={14} />
                    )}
                    Одобрить
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setRejectingPhotoId(photo.id);
                      setRejectComment("");
                    }}
                  >
                    <XCircle size={14} /> Отклонить
                  </Button>
                </div>
                {rejectingPhotoId === photo.id ? (
                  <div className="photo-card__reject">
                    <textarea
                      value={rejectComment}
                      onChange={(event) => setRejectComment(event.target.value)}
                      placeholder="Почему фото не подходит? (видно собственнику)"
                      rows={3}
                    />
                    <div className="photo-card__actions">
                      <Button
                        onClick={() => handleReject(photo.id)}
                        disabled={actionBusy === `reject-${photo.id}`}
                      >
                        {actionBusy === `reject-${photo.id}` ? (
                          <Loader2 className="spin" size={14} />
                        ) : (
                          <XCircle size={14} />
                        )}
                        Подтвердить отказ
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setRejectingPhotoId(null);
                          setRejectComment("");
                        }}
                      >
                        Отмена
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
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
  const [moderatingId, setModeratingId] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!applications.length) {
    return <EmptyState title="Заявок пока нет" text="Создайте первичную регистрацию или смену адреса." />;
  }

  const providerById = new Map(providers.map((provider) => [provider.id, provider]));
  const addressById = new Map(addresses.map((address) => [address.id, address]));

  async function runAdminAction(application: Application, action: string) {
    const busyKey = `${application.id}:${action}`;
    setActionBusy(busyKey);
    setActionError(null);
    try {
      await api.runApplicationAction(application.id, action);
      onChanged();
    } catch (err) {
      setActionError((err as Error).message);
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <section className="table-panel">
      {actionError ? <div className="table-action-error">{actionError}</div> : null}
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
        (() => {
          const inlineActions = (application.available_actions || []).filter(
            (action) => !documentModerationActions.has(action)
          );
          return (
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
              <div className="row-actions admin-row-actions">
                {inlineActions.map((action) => {
                  const busyKey = `${application.id}:${action}`;
                  const Icon =
                    action === "cancel"
                      ? XCircle
                      : action === "request_client_fix"
                        ? FileClock
                        : action === "complete" || action === "resolve_dispute"
                          ? CheckCircle2
                          : ShieldCheck;
                  return (
                    <button
                      className={action === "cancel" ? "workflow-action danger" : "workflow-action"}
                      disabled={actionBusy !== null}
                      key={action}
                      onClick={() => runAdminAction(application, action)}
                      type="button"
                    >
                      {actionBusy === busyKey ? <Loader2 className="spin" size={14} /> : <Icon size={14} />}
                      {adminWorkflowActionLabels[action] || action}
                    </button>
                  );
                })}
                {application.status === "documents_review" || application.status === "documents_revision" ? (
                  <button className="text-action" onClick={() => setModeratingId(application.id)} type="button">
                    <ShieldCheck size={15} /> Проверка
                  </button>
                ) : null}
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
          );
        })()
      ))}
      {promotingId ? (
        <PromoteContractPanel
          application={applications.find((item) => item.id === promotingId) || null}
          onClose={() => setPromotingId(null)}
          onDone={onChanged}
        />
      ) : null}
      {moderatingId ? (
        <DocumentModerationPanel
          application={applications.find((item) => item.id === moderatingId) || null}
          onClose={() => setModeratingId(null)}
          onDone={onChanged}
        />
      ) : null}
    </section>
  );
}

function DocumentModerationPanel({
  application,
  onClose,
  onDone
}: {
  application: Application | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [moderation, setModeration] = useState<ApplicationDocumentModeration | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!application) return;
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .applicationModeration(application.id)
      .then((result) => {
        if (alive) setModeration(result);
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [application?.id]);

  if (!application) return null;

  const documents = moderation?.documents || [];
  const canApprove = Boolean(moderation?.available_actions.includes("approve_documents") && documents.length > 0);
  const canRequestRevision = Boolean(moderation?.available_actions.includes("request_document_revision"));

  async function runModerationAction(action: string) {
    setActionBusy(action);
    setError(null);
    try {
      await api.runApplicationAction(application!.id, action);
      onDone();
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-panel moderation-panel" role="dialog" aria-modal="true">
        <header>
          <div>
            <span className="eyebrow">Ручная модерация</span>
            <h2>{application.company_name || application.planned_client_name || "Заявка"}</h2>
          </div>
          <button className="text-action" onClick={onClose} type="button">
            Закрыть
          </button>
        </header>

        <div className="moderation-summary">
          <div>
            <span>Статус</span>
            <strong>{statusLabels[moderation?.status || application.status] || moderation?.status || application.status}</strong>
          </div>
          <div>
            <span>Ручная проверка</span>
            <strong>{moderation ? (moderation.requires_manual_review ? "Требуется" : "Не требуется") : "—"}</strong>
          </div>
          <div>
            <span>Файлы</span>
            <strong>{moderation ? documents.length : "—"}</strong>
          </div>
        </div>

        <InlineError message={error} />

        {loading ? (
          <LoadingRows />
        ) : moderation ? (
          <div className="moderation-body">
            <div className="owner-documents-panel">
              <div className="timeline-title">
                <FileArchive size={18} />
                <strong>Документы исполнителя</strong>
              </div>
              {documents.length ? (
                <div className="owner-document-list">
                  {documents.map((document) => (
                    <a className="owner-document-item" href={document.download_url} key={document.id}>
                      <FileText size={17} />
                      <span>
                        <strong>{document.original_filename}</strong>
                        <small>
                          {documentKindLabels[document.kind]} · {formatFileSize(document.size_bytes)} ·{" "}
                          {formatDate(document.created_at)}
                        </small>
                      </span>
                      <Download size={16} />
                    </a>
                  ))}
                </div>
              ) : (
                <EmptyState title="Файлы не загружены" text="Исполнитель еще не отправил документы по заявке." />
              )}
            </div>

            <div className="moderation-actions">
              {moderation?.available_actions.length ? (
                <>
                  <Button
                    disabled={actionBusy !== null || !canApprove}
                    onClick={() => runModerationAction("approve_documents")}
                    variant="primary"
                  >
                    {actionBusy === "approve_documents" ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
                    {adminDocumentActionLabels.approve_documents}
                  </Button>
                  <Button
                    disabled={actionBusy !== null || !canRequestRevision}
                    onClick={() => runModerationAction("request_document_revision")}
                    variant="secondary"
                  >
                    {actionBusy === "request_document_revision" ? <Loader2 className="spin" size={16} /> : <FileClock size={16} />}
                    {adminDocumentActionLabels.request_document_revision}
                  </Button>
                </>
              ) : (
                <div className="success-note">
                  <CheckCircle2 size={17} />
                  <span>Решение по документам уже зафиксировано</span>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
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
  const [contactPhone, setContactPhone] = useState(formatRuPhone(application?.contact_phone || ""));
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
            <PhoneInput value={contactPhone} onChange={setContactPhone} />
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
            <PhoneInput value={contactPhone} onChange={setContactPhone} />
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
          <AddressListRow address={address} onChanged={onChanged} setError={setError} />
        )}
      />
    </div>
  );
}

function AddressListRow({
  address,
  onChanged,
  setError
}: {
  address: Address;
  onChanged: () => void;
  setError: (msg: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.submitAddressForModeration(address.id);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function archive() {
    if (!window.confirm("Архивировать адрес?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.archiveAddress(address.id);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <strong>{address.full_address}</strong>
      <span>
        {address.cadastral_number} · {address.price_6m} / {address.price_11m} руб.
      </span>
      <span>
        Статус публикации:{" "}
        <strong>
          {addressPublicationStatusLabels[address.publication_status] || address.publication_status}
        </strong>
        {address.moderation_comment ? ` · ${address.moderation_comment}` : ""}
      </span>
      <div className="row-actions">
        {(address.publication_status === "draft" || address.publication_status === "rejected") && (
          <Button disabled={busy} onClick={submit} variant="secondary">
            Отправить на модерацию
          </Button>
        )}
        {address.publication_status !== "archived" && (
          <Button disabled={busy} onClick={archive} variant="secondary">
            Архивировать
          </Button>
        )}
      </div>
    </>
  );
}

const addressPublicationStatusLabels: Record<string, string> = {
  draft: "Черновик",
  moderation: "На модерации",
  published: "Опубликовано",
  rejected: "Отклонено",
  archived: "В архиве"
};

function AdminAddressModerationView() {
  const [statusFilter, setStatusFilter] = useState<AddressPublicationStatusFilter>("moderation");
  const [items, setItems] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .adminListAddressesForModeration(statusFilter === "all" ? undefined : statusFilter)
      .then(setItems)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [statusFilter]);

  async function publish(address: Address) {
    setBusyId(address.id);
    setError(null);
    try {
      await api.adminPublishAddress(address.id);
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function reject(address: Address) {
    const comment = window.prompt("Причина отклонения") || "";
    if (comment.trim().length < 2) return;
    setBusyId(address.id);
    setError(null);
    try {
      await api.adminRejectAddress(address.id, comment.trim());
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="stack">
      <Field label="Фильтр статусов">
        <select
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value as AddressPublicationStatusFilter)
          }
        >
          <option value="all">Все</option>
          <option value="moderation">На модерации</option>
          <option value="published">Опубликованы</option>
          <option value="rejected">Отклонены</option>
          <option value="draft">Черновики</option>
          <option value="archived">В архиве</option>
        </select>
      </Field>
      <InlineError message={error} />
      {loading ? (
        <LoadingRows />
      ) : items.length === 0 ? (
        <p className="hint">Адресов в выбранном статусе нет.</p>
      ) : (
        <SimpleList
          items={items}
          render={(address) => (
            <>
              <strong>{address.full_address}</strong>
              <span>
                {address.cadastral_number} · {address.price_6m} / {address.price_11m} руб.
              </span>
              <span>
                Статус:{" "}
                <strong>
                  {addressPublicationStatusLabels[address.publication_status] ||
                    address.publication_status}
                </strong>
                {address.moderation_comment ? ` · ${address.moderation_comment}` : ""}
              </span>
              {address.publication_status === "moderation" ? (
                <div className="row-actions">
                  <Button disabled={busyId === address.id} onClick={() => publish(address)}>
                    Опубликовать
                  </Button>
                  <Button
                    disabled={busyId === address.id}
                    onClick={() => reject(address)}
                    variant="secondary"
                  >
                    Отклонить
                  </Button>
                </div>
              ) : null}
            </>
          )}
        />
      )}
    </section>
  );
}

type AddressPublicationStatusFilter = AddressPublicationStatus | "all";

const ADDRESS_SERVICE_CATALOG: Array<{ kind: string; label: string; group: "doc" | "extra" }> = [
  { kind: "guarantee_letter", label: "Гарантийное письмо", group: "doc" },
  { kind: "lease_agreement", label: "Договор аренды", group: "doc" },
  { kind: "owner_confirmation", label: "Подтверждение собственника", group: "doc" },
  { kind: "door_sign", label: "Табличка на входе", group: "extra" },
  { kind: "mail_reception", label: "Приём почты", group: "extra" },
  { kind: "fns_visit_photo", label: "Фотофиксация приёма ФНС", group: "extra" },
  { kind: "phone_answering", label: "Звонки", group: "extra" },
  { kind: "visitor_reception", label: "Приём посетителей", group: "extra" }
];

type ServiceDraft = { price: string; is_active: boolean; saving: boolean; error: string | null };

function AdminAddressServicesView() {
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [services, setServices] = useState<AddressServiceAdmin[]>([]);
  const [drafts, setDrafts] = useState<Record<string, ServiceDraft>>({});
  const [loadingServices, setLoadingServices] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .adminListAddressesForModeration()
      .then((items) => {
        setAddresses(items);
        if (items.length > 0 && !selectedId) setSelectedId(items[0].id);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoadingServices(true);
    setError(null);
    api
      .adminListAddressServices(selectedId)
      .then((items) => {
        setServices(items);
        const next: Record<string, ServiceDraft> = {};
        for (const c of ADDRESS_SERVICE_CATALOG) {
          const existing = items.find((s) => s.kind === c.kind);
          next[c.kind] = {
            price: existing ? String(existing.price) : "",
            is_active: existing ? existing.is_active : false,
            saving: false,
            error: null
          };
        }
        setDrafts(next);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingServices(false));
  }, [selectedId]);

  const selectedAddress = addresses.find((a) => a.id === selectedId);

  async function save(kind: string) {
    if (!selectedId) return;
    const draft = drafts[kind];
    if (!draft) return;
    const priceNum = Number(draft.price);
    if (!Number.isFinite(priceNum) || priceNum < 0) {
      setDrafts((prev) => ({ ...prev, [kind]: { ...draft, error: "Некорректная цена" } }));
      return;
    }
    setDrafts((prev) => ({ ...prev, [kind]: { ...draft, saving: true, error: null } }));
    try {
      const result = await api.adminUpsertAddressService(selectedId, kind, {
        price: priceNum.toFixed(2),
        is_active: draft.is_active
      });
      setServices((prev) => {
        const without = prev.filter((s) => s.kind !== kind);
        return [...without, result];
      });
      setDrafts((prev) => ({
        ...prev,
        [kind]: { price: String(result.price), is_active: result.is_active, saving: false, error: null }
      }));
    } catch (err) {
      setDrafts((prev) => ({
        ...prev,
        [kind]: { ...draft, saving: false, error: (err as Error).message }
      }));
    }
  }

  async function removeService(kind: string) {
    if (!selectedId) return;
    if (!window.confirm("Удалить услугу с адреса?")) return;
    try {
      await api.adminDeleteAddressService(selectedId, kind);
      setServices((prev) => prev.filter((s) => s.kind !== kind));
      setDrafts((prev) => ({
        ...prev,
        [kind]: { price: "", is_active: false, saving: false, error: null }
      }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (loading) return <LoadingRows />;

  return (
    <section className="address-services-panel">
      <InlineError message={error} />
      <div className="address-services-layout">
        <aside className="address-services-list">
          <h3>Адреса</h3>
          {addresses.length === 0 ? (
            <p className="hint">Нет адресов</p>
          ) : (
            <ul>
              {addresses.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    className={`address-services-list__item${
                      a.id === selectedId ? " selected" : ""
                    }`}
                    onClick={() => setSelectedId(a.id)}
                  >
                    <strong>{a.full_address}</strong>
                    <span>
                      {addressPublicationStatusLabels[a.publication_status] ||
                        a.publication_status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="address-services-editor">
          {!selectedAddress ? (
            <p className="hint">Выбери адрес слева</p>
          ) : loadingServices ? (
            <LoadingRows />
          ) : (
            <>
              <header className="address-services-editor__head">
                <h3>{selectedAddress.full_address}</h3>
                <span>{services.filter((s) => s.is_active).length} активных услуг</span>
              </header>

              {(["doc", "extra"] as const).map((group) => (
                <div key={group} className="address-services-group">
                  <h4>{group === "doc" ? "Юр. документы" : "Платный сервис"}</h4>
                  <div className="address-services-rows">
                    {ADDRESS_SERVICE_CATALOG.filter((c) => c.group === group).map((cat) => {
                      const draft = drafts[cat.kind];
                      if (!draft) return null;
                      const existing = services.find((s) => s.kind === cat.kind);
                      return (
                        <div key={cat.kind} className="address-services-row">
                          <div className="address-services-row__label">
                            <strong>{cat.label}</strong>
                            <span className="hint">{cat.kind}</span>
                          </div>
                          <label className="address-services-row__price">
                            <span>Цена, ₽</span>
                            <input
                              type="number"
                              min={0}
                              step={100}
                              value={draft.price}
                              placeholder="0"
                              onChange={(e) =>
                                setDrafts((prev) => ({
                                  ...prev,
                                  [cat.kind]: { ...draft, price: e.target.value }
                                }))
                              }
                            />
                          </label>
                          <label className="address-services-row__active">
                            <input
                              type="checkbox"
                              checked={draft.is_active}
                              onChange={(e) =>
                                setDrafts((prev) => ({
                                  ...prev,
                                  [cat.kind]: { ...draft, is_active: e.target.checked }
                                }))
                              }
                            />
                            <span>Активна</span>
                          </label>
                          <div className="row-actions">
                            <Button
                              disabled={draft.saving}
                              onClick={() => save(cat.kind)}
                            >
                              {draft.saving ? "Сохраняем…" : existing ? "Сохранить" : "Добавить"}
                            </Button>
                            {existing && (
                              <Button
                                variant="secondary"
                                onClick={() => removeService(cat.kind)}
                              >
                                Удалить
                              </Button>
                            )}
                          </div>
                          {draft.error && (
                            <div className="address-services-row__err">{draft.error}</div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </section>
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
