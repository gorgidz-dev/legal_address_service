/// Пользователь, календарь аренды и чаты — мелкие модели одного файла.
library;

class CurrentUser {
  const CurrentUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.role,
    required this.emailVerified,
  });

  final String id;
  final String email;
  final String fullName;
  final String role;
  final bool emailVerified;

  /// Инициалы для аватара в шапке кабинета.
  String get initials {
    final words = fullName.trim().split(RegExp(r'\s+'));
    if (words.isEmpty || words.first.isEmpty) {
      return email.isNotEmpty ? email[0].toUpperCase() : '·';
    }
    final first = words.first[0];
    final second = words.length > 1 ? words[1][0] : '';
    return (first + second).toUpperCase();
  }

  factory CurrentUser.fromJson(Map<String, dynamic> json) => CurrentUser(
        id: json['id'] as String,
        email: json['email'] as String? ?? '',
        fullName: json['full_name'] as String? ?? '',
        role: json['role'] as String? ?? 'client',
        emailVerified: json['email_verified'] as bool? ?? true,
      );
}

/// Сессия мобильного входа — POST /mobile/auth/login | /refresh.
class MobileSession {
  const MobileSession({
    required this.accessToken,
    required this.refreshToken,
  });

  final String accessToken;
  final String refreshToken;

  factory MobileSession.fromJson(Map<String, dynamic> json) => MobileSession(
        accessToken: json['access_token'] as String,
        refreshToken: json['refresh_token'] as String? ?? '',
      );
}

/// Строка календаря аренды — GET /client/lease-calendar.
/// renewal_status: active | due_soon | overdue (см. app/schemas/registry.py).
class LeaseCalendarItem {
  const LeaseCalendarItem({
    required this.applicationId,
    required this.contractNumber,
    required this.addressFull,
    required this.counterparty,
    required this.startDate,
    required this.endDate,
    required this.daysUntilRenewal,
    required this.renewalStatus,
    required this.priceTotal,
  });

  final String applicationId;
  final String contractNumber;
  final String addressFull;
  final String counterparty;
  final DateTime startDate;
  final DateTime endDate;
  final int daysUntilRenewal;
  final String renewalStatus;
  final String priceTotal;

  factory LeaseCalendarItem.fromJson(Map<String, dynamic> json) =>
      LeaseCalendarItem(
        applicationId: json['application_id'] as String,
        contractNumber: json['contract_number'] as String? ?? '',
        addressFull: json['address_full'] as String? ?? '',
        counterparty: json['counterparty'] as String? ?? '',
        startDate: DateTime.parse(json['start_date'] as String),
        endDate: DateTime.parse(json['end_date'] as String),
        daysUntilRenewal: json['days_until_renewal'] as int? ?? 0,
        renewalStatus: json['renewal_status'] as String? ?? 'active',
        priceTotal: (json['price_total'] ?? '0').toString(),
      );
}

/// Чат по адресу — GET /chats.
class ChatSummary {
  const ChatSummary({
    required this.id,
    required this.addressFull,
    required this.providerName,
    required this.lastMessageAt,
    required this.unreadCount,
  });

  final String id;
  final String addressFull;
  final String providerName;
  final DateTime? lastMessageAt;
  final int unreadCount;

  factory ChatSummary.fromJson(Map<String, dynamic> json) => ChatSummary(
        id: json['id'] as String,
        addressFull: json['address_full'] as String? ?? '',
        providerName: json['provider_name'] as String? ?? '',
        lastMessageAt: json['last_message_at'] == null
            ? null
            : DateTime.parse(json['last_message_at'] as String),
        unreadCount: json['unread_count'] as int? ?? 0,
      );
}

/// Сообщение чата — GET /chats/{id}/messages.
/// author_side: client | owner | staff — от него зависят сторона и подпись.
class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.authorSide,
    required this.authorName,
    required this.body,
    required this.createdAt,
    required this.attachments,
  });

  final String id;
  final String authorSide;
  final String authorName;
  final String body;
  final DateTime createdAt;
  final List<ChatAttachment> attachments;

  bool get isMine => authorSide == 'client';

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
        id: json['id'] as String,
        authorSide: json['author_side'] as String? ?? 'client',
        authorName: json['author_name'] as String? ?? '',
        body: json['body'] as String? ?? '',
        createdAt: DateTime.parse(json['created_at'] as String),
        attachments: [
          for (final attachment in (json['attachments'] as List? ?? const []))
            ChatAttachment.fromJson(attachment as Map<String, dynamic>),
        ],
      );
}

class ChatAttachment {
  const ChatAttachment({required this.filename, required this.sizeBytes});

  final String filename;
  final int? sizeBytes;

  factory ChatAttachment.fromJson(Map<String, dynamic> json) => ChatAttachment(
        filename: (json['original_filename'] ?? json['filename'] ?? 'файл')
            .toString(),
        sizeBytes: json['size_bytes'] as int?,
      );
}
