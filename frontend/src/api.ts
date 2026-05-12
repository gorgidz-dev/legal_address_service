import type {
  Address,
  ActiveClientRegistryItem,
  Application,
  ApplicationActionResult,
  ApplicationDocument,
  ApplicationDocumentModeration,
  ApplicationDocumentUploadResult,
  BootstrapState,
  ClientApplication,
  CurrentUser,
  DadataLookup,
  DemoSeedResult,
  Invitation,
  InvitationCreateResult,
  NotificationInbox,
  AppNotification,
  OwnerDashboard,
  PackageResult,
  PaymentDocument,
  Provider,
  PublicClientApplicationCreate,
  PublicClientApplicationResult,
  ProviderConnectionRequest,
  ProviderConnectionRequestCreate,
  PublicAddress,
  UserSessionInfo
} from "./types";

// All API calls go through the versioned prefix. Override with VITE_API_BASE if hosting
// the API on a different origin (e.g. https://api.example.com/v1).
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// Paths that must NOT trigger an auto-refresh attempt on 401 (would loop or be meaningless).
const NO_REFRESH_PATHS = new Set([
  "/auth/login",
  "/auth/refresh",
  "/auth/logout",
  "/auth/bootstrap-state",
  "/auth/bootstrap-admin"
]);

let refreshInFlight: Promise<boolean> | null = null;

async function attemptRefresh(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const r = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include"
      });
      return r.ok;
    } catch {
      return false;
    } finally {
      setTimeout(() => {
        refreshInFlight = null;
      }, 0);
    }
  })();
  return refreshInFlight;
}

async function doFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {})
    }
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response = await doFetch(path, init);

  if (response.status === 401 && !NO_REFRESH_PATHS.has(path)) {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      response = await doFetch(path, init);
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
          : `HTTP ${response.status}`;
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<CurrentUser>("/auth/me"),
  bootstrapState: () => request<BootstrapState>("/auth/bootstrap-state"),
  bootstrapAdmin: (payload: unknown) =>
    request<{ user: CurrentUser }>("/auth/bootstrap-admin", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload: unknown) =>
    request<{ user: CurrentUser }>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  logoutAll: () => request<void>("/auth/logout-all", { method: "POST" }),
  listSessions: () => request<UserSessionInfo[]>("/auth/sessions"),
  refreshSession: () => request<{ user: CurrentUser }>("/auth/refresh", { method: "POST" }),
  invitations: () => request<Invitation[]>("/auth/invitations"),
  createInvitation: (payload: unknown) =>
    request<InvitationCreateResult>("/auth/invitations", { method: "POST", body: JSON.stringify(payload) }),
  acceptInvitation: (token: string, payload: unknown) =>
    request<{ user: CurrentUser }>(`/auth/invitations/${encodeURIComponent(token)}/accept`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  seedDemoData: (payload?: { password?: string }) =>
    request<DemoSeedResult>("/demo/seed", {
      method: "POST",
      body: JSON.stringify(payload || {})
    }),
  notifications: (filters?: { limit?: number; unread_only?: boolean }) => {
    const params = new URLSearchParams();
    if (filters?.limit) params.set("limit", String(filters.limit));
    if (filters?.unread_only) params.set("unread_only", "true");
    const query = params.toString();
    return request<NotificationInbox>(`/notifications${query ? `?${query}` : ""}`);
  },
  markNotificationRead: (notificationId: string) =>
    request<AppNotification>(`/notifications/${notificationId}/read`, { method: "POST" }),

  publicAddresses: (filters?: {
    city?: string;
    fns_number?: number | "";
    term_months?: 6 | 11;
    correspondence?: boolean;
  }) => {
    const params = new URLSearchParams();
    if (filters?.city) params.set("city", filters.city);
    if (filters?.fns_number) params.set("fns_number", String(filters.fns_number));
    if (filters?.term_months) params.set("term_months", String(filters.term_months));
    if (filters?.correspondence) params.set("correspondence", "true");
    const query = params.toString();
    return request<PublicAddress[]>(`/marketplace/addresses${query ? `?${query}` : ""}`);
  },
  createProviderConnectionRequest: (payload: ProviderConnectionRequestCreate) =>
    request<ProviderConnectionRequest>("/marketplace/provider-requests", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createPublicApplication: (payload: PublicClientApplicationCreate) =>
    request<PublicClientApplicationResult>("/marketplace/applications", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  clientApplications: () => request<ClientApplication[]>("/client/applications"),
  ownerDashboard: () => request<OwnerDashboard>("/owner/dashboard"),
  runApplicationAction: (applicationId: string, action: string) =>
    request<ApplicationActionResult>(
      `/workflow/applications/${applicationId}/actions/${encodeURIComponent(action)}`,
      { method: "POST" }
    ),
  applicationDocuments: (applicationId: string) =>
    request<ApplicationDocument[]>(`/workflow/applications/${applicationId}/documents`),
  applicationModeration: (applicationId: string) =>
    request<ApplicationDocumentModeration>(`/workflow/applications/${applicationId}/moderation`),
  uploadApplicationDocument: (applicationId: string, form: FormData) =>
    request<ApplicationDocumentUploadResult>(`/workflow/applications/${applicationId}/documents`, {
      method: "POST",
      body: form
    }),

  providers: () => request<Provider[]>("/providers"),
  createProvider: (payload: unknown) =>
    request<Provider>("/providers", { method: "POST", body: JSON.stringify(payload) }),

  addresses: (providerId?: string) => {
    const query = providerId ? `?provider_id=${providerId}` : "";
    return request<Address[]>(`/addresses${query}`);
  },
  createAddress: (payload: unknown) =>
    request<Address>("/addresses", { method: "POST", body: JSON.stringify(payload) }),

  applications: () => request<Application[]>("/applications"),
  createApplication: (payload: unknown) =>
    request<Application>("/applications", { method: "POST", body: JSON.stringify(payload) }),
  generatePackage: (applicationId: string) =>
    request<PackageResult>(`/applications/${applicationId}/generate-package`, { method: "POST" }),
  promoteToContract: (applicationId: string, payload: unknown) =>
    request<Application>(`/applications/${applicationId}/promote-to-contract`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  lookupInn: (inn: string) =>
    request<DadataLookup>(`/clients/lookup-by-inn?inn=${encodeURIComponent(inn)}`),

  uploadEgrn: (addressId: string, form: FormData) =>
    request(`/addresses/${addressId}/egrn-extracts`, { method: "POST", body: form }),

  activeClients: (dueWithinDays?: number) => {
    const query = typeof dueWithinDays === "number" ? `?due_within_days=${dueWithinDays}` : "";
    return request<ActiveClientRegistryItem[]>(`/registry/active-clients${query}`);
  },

  paymentDocuments: (clientId: string) => request<PaymentDocument[]>(`/clients/${clientId}/payment-documents`),
  uploadPaymentDocument: (clientId: string, form: FormData) =>
    request<PaymentDocument>(`/clients/${clientId}/payment-documents`, { method: "POST", body: form })
};

export function packageDownloadUrl(applicationId: string): string {
  return `${API_BASE}/applications/${applicationId}/download-package`;
}

export function paymentDocumentDownloadUrl(path: string): string {
  return `${API_BASE}${path}`;
}
