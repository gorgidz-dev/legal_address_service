import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// База API. Переопределяется на сборке:
///   flutter run --dart-define=API_BASE=http://10.0.2.2:8000/api/v1
const String kApiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'https://uradres.net/api/v1',
);

/// Происхождение сервера — для абсолютизации относительных URL (фото).
final String kApiOrigin = Uri.parse(kApiBase).replace(path: '').toString();

String absoluteUrl(String url) =>
    url.startsWith('http') ? url : '$kApiOrigin$url';

/// HTTP-клиент с bearer-авторизацией.
///
/// Токены — в Keychain/Keystore через flutter_secure_storage (требование
/// docs/mobile-api.md). На 401 один раз пробуем refresh и повторяем запрос;
/// не вышло — чистим сессию, роутер уведёт на экран входа.
class ApiClient {
  ApiClient() {
    dio = Dio(BaseOptions(
      baseUrl: kApiBase,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
      headers: {'Accept': 'application/json'},
    ));
    dio.interceptors.add(QueuedInterceptorsWrapper(
      onRequest: (options, handler) {
        final token = _accessToken;
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
      onError: (error, handler) async {
        final response = error.response;
        final alreadyRetried = error.requestOptions.extra['retried'] == true;
        if (response?.statusCode != 401 || alreadyRetried) {
          handler.next(error);
          return;
        }
        final refreshed = await _tryRefresh();
        if (!refreshed) {
          await clearSession();
          handler.next(error);
          return;
        }
        try {
          final request = error.requestOptions..extra['retried'] = true;
          request.headers['Authorization'] = 'Bearer $_accessToken';
          handler.resolve(await dio.fetch(request));
        } on DioException catch (retryError) {
          handler.next(retryError);
        }
      },
    ));
  }

  late final Dio dio;

  static const _storage = FlutterSecureStorage();
  static const _kAccess = 'access_token';
  static const _kRefresh = 'refresh_token';

  String? _accessToken;
  String? _refreshToken;

  bool get hasSession => _accessToken != null && _accessToken!.isNotEmpty;

  /// Поднимаем токены из защищённого хранилища на старте приложения.
  Future<void> restore() async {
    _accessToken = await _storage.read(key: _kAccess);
    _refreshToken = await _storage.read(key: _kRefresh);
  }

  Future<void> saveSession({
    required String accessToken,
    required String refreshToken,
  }) async {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
    await _storage.write(key: _kAccess, value: accessToken);
    await _storage.write(key: _kRefresh, value: refreshToken);
  }

  Future<void> clearSession() async {
    _accessToken = null;
    _refreshToken = null;
    await _storage.delete(key: _kAccess);
    await _storage.delete(key: _kRefresh);
  }

  /// Refresh одноразовый (бэк отзывает токен при использовании), поэтому
  /// на успех сразу сохраняем новую пару.
  Future<bool> _tryRefresh() async {
    final refresh = _refreshToken;
    if (refresh == null || refresh.isEmpty) return false;
    try {
      // Отдельный Dio без интерсепторов: refresh не должен зациклиться.
      final bare = Dio(BaseOptions(baseUrl: kApiBase));
      final response = await bare.post<Map<String, dynamic>>(
        '/mobile/auth/refresh',
        data: {'refresh_token': refresh},
      );
      final session = response.data?['session'] as Map<String, dynamic>?;
      if (session == null) return false;
      await saveSession(
        accessToken: session['access_token'] as String,
        refreshToken: session['refresh_token'] as String? ?? '',
      );
      return true;
    } on DioException {
      return false;
    }
  }
}

/// Человеческое сообщение об ошибке для показа в интерфейсе.
String apiErrorMessage(Object error) {
  if (error is DioException) {
    final body = error.response?.data;
    // Версионированный API отвечает {"error": {"code", "message"}}
    // (app/api_errors.py); {"detail": "..."} — старый формат, терпим и его.
    // Раньше читался только detail, и понятные тексты сервера («оплата в
    // тестовом режиме», «банк не отвечает») подменялись общей фразой.
    if (body is Map) {
      final errorObj = body['error'];
      if (errorObj is Map && errorObj['message'] is String) {
        return errorObj['message'] as String;
      }
      if (body['detail'] is String) {
        return body['detail'] as String;
      }
    }
    return switch (error.type) {
      DioExceptionType.connectionTimeout ||
      DioExceptionType.receiveTimeout ||
      DioExceptionType.connectionError =>
        'Нет соединения с сервером. Проверьте интернет.',
      _ => 'Не получилось выполнить запрос. Попробуйте ещё раз.',
    };
  }
  return 'Что-то пошло не так. Попробуйте ещё раз.';
}
