export type ApplicationType = "initial_registration" | "address_change";
export type ApplicationStatus =
  | "draft"
  | "guarantee_issued"
  | "awaiting_contract"
  | "contract_signed"
  | "active"
  | "expired"
  | "terminated";
export type NoticePeriod = "1d" | "7d" | "1m";

export interface Provider {
  id: string;
  code: string;
  full_name: string;
  short_name: string;
  inn: string | null;
  kpp: string | null;
  ogrn: string | null;
  legal_address: string | null;
  signatory_name: string | null;
  signatory_position: string | null;
  signatory_initials: string | null;
  phone: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Address {
  id: string;
  provider_id: string;
  full_address: string;
  cadastral_number: string;
  ownership_doc: string;
  ownership_doc_short: string;
  ownership_doc_pages: number;
  price_6m: string;
  price_11m: string;
  correspondence_price: string | null;
  fns_number: number | null;
  fns_city: string | null;
  is_available: boolean;
  created_at: string;
  updated_at: string;
}

export interface Application {
  id: string;
  type: ApplicationType;
  status: ApplicationStatus;
  provider_id: string;
  address_id: string;
  client_id: string | null;
  planned_client_name: string | null;
  company_name: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  term_months: number | null;
  notice_period: NoticePeriod | null;
  has_correspondence_service: boolean;
  contract_city: string | null;
  fns_number: number | null;
  fns_city: string | null;
  expires_at: string | null;
  parent_application_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DadataLookup {
  inn: string;
  kpp: string | null;
  ogrn: string | null;
  full_name: string;
  short_name: string;
  legal_address: string | null;
  signatory_name: string | null;
  signatory_position: string | null;
  egrul_status: string;
  blockers: {
    liquidating_or_liquidated: boolean;
    bankrupt: boolean;
    signatory_disqualified: boolean;
    is_branch: boolean;
  };
}

export interface GeneratedDocument {
  id: string;
  application_id: string;
  kind: "contract" | "guarantee" | "package_zip";
  docx_url: string | null;
  pdf_url: string | null;
  zip_url: string | null;
  generated_at: string;
}

export interface PackageResult {
  application_id: string;
  zip_url: string;
  documents: GeneratedDocument[];
}

export interface ActiveClientRegistryItem {
  application_id: string;
  contract_id: string;
  client_id: string;
  company_name: string;
  client_inn: string;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  provider_name: string;
  address_full: string;
  contract_number: string;
  contract_date: string;
  start_date: string;
  end_date: string;
  renewal_date: string;
  term_months: number;
  days_until_renewal: number;
  price_total: string;
  renewal_status: "overdue" | "due_soon" | "active";
}
