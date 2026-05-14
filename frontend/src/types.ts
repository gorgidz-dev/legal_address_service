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

export interface UserSessionInfo {
  id: string;
  created_at: string;
  expires_at: string;
  refresh_expires_at: string | null;
  last_refreshed_at: string | null;
  last_seen_at: string | null;
  session_type: string | null;
  device_name: string | null;
  user_agent: string | null;
  ip_address: string | null;
  is_current: boolean;
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

export type PaymentStatus =
  | "pending"
  | "awaiting_user"
  | "succeeded"
  | "failed"
  | "expired"
  | "cancelled"
  | "refund_requested"
  | "refunded";

export type PaymentProvider = "cdek_pay" | "manual_invoice";
export type PaymentPayerType = "individual" | "juridical";

export interface Payment {
  id: string;
  application_id: string;
  provider: PaymentProvider;
  payer_type: PaymentPayerType;
  status: PaymentStatus;
  amount_kopeks: number;
  currency: string;
  pay_for: string;
  qr_link: string | null;
  qr_image_base64: string | null;
  cdek_access_key: string | null;
  cdek_order_id: number | null;
  cdek_payment_id: number | null;
  expires_at: string | null;
  paid_at: string | null;
  refunded_at: string | null;
  created_at: string;
  updated_at: string;
}

export type AddressPublicationStatus =
  | "draft"
  | "moderation"
  | "published"
  | "rejected"
  | "archived";

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
  publication_status: AddressPublicationStatus;
  published_at: string | null;
  moderation_comment: string | null;
  moderated_by: string | null;
  moderated_at: string | null;
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

export type AddressPhotoModerationStatus = "pending" | "approved" | "rejected";

export interface AddressPhoto {
  id: string;
  address_id: string;
  url: string;
  content_type: string;
  width: number;
  height: number;
  is_main: boolean;
  sort_order: number;
}

export interface AddressPhotoAdmin {
  id: string;
  address_id: string;
  url: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  width: number;
  height: number;
  moderation_status: AddressPhotoModerationStatus;
  moderation_comment: string | null;
  moderated_by: string | null;
  moderated_at: string | null;
  is_main: boolean;
  sort_order: number;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
}

export type PublicAddressServiceKind =
  | "guarantee_letter"
  | "lease_agreement"
  | "owner_confirmation"
  | "door_sign"
  | "mail_reception"
  | "fns_visit_photo"
  | "phone_answering"
  | "visitor_reception";

export interface AddressServiceAdmin {
  id: string;
  kind: PublicAddressServiceKind | string;
  price: string;
  is_active: boolean;
}

export interface PublicAddressService {
  id: string;
  kind: PublicAddressServiceKind | string;
  price: string;
  is_active: boolean;
}

export interface PublicAddress {
  id: string;
  provider_id: string;
  provider_name: string;
  full_address: string;
  room_number: string | null;
  description: string | null;
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
  photos: AddressPhoto[];
  main_photo_url: string | null;
  services: PublicAddressService[];
}

export interface AddressChat {
  id: string;
  address_id: string;
  address_full: string;
  provider_name: string;
  client_user_id: string;
  client_email: string;
  last_message_at: string | null;
  created_at: string;
}

export interface AddressChatMessage {
  id: string;
  chat_id: string;
  author_user_id: string;
  body: string;
  created_at: string;
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

export type OwnerConnectionRequestStatus = "new" | "reviewing" | "invited" | "rejected";

export interface ProviderConnectionRequest {
  id: string;
  company_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string | null;
  city: string | null;
  address_count: number | null;
  comment: string | null;
  status: OwnerConnectionRequestStatus;
  admin_comment: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  invitation_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProviderConnectionRequestStatusUpdate {
  status: "reviewing" | "rejected";
  admin_comment?: string | null;
}

export interface ProviderConnectionRequestApprove {
  code: string;
  short_name: string;
  full_name: string;
  admin_comment?: string | null;
}

export interface ProviderConnectionRequestApproveResult {
  request: ProviderConnectionRequest;
  provider_id: string;
  invitation_id: string;
  invitation_token: string;
  invitation_path: string;
  invitation_expires_at: string;
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
      payer_type?: PaymentPayerType;
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

export type NotificationLinkType = "application" | "chat";
export type NotificationSource = "application_event" | "user_notification";

export interface AppNotification {
  id: string;
  kind: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
  link_type: NotificationLinkType | null;
  link_id: string | null;
  application_id: string | null;
  application_status: ApplicationStatus | null;
  application_title: string | null;
  source: NotificationSource;
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
  description?: string | null;
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
