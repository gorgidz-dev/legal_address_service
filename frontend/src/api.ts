import type {
  Address,
  Application,
  DadataLookup,
  PackageResult,
  Provider
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
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
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export const api = {
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
    request(`/addresses/${addressId}/egrn-extracts`, { method: "POST", body: form })
};

export function packageDownloadUrl(applicationId: string): string {
  return `${API_BASE}/applications/${applicationId}/download-package`;
}
