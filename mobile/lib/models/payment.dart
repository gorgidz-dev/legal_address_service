/// Платёж по заявке — подмножество PaymentRead бэка (app/schemas/payment.py),
/// которое нужно экрану заявки.
class Payment {
  const Payment({
    required this.id,
    required this.provider,
    required this.status,
    required this.amountKopeks,
    this.paymentUrl,
    this.providerStatus,
    this.expiresAt,
  });

  final String id;

  /// tbank | cdek_pay | manual_invoice.
  final String provider;

  /// pending | awaiting_user | succeeded | failed | expired | cancelled |
  /// refund_requested | refunded.
  final String status;
  final int amountKopeks;

  /// Ссылка на платёжную форму Т-Банка. null — ссылку видеть нельзя
  /// (DEMO-терминал для не-тестировщика) или её ещё нет.
  final String? paymentUrl;
  final String? providerStatus;
  final DateTime? expiresAt;

  bool get isPaid => status == 'succeeded';
  bool get isOpen => status == 'awaiting_user' || status == 'pending';

  /// Статусы Т-Банка «деньги сейчас движутся» — вторую оплату не предлагаем,
  /// пока ссылка не протухла (то же правило, что в вебе, App.tsx).
  bool get isProcessingAtBank {
    const moving = {
      'PREAUTHORIZING',
      'AUTHORIZING',
      '3DS_CHECKED',
      'PAY_CHECKING',
      'AUTHORIZED',
      'CONFIRMING',
      'CONFIRM_CHECKING',
    };
    final expires = expiresAt;
    return provider == 'tbank' &&
        status == 'awaiting_user' &&
        moving.contains(providerStatus) &&
        (expires == null || expires.isAfter(DateTime.now()));
  }

  factory Payment.fromJson(Map<String, dynamic> json) => Payment(
        id: json['id'] as String,
        provider: json['provider'] as String? ?? '',
        status: json['status'] as String? ?? '',
        amountKopeks: (json['amount_kopeks'] as num?)?.toInt() ?? 0,
        paymentUrl: json['payment_url'] as String?,
        providerStatus: json['provider_status'] as String?,
        expiresAt: json['expires_at'] == null
            ? null
            : DateTime.tryParse(json['expires_at'] as String),
      );
}
