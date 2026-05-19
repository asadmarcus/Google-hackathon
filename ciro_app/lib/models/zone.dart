/// CIRO Zone model — 8 monitored zones across Pakistan.
/// No map dependency — pure data model.
class CiroZone {
  final String id;
  final String name;
  final double lat;
  final double lng;
  final String province;
  final int elevationM;
  final double drainageCapacity;
  final int populationDensity;

  const CiroZone({
    required this.id,
    required this.name,
    required this.lat,
    required this.lng,
    required this.province,
    required this.elevationM,
    required this.drainageCapacity,
    required this.populationDensity,
  });

  static const List<CiroZone> allZones = [
    CiroZone(id: 'islamabad-g10', name: 'G-10, Islamabad', lat: 33.6844, lng: 73.0479, province: 'Federal', elevationM: 507, drainageCapacity: 0.6, populationDensity: 2850),
    CiroZone(id: 'lahore-city', name: 'Lahore City', lat: 31.5204, lng: 74.3587, province: 'Punjab', elevationM: 217, drainageCapacity: 0.4, populationDensity: 6300),
    CiroZone(id: 'karachi-south', name: 'Karachi South', lat: 24.8607, lng: 67.0011, province: 'Sindh', elevationM: 10, drainageCapacity: 0.3, populationDensity: 14000),
    CiroZone(id: 'peshawar-city', name: 'Peshawar City', lat: 34.0151, lng: 71.5249, province: 'KPK', elevationM: 331, drainageCapacity: 0.5, populationDensity: 3200),
    CiroZone(id: 'multan-city', name: 'Multan City', lat: 30.1575, lng: 71.5249, province: 'Punjab', elevationM: 122, drainageCapacity: 0.35, populationDensity: 4500),
    CiroZone(id: 'jacobabad-city', name: 'Jacobabad City', lat: 28.2810, lng: 68.4376, province: 'Sindh', elevationM: 55, drainageCapacity: 0.25, populationDensity: 2100),
    CiroZone(id: 'sukkur-city', name: 'Sukkur City', lat: 27.7052, lng: 68.8574, province: 'Sindh', elevationM: 66, drainageCapacity: 0.3, populationDensity: 3800),
    CiroZone(id: 'quetta-city', name: 'Quetta City', lat: 30.1798, lng: 66.9750, province: 'Balochistan', elevationM: 1680, drainageCapacity: 0.35, populationDensity: 1800),
  ];
}
