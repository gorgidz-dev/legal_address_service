import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../api/client.dart';
import '../api/repositories.dart';
import '../models/address.dart';
import '../models/application.dart';
import '../theme/tokens.dart';
import '../widgets/ds.dart';

/// Карточка адреса — артборд «02 · Карточка адреса».
class AddressScreen extends StatefulWidget {
  const AddressScreen({super.key, required this.catalog, required this.addressId});

  final CatalogRepository catalog;
  final String addressId;

  @override
  State<AddressScreen> createState() => _AddressScreenState();
}

class _AddressScreenState extends State<AddressScreen> {
  PublicAddress? _address;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final address = await widget.catalog.detail(widget.addressId);
      if (!mounted) return;
      setState(() => _address = address);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final address = _address;
    return Scaffold(
      backgroundColor: DsColors.pageBg,
      appBar: AppBar(
        backgroundColor: DsColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: BackButton(color: DsColors.text, onPressed: context.pop),
        title: Text('Каталог', style: DsText.headingSm),
        shape: const Border(bottom: BorderSide(color: DsColors.borderSoft)),
      ),
      body: _error != null
          ? ListState.error(apiErrorMessage(_error!), onRetry: _load)
          : address == null
              ? const ListState.loading()
              : _body(address),
      bottomNavigationBar: address == null
          ? null
          : Container(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
              decoration: const BoxDecoration(
                color: DsColors.surface,
                border: Border(top: BorderSide(color: DsColors.borderSoft)),
                boxShadow: DsShadows.raised,
              ),
              child: SafeArea(
                top: false,
                child: DsButton(
                  label: 'Оформить заявку',
                  expanded: true,
                  onPressed: () =>
                      context.push('/address/${address.id}/apply', extra: address),
                ),
              ),
            ),
    );
  }

  Widget _body(PublicAddress address) {
    return ListView(
      padding: EdgeInsets.zero,
      children: [
        _gallery(address),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(address.fullAddress, style: DsText.headingLg),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  if (address.fnsNumber != null)
                    ToneBadge(
                      label: 'ИФНС № ${address.fnsNumber}',
                      tone: StatusTone.brand,
                    ),
                  if (address.roomNumber != null)
                    ToneBadge(
                      label: address.roomNumber!,
                      tone: StatusTone.neutral,
                    ),
                  if (address.ratingAvg != null)
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.star, size: 15, color: DsColors.star),
                        const SizedBox(width: 4),
                        Text(
                          address.ratingAvg!.toStringAsFixed(1),
                          style: DsText.bodySm
                              .copyWith(fontWeight: FontWeight.w600),
                        ),
                        Text(
                          ' · ${address.ratingCount} отзывов',
                          style: DsText.muted,
                        ),
                      ],
                    ),
                ],
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 18, 16, 0),
          child: DsCard(
            child: Column(
              children: [
                _priceRow('6 месяцев', address.price6m, highlighted: false),
                const Divider(height: 1, color: Color(0xFFEEF0F4)),
                _priceRow('11 месяцев', address.price11m, highlighted: true),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 22, 16, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SectionLabel('Входит в стоимость'),
              const SizedBox(height: 12),
              for (final included in const [
                'Гарантийное письмо',
                'Выписка ЕГРН',
                'Договор аренды',
              ])
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Row(
                    children: [
                      const Icon(Icons.check,
                          size: 17, color: DsColors.successFg),
                      const SizedBox(width: 10),
                      Text(included, style: DsText.body),
                    ],
                  ),
                ),
              if (address.correspondencePrice != null)
                Container(
                  margin: const EdgeInsets.only(top: 4),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: DsColors.surface,
                    borderRadius: BorderRadius.circular(DsRadii.pill),
                    border: Border.all(color: DsColors.slate300),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.mail_outline,
                          size: 15, color: DsColors.textMuted),
                      const SizedBox(width: 7),
                      Text(
                        'Почтовое обслуживание — '
                        '${formatRub(address.correspondencePrice!)}/мес',
                        style: DsText.bodySm
                            .copyWith(color: DsColors.neutralFg),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        if (address.description != null && address.description!.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 22, 16, 0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionLabel('Об адресе'),
                const SizedBox(height: 10),
                Text(
                  address.description!,
                  style: DsText.bodySm.copyWith(color: DsColors.slate700),
                ),
              ],
            ),
          ),
        const SizedBox(height: 28),
      ],
    );
  }

  Widget _gallery(PublicAddress address) {
    final photos = address.photos;
    return SizedBox(
      height: 260,
      child: photos.isEmpty
          ? InitialsTile(initials: address.initials)
          : PageView.builder(
              itemCount: photos.length,
              itemBuilder: (_, index) => Image.network(
                absoluteUrl(photos[index].url),
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) =>
                    InitialsTile(initials: address.initials),
              ),
            ),
    );
  }

  Widget _priceRow(String term, String amount, {required bool highlighted}) {
    return Container(
      color: highlighted ? DsColors.brandBg : null,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Text(
            term,
            style: highlighted
                ? DsText.body.copyWith(
                    fontWeight: FontWeight.w600, color: DsColors.brandFg)
                : DsText.body.copyWith(color: DsColors.textMuted),
          ),
          if (highlighted) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: DsColors.indigo500,
                borderRadius: BorderRadius.circular(DsRadii.pill),
              ),
              child: Text(
                'ВЫГОДНО',
                style: DsText.label.copyWith(fontSize: 10, color: Colors.white),
              ),
            ),
          ],
          const Spacer(),
          Text(
            formatRub(amount),
            style: highlighted
                ? DsText.headingLg.copyWith(color: DsColors.indigo500)
                : DsText.headingMd,
          ),
        ],
      ),
    );
  }
}
