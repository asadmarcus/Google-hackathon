import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../theme/ciro_theme.dart';

/// AI Agents Pipeline screen.
/// Shows orchestrator runs, debate results, Agent 4 response actions, and logs.
/// No city selector, no individual debate/response buttons — only the full pipeline.
class AgentsScreen extends StatefulWidget {
  const AgentsScreen({super.key});

  @override
  State<AgentsScreen> createState() => _AgentsScreenState();
}

class _AgentsScreenState extends State<AgentsScreen> {
  final ApiService _api = ApiService();
  Map<String, dynamic>? _pipelineResult;
  List<dynamic>? _logs;
  Map<String, dynamic>? _selectedLog;
  bool _loadingPipeline = false;
  bool _loadingLogs = false;

  Future<void> _runPipeline() async {
    setState(() { _loadingPipeline = true; _pipelineResult = null; });
    final result = await _api.runOrchestrator();
    setState(() { _pipelineResult = result; _loadingPipeline = false; });
  }

  Future<void> _fetchLogs() async {
    setState(() { _loadingLogs = true; _logs = null; });
    final result = await _api.getOrchestratorStatus();
    // Fetch all logs
    try {
      final dio = ApiService().dio;
      final resp = await dio.get('/api/v1/orchestrator/logs');
      if (resp.statusCode == 200) {
        setState(() { _logs = resp.data['logs'] ?? []; });
      }
    } catch (e) {
      debugPrint('Logs fetch error: $e');
    }
    setState(() { _loadingLogs = false; });
  }

  Future<void> _fetchLogDetail(String runId) async {
    try {
      final dio = ApiService().dio;
      final resp = await dio.get('/api/v1/orchestrator/logs/$runId');
      if (resp.statusCode == 200) {
        setState(() { _selectedLog = resp.data; });
      }
    } catch (e) {
      debugPrint('Log detail error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CiroTheme.bg,
      appBar: AppBar(
        backgroundColor: CiroTheme.surface,
        elevation: 0,
        title: const Text('Orchestration Pipeline',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: CiroTheme.textPrimary)),
        actions: [
          _statusIndicator(),
          const SizedBox(width: 12),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Run pipeline button
          _buildRunButton(),
          const SizedBox(height: 16),

          // Pipeline result
          if (_loadingPipeline) _buildLoadingState('Evaluating zones, running debates, planning responses...'),
          if (_pipelineResult != null) ...[
            _buildSummaryCard(),
            const SizedBox(height: 14),
            if ((_pipelineResult!['agent4_responses'] as List?)?.isNotEmpty ?? false) ...[
              _buildSectionHeader('Response Actions'),
              const SizedBox(height: 8),
              ..._buildAgent4Responses(),
              const SizedBox(height: 14),
            ],
            if ((_pipelineResult!['agent4_queue'] as List?)?.isNotEmpty ?? false) ...[
              _buildSectionHeader('Zones Requiring Action'),
              const SizedBox(height: 8),
              ..._buildActionQueue(),
              const SizedBox(height: 14),
            ],
            if ((_pipelineResult!['full_results'] as List?)?.isNotEmpty ?? false) ...[
              _buildSectionHeader('Expert Debate Transcripts'),
              const SizedBox(height: 8),
              ..._buildDebateResults(),
            ],
          ],

          const SizedBox(height: 20),
          _buildLogsButton(),
          if (_loadingLogs) _buildLoadingState('Fetching orchestration logs...'),
          if (_logs != null) _buildLogsList(),
          if (_selectedLog != null) _buildLogDetail(),
        ],
      ),
    );
  }

