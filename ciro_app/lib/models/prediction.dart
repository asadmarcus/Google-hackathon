class DayPrediction {
  final int day;
  final String date;
  final double floodRisk;
  final double heatstrokeRisk;
  final String dominantFactor;
  final double expectedTempC;
  final double expectedRainMm;
  final double expectedHumidity;
  final String alertLevel;
  final String confidence;
  final String dataSource;

  DayPrediction({
    required this.day,
    required this.date,
    required this.floodRisk,
    required this.heatstrokeRisk,
    required this.dominantFactor,
    required this.expectedTempC,
    required this.expectedRainMm,
    required this.expectedHumidity,
    required this.alertLevel,
    required this.confidence,
    required this.dataSource,
  });

  factory DayPrediction.fromJson(Map<String, dynamic> json) {
    return DayPrediction(
      day: json['day'] ?? 0,
      date: json['date'] ?? '',
      floodRisk: (json['flood_risk'] ?? 0).toDouble(),
      heatstrokeRisk: (json['heatstroke_risk'] ?? 0).toDouble(),
      dominantFactor: json['dominant_factor'] ?? '',
      expectedTempC: (json['expected_temp_c'] ?? 0).toDouble(),
      expectedRainMm: (json['expected_rain_mm'] ?? 0).toDouble(),
      expectedHumidity: (json['expected_humidity'] ?? 0).toDouble(),
      alertLevel: json['alert_level'] ?? 'NONE',
      confidence: json['confidence'] ?? 'low',
      dataSource: json['data_source'] ?? '',
    );
  }
}

class PredictionSummary {
  final int peakFloodDay;
  final double peakFloodRisk;
  final int peakHeatDay;
  final double peakHeatRisk;
  final double avgFloodRisk;
  final double avgHeatRisk;
  final int highFloodDays;
  final int highHeatDays;
  final String overallAlertLevel;

  PredictionSummary({
    required this.peakFloodDay,
    required this.peakFloodRisk,
    required this.peakHeatDay,
    required this.peakHeatRisk,
    required this.avgFloodRisk,
    required this.avgHeatRisk,
    required this.highFloodDays,
    required this.highHeatDays,
    required this.overallAlertLevel,
  });

  factory PredictionSummary.fromJson(Map<String, dynamic> json) {
    return PredictionSummary(
      peakFloodDay: json['peak_flood_day'] ?? 0,
      peakFloodRisk: (json['peak_flood_risk'] ?? 0).toDouble(),
      peakHeatDay: json['peak_heat_day'] ?? 0,
      peakHeatRisk: (json['peak_heat_risk'] ?? 0).toDouble(),
      avgFloodRisk: (json['avg_flood_risk'] ?? 0).toDouble(),
      avgHeatRisk: (json['avg_heat_risk'] ?? 0).toDouble(),
      highFloodDays: json['high_flood_days'] ?? 0,
      highHeatDays: json['high_heat_days'] ?? 0,
      overallAlertLevel: json['overall_alert_level'] ?? 'NONE',
    );
  }
}

class ZonePrediction {
  final String zoneId;
  final String zoneName;
  final String province;
  final String predictedAt;
  final List<DayPrediction> predictions;
  final PredictionSummary summary;

  ZonePrediction({
    required this.zoneId,
    required this.zoneName,
    required this.province,
    required this.predictedAt,
    required this.predictions,
    required this.summary,
  });

  factory ZonePrediction.fromJson(Map<String, dynamic> json) {
    return ZonePrediction(
      zoneId: json['zone_id'] ?? '',
      zoneName: json['zone_name'] ?? '',
      province: json['province'] ?? '',
      predictedAt: json['predicted_at'] ?? '',
      predictions: (json['predictions'] as List? ?? [])
          .map((p) => DayPrediction.fromJson(p))
          .toList(),
      summary: PredictionSummary.fromJson(json['summary'] ?? {}),
    );
  }
}
