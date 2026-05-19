import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../models/zone.dart';
import '../models/prediction.dart';
import '../services/api_service.dart';
import '../theme/ciro_theme.dart';

/// 30-day detection/prediction view for a selected zone.
/// Shows: AI risk summary, current conditions, satellite status,
/// interactive chart + day details.
class PredictionScreen extends StatefulWidget {
  final CiroZone zone;
  const PredictionScreen({super.key, required this.zone});

  @override
  State<PredictionScreen> createState() => _PredictionScreenState();
}

class _PredictionScreenState extends State<PredictionScreen> {
  final ApiService _api = ApiService();
  ZonePrediction? _prediction;
  Map<String, dynamic>? _satelliteData;
  bool _loading = true;
  bool _loadingSatellite = true;
  int? _selectedDay;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _loading = true);
    final results = await Future.wait([
      _api.getPrediction(widget.zone.id),
      _api.getSatelliteAnalysis(widget.zone.id),
    ]);
    setState(() {
      _prediction = results[0] as ZonePrediction?;
      _satelliteData = results[1] as Map<String, dynamic>?;
      _loading = false;
      _loadingSatellite = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CiroTheme.bg,
      appBar: AppBar(
        backgroundColor: CiroTheme.surface,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded, color: CiroTheme.textPrimary),
          onPressed: () => Navigator.pop(context),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.zone.name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: CiroTheme.textPrimary)),
            Text('${widget.zone.province} • 30-Day Forecast', style: const TextStyle(fontSize: 11, color: CiroTheme.textMuted)),
          ],
        ),
        actions: [
          if (_prediction != null)
            Container(
              margin: const EdgeInsets.only(right: 12),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: CiroTheme.alertColor(_prediction!.summary.overallAlertLevel).withOpacity(0.15),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: CiroTheme.alertColor(_prediction!.summary.overallAlertLevel).withOpacity(0.4)),
              ),
              child: Text(
                _prediction!.summary.overallAlertLevel,
                style: TextStyle(
                  color: CiroTheme.alertColor(_prediction!.summary.overallAlertLevel),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: CiroTheme.accent))
          : _prediction == null
              ? _buildError()
              : _buildContent(),
    );
  }

  Widget _buildError() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.cloud_off, color: CiroTheme.textMuted, size: 48),
          const SizedBox(height: 12),
          const Text('Failed to load prediction', style: TextStyle(color: CiroTheme.textMuted)),
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: _loadData,
            icon: const Icon(Icons.refresh_rounded, size: 18),
            label: const Text('Retry'),
            style: ElevatedButton.styleFrom(
              backgroundColor: CiroTheme.accent,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    final pred = _prediction!;
    final selected = _selectedDay != null
        ? pred.predictions.firstWhere((p) => p.day == _selectedDay, orElse: () => pred.predictions.first)
        : null;

    return RefreshIndicator(
      onRefresh: _loadData,
      color: CiroTheme.accent,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // AI Risk Summary (plain language)
          _buildRiskSummary(pred),
          const SizedBox(height: 16),

          // Current conditions / weather
          _buildCurrentConditions(pred),
          const SizedBox(height: 16),

          // Satellite analysis status
          _buildSatelliteStatus(),
          const SizedBox(height: 20),

          // Summary metric cards
          _buildSummaryRow(pred.summary),
          const SizedBox(height: 20),

          // 30-day chart
          _buildSectionTitle('30-DAY RISK FORECAST', 'Tap a bar for details'),
          const SizedBox(height: 10),
          Container(
            height: 200,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: CiroTheme.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: CiroTheme.border),
            ),
            child: _buildChart(pred.predictions),
          ),
          const SizedBox(height: 8),
          _buildLegend(),
          const SizedBox(height: 20),

          // Selected day detail
          if (selected != null) _buildDayDetail(selected),

          // Confidence indicator
          const SizedBox(height: 16),
          _buildConfidenceInfo(),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  /// AI-generated plain language risk summary
  Widget _buildRiskSummary(ZonePrediction pred) {
    final summary = pred.summary;
    final floodPercent = (summary.peakFloodRisk * 100).toInt();
    final heatPercent = (summary.peakHeatRisk * 100).toInt();

    // Generate plain-language summary
    String summaryText;
    if (summary.peakFloodRisk > summary.peakHeatRisk) {
      summaryText = 'Flood risk peaks on Day ${summary.peakFloodDay} at $floodPercent%. ';
      if (summary.peakFloodRisk >= 0.7) {
        summaryText += 'Expected heavy monsoon rainfall with potential river discharge exceeding normal levels. ';
      } else if (summary.peakFloodRisk >= 0.4) {
        summaryText += 'Moderate rainfall accumulation expected. Urban drainage may be strained. ';
      } else {
        summaryText += 'Low flood likelihood — standard seasonal patterns. ';
      }
      if (summary.peakHeatRisk >= 0.4) {
        summaryText += 'Heat risk also elevated at $heatPercent% on Day ${summary.peakHeatDay}.';
      }
    } else {
      summaryText = 'Heat risk peaks on Day ${summary.peakHeatDay} at $heatPercent%. ';
      if (summary.peakHeatRisk >= 0.7) {
        summaryText += 'Extreme temperatures expected, possible heatstroke conditions for vulnerable populations. ';
      } else if (summary.peakHeatRisk >= 0.4) {
        summaryText += 'Elevated temperatures with high humidity — stay hydrated. ';
      } else {
        summaryText += 'Manageable heat levels expected. ';
      }
      if (summary.peakFloodRisk >= 0.4) {
        summaryText += 'Flood risk also notable at $floodPercent% on Day ${summary.peakFloodDay}.';
      }
    }

    final alertColor = CiroTheme.alertColor(summary.overallAlertLevel);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: alertColor.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: alertColor.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.auto_awesome_rounded, color: alertColor, size: 16),
              const SizedBox(width: 8),
              Text(
                'Risk Assessment',
                style: TextStyle(color: alertColor, fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.3),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            summaryText,
            style: const TextStyle(
              color: CiroTheme.textPrimary,
              fontSize: 13,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  /// Current weather conditions (from first day prediction)
  Widget _buildCurrentConditions(ZonePrediction pred) {
    final today = pred.predictions.isNotEmpty ? pred.predictions.first : null;
    if (today == null) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CiroTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(Icons.cloud_rounded, color: CiroTheme.blue, size: 16),
              SizedBox(width: 8),
              Text(
                'Current Conditions',
                style: TextStyle(color: CiroTheme.textSecondary, fontSize: 12, fontWeight: FontWeight.w600),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _weatherItem('🌡️', '${today.expectedTempC.toInt()}°C', 'Temp'),
              _weatherItem('🌧️', '${today.expectedRainMm.toInt()}mm', 'Rain'),
              _weatherItem('💧', '${today.expectedHumidity.toInt()}%', 'Humidity'),
              _weatherItem('🌊', '${(today.floodRisk * 100).toInt()}%', 'Flood'),
              _weatherItem('🔥', '${(today.heatstrokeRisk * 100).toInt()}%', 'Heat'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _weatherItem(String emoji, String value, String label) {
    return Expanded(
      child: Column(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 18)),
          const SizedBox(height: 4),
          Text(
            value,
            style: const TextStyle(
              color: CiroTheme.textPrimary,
              fontSize: 14,
              fontWeight: FontWeight.w700,
              fontFamily: 'monospace',
            ),
          ),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 9)),
        ],
      ),
    );
  }

  /// Satellite analysis status from Agent 1
  Widget _buildSatelliteStatus() {
    final hasData = _satelliteData != null;
    final ndwi = _satelliteData?['ndwi_value'];
    final lastAnalyzed = _satelliteData?['analyzed_at'] ?? '';
    final status = _satelliteData?['status'] ?? 'unavailable';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: hasData ? CiroTheme.blue.withOpacity(0.3) : CiroTheme.border),
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: hasData ? CiroTheme.blue.withOpacity(0.1) : CiroTheme.border.withOpacity(0.3),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              Icons.satellite_alt_rounded,
              color: hasData ? CiroTheme.blue : CiroTheme.textMuted,
              size: 18,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Agent 1 — Satellite Analysis',
                  style: TextStyle(color: CiroTheme.textPrimary, fontSize: 12, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 3),
                Text(
                  hasData
                      ? 'NDWI: ${ndwi?.toStringAsFixed(3) ?? "N/A"} • $status'
                      : _loadingSatellite ? 'Loading...' : 'No satellite data available',
                  style: TextStyle(
                    color: hasData ? CiroTheme.blue : CiroTheme.textMuted,
                    fontSize: 11,
                  ),
                ),
                if (lastAnalyzed.isNotEmpty)
                  Text(
                    'Last: $lastAnalyzed',
                    style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10),
                  ),
              ],
            ),
          ),
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: hasData ? CiroTheme.green : CiroTheme.textMuted,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryRow(PredictionSummary summary) {
    return Row(
      children: [
        _summaryCard('Peak Flood', '${(summary.peakFloodRisk * 100).toInt()}%', 'Day ${summary.peakFloodDay}', CiroTheme.blue),
        const SizedBox(width: 8),
        _summaryCard('Peak Heat', '${(summary.peakHeatRisk * 100).toInt()}%', 'Day ${summary.peakHeatDay}', CiroTheme.accent),
        const SizedBox(width: 8),
        _summaryCard('⚠️ Days', '${summary.highFloodDays + summary.highHeatDays}', 'High risk', CiroTheme.red),
      ],
    );
  }

  Widget _summaryCard(String label, String value, String sub, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: CiroTheme.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withOpacity(0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(value, style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
            Text(sub, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10)),
          ],
        ),
      ),
    );
  }

  Widget _buildChart(List<DayPrediction> predictions) {
    return BarChart(
      BarChartData(
        barTouchData: BarTouchData(
          touchCallback: (event, response) {
            if (response != null && response.spot != null) {
              setState(() => _selectedDay = response.spot!.touchedBarGroupIndex + 1);
            }
          },
          touchTooltipData: BarTouchTooltipData(
            getTooltipItem: (group, groupIndex, rod, rodIndex) {
              final day = predictions[groupIndex];
              return BarTooltipItem(
                'Day ${day.day}\n${rodIndex == 0 ? 'Flood' : 'Heat'}: ${(rod.toY * 100).toInt()}%',
                const TextStyle(color: CiroTheme.textPrimary, fontSize: 11),
              );
            },
          ),
        ),
        titlesData: FlTitlesData(
          show: true,
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              getTitlesWidget: (value, meta) {
                final day = value.toInt() + 1;
                if (day % 5 == 0 || day == 1) {
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text('D$day', style: const TextStyle(color: CiroTheme.textMuted, fontSize: 9)),
                  );
                }
                return const SizedBox.shrink();
              },
            ),
          ),
          leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        borderData: FlBorderData(show: false),
        gridData: const FlGridData(show: false),
        barGroups: predictions.map((p) {
          return BarChartGroupData(
            x: p.day - 1,
            barRods: [
              BarChartRodData(
                toY: p.floodRisk,
                color: CiroTheme.blue,
                width: 4,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(2)),
              ),
              BarChartRodData(
                toY: p.heatstrokeRisk,
                color: CiroTheme.accent,
                width: 4,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(2)),
              ),
            ],
          );
        }).toList(),
      ),
    );
  }

  Widget _buildLegend() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _legendItem(CiroTheme.blue, 'Flood Risk'),
        const SizedBox(width: 20),
        _legendItem(CiroTheme.accent, 'Heat Risk'),
      ],
    );
  }

  Widget _legendItem(Color color, String label) {
    return Row(
      children: [
        Container(width: 12, height: 12, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3))),
        const SizedBox(width: 6),
        Text(label, style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 11)),
      ],
    );
  }

  Widget _buildDayDetail(DayPrediction day) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CiroTheme.accent.withOpacity(0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Day ${day.day}', style: const TextStyle(color: CiroTheme.accent, fontSize: 14, fontWeight: FontWeight.w700)),
              const SizedBox(width: 8),
              Text(day.date, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 12)),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: CiroTheme.alertColor(day.alertLevel).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(day.alertLevel, style: TextStyle(color: CiroTheme.alertColor(day.alertLevel), fontSize: 10, fontWeight: FontWeight.w700)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _detailItem('🌊 Flood', '${(day.floodRisk * 100).toInt()}%', CiroTheme.blue),
              _detailItem('🔥 Heat', '${(day.heatstrokeRisk * 100).toInt()}%', CiroTheme.accent),
              _detailItem('🌡️ Temp', '${day.expectedTempC.toInt()}°C', CiroTheme.textPrimary),
              _detailItem('🌧️ Rain', '${day.expectedRainMm.toInt()}mm', CiroTheme.blue),
              _detailItem('💧 Humid', '${day.expectedHumidity.toInt()}%', CiroTheme.textSecondary),
            ],
          ),
          const SizedBox(height: 10),
          Text(day.dominantFactor, style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 12)),
          const SizedBox(height: 4),
          Text(
            'Source: ${day.dataSource} • Confidence: ${day.confidence}',
            style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10),
          ),
        ],
      ),
    );
  }

  Widget _detailItem(String label, String value, Color color) {
    return Expanded(
      child: Column(
        children: [
          Text(value, style: TextStyle(color: color, fontSize: 16, fontWeight: FontWeight.w700, fontFamily: 'monospace')),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 9)),
        ],
      ),
    );
  }

  Widget _buildConfidenceInfo() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: CiroTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          Text('DATA SOURCES', style: TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w600, letterSpacing: 0.5)),
          SizedBox(height: 6),
          Text('Days 1-7: ECMWF/GFS weather model (high confidence)', style: TextStyle(color: CiroTheme.green, fontSize: 11)),
          Text('Days 8-16: Prophet + GloFAS blend (moderate confidence)', style: TextStyle(color: CiroTheme.yellow, fontSize: 11)),
          Text('Days 17-30: XGBoost ML forecast (lower confidence)', style: TextStyle(color: CiroTheme.textMuted, fontSize: 11)),
          SizedBox(height: 4),
          Text('Satellite NDWI data from Agent 1 boosts flood accuracy', style: TextStyle(color: CiroTheme.blue, fontSize: 11)),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(String title, String subtitle) {
    return Row(
      children: [
        Text(title, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w600, letterSpacing: 0.5)),
        const Spacer(),
        Text(subtitle, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10)),
      ],
    );
  }
}
