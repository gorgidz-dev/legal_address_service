export type ApplicationType = "initial_registration" | "address_change";
export type ApplicationStatus =
  | "draft"
  | "guarantee_issued"
  | "awaiting_contract"
  | "contract_signed"
  | "active"
  | "expired"
  | "terminated"
  | "awaiting_payment"
  | "paid"
  | "admin_review"
  | "needs_client_fix"
  | "assigned_to_owner"
  | "accepted_by_owner"
  | "rejected_by_owner"
  | "documents_preparing"
  | "documents_uploaded"
  | "documents_review"
  | "documents_revision"
  | "ready_for_client"
  | "completed"
  | "cancelled"
  | "dispute"
  | "refund_pending"
  | "refunded";
export type NoticePeriod = "1d" | "7d" | "1m";
export type UserRole = "manager" | "lawyer" | "admin" | "client" | "owner";
export type DocumentFileKind =
  | "client_requisites"
  | "company_details"
  | "ownership_proof"
  | "guarantee_letter"
  | "contract"
  | "act"
  | "owner_consent"
  | "postal_service"
  | "admin_review_file";

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  provider_id: string | null;
}

export interface BootstrapState {
  can_bootstrap: boolean;
}

export interface Invitation {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
  created_by: string | null;
}

export interface InvitationCreateResult {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  expires_at: string;
  accepted_at: string | null;
  invitation_token: string;
  invitation_path: string;
}

export interface DemoSeedCounts {
  users: number;
  providers: number;
  clients: number;
  addresses: number;
  applications: number;
  documents: number;
  events: number;
}

export interface DemoCredential {
  email: string;
  full_name: string;
  role: UserRole;
  password: string;
}

export interface DemoSeedResult {
  created: DemoSeedCounts;
  updated: DemoSeedCounts;
  credentials: DemoCredential[];
}

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
  available_actions: string[];
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

export interface PaymentDocument {
  id: string;
  client_id: string;
  file_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  payment_date: string | null;
  amount: string | null;
  comment: string | null;
  created_at: string;
  uploaded_by: string | null;
  download_url: string;
}

export interface PublicAddress {
  id: string;
  provider_id: string;
  provider_name: string;
  full_address: string;
  room_number: string | null;
  price_6m: string;
  price_11m: string;
  selected_price: string;
  correspondence_price: string | null;
  fns_number: number | null;
  fns_city: string | null;
  is_available: boolean;
  publication_status: string;
  created_at: string;
  updated_at: string;
}

export interface ProviderConnectionRequestCreate {
  company_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone?: string | null;
  city?: string | null;
  address_count?: number | null;
  comment?: string | null;
}

export interface ProviderConnectionRequest {
  id: string;
  company_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string | null;
  city: string | null;
  address_count: number | null;
  comment: string | null;
  status: "new" | "reviewing" | "invited" | "rejected";
  admin_comment: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type PublicClientApplicationCreate =
  | {
      type: "initial_registration";
      address_id: string;
      planned_client_name: string;
      contact_name: string;
      contact_email: string;
      contact_phone?: string | null;
      password: string;
      term_months: 6 | 11;
      has_correspondence_service: boolean;
      contract_city?: string | null;
    }
  | {
      type: "address_change";
      address_id: string;
      client_inn: string;
      contact_name: string;
      contact_email: string;
      contact_phone?: string | null;
      password: string;
      term_months: 6 | 11;
      notice_period: NoticePeriod;
      has_correspondence_service: boolean;
      contract_city?: string | null;
    };

export interface PublicClientApplicationResult {
  user: CurrentUser;
  application: Application;
}

export interface ApplicationActionResult {
  application_id: string;
  status: ApplicationStatus;
  available_actions: string[];
}

export interface ApplicationDocument {
  id: string;
  application_id: string;
  kind: DocumentFileKind;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  uploaded_by: string | null;
  download_url: string;
}

export interface ApplicationDocumentUploadResult {
  application_id: string;
  application_status: ApplicationStatus;
  document: ApplicationDocument;
}

export interface ApplicationDocumentModeration {
  application_id: string;
  status: ApplicationStatus;
  requires_manual_review: boolean;
  available_actions: string[];
  documents: ApplicationDocument[];
}

export interface ClientApplicationEvent {
  id: string;
  application_id: string;
  kind:
    | "created"
    | "status_changed"
    | "comment_added"
    | "document_uploaded"
    | "document_approved"
    | "correction_requested"
    | "dispute_opened"
    | "cancelled";
  audience: "client" | "owner" | "admin";
  title: string;
  message: string;
  payload: Record<string, unknown>;
  is_read: boolean;
  created_by: string | null;
  created_at: string;
  read_at: string | null;
}

export interface AppNotification extends ClientApplicationEvent {
  application_status: ApplicationStatus;
  application_title: string;
}

export interface NotificationInbox {
  unread_count: number;
  items: AppNotification[];
}

export interface ClientApplication {
  id: string;
  type: ApplicationType;
  status: ApplicationStatus;
  provider_id: string;
  address_id: string;
  provider_name: string;
  full_address: string;
  room_number: string | null;
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
  selected_price: string;
  correspondence_price: string | null;
  events: ClientApplicationEvent[];
  created_at: string;
  updated_at: string;
}

export interface OwnerAddress {
  id: string;
  provider_id: string;
  full_address: string;
  room_number: string | null;
  cadastral_number: string;
  price_6m: string;
  price_11m: string;
  correspondence_price: string | null;
  fns_number: number | null;
  fns_city: string | null;
  is_available: boolean;
  publication_status: "draft" | "moderation" | "published" | "rejected" | "archived";
  created_at: string;
  updated_at: string;
}

export interface OwnerApplication {
  id: string;
  type: ApplicationType;
  status: ApplicationStatus;
  provider_id: string;
  address_id: string;
  full_address: string;
  room_number: string | null;
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
  selected_price: string;
  correspondence_price: string | null;
  available_actions: string[];
  events: ClientApplicationEvent[];
  created_at: string;
  updated_at: string;
}

export interface OwnerDashboard {
  provider: Provider;
  addresses: OwnerAddress[];
  applications: OwnerApplication[];
}
