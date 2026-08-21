import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../api/client.dart';
import '../api/repositories.dart';
import '../models/address.dart';
import '../theme/tokens.dart';
import '../widgets/ds.dart';

/// Каталог — главный экран до входа. Артборд «01 · Каталог» канваса.
class CatalogScreen extends StatefulWidget {
  const CatalogScreen({super.key, required this.catalog});

  final CatalogRepository catalog;

  @override
  State<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends State<CatalogScreen> {
  final _searchController = TextEditingController();

  AddressSearchPage? _page;
  Object? _error;
  bool _loading = true;

  int _termMonths = 11;
  int? _priceLt;
  bool _withMail = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await widget.catalog.search(
        query: _searchController.text.trim(),
        correspondence: _withMail ? true : null,
        priceLt: _priceLt,
        termMonths: _termMonths,
      );
      if (!mounted) return;
      setState(() {
        _page = page;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: DsColors.pageBg,
      body: SafeArea(
        child: RefreshIndicator(
          color: DsColors.indigo500,
          onRefresh: _load,
          child: ListView(
            padding: EdgeInsets.zero,
            children: [
              _topNav(context),
              _hero(),
              _promises(),
              _stats(),
              _search(),
              _chips(),
              const SizedBox(height: 14),
              ..._results(),
              const SizedBox(height: 28),
            ],
          ),
        ),
      ),
    );
  }

  Widget _topNav(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: const BoxDecoration(
        color: DsColors.surface,
        border: Border(bottom: BorderSide(color: DsColors.borderSoft)),
      ),
      child: Row(
        children: [
          Container(
            width: 30,
            height: 30,
            decoration: BoxDecoration(
              gradient: DsColors.logoGradient,
              borderRadius: BorderRadius.circular(9),
            ),
            child: const Icon(Icons.place_outlined, size: 17, color: Colors.white),
          ),
          const SizedBox(width: 9),
          Text.rich(
            TextSpan(
              text: 'uradres',
              style: DsText.headingMd.copyWith(fontWeight: FontWeight.w800),
              children: [
                TextSpan(
                  text: '.net',
                  style: TextStyle(color: DsColors.indigo500),
                ),
              ],
            ),
          ),
          const Spacer(),
          DsButton(
            label: 'Войти',
            kind: DsButtonKind.ghost,
            onPressed: () => context.push('/login'),
          ),
        ],
      ),
    );
  }

