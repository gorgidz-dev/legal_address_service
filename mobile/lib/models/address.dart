/// Публичный адрес каталога — GET /marketplace/addresses/search и /{id}.
///
/// Цены приходят строками (Decimal сериализуется строкой), храним как есть
/// и форматируем на месте показа.
class AddressPhoto {
  const AddressPhoto({required this.url, required this.isMain});

  final String url;
  final bool isMain;

  factory AddressPhoto.fromJson(Map<String, dynamic> json) => AddressPhoto(
        url: json['url'] as String? ?? '',
        isMain: json['is_main'] as bool? ?? false,
      );
}

class AddressService {
  const AddressService({required this.name, required this.priceMonthly});

  final String name;
  final String? priceMonthly;

  factory AddressService.fromJson(Map<String, dynamic> json) => AddressService(
        name: (json['name'] ?? json['title'] ?? '').toString(),
        priceMonthly: json['price_monthly']?.toString() ??
            json['price']?.toString(),
      );
}

class PublicAddress {
  const PublicAddress({
    required this.id,
    required this.providerName,
    required this.fullAddress,
    required this.roomNumber,
    required this.description,
    required this.price6m,
    required this.price11m,
    required this.correspondencePrice,
    required this.fnsNumber,
    required this.fnsCity,
    required this.mainPhotoUrl,
    required this.photos,
    required this.services,
    required this.ratingAvg,
    required this.ratingCount,
  });

  final String id;
  final String providerName;
  final String fullAddress;
  final String? roomNumber;
  final String? description;
  final String price6m;
  final String price11m;
  final String? correspondencePrice;
  final int? fnsNumber;
  final String? fnsCity;
  final String? mainPhotoUrl;
  final List<AddressPhoto> photos;
  final List<AddressService> services;
  final double? ratingAvg;
  final int ratingCount;

  String priceFor(int termMonths) => termMonths == 6 ? price6m : price11m;

  /// Инициалы улицы для плитки-заглушки: первые буквы значимого слова
  /// («ул. Малышева» → «МА»), как фолбэк карточки в вебе.
  String get initials {
    final parts = fullAddress
        .split(RegExp(r'[,\s]+'))
        .where((word) =>
            word.length > 2 &&
            !RegExp(r'^(г|ул|д|стр|корп|пос|пр|обл|наб|лит|офис|пом)\.?$',
                    caseSensitive: false)
                .hasMatch(word))
        .toList();
    final source = parts.length > 1 ? parts[1] : (parts.isNotEmpty ? parts[0] : '·');
    return source.substring(0, source.length >= 2 ? 2 : source.length).toUpperCase();
  }

  factory PublicAddress.fromJson(Map<String, dynamic> json) => PublicAddress(
        id: json['id'] as String,
        providerName: json['provider_name'] as String? ?? '',
        fullAddress: json['full_address'] as String? ?? '',
        roomNumber: json['room_number'] as String?,
        description: json['description'] as String?,
        price6m: (json['price_6m'] ?? '0').toString(),
        price11m: (json['price_11m'] ?? '0').toString(),
        correspondencePrice: json['correspondence_price']?.toString(),
        fnsNumber: json['fns_number'] as int?,
        fnsCity: json['fns_city'] as String?,
        mainPhotoUrl: json['main_photo_url'] as String?,
        photos: [
          for (final photo in (json['photos'] as List? ?? const []))
            AddressPhoto.fromJson(photo as Map<String, dynamic>),
        ],
        services: [
          for (final service in (json['services'] as List? ?? const []))
            AddressService.fromJson(service as Map<String, dynamic>),
        ],
        ratingAvg: (json['rating_avg'] as num?)?.toDouble(),
        ratingCount: json['rating_count'] as int? ?? 0,
      );
}

class AddressSearchPage {
  const AddressSearchPage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
  });

  final List<PublicAddress> items;
  final int total;
  final int page;
  final int pageSize;

  factory AddressSearchPage.fromJson(Map<String, dynamic> json) =>
      AddressSearchPage(
        items: [
          for (final item in (json['items'] as List? ?? const []))
            PublicAddress.fromJson(item as Map<String, dynamic>),
        ],
        total: json['total'] as int? ?? 0,
        page: json['page'] as int? ?? 1,
        pageSize: json['page_size'] as int? ?? 24,
      );
}
