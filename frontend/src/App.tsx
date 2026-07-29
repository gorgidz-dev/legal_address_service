import {
  Bell,
  Building2,
  Camera,
  CheckCircle2,
  ChevronLeft,
  Copy,
  Database,
  Download,
  FileClock,
  FileArchive,
  FileCheck2,
  FileText,
  Home,
  KeyRound,
  Loader2,
  MessageSquare,
  LogOut,
  Monitor,
  Plus,
  RefreshCw,
  Smartphone,
  ReceiptText,
  Search,
  ShieldCheck,
  Star,
  Trash2,
  Upload,
  UserPlus,
  X,
  XCircle
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  SESSION_EXPIRED_EVENT,
  api,
  packageDownloadUrl,
  apiDownloadUrl
} from "./api";
import { PhoneInput, formatRuPhone } from "./PhoneInput";
import PublicCatalog from "./publicCatalog";
import { parsePath, routeToPath, useRouter } from "./router";
import { LegalPage } from "./sections/LegalPage";
import { EmailVerificationPage } from "./sections/EmailVerification";
import { AddressChatPanel } from "./AddressChatPanel";
import {
  ApplicationDrawer,
  DrawerRow,
  DrawerTimeline
} from "./applications/ApplicationDrawer";
import { ApplicationsQueue, type QueueFilter } from "./applications/ApplicationsQueue";
import { AppShell } from "./shell/AppShell";
import {
  navItemsFor,
  sectionLabel,
  type ClientSectionId,
  type OwnerSectionId
} from "./shell/navConfig";
import { statusLabel as statusText, statusMeta } from "./status";
import { Badge, StatusBadge } from "./ui/Badge";
import { ListEmpty, ListError, ListLoading } from "./ui/ListState";
import { useModalDismiss } from "./useModalDismiss";
import { ChatsListPanel } from "./ChatsListPanel";
import { DownloadLink } from "./DownloadLink";
import { OwnerAddressEditor } from "./OwnerAddressEditor";
import { PushToggle } from "./PushToggle";
import { AdminReviewModeration } from "./sections/AdminReviewModeration";
import {
  OwnerPaymentSection,
  PaymentAttachmentsPanel
} from "./sections/PaymentAttachmentsPanel";
import type {
  ActiveClientRegistryItem,
  AdminUser,
  Address,
  AddressChat,
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

/**
 * Разделы кабинетов клиента и собственника — они же сегменты URL /app/<section>.
 * Первый в списке считается разделом по умолчанию для «/app».
 */
/*
 * Списки разделов клиента и собственника живут в shell/navConfig.ts вместе с
 * меню — один источник вместо двух, которые могли разъехаться.
 */

/**
 * Синонимы разделов: один и тот же экран у разных ролей называется по-разному.
 * Нужно, чтобы общая ссылка (push-уведомление про чат) вела куда надо и клиенту,
 * и админу.
 */
const SECTION_ALIASES: Record<string, string> = { chats: "address-chats" };

function resolveSection(raw: string | null, allowed: string[]): string | null {
  if (!raw) return null;
  if (allowed.includes(raw)) return raw;
  const alias = SECTION_ALIASES[raw];
  return alias && allowed.includes(alias) ? alias : null;
}

/*
 * Разделы всех ролей теперь описаны в shell/navConfig.ts — здесь их
 * определений больше нет. Раньше меню оператора собиралось из семи отдельных
 * объектов, а у клиента и собственника пункты были просто набором кнопок в
 * разметке, поэтому «Заявки» в трёх кабинетах отличались иконкой и порядком.
 */

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

/**
 * Клиенту список документов отдают только после проверки: до этого сервер
 * отвечает 403 (app/services/application_documents.py). Вкладку в панели
 * блокируем заранее — красная ошибка вместо ожидаемого «ещё рано» пугает
 * сильнее, чем сама задержка.
 */
const CLIENT_DOCUMENT_STATUSES = new Set(["ready_for_client", "completed", "dispute"]);

function clientCanSeeDocuments(status: string): boolean {
  return CLIENT_DOCUMENT_STATUSES.has(status);
}

const FINISHED_STATUSES = new Set(["completed", "cancelled", "refunded", "terminated", "expired"]);

const CLIENT_QUEUE_FILTERS: QueueFilter[] = [
  { id: "all", label: "Все", match: () => true },
  { id: "active", label: "Активные", match: (row) => !FINISHED_STATUSES.has(row.status) },
  { id: "done", label: "Завершённые", match: (row) => FINISHED_STATUSES.has(row.status) }
];

/**
 * Собственнику важна не полнота списка, а что от него ждут действия, поэтому
 * этот фильтр стоит первым. «Требуют действия» считается по available_actions
 * с бэкенда — фронт не решает сам, что можно делать с заявкой.
 */
const OWNER_ACTIONABLE_STATUSES = new Set([
  "assigned_to_owner",
  "documents_preparing",
  "documents_revision"
]);

const OWNER_QUEUE_FILTERS: QueueFilter[] = [
  {
    id: "actionable",
    label: "Требуют действия",
    match: (row) => OWNER_ACTIONABLE_STATUSES.has(row.status)
  },
  { id: "all", label: "Все", match: () => true },
  {
    id: "in-work",
    label: "В работе",
    match: (row) => !FINISHED_STATUSES.has(row.status) && row.status !== "ready_for_client"
  },
  { id: "ready", label: "Готовы к выдаче", match: (row) => row.status === "ready_for_client" }
];

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
  title,
  type = "button"
}: {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  onClick?: () => void;
  /** Подсказка при наведении — нужна, чтобы объяснить, почему кнопка выключена. */
  title?: string;
  type?: "button" | "submit";
}) {
  return (
    <button
      className={`btn ${variant}`}
      disabled={disabled}
      onClick={onClick}
      title={title}
      type={type}
    >
      {children}
    </button>
  );
}