  Widget _statusIndicator() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: CiroTheme.green.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: CiroTheme.green.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 6, height: 6, decoration: BoxDecoration(color: CiroTheme.green, borderRadius: BorderRadius.circular(3))),
          const SizedBox(width: 6),
          const Text('Active', style: TextStyle(color: CiroTheme.green, fontSize: 10, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _buildRunButton() {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: _loadingPipeline ? null : _runPipeline,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 18),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [CiroTheme.accent.withOpacity(0.15), CiroTheme.accent.withOpacity(0.05)],
            ),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: CiroTheme.accent.withOpacity(0.3)),
          ),
          child: Column(
            children: [
              if (_loadingPipeline)
                const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2, color: CiroTheme.accent))
              else
                const Icon(Icons.play_arrow_rounded, color: CiroTheme.accent, size: 28),
              const SizedBox(height: 8),
              const Text('Run Full Pipeline', style: TextStyle(color: CiroTheme.accent, fontSize: 14, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(
                'Predict all zones  ·  Debate high-risk  ·  Plan response  ·  Simulate',
                style: TextStyle(color: CiroTheme.textMuted, fontSize: 11),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSummaryCard() {
    final summary = _pipelineResult!['summary'] as Map<String, dynamic>? ?? {};
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
            children: [
              const Icon(Icons.analytics_outlined, color: CiroTheme.textSecondary, size: 16),
              const SizedBox(width: 8),
              const Text('Pipeline Summary', style: TextStyle(color: CiroTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w600)),
              const Spacer(),
              Text('${summary['duration_seconds'] ?? 0}s', style: const TextStyle(color: CiroTheme.textMuted, fontSize: 11, fontFamily: 'monospace')),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _metricTile('Evaluated', '${summary['total_zones_evaluated'] ?? 0}', CiroTheme.textPrimary),
              _metricTile('High Risk', '${summary['zones_above_threshold'] ?? 0}', CiroTheme.yellow),
              _metricTile('Debated', '${summary['zones_debated'] ?? 0}', CiroTheme.purple),
              _metricTile('Responded', '${summary['zones_responded'] ?? 0}', CiroTheme.accent),
            ],
          ),
        ],
      ),
    );
  }

  Widget _metricTile(String label, String value, Color color) {
    return Expanded(
      child: Column(
        children: [
          Text(value, style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 9, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }

  // ─── Agent 4 Responses ─────────────────────────────────────────

  List<Widget> _buildAgent4Responses() {
    final responses = (_pipelineResult!['agent4_responses'] as List?) ?? [];
    return responses.map<Widget>((resp) {
      final actions = (resp['actions'] as List?) ?? [];
      final simulation = resp['simulation'] as Map<String, dynamic>? ?? {};
      final narrative = resp['narrative'] ?? '';
      final urgency = resp['urgency'] ?? '';
      final zoneName = resp['zone_name'] ?? '';

      final urgColor = urgency == 'ACT_NOW' ? CiroTheme.red : urgency == 'PREPARE' ? CiroTheme.yellow : CiroTheme.green;

      return Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: CiroTheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: urgColor.withOpacity(0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              children: [
                Expanded(child: Text(zoneName, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w700))),
                _urgencyBadge(urgency, urgColor),
              ],
            ),
            const SizedBox(height: 10),

            // Narrative
            if (narrative.isNotEmpty)
              Text(narrative, style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 12, height: 1.6)),
            const SizedBox(height: 12),

            // Actions list
            if (actions.isNotEmpty) ...[
              Text('${actions.length} Planned Actions', style: TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w600, letterSpacing: 0.5)),
              const SizedBox(height: 8),
              ...actions.map<Widget>((a) => _buildActionItem(a)),
            ],

            // Simulation
            if (simulation.isNotEmpty) ...[
              const SizedBox(height: 12),
              _buildSimulationRow(simulation),
            ],
          ],
        ),
      );
    }).toList();
  }

  Widget _buildActionItem(Map<String, dynamic> action) {
    final category = action['category'] ?? '';
    final desc = action['description'] ?? '';
    final priority = action['priority'] ?? '';
    final agency = action['responsible_agency'] ?? '';

    final priorityColor = priority == 'IMMEDIATE' ? CiroTheme.red : priority == 'WITHIN_6H' ? CiroTheme.yellow : CiroTheme.green;

    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: CiroTheme.bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: CiroTheme.border.withOpacity(0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(color: CiroTheme.accent.withOpacity(0.1), borderRadius: BorderRadius.circular(4)),
                child: Text(category, style: const TextStyle(color: CiroTheme.accent, fontSize: 9, fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(color: priorityColor.withOpacity(0.1), borderRadius: BorderRadius.circular(3)),
                child: Text(priority, style: TextStyle(color: priorityColor, fontSize: 8, fontWeight: FontWeight.w700)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(desc, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 11, height: 1.4)),
          if (agency.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text(agency, style: TextStyle(color: CiroTheme.blue.withOpacity(0.7), fontSize: 10)),
            ),
        ],
      ),
    );
  }

  Widget _buildSimulationRow(Map<String, dynamic> sim) {
    final before = sim['before'] as Map<String, dynamic>? ?? {};
    final after = sim['after'] as Map<String, dynamic>? ?? {};
    final effectiveness = ((sim['effectiveness_score'] ?? 0) * 100).toInt();

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CiroTheme.bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: CiroTheme.green.withOpacity(0.2)),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Simulation Result', style: TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w600)),
              Text('$effectiveness% effective', style: TextStyle(color: CiroTheme.green, fontSize: 12, fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(child: _simMetric('Evacuated', '${after['population_evacuated'] ?? 0}')),
              Expanded(child: _simMetric('Shelters', '${after['shelters_activated'] ?? 0}')),
              Expanded(child: _simMetric('Medical', '${after['medical_units_deployed'] ?? 0}')),
              Expanded(child: _simMetric('Lives Saved', '${after['estimated_lives_saved'] ?? 0}')),
            ],
          ),
        ],
      ),
    );
  }

  Widget _simMetric(String label, String value) {
    return Column(
      children: [
        Text(value, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w700, fontFamily: 'monospace')),
        Text(label, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 8)),
      ],
    );
  }

  // ─── Action Queue ──────────────────────────────────────────────

  List<Widget> _buildActionQueue() {
    final queue = (_pipelineResult!['agent4_queue'] as List?) ?? [];
    return queue.map<Widget>((zone) {
      final urgency = zone['urgency'] ?? '';
      final urgColor = urgency == 'ACT_NOW' ? CiroTheme.red : urgency == 'PREPARE' ? CiroTheme.yellow : CiroTheme.green;
      final prob = ((zone['primary_risk_probability'] ?? 0) * 100).toStringAsFixed(0);

      return Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: CiroTheme.surface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: urgColor.withOpacity(0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(zone['zone_name'] ?? '', style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w700))),
                _urgencyBadge(urgency, urgColor),
                const SizedBox(width: 8),
                Text('$prob%', style: TextStyle(color: urgColor, fontSize: 16, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
              ],
            ),
            const SizedBox(height: 6),
            Text(zone['verdict'] ?? '', style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 11, height: 1.5)),
          ],
        ),
      );
    }).toList();
  }

  // ─── Debate Results ────────────────────────────────────────────

  List<Widget> _buildDebateResults() {
    final results = (_pipelineResult!['full_results'] as List?) ?? [];
    return results.map<Widget>((result) {
      final zoneName = result['zone_name'] ?? '';
      final personas = (result['personas'] as List?) ?? [];
      final consensus = result['consensus'] as Map<String, dynamic>? ?? {};

      return Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: CiroTheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: CiroTheme.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(zoneName, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            // Personas
            ...personas.map<Widget>((p) => _buildPersonaItem(p)),
            // Consensus
            if (consensus.isNotEmpty) ...[
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: CiroTheme.accent.withOpacity(0.04),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: CiroTheme.accent.withOpacity(0.2)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Consensus', style: TextStyle(color: CiroTheme.accent, fontSize: 10, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text(consensus['verdict'] ?? '', style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 12, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 4),
                    Text(consensus['rationale'] ?? '', style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 11, height: 1.5)),
                  ],
                ),
              ),
            ],
          ],
        ),
      );
    }).toList();
  }

  Widget _buildPersonaItem(Map<String, dynamic> p) {
    final urgency = p['urgency'] ?? '';
    final urgColor = urgency == 'ACT_NOW' ? CiroTheme.red : urgency == 'PREPARE' ? CiroTheme.yellow : CiroTheme.green;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 4, height: 4, margin: const EdgeInsets.only(top: 6),
            decoration: BoxDecoration(color: urgColor, borderRadius: BorderRadius.circular(2)),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(p['persona'] ?? '', style: TextStyle(color: CiroTheme.textPrimary, fontSize: 11, fontWeight: FontWeight.w600)),
                    const Spacer(),
                    Text('${((p['risk_vote'] ?? 0) * 100).toInt()}%', style: TextStyle(color: urgColor, fontSize: 11, fontWeight: FontWeight.w700, fontFamily: 'monospace')),
                  ],
                ),
                const SizedBox(height: 2),
                Text(p['assessment'] ?? '', style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10, height: 1.4)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ─── Logs ──────────────────────────────────────────────────────

  Widget _buildLogsButton() {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: _loadingLogs ? null : _fetchLogs,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(
            color: CiroTheme.surface,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: CiroTheme.border),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.history, color: CiroTheme.textSecondary, size: 16),
              const SizedBox(width: 8),
              Text('View Run Logs', style: TextStyle(color: CiroTheme.textSecondary, fontSize: 13, fontWeight: FontWeight.w600)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildLogsList() {
    if (_logs == null || _logs!.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(16),
        child: Text('No orchestration runs yet.', style: TextStyle(color: CiroTheme.textMuted, fontSize: 12)),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 12),
        ..._logs!.take(10).map<Widget>((log) {
          final runId = log['run_id'] ?? '';
          final startedAt = log['started_at'] ?? '';
          final duration = log['duration_seconds'] ?? 0;
          final debated = log['zones_debated'] ?? 0;
          final responded = log['zones_responded'] ?? 0;

          return GestureDetector(
            onTap: () => _fetchLogDetail(runId),
            child: Container(
              margin: const EdgeInsets.only(bottom: 6),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: CiroTheme.surface,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: _selectedLog?['run_id'] == runId ? CiroTheme.accent.withOpacity(0.5) : CiroTheme.border),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(runId, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 11, fontFamily: 'monospace')),
                        const SizedBox(height: 2),
                        Text(startedAt.toString().substring(0, 19), style: TextStyle(color: CiroTheme.textMuted, fontSize: 10)),
                      ],
                    ),
                  ),
                  Text('${duration}s', style: TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontFamily: 'monospace')),
                  const SizedBox(width: 10),
                  Text('$debated debated', style: TextStyle(color: CiroTheme.purple, fontSize: 10)),
                  const SizedBox(width: 6),
                  Text('$responded responded', style: TextStyle(color: CiroTheme.accent, fontSize: 10)),
                ],
              ),
            ),
          );
        }).toList(),
      ],
    );
  }

  Widget _buildLogDetail() {
    if (_selectedLog == null) return const SizedBox.shrink();
    final steps = (_selectedLog!['steps'] as List?) ?? [];

    return Container(
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CiroTheme.accent.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.receipt_long, color: CiroTheme.accent, size: 14),
              const SizedBox(width: 8),
              Text('Trace: ${_selectedLog!['run_id']}', style: const TextStyle(color: CiroTheme.accent, fontSize: 11, fontWeight: FontWeight.w600)),
              const Spacer(),
              GestureDetector(
                onTap: () => setState(() => _selectedLog = null),
                child: const Icon(Icons.close, color: CiroTheme.textMuted, size: 16),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...steps.map<Widget>((step) {
            final status = step['status'] ?? 'ok';
            final statusColor = status == 'error' ? CiroTheme.red : status == 'skip' ? CiroTheme.yellow : CiroTheme.green;

            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 6, height: 6, margin: const EdgeInsets.only(top: 5),
                    decoration: BoxDecoration(color: statusColor, borderRadius: BorderRadius.circular(3)),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(step['action'] ?? '', style: TextStyle(color: CiroTheme.textPrimary, fontSize: 10, fontWeight: FontWeight.w600, fontFamily: 'monospace')),
                        Text(step['detail'] ?? '', style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10, height: 1.3)),
                      ],
                    ),
                  ),
                ],
              ),
            );
          }).toList(),
        ],
      ),
    );
  }

  // ─── Helpers ───────────────────────────────────────────────────

  Widget _buildSectionHeader(String title) {
    return Text(title, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.8));
  }

  Widget _buildLoadingState(String message) {
    return Container(
      padding: const EdgeInsets.all(20),
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CiroTheme.border),
      ),
      child: Column(
        children: [
          const SizedBox(height: 24, width: 24, child: CircularProgressIndicator(strokeWidth: 2, color: CiroTheme.accent)),
          const SizedBox(height: 12),
          Text(message, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 11), textAlign: TextAlign.center),
        ],
      ),
    );
  }

  Widget _urgencyBadge(String urgency, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Text(urgency, style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.w700)),
    );
  }
}
