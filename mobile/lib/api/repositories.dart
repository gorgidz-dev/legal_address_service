import 'package:flutter/foundation.dart';

import '../models/address.dart';
import '../models/application.dart';
import '../models/misc.dart';
import 'client.dart';

/// Каталог — публичные эндпоинты, токен не нужен.
class CatalogRepository {
  CatalogRepository(this._api);

  final ApiClient _api;

  Future<AddressSearchPage> search({
    String? query,
    bool? correspondence,
    int? priceLt,
    int termMonths = 11,
    int page = 1,
  }) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/marketplace/addresses/search',
      queryParameters: {
        if (query != null && query.isNotEmpty) 'q': query,
        'correspondence': ?correspondence,
        'price_lt': ?priceLt,
        'term_months': termMonths,
        'page': page,
        'page_size': 24,
      },
    );
    return AddressSearchPage.fromJson(response.data ?? const {});
  }

  Future<PublicAddress> detail(String id) async {
    final response =
        await _api.dio.get<Map<String, dynamic>>('/marketplace/addresses/$id');
    return PublicAddress.fromJson(response.data ?? const {});
  }

  /// Публичная заявка. Бэк создаёт аккаунт клиента этим же действием,
  /// поэтому пароль обязателен; занятый e-mail — 409.
  Future<void> createApplication({
    required String addressId,
    required String companyName,
    required String contactName,
    required String contactEmail,
    String? contactPhone,
    required String password,
    required int termMonths,
    required bool hasCorrespondence,
    required bool isAddressChange,
    String? clientInn,
  }) async {
    await _api.dio.post<Map<String, dynamic>>(
      '/marketplace/applications',
      data: {
        'type': isAddressChange ? 'address_change' : 'initial_registration',
        'address_id': addressId,
        'contact_name': contactName,
        'contact_email': contactEmail,
        if (contactPhone != null && contactPhone.isNotEmpty)
          'contact_phone': contactPhone,
        'password': password,
        'term_months': termMonths,
        'has_correspondence_service': hasCorrespondence,
        if (!isAddressChange) 'planned_client_name': companyName,
        if (isAddressChange) 'client_inn': clientInn,
      },
    );
  }
}

/// Кабинет клиента — всё под bearer.
class CabinetRepository {
  CabinetRepository(this._api);

  final ApiClient _api;

  Future<List<ClientApplication>> applications() async {
    final response = await _api.dio.get<List<dynamic>>('/client/applications');
    return [
      for (final item in response.data ?? const [])
        ClientApplication.fromJson(item as Map<String, dynamic>),
    ];
  }

  Future<List<LeaseCalendarItem>> leaseCalendar() async {
    final response =
        await _api.dio.get<List<dynamic>>('/client/lease-calendar');
    return [
      for (final item in response.data ?? const [])
        LeaseCalendarItem.fromJson(item as Map<String, dynamic>),
    ];
  }

  Future<List<ChatSummary>> chats() async {
    final response = await _api.dio.get<List<dynamic>>('/chats');
    return [
      for (final item in response.data ?? const [])
        ChatSummary.fromJson(item as Map<String, dynamic>),
    ];
  }

  Future<List<ChatMessage>> messages(String chatId) async {
    final response =
        await _api.dio.get<List<dynamic>>('/chats/$chatId/messages');
    return [
      for (final item in response.data ?? const [])
        ChatMessage.fromJson(item as Map<String, dynamic>),
    ];
  }
}

/// Состояние авторизации. Роутер слушает его и переключает стек
/// публичная часть ↔ кабинет.
class AuthState extends ChangeNotifier {
  AuthState(this._api);

  final ApiClient _api;

  CurrentUser? user;
  bool restoring = true;

  bool get isAuthenticated => user != null;

  /// На старте: есть сохранённые токены — пробуем /auth/me.
  Future<void> restore() async {
    await _api.restore();
    if (_api.hasSession) {
      try {
        final response =
            await _api.dio.get<Map<String, dynamic>>('/auth/me');
        final data = response.data ?? const {};
        final payload = data['user'] is Map<String, dynamic>
            ? data['user'] as Map<String, dynamic>
            : data;
        user = CurrentUser.fromJson(payload);
      } catch (_) {
        // Токены умерли — интерсептор уже почистил сессию.
        user = null;
      }
    }
    restoring = false;
    notifyListeners();
  }

  Future<void> login({required String email, required String password}) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/mobile/auth/login',
      data: {
        'email': email,
        'password': password,
        'device_name': 'Uradres Mobile',
      },
    );
    final data = response.data ?? const {};
    final session =
        MobileSession.fromJson(data['session'] as Map<String, dynamic>);
    await _api.saveSession(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
    );
    user = CurrentUser.fromJson(data['user'] as Map<String, dynamic>);
    notifyListeners();
  }

  Future<void> logout() async {
    await _api.clearSession();
    user = null;
    notifyListeners();
  }
}