function InlineError({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="inline-error">{message}</div>;
}

/** Нейтральное сообщение — не ошибка, но и молчать нельзя. */
function InlineNotice({
  message,
  onDismiss
}: {
  message: string | null;
  onDismiss: () => void;
}) {
  if (!message) return null;
  return (
    <div className="inline-notice">
      <span>{message}</span>
      <button aria-label="Скрыть" className="text-action" onClick={onDismiss} type="button">
        <X size={14} />
      </button>
    </div>
  );
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

  // Поповер закрывается кликом мимо и по Escape. Раньше не закрывался вообще:
  // оставался поверх нового раздела и перекрывал правую часть экрана.
  const rootRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="notification-center" ref={rootRef}>
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
                const meta = notification.application_status
                  ? statusMeta(notification.application_status)
                  : null;
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
                    <Badge tone={meta ? meta.tone : isChat ? "info" : "neutral"}>
                      {meta ? meta.label : isChat ? "Чат" : "Уведомление"}
                    </Badge>
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
  initialToken,
  onAuthenticated,
  onHome,
  onBack,
  canGoBack
}: {
  canBootstrap: boolean;
  /** Токен из ссылки /invite/<token> — сразу открывает вкладку «Приглашение». */
  initialToken?: string;
  onAuthenticated: (user: CurrentUser) => void;
  onHome: () => void;
  onBack: () => void;
  canGoBack: boolean;
}) {
  const [mode, setMode] = useState<"login" | "bootstrap" | "invite">(
    initialToken ? "invite" : canBootstrap ? "bootstrap" : "login"
  );
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [inviteToken, setInviteToken] = useState(initialToken || "");
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
      // Куда уйти после входа, решает роутер в App (учитывает ?next=).
      onAuthenticated(response.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <form className="auth-panel" onSubmit={submit}>
        <button className="brand auth-brand auth-brand--link" onClick={onHome} type="button">
          <div className="brand-mark">UR</div>
          <div>
            <strong>uradres.net</strong>
            <span>онлайн-доступ к сервису</span>
          </div>
        </button>

        <div className="auth-nav">
          {canGoBack ? (
            <button className="text-action" onClick={onBack} type="button">
              <ChevronLeft size={15} /> Назад
            </button>
          ) : null}
          <button className="text-action" onClick={onHome} type="button">
            <Home size={15} /> На главную
          </button>
        </div>

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

/**
 * Учётные записи: включить/отключить доступ. Отключение действует сразу —
 * бэкенд проверяет is_active на каждом запросе и отзывает живые сессии.
 */
function UsersAccessPanel({ currentUserId }: { currentUserId: string }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .adminUsers()
      .then(setUsers)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function toggle(user: AdminUser) {
    if (user.is_active && !window.confirm(`Отключить доступ для ${user.email}?`)) return;
    setBusyId(user.id);
    setError(null);
    try {
      const updated = await api.adminSetUserActive(user.id, !user.is_active);
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="table-panel">
      <div className="panel-title">
        <ShieldCheck size={20} />
        <div>
          <strong>Учётные записи</strong>
          <span>Отключённый пользователь теряет доступ сразу, данные остаются.</span>
        </div>
      </div>

      <InlineError message={error} />

      {loading ? (
        <LoadingRows />
      ) : users.length === 0 ? (
        <EmptyState title="Пользователей нет" text="Пригласите сотрудника формой ниже." />
      ) : (
        <div className="simple-list">
          {users.map((user) => {
            const isSelf = user.id === currentUserId;
            return (
              <div className="simple-row" key={user.id}>
                <div>
                  <strong>{user.email}</strong>
                  <span>
                    {user.full_name} · {roleLabels[user.role] || user.role}
                    {user.is_active ? "" : " · отключён"}
                  </span>
                </div>
                <div className="row-actions">
                  {/* Тон задаётся явно: это активность УЧЁТНОЙ ЗАПИСИ, а не
                      статус заявки. Раньше класс «status active» случайно
                      совпадал с ApplicationStatus.active и красился его
                      правилом. */}
                  <Badge tone={user.is_active ? "success" : "neutral"}>
                    {user.is_active ? "Активен" : "Отключён"}
                  </Badge>
                  <Button
                    disabled={isSelf || busyId === user.id}
                    onClick={() => toggle(user)}
                    title={isSelf ? "Нельзя отключить самого себя" : undefined}
                    variant="secondary"
                  >
                    {busyId === user.id ? (
                      <Loader2 className="spin" size={16} />
                    ) : user.is_active ? (
                      <XCircle size={16} />
                    ) : (
                      <CheckCircle2 size={16} />
                    )}
                    {user.is_active ? "Отключить" : "Включить"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function AccessView({ currentUserId }: { currentUserId: string }) {
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
      <UsersAccessPanel currentUserId={currentUserId} />

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
    // Отмена в prompt возвращает null и раньше всё равно отклоняла заявку —
    // спрашиваем ДО того, как что-то менять, и на отмене выходим.
    let comment: string | undefined;
    if (status === "rejected") {
      const answer = window.prompt("Комментарий (необязательно)");
      if (answer === null) return;
      comment = answer.trim() || undefined;
    }
    setBusyId(req.id);
    setError(null);
    try {
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

  useModalDismiss(true, onCancel);

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
  // Экран определяется адресом в строке браузера, а не внутренним состоянием:
  // «/» — всегда публичная главная, «/app/...» — кабинет. Раньше залогиненный
  // пользователь на «/» видел кабинет, из-за чего клик по логотипу и F5
  // возвращали в «Заявки».
  const { route, navigate, back, canGoBack } = useRouter();
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [canBootstrap, setCanBootstrap] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  /** Справочники уже приезжали хотя бы раз — второй скелет не нужен. */
  const staffDataLoaded = useRef(false);

  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((user) => {
        if (!alive) return;
        setCurrentUser(user);
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

  // Сессия протухла где угодно (в т.ч. в фоновом поллинге уведомлений) —
  // сбрасываем пользователя, а охрана маршрутов ниже уведёт на вход. Без этого
  // кабинет оставался открытым и молча сыпал ошибками на каждое действие.
  useEffect(() => {
    function handleExpired() {
      setCurrentUser(null);
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired);
  }, []);

  // Справочники нужны только админской части кабинета — на публичной главной
  // залогиненного сотрудника их тянуть незачем.
  const needsStaffData = route.name === "cabinet";

  useEffect(() => {
    if (!currentUser || !needsStaffData) {
      setLoading(false);
      return;
    }
    if (currentUser.role === "client" || currentUser.role === "owner") {
      setLoading(false);
      return;
    }
    let alive = true;
    // Скелет показываем только при первой загрузке. Раньше любое «Обновить»
    // (в т.ч. автоматическое после действия) подменяло рабочую область
    // скелетом — раздел размонтировался, а открытая модалка закрывалась
    // вместе с заполненной формой.
    if (!staffDataLoaded.current) setLoading(true);
    setError(null);
    Promise.all([api.providers(), api.addresses(), api.applications()])
      .then(([providersResult, addressesResult, applicationsResult]) => {
        if (!alive) return;
        setProviders(providersResult);
        setAddresses(addressesResult);
        setApplications(applicationsResult);
        staffDataLoaded.current = true;
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
  }, [currentUser, needsStaffData, refreshKey]);

  // Разделы кабинета = сегменты URL /app/<section>. Список зависит от роли:
  // чужой раздел в адресе не должен открывать чужой экран.
  const sections = useMemo<string[]>(
    () => (currentUser ? navItemsFor(currentUser.role).map((item) => item.id) : []),
    [currentUser]
  );

  const section =
    (route.name === "cabinet" ? resolveSection(route.section, sections) : null) ||
    sections[0] ||
    "applications";
  const selectedId = route.name === "cabinet" ? route.id : null;
  const view = section as View;
  const selectedTitle = currentUser ? sectionLabel(currentUser.role, view) : "Сервис";
  // Подзаголовок в шапке заменил три строки текста, с которых начинался экран
  // («Заявки» в меню → «Мои заявки» → «Статус и адрес по заявке…»). Здесь —
  // только то, что человек не видит и так: сколько всего записей.
  const sectionSubtitle =
    view === "applications" && !loading ? `Всего заявок: ${applications.length}` : undefined;

  const goHome = useCallback(() => navigate({ name: "home" }), [navigate]);
  const openCabinet = useCallback(
    (nextSection: string | null = null, id: string | null = null) =>
      navigate({ name: "cabinet", section: nextSection, id }),
    [navigate]
  );
  /** Выбор карточки внутри раздела — это не «переход», историю не засоряем. */
  const selectInSection = useCallback(
    (id: string | null) => navigate({ name: "cabinet", section, id }, { replace: true }),
    [navigate, section]
  );

  // Охрана маршрутов: неавторизованного — на вход (с запоминанием куда он шёл),
  // авторизованного со страницы входа — туда, куда он собирался.
  useEffect(() => {
    if (!authChecked) return;
    if (route.name === "cabinet") {
      if (!currentUser) {
        navigate({ name: "login", next: routeToPath(route) }, { replace: true });
      } else if (route.section && route.section !== section) {
        // Раздел не существует у этой роли (или это синоним) — нормализуем URL.
        navigate({ name: "cabinet", section, id: route.id }, { replace: true });
      }
      return;
    }
    if (route.name === "login" && currentUser) {
      const target = route.next ? parsePath(route.next) : null;
      navigate(
        target && target.name !== "login" ? target : { name: "cabinet", section: null, id: null },
        { replace: true }
      );
    }
  }, [authChecked, route, currentUser, section, navigate]);

  async function handleLogout() {
    await api.logout().catch(() => undefined);
    setCurrentUser(null);
    setProviders([]);
    setAddresses([]);
    setApplications([]);
    navigate({ name: "home" }, { replace: true });
  }

  if (!authChecked) {
    return (
      <div className="auth-shell">
        <LoadingRows />
      </div>
    );
  }

  // Приглашение принимаем на любом состоянии сессии: иначе ссылка из письма,
  // открытая в браузере с чужим активным входом, молча терялась.
  if (route.name === "invite") {
    return (
      <AuthView
        canBootstrap={canBootstrap}
        initialToken={route.token}
        onAuthenticated={(user) => {
          setCurrentUser(user);
          navigate({ name: "cabinet", section: null, id: null }, { replace: true });
        }}
        onHome={goHome}
        onBack={back}
        canGoBack={canGoBack}
      />
    );
  }

  if (route.name === "login") {
    // Уже авторизован — редирект отработает в эффекте выше.
    if (currentUser) {
      return (
        <div className="auth-shell">
          <LoadingRows />
        </div>
      );
    }
    return (
      <AuthView
        canBootstrap={canBootstrap}
        onAuthenticated={(user) => setCurrentUser(user)}
        onHome={goHome}
        onBack={back}
        canGoBack={canGoBack}
      />
    );
  }

  // Ссылку из письма открывают в любом браузере — авторизация не нужна.
  if (route.name === "verify") {
    return <EmailVerificationPage token={route.token} onHome={goHome} />;
  }

  // Правовые документы доступны всем и по прямой ссылке.
  if (route.name === "legal") {
    return <LegalPage doc={route.doc} onHome={goHome} onBack={back} canGoBack={canGoBack} />;
  }

  if (route.name !== "cabinet") {
    // «/» и «/address/<id>» — публичная главная, одинаково для гостя и для
    // залогиненного. Это и есть починка «логотип уводит в Заявки».
    return (
      <PublicCatalog
        canBootstrap={canBootstrap}
        currentUser={currentUser}
        onAuthenticated={(user) => setCurrentUser(user)}
        onLoginClick={() => navigate({ name: "login", next: routeToPath(route) })}
        onOpenDashboard={() => openCabinet()}
        openAddressId={route.name === "address" ? route.id : null}
        onOpenLegal={(doc) => navigate({ name: "legal", doc })}
        onOpenAddress={(id) => {
          if (id) {
            navigate({ name: "address", id });
          } else if (canGoBack) {
            back();
          } else {
            navigate({ name: "home" }, { replace: true });
          }
        }}
      />
    );
  }

  // Кабинет: без сессии редирект на вход отработает в эффекте выше.
  if (!currentUser) {
    return (
      <div className="auth-shell">
        <LoadingRows />
      </div>
    );
  }

  if (currentUser.role === "client") {
    return (
      <ClientDashboardView
        user={currentUser}
        view={section as ClientSectionId}
        onView={(next, id) => openCabinet(next, id ?? null)}
        selectedId={selectedId}
        onSelect={selectInSection}
        onLogout={handleLogout}
        onOpenCatalog={goHome}
        onBack={back}
        canGoBack={canGoBack}
      />
    );
  }

  if (currentUser.role === "owner") {
    return (
      <OwnerDashboardView
        user={currentUser}
        view={section as OwnerSectionId}
        onView={(next, id) => openCabinet(next, id ?? null)}
        selectedId={selectedId}
        onSelect={selectInSection}
        onLogout={handleLogout}
        onOpenCatalog={goHome}
        onBack={back}
        canGoBack={canGoBack}
      />
    );
  }

  return (
    <AppShell
      user={currentUser}
      section={view}
      onSection={(id) => openCabinet(id)}
      title={selectedTitle}
      subtitle={sectionSubtitle}
      counts={{ applications: applications.length }}
      onOpenSite={goHome}
      onBack={back}
      canGoBack={canGoBack}
      onLogout={handleLogout}
      onRefresh={() => setRefreshKey((value) => value + 1)}
      actions={
        <NotificationCenter
          refreshKey={refreshKey}
          onNavigate={(n) => {
            if (n.link_type === "application" && n.link_id) {
              openCabinet("applications");
              // Админский список заявок сам управляет selected — внешнего
              // пробрасывания selected пока нет; пользователь увидит список
              // и сможет найти нужную. Линк хотя бы переключит раздел.
            } else if (n.link_type === "chat") {
              openCabinet("address-chats");
            }
          }}
        />
      }
      banner={
        error ? (
          <ListError
            message={error}
            onRetry={() => setRefreshKey((value) => value + 1)}
            onRelogin={handleLogout}
          />
        ) : null
      }
    >
      {loading ? (
        <ListLoading />
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
                  openCabinet("applications");
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
              <ChatsListPanel currentUser={currentUser} refreshToken={refreshKey} />
            )}
            {view === "review-moderation" && currentUser.role === "admin" && (
              <AdminReviewModeration />
            )}
            {view === "access" && currentUser.role === "admin" && (
              <>
                <SessionsView />
                <AccessView currentUserId={currentUser.id} />
              </>
            )}
        </>
      )}
    </AppShell>
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
  const [retryKey, setRetryKey] = useState(0);

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
  }, [applicationId, retryKey]);

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
  if (error) {
    // Без «Повторить» экран оплаты залипал: единственным выходом был F5.
    return (
      <div style={cardStyle}>
        <InlineError message={error} />
        <div className="row-actions">
          <Button onClick={() => setRetryKey((value) => value + 1)} variant="secondary">
            <RefreshCw size={16} /> Повторить
          </Button>
        </div>
      </div>
    );
  }
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
          Скачайте счёт от собственника, оплатите по реквизитам и приложите
          платёжное поручение. После подтверждения собственником заявка перейдёт
          к подготовке документов.
        </p>
        <PaymentAttachmentsPanel
          paymentId={payment.id}
          viewerRole="client"
          paymentStatus={payment.status}
        />
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

type ClientCabinetView = ClientSectionId;

function ClientDashboardView({
  user,
  view,
  onView,
  selectedId,
  onSelect,
  onLogout,
  onOpenCatalog,
  onBack,
  canGoBack,
}: {
  user: CurrentUser;
  /** Раздел и выбранная заявка приходят из URL — F5 их больше не сбрасывает. */
  view: ClientCabinetView;
  onView: (view: ClientCabinetView, id?: string | null) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onLogout: () => void;
  onOpenCatalog: () => void;
  onBack: () => void;
  canGoBack: boolean;
}) {
  const [applications, setApplications] = useState<ClientApplication[]>([]);
  const [pendingChatId, setPendingChatId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
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
        // Заявки из URL может не быть в списке (чужая ссылка, удалённая заявка).
        if (!selectedId) {
          onSelect(result[0]?.id || null);
        } else if (!result.some((application) => application.id === selectedId)) {
          // Молча подставлять первую нельзя: по ссылке из уведомления человек
          // открыл бы чужую заявку и решил, что смотрит нужную.
          setNotice("Заявка не найдена — возможно, её удалили. Показан список.");
          onSelect(result[0]?.id || null);
        }
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // selectedId намеренно не в зависимостях: список перезагружается только по
    // refreshKey, иначе смена выбранной заявки дёргала бы сеть.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  const selectedApplication = useMemo(
    () => applications.find((application) => application.id === selectedId) || applications[0] || null,
    [applications, selectedId]
  );

  const [documents, setDocuments] = useState<ApplicationDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);

  // Документы грузим только для выбранной заявки и только когда сервер их
  // отдаст. Запрашивать их для каждой строки списка значило бы N запросов на
  // отрисовку очереди — агрегата с количеством файлов в списке нет.
  useEffect(() => {
    const application = selectedApplication;
    if (!application || !clientCanSeeDocuments(application.status)) {
      setDocuments([]);
      setDocumentsError(null);
      return;
    }
    let alive = true;
    setDocumentsLoading(true);
    setDocumentsError(null);
    api
      .applicationDocuments(application.id)
      .then((result) => alive && setDocuments(result))
      .catch((err: Error) => alive && setDocumentsError(err.message))
      .finally(() => alive && setDocumentsLoading(false));
    return () => {
      alive = false;
    };
  }, [selectedApplication?.id, selectedApplication?.status]);

  const [applicationChat, setApplicationChat] = useState<AddressChat | null>(null);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  // Смена заявки закрывает открытый чат: адрес другой, и оставлять переписку
  // по прошлому адресу под шапкой новой заявки нельзя.
  useEffect(() => {
    setApplicationChat(null);
    setChatError(null);
  }, [selectedApplication?.id]);

  async function openApplicationChat(addressId: string) {
    setChatBusy(true);
    setChatError(null);
    try {
      // Чат заводится по паре «адрес × клиент», отдельной привязки к заявке в
      // модели нет. Для клиента это безопасно: свой адрес — свой чат.
      setApplicationChat(await api.openChatForAddress(addressId));
    } catch (err) {
      setChatError((err as Error).message);
    } finally {
      setChatBusy(false);
    }
  }

  return (
    <AppShell
      user={user}
      section={view}
      onSection={(id) => onView(id as ClientCabinetView)}
      title={view === "applications" ? "Заявки" : "Чаты"}
      subtitle={
        view === "applications" && !loading
          ? applications.length
            ? `Всего заявок: ${applications.length}`
            : undefined
          : "Переписка с собственниками адресов"
      }
      counts={{ applications: applications.length }}
      onOpenSite={onOpenCatalog}
      onBack={onBack}
      canGoBack={canGoBack}
      onLogout={onLogout}
      onRefresh={() => setRefreshKey((value) => value + 1)}
      actions={
        <>
          <NotificationCenter
            refreshKey={refreshKey}
            onNavigate={(n) => {
              if (n.link_type === "application" && n.link_id) {
                // Раздел и заявка одним переходом: два подряд ушли бы
                // в историю двумя записями и второй перетёр бы первый.
                onView("applications", n.link_id);
              } else if (n.link_type === "chat" && n.link_id) {
                onView("chats");
                setPendingChatId(n.link_id);
              }
            }}
          />
          <PushToggle />
        </>
      }
      banner={
        <>
          {error ? (
            <ListError message={error} onRetry={() => setRefreshKey((value) => value + 1)} />
          ) : null}
          <InlineNotice message={notice} onDismiss={() => setNotice(null)} />
        </>
      }
    >
      {view === "applications" && (loading ? (
        <ListLoading />
      ) : applications.length === 0 ? (
        <ListEmpty
          title="Заявок пока нет"
          text="Выберите адрес в каталоге и отправьте заявку — она появится здесь."
          action={{ label: "Открыть каталог", onClick: onOpenCatalog }}
        />
      ) : (
        <ApplicationsQueue
          rows={applications.map((application) => ({
            id: application.id,
            subject:
              application.company_name || application.planned_client_name || "Компания",
            address: application.full_address,
            status: application.status,
            updatedAt: application.updated_at,
            amount: formatMoney(application.selected_price)
          }))}
          selectedId={selectedApplication?.id || null}
          onSelect={onSelect}
          subjectLabel="Компания"
          filters={CLIENT_QUEUE_FILTERS}
          drawer={
            selectedApplication ? (
              <ApplicationDrawer
                id={selectedApplication.id}
                title={
                  selectedApplication.company_name ||
                  selectedApplication.planned_client_name ||
                  "Заявка"
                }
                address={selectedApplication.full_address}
                status={selectedApplication.status}
                docsCount={documents.length || null}
                docsDisabledReason={
                  clientCanSeeDocuments(selectedApplication.status)
                    ? null
                    : "Документы открываются после проверки — когда заявка будет готова к выдаче"
                }
                chatDisabledReason={null}
                main={
                  <>
                    <div className="cab-kv">
                      <DrawerRow label="Тип" value={typeLabels[selectedApplication.type]} />
                      <DrawerRow
                        label="Стоимость"
                        value={formatMoney(selectedApplication.selected_price)}
                      />
                      <DrawerRow
                        label="Срок"
                        value={
                          selectedApplication.term_months
                            ? `${selectedApplication.term_months} мес.`
                            : "—"
                        }
                      />
                      <DrawerRow
                        label="ИФНС"
                        value={
                          selectedApplication.fns_number
                            ? `№ ${selectedApplication.fns_number}`
                            : "—"
                        }
                      />
                      <DrawerRow label="Собственник" value={selectedApplication.provider_name} />
                      <DrawerRow
                        label="Корреспонденция"
                        value={
                          selectedApplication.has_correspondence_service
                            ? selectedApplication.correspondence_price
                              ? `Подключена · ${formatMoney(selectedApplication.correspondence_price)}`
                              : "Подключена"
                            : "Не подключена"
                        }
                      />
                      {selectedApplication.room_number ? (
                        <DrawerRow label="Помещение" value={selectedApplication.room_number} />
                      ) : null}
                    </div>

                    {selectedApplication.status === "awaiting_payment" ? (
                      <div className="cab-actions">
                        <SbpPaymentPanel
                          applicationId={selectedApplication.id}
                          onPaid={() => setRefreshKey((value) => value + 1)}
                        />
                      </div>
                    ) : null}

                    <DrawerTimeline
                      emptyText="Обновления по заявке появятся после проверки."
                      events={selectedApplication.events}
                    />
                  </>
                }
                docs={
                  documentsLoading ? (
                    <ListLoading rows={2} />
                  ) : documentsError ? (
                    <ListError message={documentsError} />
                  ) : documents.length ? (
                    <div className="cab-actions">
                      {documents.map((document) => (
                        <DownloadLink
                          className="cab-doc"
                          href={apiDownloadUrl(document.download_url)}
                          key={document.id}
                        >
                          <FileText size={17} />
                          <span style={{ minWidth: 0, flex: 1 }}>
                            <strong className="cab-doc__name">{document.original_filename}</strong>
                            <span className="cab-doc__meta">
                              {documentKindLabels[document.kind]} ·{" "}
                              {formatFileSize(document.size_bytes)} ·{" "}
                              {formatDate(document.created_at)}
                            </span>
                          </span>
                          <Download size={16} />
                        </DownloadLink>
                      ))}
                    </div>
                  ) : (
                    <div className="cab-actions">
                      <ListEmpty
                        text="Как только собственник загрузит комплект и оператор его проверит, файлы появятся здесь."
                        title="Документов пока нет"
                      />
                    </div>
                  )
                }
                chat={
                  <div className="cab-actions">
                    {chatError ? <ListError message={chatError} /> : null}
                    {applicationChat ? (
                      <AddressChatPanel
                        chat={applicationChat}
                        currentUser={user}
                        onClose={() => setApplicationChat(null)}
                      />
                    ) : (
                      <>
                        <p className="cab-timeline__text">
                          Переписка с собственником по адресу этой заявки.
                        </p>
                        <button
                          className="cab-chat-cta"
                          disabled={chatBusy}
                          onClick={() => openApplicationChat(selectedApplication.address_id)}
                          type="button"
                        >
                          {chatBusy ? <Loader2 className="spin" size={15} /> : <MessageSquare size={15} />}
                          Открыть чат с собственником
                        </button>
                      </>
                    )}
                  </div>
                }
              />
            ) : null
          }
        />
      ))}

      {view === "chats" && (
        <ChatsListPanel
          currentUser={user}
          refreshToken={refreshKey}
          autoOpenChatId={pendingChatId}
          onChatOpened={() => setPendingChatId(null)}
        />
      )}
    </AppShell>
  );
}

type OwnerCabinetView = OwnerSectionId;

function OwnerDashboardView({
  user,
  view,
  onView,
  selectedId,
  onSelect,
  onLogout,
  onOpenCatalog,
  onBack,
  canGoBack,
}: {
  user: CurrentUser;
  /** Раздел и выбранная заявка приходят из URL — F5 их больше не сбрасывает. */
  view: OwnerCabinetView;
  onView: (view: OwnerCabinetView, id?: string | null) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onLogout: () => void;
  onOpenCatalog: () => void;
  onBack: () => void;
  canGoBack: boolean;
}) {
  const [pendingChatId, setPendingChatId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<OwnerDashboard | null>(null);
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
        // Заявки из URL может не быть в списке (ссылка из уведомления на уже
        // удалённую заявку) — сообщаем, а не подменяем молча чужой.
        if (!selectedId) {
          onSelect(result.applications[0]?.id || null);
        } else if (!result.applications.some((application) => application.id === selectedId)) {
          setNotice("Заявка не найдена — возможно, её удалили. Показан список.");
          onSelect(result.applications[0]?.id || null);
        }
      })
      .catch((err: Error) => {
        if (alive) setError(err.message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // selectedId намеренно не в зависимостях — иначе смена выбранной заявки
    // перезапрашивала бы весь дашборд.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  /**
   * Чат по адресу заявки. Собственник не может его создать — сервер разрешает
   * это только клиенту, — поэтому ищем уже существующий среди своих.
   *
   * Совпадение только по адресу: привязки чата к заявке в модели нет. Если по
   * одному адресу переписываются несколько клиентов, подходящих чатов будет
   * больше одного, и открывать первый попавшийся нельзя — это чужая переписка.
   * В таком случае вкладка остаётся пустой, а разговоры доступны в разделе
   * «Чаты», где видно, кто собеседник.
   */
  const [ownerChat, setOwnerChat] = useState<AddressChat | null>(null);

  useEffect(() => {
    const addressId = selectedApplication?.address_id;
    if (!addressId) {
      setOwnerChat(null);
      return;
    }
    let alive = true;
    api
      .listMyChats()
      .then((chats) => {
        if (!alive) return;
        const matching = chats.filter((chat) => chat.address_id === addressId);
        setOwnerChat(matching.length === 1 ? matching[0] : null);
      })
      .catch(() => alive && setOwnerChat(null));
    return () => {
      alive = false;
    };
  }, [selectedApplication?.address_id]);

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
    <AppShell
      user={user}
      section={view}
      onSection={(id) => onView(id as OwnerCabinetView)}
      title={view === "applications" ? "Заявки" : view === "addresses" ? "Адреса" : "Чаты"}
      subtitle={
        view === "applications"
          ? actionableCount
            ? `Требуют действия: ${actionableCount} из ${applications.length}`
            : applications.length
              ? `Всего заявок: ${applications.length}`
              : undefined
          : view === "addresses"
            ? `Опубликовано: ${publishedCount} из ${addresses.length}`
            : "Входящие сообщения по вашим адресам"
      }
      counts={{ applications: applications.length, addresses: addresses.length }}
      onOpenSite={onOpenCatalog}
      onBack={onBack}
      canGoBack={canGoBack}
      onLogout={onLogout}
      onRefresh={() => setRefreshKey((value) => value + 1)}
      actions={
        <>
          <NotificationCenter
            refreshKey={refreshKey}
            onNavigate={(n) => {
              if (n.link_type === "application" && n.link_id) {
                // Раздел и заявка одним переходом — иначе вторая навигация
                // затирает первую.
                onView("applications", n.link_id);
              } else if (n.link_type === "chat" && n.link_id) {
                onView("chats");
                setPendingChatId(n.link_id);
              }
            }}
          />
          <PushToggle />
        </>
      }
      banner={
        <>
          {error ? (
            <ListError message={error} onRetry={() => setRefreshKey((value) => value + 1)} />
          ) : null}
          <InlineNotice message={notice} onDismiss={() => setNotice(null)} />
        </>
      }
    >
        {(view === "applications" || view === "addresses") && (loading ? (
          <ListLoading />
        ) : !dashboard ? (
          <ListEmpty title="Кабинет недоступен" text="Проверьте привязку пользователя к организации собственника." />
        ) : (
          // Раскладка owner-layout нужна только разделу «Адреса»: заявки рисует
          // общая очередь со своей сеткой. Тернарник с двумя одинаковыми
          // ветками, стоявший здесь, остался от времён, когда раскладок было две.
          <section className={view === "addresses" ? "owner-layout owner-layout--single" : undefined}>
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
            applications.length === 0 ? (
              <ListEmpty
                text="Когда оператор назначит заявку на ваш адрес, она появится здесь."
                title="Заявок пока нет"
              />
            ) : (
              <ApplicationsQueue
                rows={applications.map((application) => ({
                  id: application.id,
                  subject:
                    application.company_name || application.planned_client_name || "Клиент",
                  address: application.full_address,
                  status: application.status,
                  updatedAt: application.updated_at,
                  amount: formatMoney(application.selected_price)
                }))}
                selectedId={selectedApplication?.id || null}
                onSelect={onSelect}
                subjectLabel="Клиент"
                filters={OWNER_QUEUE_FILTERS}
                drawer={
                  selectedApplication ? (
                    <ApplicationDrawer
                      id={selectedApplication.id}
                      title={
                        selectedApplication.company_name ||
                        selectedApplication.planned_client_name ||
                        "Заявка"
                      }
                      address={selectedApplication.full_address}
                      status={selectedApplication.status}
                      docsCount={documents.length || null}
                      chatDisabledReason={
                        ownerChat
                          ? null
                          : "Чат по адресу открывает клиент — здесь появится уже начатая переписка"
                      }
                      main={
                        <>
                          <div className="cab-kv">
                            <DrawerRow label="Тип" value={typeLabels[selectedApplication.type]} />
                            <DrawerRow
                              label="Сумма адреса"
                              value={formatMoney(selectedApplication.selected_price)}
                            />
                            <DrawerRow
                              label="Срок"
                              value={
                                selectedApplication.term_months
                                  ? `${selectedApplication.term_months} мес.`
                                  : "—"
                              }
                            />
                            <DrawerRow
                              label="ИФНС"
                              value={
                                selectedApplication.fns_number
                                  ? `№ ${selectedApplication.fns_number}`
                                  : "—"
                              }
                            />
                            <DrawerRow
                              label="Контакт клиента"
                              value={selectedApplication.contact_name || "—"}
                            />
                            <DrawerRow
                              label="Связь"
                              value={
                                [
                                  selectedApplication.contact_phone,
                                  selectedApplication.contact_email
                                ]
                                  .filter(Boolean)
                                  .join(" · ") || "—"
                              }
                            />
                            <DrawerRow
                              label="Следующий шаг"
                              value={ownerNextStepLabel(selectedApplication)}
                            />
                            <DrawerRow
                              label="Корреспонденция"
                              value={
                                selectedApplication.has_correspondence_service
                                  ? selectedApplication.correspondence_price
                                    ? `Подключена · ${formatMoney(selectedApplication.correspondence_price)}`
                                    : "Подключена"
                                  : "Не подключена"
                              }
                            />
                          </div>

                          <div className="cab-actions">
                            <OwnerPaymentSection
                              applicationId={selectedApplication.id}
                              onConfirmed={() => setRefreshKey((value) => value + 1)}
                            />

                            {/* Набор действий приходит с бэкенда: право решать,
                                что можно делать с заявкой, остаётся там. */}
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
                                <button
                                  className={
                                    action === "reject"
                                      ? "cab-btn cab-btn--danger cab-btn--block"
                                      : "cab-btn cab-btn--primary cab-btn--block"
                                  }
                                  disabled={actionBusy !== null}
                                  key={action}
                                  onClick={() => runOwnerAction(action)}
                                  type="button"
                                >
                                  {actionBusy === action ? (
                                    <Loader2 className="spin" size={15} />
                                  ) : (
                                    <Icon size={15} />
                                  )}
                                  {ownerActionLabels[action] || action}
                                </button>
                              );
                            })}
                            {actionError ? <ListError message={actionError} /> : null}
                          </div>

                          <DrawerTimeline
                            emptyText="События появятся после назначения заявки."
                            events={selectedApplication.events}
                          />
                        </>
                      }
                      docs={
                        <div className="cab-actions">
                          {ownerCanUploadDocuments(selectedApplication) ? (
                            <form className="owner-upload-form" onSubmit={uploadOwnerDocument}>
                              <Field label="Тип документа">
                                <select
                                  value={documentKind}
                                  onChange={(event) =>
                                    setDocumentKind(event.target.value as DocumentFileKind)
                                  }
                                >
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
                                  onChange={(event) =>
                                    setDocumentFile(event.target.files?.[0] || null)
                                  }
                                  type="file"
                                />
                              </Field>
                              <button
                                className="cab-btn cab-btn--primary cab-btn--block"
                                disabled={uploadBusy || !documentFile}
                                type="submit"
                              >
                                {uploadBusy ? (
                                  <Loader2 className="spin" size={15} />
                                ) : (
                                  <Upload size={15} />
                                )}
                                Отправить на проверку
                              </button>
                            </form>
                          ) : null}

                          {uploadError || documentsError ? (
                            <ListError message={uploadError || documentsError || ""} />
                          ) : null}

                          {documentsLoading ? (
                            <ListLoading rows={2} />
                          ) : documents.length ? (
                            documents.map((document) => (
                              <DownloadLink
                                className="cab-doc"
                                href={apiDownloadUrl(document.download_url)}
                                key={document.id}
                              >
                                <FileText size={17} />
                                <span style={{ minWidth: 0, flex: 1 }}>
                                  <strong className="cab-doc__name">
                                    {document.original_filename}
                                  </strong>
                                  <span className="cab-doc__meta">
                                    {documentKindLabels[document.kind]} ·{" "}
                                    {formatFileSize(document.size_bytes)} ·{" "}
                                    {formatDate(document.created_at)}
                                  </span>
                                </span>
                                <Download size={16} />
                              </DownloadLink>
                            ))
                          ) : (
                            <ListEmpty
                              text="Загрузите комплект — он уйдёт оператору на проверку."
                              title="Документов пока нет"
                            />
                          )}
                        </div>
                      }
                      chat={
                        <div className="cab-actions">
                          {ownerChat ? (
                            <AddressChatPanel
                              chat={ownerChat}
                              currentUser={user}
                              onClose={() => onView("chats")}
                            />
                          ) : (
                            <p className="cab-timeline__text">
                              Переписки по адресу этой заявки пока нет. Создать её может
                              только клиент — из карточки адреса или из своей заявки.
                            </p>
                          )}
                        </div>
                      }
                    />
                  ) : null
                }
              />
            )
          )}

        </section>
        ))}

        {view === "chats" && (
          <ChatsListPanel
            currentUser={user}
            refreshToken={refreshKey}
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
            initialAmenities={editorAddress.amenities}
            initialDescription={editorAddress.description ?? null}
            onClose={() => setEditorAddress(null)}
            onSaved={() => setRefreshKey((value) => value + 1)}
          />
        ) : null}
    </AppShell>
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

  useModalDismiss(true, onClose);
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
              <StatusBadge status={application.status} />
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
                <DownloadLink className="download-link" href={packageDownloadUrl(application.id)}>
                  <Download size={16} /> ZIP
                </DownloadLink>
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

  useModalDismiss(!!application, onClose);

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
            <strong>{statusText(moderation?.status || application.status)}</strong>
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
                    <DownloadLink className="owner-document-item" href={apiDownloadUrl(document.download_url)} key={document.id}>
                      <FileText size={17} />
                      <span>
                        <strong>{document.original_filename}</strong>
                        <small>
                          {documentKindLabels[document.kind]} · {formatFileSize(document.size_bytes)} ·{" "}
                          {formatDate(document.created_at)}
                        </small>
                      </span>
                      <Download size={16} />
                    </DownloadLink>
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

  useModalDismiss(!!application, null);
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
            <DownloadLink className="btn secondary" href={downloadUrl}>
              <Download size={16} /> Скачать ZIP
            </DownloadLink>
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
            <DownloadLink className="btn secondary" href={resultUrl}>
              <Download size={16} /> Скачать ZIP
            </DownloadLink>
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
                <DownloadLink className="download-link" href={packageDownloadUrl(item.application_id)}>
                  <Download size={16} /> ZIP
                </DownloadLink>
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

  useModalDismiss(true, null);

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
                <DownloadLink className="download-link" href={apiDownloadUrl(document.download_url)}>
                  <Download size={16} /> Скачать
                </DownloadLink>
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
            <p className="hint">Выберите адрес слева</p>
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
