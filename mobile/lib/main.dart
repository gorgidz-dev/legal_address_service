import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'api/client.dart';
import 'api/repositories.dart';
import 'models/address.dart';
import 'models/application.dart';
import 'screens/address_screen.dart';
import 'screens/application_screen.dart';
import 'screens/cabinet/calendar_screen.dart';
import 'screens/cabinet/chats_screen.dart';
import 'screens/cabinet/request_detail_screen.dart';
import 'screens/cabinet/requests_screen.dart';
import 'screens/catalog_screen.dart';
import 'screens/login_screen.dart';
import 'theme/tokens.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('ru');

  final api = ApiClient();
  final auth = AuthState(api);
  // Не ждём restore до первого кадра: каталог публичный, а роутер сам
  // переключится, когда сессия поднимется.
  auth.restore();

  runApp(UradresApp(
    auth: auth,
    catalog: CatalogRepository(api),
    cabinet: CabinetRepository(api),
  ));
}

class UradresApp extends StatefulWidget {
  const UradresApp({
    super.key,
    required this.auth,
    required this.catalog,
    required this.cabinet,
  });

  final AuthState auth;
  final CatalogRepository catalog;
  final CabinetRepository cabinet;

  @override
  State<UradresApp> createState() => _UradresAppState();
}

class _UradresAppState extends State<UradresApp> {
  late final GoRouter _router = _buildRouter();

  GoRouter _buildRouter() {
    return GoRouter(
      initialLocation: '/',
      refreshListenable: widget.auth,
      redirect: (context, state) {
        final inCabinet = state.matchedLocation.startsWith('/cabinet');
        if (inCabinet && !widget.auth.isAuthenticated) return '/login';
        return null;
      },
      routes: [
        GoRoute(
          path: '/',
          builder: (_, _) => CatalogScreen(catalog: widget.catalog),
        ),
        GoRoute(
          path: '/login',
          builder: (_, _) => LoginScreen(auth: widget.auth),
        ),
        GoRoute(
          path: '/address/:id',
          builder: (_, state) => AddressScreen(
            catalog: widget.catalog,
            addressId: state.pathParameters['id']!,
          ),
          routes: [
            GoRoute(
              path: 'apply',
              builder: (_, state) => ApplicationScreen(
                catalog: widget.catalog,
                auth: widget.auth,
                address: state.extra! as PublicAddress,
              ),
            ),
          ],
        ),
        StatefulShellRoute.indexedStack(
          builder: (_, _, shell) => _CabinetShell(shell: shell),
          branches: [
            StatefulShellBranch(routes: [
              GoRoute(
                path: '/cabinet/requests',
                builder: (_, _) => RequestsScreen(
                  cabinet: widget.cabinet,
                  auth: widget.auth,
                ),
                routes: [
                  GoRoute(
                    path: ':id',
                    builder: (_, state) => RequestDetailScreen(
                      application: state.extra! as ClientApplication,
                    ),
                  ),
                ],
              ),
            ]),
            StatefulShellBranch(routes: [
              GoRoute(
                path: '/cabinet/calendar',
                builder: (_, _) => CalendarScreen(
                  cabinet: widget.cabinet,
                  auth: widget.auth,
                ),
              ),
            ]),
            StatefulShellBranch(routes: [
              GoRoute(
                path: '/cabinet/chats',
                builder: (_, _) => ChatsScreen(
                  cabinet: widget.cabinet,
                  auth: widget.auth,
                ),
              ),
            ]),
          ],
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Uradres',
      debugShowCheckedModeBanner: false,
      routerConfig: _router,
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: DsColors.pageBg,
        colorScheme: ColorScheme.fromSeed(
          seedColor: DsColors.indigo500,
          primary: DsColors.indigo500,
          surface: DsColors.surface,
        ),
        textTheme: GoogleFonts.interTextTheme(),
        splashFactory: InkRipple.splashFactory,
      ),
    );
  }
}

/// Оболочка кабинета: нижний таб-бар «Заявки · Календарь · Чаты» —
/// ровно три вкладки клиента из shell/navConfig.ts веба.
class _CabinetShell extends StatelessWidget {
  const _CabinetShell({required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context) {
    const items = [
      (Icons.folder_outlined, 'Заявки'),
      (Icons.calendar_today_outlined, 'Календарь'),
      (Icons.chat_bubble_outline, 'Чаты'),
    ];
    return Scaffold(
      body: shell,
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: DsColors.surface,
          border: Border(top: BorderSide(color: DsColors.borderSoft)),
        ),
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.only(top: 10, bottom: 6),
            child: Row(
              children: [
                for (var i = 0; i < items.length; i++)
                  Expanded(
                    child: GestureDetector(
                      onTap: () => shell.goBranch(
                        i,
                        initialLocation: i == shell.currentIndex,
                      ),
                      behavior: HitTestBehavior.opaque,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            items[i].$1,
                            size: 22,
                            color: i == shell.currentIndex
                                ? DsColors.indigo500
                                : DsColors.textMuted,
                          ),
                          const SizedBox(height: 4),
                          Text(
                            items[i].$2,
                            style: DsText.label.copyWith(
                              letterSpacing: 0,
                              color: i == shell.currentIndex
                                  ? DsColors.indigo500
                                  : DsColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
