import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:provider/provider.dart';
import '../models/zone.dart';
import '../models/prediction.dart';
import '../services/api_service.dart';
import '../services/websocket_service.dart';
import '../theme/ciro_theme.dart';
import 'prediction_screen.dart';

/// Home screen — card-based dashboard showing all 8 zones sorted by risk.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _api = ApiService();
  final Map<String, ZonePrediction> _predictions = {};
  bool _loading = true;
  bool _hasError = false;

  @override
  void initState() {
    super.initState();
    _loadAllPredictions();
  }

  Future<void> _loadAllPredictions() async {
    setState(() {
      _loading = true;
      _hasError = false;
    });

    int successCount = 0;
    for (final zone in CiroZone.allZones) {
      final prediction = await _api.getPrediction(zone.id);
      if (prediction != null) {
        _predictions[zone.id] = prediction;
        successCount++;
      }
    }

    setState(() {
      _loading = false;
      _hasError = successCount == 0;
    });
  }

  /// Get zones sorted by highest combined risk
  List<CiroZone> get _sortedZones {
    final zones = List<CiroZone>.from(CiroZone.allZones);
    zones.sort((a, b) {
      final predA = _predictions[a.id];
      final predB = _predictions[b.id];
      final riskA = predA != null
          ? (predA.summary.peakFloodRisk + predA.summary.peakHeatRisk)
          : 0.0;
      final riskB = predB != null
          ? (predB.summary.peakFloodRisk + predB.summary.peakHeatRisk)
          : 0.0;
      return riskB.compareTo(riskA);
    });
    return zones;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CiroTheme.bg,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader(),
            Expanded(
              child: _loading
                  ? _buildLoadingState()
                  : _hasError
                      ? _buildErrorState()
                      : _buildZoneCards(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    final ws = Provider.of<WebSocketService>(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'CIRO',
                style: TextStyle(
                  color: CiroTheme.accent,
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.5,
                ),
              ),
              const SizedBox(width: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: ws.isConnected
                      ? CiroTheme.green.withOpacity(0.15)
                      : CiroTheme.red.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: ws.isConnected
                        ? CiroTheme.green.withOpacity(0.4)
                        : CiroTheme.red.withOpacity(0.4),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: ws.isConnected ? CiroTheme.green : CiroTheme.red,
                      ),
                    ),
                    const SizedBox(width: 5),
                    Text(
                      ws.isConnected ? 'LIVE' : 'OFFLINE',
                      style: TextStyle(
                        color: ws.isConnected ? CiroTheme.green : CiroTheme.red,
                        fontSize: 9,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.refresh_rounded, color: CiroTheme.textMuted, size: 22),
                onPressed: _loadAllPredictions,
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'Crisis Intelligence & Response',
            style: TextStyle(color: CiroTheme.textMuted, fontSize: 12),
          ),
          const SizedBox(height: 12),
          // Stats row
          if (!_loading && !_hasError) _buildQuickStats(),
        ],
      ),
    );
  }

  Widget _buildQuickStats() {
    int criticalCount = 0;
    int highCount = 0;
    for (final pred in _predictions.values) {
      final level = pred.summary.overallAlertLevel.toUpperCase();
      if (level == 'CRITICAL') criticalCount++;
      else if (level == 'HIGH') highCount++;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: CiroTheme.border),
      ),
      child: Row(
        children: [
          _quickStat('${_predictions.length}', 'Zones Active', CiroTheme.green),
          _divider(),
          _quickStat('$criticalCount', 'Critical', CiroTheme.red),
          _divider(),
          _quickStat('$highCount', 'High Risk', CiroTheme.yellow),
          _divider(),
          _quickStat('30d', 'Forecast', CiroTheme.blue),
        ],
      ),
    );
  }

  Widget _quickStat(String value, String label, Color color) {
    return Expanded(
      child: Column(
        children: [
          Text(value, style: TextStyle(color: color, fontSize: 16, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 9)),
        ],
      ),
    );
  }

  Widget _divider() {
    return Container(width: 1, height: 28, color: CiroTheme.border);
  }

  Widget _buildLoadingState() {
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      itemCount: 8,
      itemBuilder: (context, index) => _buildSkeletonCard(),
    );
  }

  Widget _buildSkeletonCard() {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: CiroTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(width: 120, height: 14, decoration: BoxDecoration(color: CiroTheme.border, borderRadius: BorderRadius.circular(4))),
          const SizedBox(height: 8),
          Container(width: 80, height: 10, decoration: BoxDecoration(color: CiroTheme.border, borderRadius: BorderRadius.circular(4))),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(child: Container(height: 40, decoration: BoxDecoration(color: CiroTheme.border, borderRadius: BorderRadius.circular(6)))),
              const SizedBox(width: 8),
              Expanded(child: Container(height: 40, decoration: BoxDecoration(color: CiroTheme.border, borderRadius: BorderRadius.circular(6)))),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.cloud_off_rounded, color: CiroTheme.textMuted, size: 56),
            const SizedBox(height: 16),
            const Text(
              'Unable to connect to CIRO backend',
              style: TextStyle(color: CiroTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            const Text(
              'Make sure the backend is running at localhost:8000',
              style: TextStyle(color: CiroTheme.textMuted, fontSize: 13),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _loadAllPredictions,
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Retry'),
              style: ElevatedButton.styleFrom(
                backgroundColor: CiroTheme.accent,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildZoneCards() {
    final zones = _sortedZones;
    return RefreshIndicator(
      onRefresh: _loadAllPredictions,
      color: CiroTheme.accent,
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
        itemCount: zones.length,
        itemBuilder: (context, index) {
          final zone = zones[index];
          final prediction = _predictions[zone.id];
          return _ZoneRiskCard(
            zone: zone,
            prediction: prediction,
            onTap: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => PredictionScreen(zone: zone)),
              );
            },
          );
        },
      ),
    );
  }
}

