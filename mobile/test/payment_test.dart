import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uradres_mobile/api/client.dart';
import 'package:uradres_mobile/models/payment.dart';
import 'package:uradres_mobile/widgets/sbp_pay_button.dart';

DioException _httpError(int status, Object body) {
  final request = RequestOptions(path: '/payments/initiate');
  return DioException(
    requestOptions: request,
    response: Response(requestOptions: request, statusCode: status, data: body),
    type: DioExceptionType.badResponse,
  );
}

void main() {
  group('apiErrorMessage', () {
    test('читает текст из формата API {"error": {"message"}}', () {
      // Раньше читался только detail — и покупатель видел общую фразу вместо
      // «Онлайн-оплата работает в тестовом режиме…».
      final error = _httpError(403, {
        'error': {'code': 'forbidden', 'message': 'Онлайн-оплата в тестовом режиме'},
      });
      expect(apiErrorMessage(error), 'Онлайн-оплата в тестовом режиме');
    });

    test('терпит старый формат {"detail": "..."}', () {
      expect(apiErrorMessage(_httpError(409, {'detail': 'Конфликт'})), 'Конфликт');
    });

    test('без тела — общая фраза, а не исключение', () {
      expect(apiErrorMessage(_httpError(500, 'oops')), isNotEmpty);
    });
  });

  group('Payment', () {
    Map<String, dynamic> json({
      String status = 'awaiting_user',
      String? providerStatus,
      DateTime? expiresAt,
    }) =>
        {
          'id': 'p1',
          'provider': 'tbank',
          'status': status,
          'amount_kopeks': 3000000,
          'payment_url': 'https://pay.tbank.ru/new/abc',
          'provider_status': providerStatus,
          'expires_at': expiresAt?.toUtc().toIso8601String(),
        };

    test('разбирает ответ PaymentRead', () {
      final payment = Payment.fromJson(json());
      expect(payment.amountKopeks, 3000000);
      expect(payment.paymentUrl, 'https://pay.tbank.ru/new/abc');
      expect(payment.isOpen, isTrue);
      expect(payment.isPaid, isFalse);
    });

    test('«банк обрабатывает» — только пока ссылка жива', () {
      final future = DateTime.now().add(const Duration(hours: 1));
      final past = DateTime.now().subtract(const Duration(hours: 1));
      expect(
        Payment.fromJson(json(providerStatus: 'AUTHORIZED', expiresAt: future))
            .isProcessingAtBank,
        isTrue,
      );
      // Зависшая после срока операция: бэкенд закроет её сам, кнопка нужна.
      expect(
        Payment.fromJson(json(providerStatus: 'AUTHORIZED', expiresAt: past))
            .isProcessingAtBank,
        isFalse,
      );
      expect(
        Payment.fromJson(json(providerStatus: 'FORM_SHOWED', expiresAt: future))
            .isProcessingAtBank,
        isFalse,
      );
    });
  });

  testWidgets('кнопка СБП: фирменный фон, «Оплатить» и знак НСПК', (tester) async {
    var taps = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: SbpPayButton(onPressed: () => taps++)),
    ));
    await tester.pump();

    expect(find.text('Оплатить'), findsOneWidget);
    expect(find.byType(SvgPicture), findsOneWidget);
    final material = tester.widget<Material>(
      find.descendant(of: find.byType(SbpPayButton), matching: find.byType(Material)).first,
    );
    expect(material.color, const Color(0xFF1D1346));
    expect(tester.getSize(find.byType(SbpPayButton)).height, greaterThanOrEqualTo(44));
    expect(find.bySemanticsLabel('Оплатить через СБП'), findsOneWidget);

    await tester.tap(find.byType(SbpPayButton));
    expect(taps, 1);
  });

  testWidgets('в загрузке кнопка не нажимается повторно', (tester) async {
    var taps = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: SbpPayButton(busy: true, onPressed: () => taps++)),
    ));
    await tester.tap(find.byType(SbpPayButton));
    expect(taps, 0);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