  Widget _hero() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 26, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Маркетплейс юридических адресов.', style: DsText.displayXl),
          Text(
            'За 1 день.',
            style: DsText.displayXl.copyWith(color: DsColors.indigo500),
          ),
          const SizedBox(height: 14),
          Text(
            'Проверенные собственники, готовый комплект документов '
            'с гарантийным письмом и выпиской ЕГРН.',
            style: DsText.body.copyWith(
              fontSize: 15,
              color: DsColors.textMuted,
              height: 1.55,
            ),
          ),
        ],
      ),
    );
  }

  Widget _promises() {
    const promises = [
      (Icons.verified_user_outlined, 'Возврат средств при отказе налоговой'),
      (Icons.sync_outlined, 'Замена адреса без доплат'),
      (Icons.task_outlined, 'Документы соответствуют требованиям ФНС'),
    ];
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 0),
      child: Column(
        children: [
          for (final (icon, text) in promises)
            Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
              decoration: BoxDecoration(
                color: DsColors.surface,
                borderRadius: BorderRadius.circular(DsRadii.pill),
                border: Border.all(color: DsColors.slate200),
              ),
              child: Row(
                children: [
                  Icon(icon, size: 18, color: DsColors.indigo500),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      text,
                      style: DsText.body.copyWith(fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _stats() {
    const stats = [
      ('26', 'Адресов в каталоге'),
      ('10', 'ИФНС в каталоге'),
      ('10', 'Городов'),
      ('6 и 11', 'Месяцев аренды'),
    ];
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 22),
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: Color(0xFFEEF0F4)),
          bottom: BorderSide(color: Color(0xFFEEF0F4)),
        ),
      ),
      child: GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        childAspectRatio: 3.4,
        mainAxisSpacing: 12,
        crossAxisSpacing: 20,
        children: [
          for (final (number, label) in stats)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  number,
                  style: DsText.displayMd.copyWith(fontSize: 26, height: 1),
                ),
                const SizedBox(height: 6),
                Text(label.toUpperCase(), style: DsText.label),
              ],
            ),
        ],
      ),
    );
  }

  Widget _search() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 0),
      child: TextField(
        controller: _searchController,
        style: DsText.body,
        textInputAction: TextInputAction.search,
        onSubmitted: (_) => _load(),
        decoration: InputDecoration(
          hintText: 'По адресу или ИФНС',
          hintStyle: DsText.body.copyWith(color: DsColors.slate400),
          prefixIcon:
              const Icon(Icons.search, size: 20, color: DsColors.slate400),
          filled: true,
          fillColor: DsColors.surface,
          isDense: true,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(DsRadii.input),
            borderSide: const BorderSide(color: DsColors.slate200),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(DsRadii.input),
            borderSide: const BorderSide(color: DsColors.indigo500, width: 1.5),
          ),
        ),
      ),
    );
  }

  Widget _chips() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          DsChip(
            label: 'Дешевле 20 000 ₽',
            selected: _priceLt == 20000,
            onTap: () {
              setState(() => _priceLt = _priceLt == 20000 ? null : 20000);
              _load();
            },
          ),
          DsChip(
            label: 'Дешевле 30 000 ₽',
            selected: _priceLt == 30000,
            onTap: () {
              setState(() => _priceLt = _priceLt == 30000 ? null : 30000);
              _load();
            },
          ),
          DsChip(
            label: 'С почтой',
            selected: _withMail,
            onTap: () {
              setState(() => _withMail = !_withMail);
              _load();
            },
          ),
        ],
      ),
    );
  }

  List<Widget> _results() {
    if (_loading) return const [ListState.loading()];
    if (_error != null) {
      return [ListState.error(apiErrorMessage(_error!), onRetry: _load)];
    }
    final page = _page;
    if (page == null || page.items.isEmpty) {
      return const [ListState.empty('По этим фильтрам адресов не нашлось.')];
    }
    return [
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text.rich(
          TextSpan(
            text: 'Найдено ',
            style: DsText.muted,
            children: [
              TextSpan(
                text: '${page.total}',
                style: DsText.bodySm.copyWith(fontWeight: FontWeight.w700),
              ),
              const TextSpan(text: ' адресов'),
            ],
          ),
        ),
      ),
      const SizedBox(height: 12),
      for (final address in page.items)
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
          child: _AddressCard(
            address: address,
            termMonths: _termMonths,
            onTermChanged: (term) {
              setState(() => _termMonths = term);
              _load();
            },
            onOpen: () => context.push('/address/${address.id}'),
          ),
        ),
    ];
  }
}

class _AddressCard extends StatelessWidget {
  const _AddressCard({
    required this.address,
    required this.termMonths,
    required this.onTermChanged,
    required this.onOpen,
  });

  final PublicAddress address;
  final int termMonths;
  final ValueChanged<int> onTermChanged;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    return DsCard(
      onTap: onOpen,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _media(),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(address.fullAddress, style: DsText.headingMd),
                const SizedBox(height: 6),
                Text(
                  [
                    if (address.roomNumber != null) 'офис ${address.roomNumber}',
                    if (address.fnsNumber != null) 'ИФНС № ${address.fnsNumber}',
                  ].join(' · '),
                  style: DsText.muted,
                ),
                const SizedBox(height: 10),
                DsSegmented(
                  options: const ['11 мес.', '6 мес.'],
                  selectedIndex: termMonths == 11 ? 0 : 1,
                  onChanged: (index) => onTermChanged(index == 0 ? 11 : 6),
                ),
                if (address.correspondencePrice != null) ...[
                  const SizedBox(height: 10),
                  Text(
                    '+ почта ${formatRub(address.correspondencePrice!)}/мес',
                    style: DsText.bodySm,
                  ),
                ],
                const SizedBox(height: 12),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            formatRub(address.priceFor(termMonths)),
                            style: DsText.price,
                          ),
                          const SizedBox(height: 2),
                          Text('за $termMonths мес.', style: DsText.caption),
                        ],
                      ),
                    ),
                    DsButton(label: 'Оформить заявку', onPressed: onOpen),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _media() {
    final photoUrl = address.mainPhotoUrl;
    final photoCount = address.photos.length;
    return SizedBox(
      height: 190,
      width: double.infinity,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (photoUrl != null)
            Image.network(
              absoluteUrl(photoUrl),
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) =>
                  InitialsTile(initials: address.initials),
            )
          else
            InitialsTile(initials: address.initials),
          if (photoCount > 1)
            Positioned(
              right: 10,
              bottom: 10,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xB80B0A2E),
                  borderRadius: BorderRadius.circular(DsRadii.pill),
                ),
                child: Text(
                  '+${photoCount - 1} фото',
                  style: DsText.label.copyWith(color: Colors.white),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