/// Individual zone risk card with gradient border for high-risk zones.
class _ZoneRiskCard extends StatelessWidget {
  final CiroZone zone;
  final ZonePrediction? prediction;
  final VoidCallback onTap;

  const _ZoneRiskCard({
    required this.zone,
    required this.prediction,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final pred = prediction;
    final maxRisk = pred != null
        ? (pred.summary.peakFloodRisk > pred.summary.peakHeatRisk
            ? pred.summary.peakFloodRisk
            : pred.summary.peakHeatRisk)
        : 0.0;
    final isHighRisk = maxRisk >= 0.6;
    final alertLevel = pred?.summary.overallAlertLevel ?? 'NONE';
    final alertColor = CiroTheme.alertColor(alertLevel);

    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          gradient: isHighRisk
              ? LinearGradient(
                  colors: [
                    alertColor.withOpacity(0.4),
                    alertColor.withOpacity(0.1),
                    CiroTheme.border.withOpacity(0.3),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                )
              : null,
          border: isHighRisk ? null : Border.all(color: CiroTheme.border),
        ),
        child: Container(
          margin: isHighRisk ? const EdgeInsets.all(1.5) : EdgeInsets.zero,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: CiroTheme.surface,
            borderRadius: BorderRadius.circular(isHighRisk ? 12.5 : 14),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Top row: zone name + alert badge
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          zone.name,
                          style: const TextStyle(
                            color: CiroTheme.textPrimary,
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${zone.province} • Elev ${zone.elevationM}m',
                          style: const TextStyle(
                            color: CiroTheme.textMuted,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  _buildAlertBadge(alertLevel, alertColor),
                ],
              ),
              const SizedBox(height: 14),

              // Risk bars + sparkline
              Row(
                children: [
                  // Risk percentages
                  Expanded(
                    flex: 3,
                    child: Column(
                      children: [
                        _riskBar('Flood', pred?.summary.peakFloodRisk ?? 0, CiroTheme.blue),
                        const SizedBox(height: 8),
                        _riskBar('Heat', pred?.summary.peakHeatRisk ?? 0, CiroTheme.accent),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Sparkline
                  Expanded(
                    flex: 2,
                    child: SizedBox(
                      height: 44,
                      child: pred != null
                          ? _buildSparkline(pred.predictions)
                          : Container(
                              decoration: BoxDecoration(
                                color: CiroTheme.border.withOpacity(0.3),
                                borderRadius: BorderRadius.circular(6),
                              ),
                            ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),

              // Next danger day info
              if (pred != null) _buildNextDangerDay(pred),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAlertBadge(String level, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Text(
        level,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w800,
          letterSpacing: 0.3,
        ),
      ),
    );
  }

  Widget _riskBar(String label, double risk, Color color) {
    final percent = (risk * 100).toInt();
    return Row(
      children: [
        SizedBox(
          width: 36,
          child: Text(
            label,
            style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w500),
          ),
        ),
        Expanded(
          child: Container(
            height: 6,
            decoration: BoxDecoration(
              color: CiroTheme.border.withOpacity(0.4),
              borderRadius: BorderRadius.circular(3),
            ),
            child: FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: risk.clamp(0.0, 1.0),
              child: Container(
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(3),
                  boxShadow: risk > 0.6
                      ? [BoxShadow(color: color.withOpacity(0.4), blurRadius: 4)]
                      : null,
                ),
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 32,
          child: Text(
            '$percent%',
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w700,
              fontFamily: 'monospace',
            ),
            textAlign: TextAlign.right,
          ),
        ),
      ],
    );
  }

  Widget _buildSparkline(List<DayPrediction> predictions) {
    if (predictions.isEmpty) return const SizedBox.shrink();

    final spots = predictions.map((p) {
      return FlSpot(p.day.toDouble(), (p.floodRisk + p.heatstrokeRisk) / 2);
    }).toList();

    return LineChart(
      LineChartData(
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        minX: 1,
        maxX: 30,
        minY: 0,
        maxY: 1,
        lineTouchData: const LineTouchData(enabled: false),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: CiroTheme.accent.withOpacity(0.8),
            barWidth: 1.5,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: CiroTheme.accent.withOpacity(0.08),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNextDangerDay(ZonePrediction pred) {
    // Find next high-risk day
    DayPrediction? nextDanger;
    for (final day in pred.predictions) {
      if (day.floodRisk >= 0.6 || day.heatstrokeRisk >= 0.6) {
        nextDanger = day;
        break;
      }
    }

    if (nextDanger == null) {
      return Row(
        children: [
          Icon(Icons.check_circle_outline_rounded, color: CiroTheme.green, size: 14),
          const SizedBox(width: 6),
          const Text(
            'No high-risk days in 30-day forecast',
            style: TextStyle(color: CiroTheme.green, fontSize: 11),
          ),
        ],
      );
    }

    final dangerType = nextDanger.floodRisk > nextDanger.heatstrokeRisk ? 'Flood' : 'Heat';
    final dangerIcon = dangerType == 'Flood' ? '🌊' : '🔥';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: CiroTheme.red.withOpacity(0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: CiroTheme.red.withOpacity(0.15)),
      ),
      child: Row(
        children: [
          Text(dangerIcon, style: const TextStyle(fontSize: 12)),
          const SizedBox(width: 6),
          Text(
            'Next danger: Day ${nextDanger.day}',
            style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 11, fontWeight: FontWeight.w600),
          ),
          const SizedBox(width: 6),
          Text(
            '• $dangerType ${(((dangerType == 'Flood' ? nextDanger.floodRisk : nextDanger.heatstrokeRisk) * 100).toInt())}%',
            style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 11),
          ),
          const Spacer(),
          const Icon(Icons.chevron_right_rounded, color: CiroTheme.textMuted, size: 16),
        ],
      ),
    );
  }
}
