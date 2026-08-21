import 'package:flutter_test/flutter_test.dart';
import 'package:uradres_mobile/models/application.dart';

/// Карта статусов — перенос frontend/src/status.ts. Тест держит инварианты
/// переноса: полнота основной цепочки, фолбэк на неизвестное значение.
void main() {
  test('основная цепочка маркетплейса покрыта картой статусов', () {
    // Цепочка из CLAUDE.md; enum-значения бэка стабильны.
    const chain = [
      'draft',
      'awaiting_payment',
      'paid',
      'admin_review',
      'assigned_to_owner',
      'accepted_by_owner',
      'documents_preparing',
      'documents_uploaded',
      'documents_review',
      'ready_for_client',
      'completed',
    ];
    for (final status in chain) {
      expect(kStatusMeta.containsKey(status), isTrue,
          reason: 'нет подписи для $status');
    }
  });

  test('боковые и легаси-статусы тоже покрыты', () {
    const side = [
      'needs_client_fix', 'documents_revision', 'rejected_by_owner',
      'cancelled', 'dispute', 'refund_pending', 'refunded',
      // легаси
      'guarantee_issued', 'awaiting_contract', 'contract_signed',
      'active', 'expired', 'terminated',
    ];
    for (final status in side) {
      expect(kStatusMeta.containsKey(status), isTrue,
          reason: 'нет подписи для $status');
    }
  });

  test('неизвестный статус показывает сырой код, а не пустоту', () {
    final meta = statusMeta('brand_new_status');
    expect(meta.label, 'brand_new_status');
    expect(meta.tone, StatusTone.neutral);

    expect(statusMeta(null).label, '—');
  });

  test('подписи дословно совпадают с status.ts (выборочно)', () {
    expect(kStatusMeta['awaiting_payment']!.label, 'Ожидает оплату');
    expect(kStatusMeta['documents_preparing']!.label, 'Готовятся документы');
    expect(kStatusMeta['ready_for_client']!.label, 'Готова к выдаче');
    expect(kStatusMeta['awaiting_payment']!.tone, StatusTone.brand);
    expect(kStatusMeta['dispute']!.tone, StatusTone.danger);
  });
}
