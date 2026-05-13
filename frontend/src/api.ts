import type {
  Address,
  AddressPublicationStatus,
  ActiveClientRegistryItem,
  AddressChat,
  AddressChatMessage,
  AddressPhotoAdmin,
  AddressServiceAdmin,
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
  OwnerConnectionRequestStatus,
  ProviderConnectionRequest,
  ProviderConnectionRequestApprove,
  ProviderConnectionRequestApproveResult,
  Payment,
  ProviderConnectionRequestCreate,
  ProviderConnectionRequestStatusUpdate,
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
      // Reset on next microtask so concurrent callers share this run, future callers get a fresh attempt.
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
    // Versioned API uses { error: { code, message, details } }; tolerate legacy { detail }.
    const errorObj = body?.error;
    const detail = body?.detail;
    const message =
      typeof errorObj?.message === "string"
        ? errorObj.message
        : typeof detail === "string"
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

  initiatePayment: (applicationId: string) =>
    request<Payment>("/payments/initiate", {
      method: "POST",
      body: JSON.stringify({ application_id: applicationId, payer_type: "individual" })
    }),
  getPayment: (paymentId: string) => request<Payment>(`/payments/${paymentId}`),
  cancelPayment: (paymentId: string) =>
    request<Payment>(`/payments/${paymentId}/cancel`, { method: "POST" }),
  refundPayment: (paymentId: string, valueRefundKopeks: number | null, reason: string) =>
    request<Payment>(`/payments/${paymentId}/refund`, {
      method: "POST",
      body: JSON.stringify({ value_refund_kopeks: valueRefundKopeks, reason })
    }),
  adminMarkPaymentPaid: (paymentId: string, comment?: string) =>
    request<Payment>(`/payments/${paymentId}/mark-paid`, {
      method: "POST",
      body: JSON.stringify({ comment: comment ?? null })
    }),
  adminRejectPayment: (paymentId: string, reason: string) =>
    request<Payment>(`/payments/${paymentId}/reject-payment`, {
      method: "POST",
      body: JSON.stringify({ reason })
    }),

  adminListProviderRequests: (status?: OwnerConnectionRequestStatus) => {
    const query = status ? `?status=${status}` : "";
    return request<ProviderConnectionRequest[]>(`/admin/provider-requests${query}`);
  },
  adminUpdateProviderRequestStatus: (
    requestId: string,
    payload: ProviderConnectionRequestStatusUpdate
  ) =>
    request<ProviderConnectionRequest>(`/admin/provider-requests/${requestId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  adminApproveProviderRequest: (
    requestId: string,
    payload: ProviderConnectionRequestApprove
  ) =>
    request<ProviderConnectionRequestApproveResult>(
      `/admin/provider-requests/${requestId}/approve`,
      { method: "POST", body: JSON.stringify(payload) }
    ),

  addresses: (providerId?: string) => {
    const query = providerId ? `?provider_id=${providerId}` : "";
    return request<Address[]>(`/addresses${query}`);
  },
  createAddress: (payload: unknown) =>
    request<Address>("/addresses", { method: "POST", body: JSON.stringify(payload) }),

  submitAddressForModeration: (addressId: string) =>
    request<Address>(`/addresses/${addressId}/submit`, { method: "POST" }),
  archiveAddress: (addressId: string) =>
    request<Address>(`/addresses/${addressId}/archive`, { method: "POST" }),
  adminListAddressesForModeration: (status?: AddressPublicationStatus) => {
    const query = status ? `?status=${status}` : "";
    return request<Address[]>(`/admin/addresses${query}`);
  },
  adminPublishAddress: (addressId: string) =>
    request<Address>(`/admin/addresses/${addressId}/publish`, { method: "POST" }),
  adminRejectAddress: (addressId: string, moderationComment: string) =>
    request<Address>(`/admin/addresses/${addressId}/reject`, {
      method: "POST",
      body: JSON.stringify({ moderation_comment: moderationComment })
    }),
  adminListAddressServices: (addressId: string) =>
    request<AddressServiceAdmin[]>(`/admin/addresses/${addressId}/services`),
  adminUpsertAddressService: (
    addressId: string,
    kind: string,
    payload: { price: string | number; is_active: boolean }
  ) =>
    request<AddressServiceAdmin>(
      `/admin/addresses/${addressId}/services/${kind}`,
      { method: "PUT", body: JSON.stringify(payload) }
    ),
  adminDeleteAddressService: (addressId: string, kind: string) =>
    request<void>(`/admin/addresses/${addressId}/services/${kind}`, {
      method: "DELETE"
    }),

  // ===== Address chats =====
  openChatForAddress: (addressId: string) =>
    request<AddressChat>(`/chats/addresses/${addressId}`, { method: "POST" }),
  listMyChats: () => request<AddressChat[]>(`/chats`),
  getChatMessages: (chatId: string) =>
    request<AddressChatMessage[]>(`/chats/${chatId}/messages`),
  postChatMessage: (chatId: string, body: string) =>
    request<AddressChatMessage>(`/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ body })
    }),

  // ===== Owner address description =====
  ownerUpdateAddressDescription: (addressId: string, description: string | null) =>
    request<{ id: string; description: string | null }>(
      `/owner/addresses/${addressId}/description`,
      { method: "PATCH", body: JSON.stringify({ description }) }
    ),

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
    request<PaymentDocument>(`/clients/${clientId}/payment-documents`, { method: "POST", body: form }),

  // Address photos — owner
  ownerListAddressPhotos: (addressId: string) =>
    request<AddressPhotoAdmin[]>(`/owner/addresses/${addressId}/photos`),
  ownerUploadAddressPhoto: (addressId: string, form: FormData) =>
    request<AddressPhotoAdmin>(`/owner/addresses/${addressId}/photos`, { method: "POST", body: form }),
  ownerDeletePhoto: (photoId: string) =>
    request<void>(`/owner/photos/${photoId}`, { method: "DELETE" }),
  ownerSetMainPhoto: (photoId: string) =>
    request<AddressPhotoAdmin>(`/owner/photos/${photoId}/main`, { method: "POST" }),

  // Address photos — admin moderation
  adminPendingPhotos: () =>
    request<AddressPhotoAdmin[]>("/admin/address-photos/pending"),
  adminApprovePhoto: (photoId: string) =>
    request<AddressPhotoAdmin>(`/admin/address-photos/${photoId}/approve`, { method: "POST" }),
  adminRejectPhoto: (photoId: string, comment: string) =>
    request<AddressPhotoAdmin>(`/admin/address-photos/${photoId}/reject`, {
      method: "POST",
      body: JSON.stringify({ comment })
    })
};

export function packageDownloadUrl(applicationId: string): string {
  return `${API_BASE}/applications/${applicationId}/download-package`;
}

export function paymentDocumentDownloadUrl(path: string): string {
  return `${API_BASE}${path}`;
}
