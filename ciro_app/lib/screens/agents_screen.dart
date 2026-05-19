import 'package:flutter/material.dart';
import '../models/zone.dart';
import '../services/api_service.dart';
import '../theme/ciro_theme.dart';

/// AI Agents screen — shows the multi-agent debate system and response planning.
/// Users can trigger a debate for any zone and see:
/// - 3 expert personas arguing (Hydrologist, Meteorologist, Urban Planner)
/// - Consensus reached
/// - Agent 4 response plan with actions + before/after simulation
class AgentsScreen extends StatefulWidget {
  const AgentsScreen({super.key});

  @override
  State<AgentsScreen> createState() => _AgentsScreenState();
}

class _AgentsScreenState extends State<AgentsScreen> {
  final ApiService _api = ApiService();
  String _selectedZone = 'sukkur-city';
  Map<String, dynamic>? _debateResult;
  Map<String, dynamic>? _responsePlan;
  Map<String, dynamic>? _orchestratorResult;
  bool _loadingDebate = false;
  bool _loadingResponse = false;
  bool _loadingOrchestrator = false;

  Future<void> _runDebate() async {
    setState(() { _loadingDebate = true; _debateResult = null; _responsePlan = null; });
    final result = await _api.runDebate(_selectedZone);
    setState(() { _debateResult = result; _loadingDebate = false; });
  }

  Future<void> _runFullResponse() async {
    setState(() { _loadingResponse = true; _responsePlan = null; });
    final result = await _api.getResponsePlan(_selectedZone);
    setState(() { _responsePlan = result; _loadingResponse = false; });
  }

  Future<void> _runOrchestrator() async {
    setState(() { _loadingOrchestrator = true; _orchestratorResult = null; });
    final result = await _api.runOrchestrator();
    setState(() { _orchestratorResult = result; _loadingOrchestrator = false; });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: CiroTheme.bg,
      appBar: AppBar(
        backgroundColor: CiroTheme.surface,
        title: const Text('AI Agent System', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        actions: [
          Container(
            margin: const EdgeInsets.only(right: 12),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: CiroTheme.green.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Row(
              children: [
                Icon(Icons.circle, size: 8, color: CiroTheme.green),
                SizedBox(width: 4),
                Text('LIVE', style: TextStyle(color: CiroTheme.green, fontSize: 10, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Zone selector
          _buildZoneSelector(),
          const SizedBox(height: 16),

          // Full pipeline button
          _buildActionButton(
            '🚀 Run Full Pipeline',
            'Evaluates all 8 zones → Debates high-risk → Plans response',
            CiroTheme.green,
            _loadingOrchestrator ? null : _runOrchestrator,
            _loadingOrchestrator,
          ),
          const SizedBox(height: 12),

          if (_loadingOrchestrator) _buildLoading('Running full AI pipeline across all zones...'),
          if (_orchestratorResult != null) _buildOrchestratorResult(),
          const SizedBox(height: 12),

          // Action buttons
          Row(
            children: [
              Expanded(
                child: _buildActionButton(
                  '🧠 Run Debate',
                  'Triggers 3 AI experts to analyze the crisis',
                  CiroTheme.purple,
                  _loadingDebate ? null : _runDebate,
                  _loadingDebate,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _buildActionButton(
                  '🎯 Full Response',
                  'Debate + Plan + Simulate actions',
                  CiroTheme.accent,
                  _loadingResponse ? null : _runFullResponse,
                  _loadingResponse,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Debate results
          if (_loadingDebate) _buildLoading('AI experts debating...'),
          if (_debateResult != null) _buildDebateSection(),

          // Response plan
          if (_loadingResponse) _buildLoading('Planning response & simulating outcomes...'),
          if (_responsePlan != null) _buildResponseSection(),
        ],
      ),
    );
  }

  Widget _buildZoneSelector() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: CiroTheme.border),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: _selectedZone,
          isExpanded: true,
          dropdownColor: CiroTheme.surface,
          style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 14),
          items: CiroZone.allZones.map((z) => DropdownMenuItem(
            value: z.id,
            child: Text('${z.name} (${z.province})'),
          )).toList(),
          onChanged: (v) => setState(() => _selectedZone = v!),
        ),
      ),
    );
  }

  Widget _buildActionButton(String title, String subtitle, Color color, VoidCallback? onTap, bool loading) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: color.withOpacity(0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.3)),
        ),
        child: Column(
          children: [
            if (loading)
              SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2, color: color))
            else
              Text(title, style: TextStyle(color: color, fontSize: 14, fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(subtitle, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10), textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }

  Widget _buildLoading(String message) {
    return Container(
      padding: const EdgeInsets.all(24),
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CiroTheme.border),
      ),
      child: Column(
        children: [
          const CircularProgressIndicator(color: CiroTheme.accent, strokeWidth: 2),
          const SizedBox(height: 12),
          Text(message, style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 12)),
        ],
      ),
    );
  }

