import type {
  Address,
  ActiveClientRegistryItem,
  Application,
  BootstrapState,
  CurrentUser,
  DadataLookup,
  Invitation,
  InvitationCreateResult,
  PackageResult,
  PaymentDocument,
  Provider,
  PublicClientApplicationCreate,
  PublicClientApplicationResult,
  ProviderConnectionRequest,
  ProviderConnectionRequestCreate,
  PublicAddress
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {})
    }
  });

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
  invitations: () => request<Invitation[]>("/auth/invitations"),
  createInvitation: (payload: unknown) =>
    request<InvitationCreateResult>("/auth/invitations", { method: "POST", body: JSON.stringify(payload) }),
  acceptInvitation: (token: string, payload: unknown) =>
    request<{ user: CurrentUser }>(`/auth/invitations/${encodeURIComponent(token)}/accept`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),

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