  // ─── Orchestrator Result ───────────────────────────────────────────

  Widget _buildOrchestratorResult() {
    final summary = _orchestratorResult?['summary'] as Map<String, dynamic>? ?? {};
    final agent4Queue = (_orchestratorResult?['agent4_queue'] as List?) ?? [];
    final fullResults = (_orchestratorResult?['full_results'] as List?) ?? [];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sectionTitle('PIPELINE RESULTS', Icons.rocket_launch),
        const SizedBox(height: 10),

        // Summary stats
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: CiroTheme.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: CiroTheme.green.withOpacity(0.3)),
          ),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _statBubble('${summary['total_zones_evaluated'] ?? 8}', 'Evaluated'),
                  _statBubble('${summary['zones_above_threshold'] ?? 0}', 'High Risk'),
                  _statBubble('${summary['zones_debated'] ?? 0}', 'Debated'),
                  _statBubble('${summary['zones_for_agent4'] ?? 0}', 'Action Queue'),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),

        // Agent 4 Queue — zones needing response
        if (agent4Queue.isNotEmpty) ...[
          _sectionTitle('⚠️ ACTION QUEUE (${agent4Queue.length} zones)', Icons.warning_amber),
          const SizedBox(height: 8),
          ...agent4Queue.map((zone) => _buildQueueCard(zone)),
          const SizedBox(height: 12),
        ],

        // Full debate results
        if (fullResults.isNotEmpty) ...[
          _sectionTitle('DEBATE TRANSCRIPTS (${fullResults.length})', Icons.forum),
          const SizedBox(height: 8),
          ...fullResults.map((result) => _buildFullDebateCard(result)),
        ],
      ],
    );
  }

  Widget _statBubble(String value, String label) {
    return Column(
      children: [
        Text(value, style: const TextStyle(color: CiroTheme.accent, fontSize: 22, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 9, fontWeight: FontWeight.w600)),
      ],
    );
  }

  Widget _buildQueueCard(Map<String, dynamic> zone) {
    final urgency = zone['urgency'] ?? '';
    final urgColor = urgency == 'ACT_NOW' ? CiroTheme.red : urgency == 'PREPARE' ? CiroTheme.yellow : CiroTheme.green;
    final prob = ((zone['primary_risk_probability'] ?? 0) * 100).toStringAsFixed(0);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: urgColor.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: urgColor.withOpacity(0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(zone['zone_name'] ?? '', style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w700))),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(color: urgColor.withOpacity(0.2), borderRadius: BorderRadius.circular(6)),
                child: Text(urgency, style: TextStyle(color: urgColor, fontSize: 10, fontWeight: FontWeight.w800)),
              ),
              const SizedBox(width: 8),
              Text('$prob%', style: TextStyle(color: urgColor, fontSize: 18, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
            ],
          ),
          const SizedBox(height: 6),
          Text(zone['verdict'] ?? '', style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 12, height: 1.5)),
          const SizedBox(height: 4),
          Text('Action window: Days ${zone['action_window_days'] ?? []}', style: TextStyle(color: urgColor.withOpacity(0.7), fontSize: 10)),
        ],
      ),
    );
  }

  Widget _buildFullDebateCard(Map<String, dynamic> result) {
    final zoneName = result['zone_name'] ?? '';
    final trigger = result['trigger'] ?? '';
    final personas = (result['personas'] as List?) ?? [];
    final consensus = result['consensus'] as Map<String, dynamic>? ?? {};

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CiroTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(zoneName, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w700)),
          Text(trigger, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10)),
          const SizedBox(height: 10),
          ...personas.map((p) => _buildPersonaCard(p)),
          if (consensus.isNotEmpty) _buildConsensusCard(consensus),
        ],
      ),
    );
  }

  // ─── Debate Section ──────────────────────────────────────────────

  Widget _buildDebateSection() {
    final personas = (_debateResult?['personas'] as List?) ?? [];
    final consensus = _debateResult?['consensus'] as Map<String, dynamic>? ?? {};

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sectionTitle('MULTI-AGENT DEBATE', Icons.psychology),
        const SizedBox(height: 10),

        // Persona cards
        ...personas.map((p) => _buildPersonaCard(p)),

        // Consensus
        if (consensus.isNotEmpty) _buildConsensusCard(consensus),
        const SizedBox(height: 20),
      ],
    );
  }

  Widget _buildPersonaCard(Map<String, dynamic> persona) {
    final name = persona['persona'] ?? 'Expert';
    final assessment = persona['assessment'] ?? '';
    final riskVote = (persona['risk_vote'] ?? 0).toDouble();
    final keyFactor = persona['key_factor'] ?? '';
    final urgency = persona['urgency'] ?? 'MONITOR';

    final icon = name.contains('Hydro') ? '🌊' : name.contains('Meteo') ? '🌡️' : '🏙️';
    final urgencyColor = urgency == 'ACT_NOW' ? CiroTheme.red : urgency == 'PREPARE' ? CiroTheme.yellow : CiroTheme.green;

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
          Row(
            children: [
              Text(icon, style: const TextStyle(fontSize: 18)),
              const SizedBox(width: 8),
              Expanded(child: Text(name, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w700))),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(color: urgencyColor.withOpacity(0.15), borderRadius: BorderRadius.circular(6)),
                child: Text(urgency, style: TextStyle(color: urgencyColor, fontSize: 9, fontWeight: FontWeight.w800)),
              ),
              const SizedBox(width: 8),
              Text('${(riskVote * 100).toInt()}%', style: const TextStyle(color: CiroTheme.accent, fontSize: 14, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
            ],
          ),
          const SizedBox(height: 8),
          Text(assessment, style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 12, height: 1.5)),
          if (keyFactor.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text('Key factor: $keyFactor', style: TextStyle(color: CiroTheme.accent.withOpacity(0.8), fontSize: 11, fontStyle: FontStyle.italic)),
          ],
        ],
      ),
    );
  }

  Widget _buildConsensusCard(Map<String, dynamic> consensus) {
    final verdict = consensus['verdict'] ?? '';
    final urgency = consensus['urgency'] ?? '';
    final rationale = consensus['rationale'] ?? '';
    final unanimous = consensus['unanimous'] == true;

    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: CiroTheme.accent.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CiroTheme.accent.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('⚖️', style: TextStyle(fontSize: 18)),
              const SizedBox(width: 8),
              const Expanded(child: Text('CONSENSUS', style: TextStyle(color: CiroTheme.accent, fontSize: 12, fontWeight: FontWeight.w800, letterSpacing: 1))),
              if (unanimous) const Text('UNANIMOUS', style: TextStyle(color: CiroTheme.green, fontSize: 9, fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 10),
          Text(verdict, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w600, height: 1.4)),
          const SizedBox(height: 8),
          Text(rationale, style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 12, height: 1.5)),
        ],
      ),
    );
  }

  // ─── Response Section ────────────────────────────────────────────

  Widget _buildResponseSection() {
    final actions = (_responsePlan?['actions'] as List?) ?? [];
    final simulation = _responsePlan?['simulation'] as Map<String, dynamic>? ?? {};
    final narrative = _responsePlan?['narrative'] ?? '';
    final reasoning = (_responsePlan?['reasoning_trace'] as List?) ?? [];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sectionTitle('RESPONSE PLAN', Icons.shield),
        const SizedBox(height: 10),

        // Narrative
        if (narrative.isNotEmpty)
          Container(
            padding: const EdgeInsets.all(14),
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
              color: CiroTheme.surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: CiroTheme.border),
            ),
            child: Text(narrative, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 13, height: 1.6)),
          ),

        // Reasoning trace
        if (reasoning.isNotEmpty) ...[
          _sectionTitle('REASONING TRACE', Icons.route),
          const SizedBox(height: 8),
          ...reasoning.map((step) => _buildReasoningStep(step)),
          const SizedBox(height: 12),
        ],

        // Actions
        _sectionTitle('PLANNED ACTIONS (${actions.length})', Icons.checklist),
        const SizedBox(height: 8),
        ...actions.map((a) => _buildActionCard(a)),

        // Simulation before/after
        if (simulation.isNotEmpty) ...[
          const SizedBox(height: 12),
          _sectionTitle('SIMULATION: BEFORE vs AFTER', Icons.compare_arrows),
          const SizedBox(height: 8),
          _buildSimulation(simulation),
        ],
      ],
    );
  }

  Widget _buildReasoningStep(Map<String, dynamic> step) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: CiroTheme.border.withOpacity(0.5)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 22, height: 22,
            decoration: BoxDecoration(color: CiroTheme.accent.withOpacity(0.2), borderRadius: BorderRadius.circular(6)),
            child: Center(child: Text('${step['step'] ?? ''}', style: const TextStyle(color: CiroTheme.accent, fontSize: 10, fontWeight: FontWeight.w800))),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(step['thought'] ?? '', style: const TextStyle(color: CiroTheme.textSecondary, fontSize: 11)),
                const SizedBox(height: 2),
                Text('→ ${step['decision'] ?? ''}', style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 11, fontWeight: FontWeight.w600)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionCard(Map<String, dynamic> action) {
    final category = action['category'] ?? '';
    final desc = action['description'] ?? '';
    final priority = action['priority'] ?? '';
    final agency = action['responsible_agency'] ?? '';
    final time = action['estimated_time_hours'] ?? 0;

    final categoryIcon = {
      'EVACUATE': '🚨', 'ALERT': '📢', 'DEPLOY': '🚁',
      'REROUTE': '🛣️', 'SHELTER': '🏕️', 'MEDICAL': '🏥',
    }[category] ?? '📋';

    final priorityColor = priority == 'IMMEDIATE' ? CiroTheme.red : priority == 'WITHIN_6H' ? CiroTheme.yellow : CiroTheme.green;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: CiroTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(categoryIcon, style: const TextStyle(fontSize: 16)),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(color: priorityColor.withOpacity(0.15), borderRadius: BorderRadius.circular(4)),
                child: Text(priority, style: TextStyle(color: priorityColor, fontSize: 8, fontWeight: FontWeight.w800)),
              ),
              const Spacer(),
              Text('${time}h', style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontFamily: 'monospace')),
            ],
          ),
          const SizedBox(height: 6),
          Text(desc, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 12, height: 1.4)),
          const SizedBox(height: 4),
          Text(agency, style: TextStyle(color: CiroTheme.blue.withOpacity(0.8), fontSize: 10)),
        ],
      ),
    );
  }

  Widget _buildSimulation(Map<String, dynamic> sim) {
    final before = sim['before'] as Map<String, dynamic>? ?? {};
    final after = sim['after'] as Map<String, dynamic>? ?? {};
    final effectiveness = (sim['effectiveness_score'] ?? 0).toDouble();

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: CiroTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: CiroTheme.green.withOpacity(0.3)),
      ),
      child: Column(
        children: [
          // Effectiveness score
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('Effectiveness: ', style: TextStyle(color: CiroTheme.textMuted, fontSize: 11)),
              Text('${(effectiveness * 100).toInt()}%', style: const TextStyle(color: CiroTheme.green, fontSize: 20, fontWeight: FontWeight.w800, fontFamily: 'monospace')),
            ],
          ),
          const SizedBox(height: 14),
          // Before/After grid
          Row(
            children: [
              Expanded(child: _simColumn('BEFORE', before, CiroTheme.red)),
              Container(width: 1, height: 100, color: CiroTheme.border),
              Expanded(child: _simColumn('AFTER', after, CiroTheme.green)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _simColumn(String title, Map<String, dynamic> data, Color color) {
    return Column(
      children: [
        Text(title, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 1)),
        const SizedBox(height: 8),
        _simStat('Evacuated', '${data['population_evacuated'] ?? 0}'),
        _simStat('Shelters', '${data['shelters_activated'] ?? 0}'),
        _simStat('Medical', '${data['medical_units_deployed'] ?? 0}'),
        _simStat('Lives Saved', '${data['estimated_lives_saved'] ?? 0}'),
      ],
    );
  }

  Widget _simStat(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text('$label: ', style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10)),
          Text(value, style: const TextStyle(color: CiroTheme.textPrimary, fontSize: 11, fontWeight: FontWeight.w700, fontFamily: 'monospace')),
        ],
      ),
    );
  }

  Widget _sectionTitle(String title, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 16, color: CiroTheme.accent),
        const SizedBox(width: 8),
        Text(title, style: const TextStyle(color: CiroTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 1)),
      ],
    );
  }
}
