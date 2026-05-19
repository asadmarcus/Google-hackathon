import 'package:dio/dio.dart';
import '../config/api_config.dart';
import '../models/prediction.dart';

class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;

  late final Dio _dio;

  Dio get dio => _dio;

  ApiService._internal() {
    _dio = Dio(BaseOptions(
      baseUrl: ApiConfig.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ));
  }

  /// Get 30-day prediction for a zone
  Future<ZonePrediction?> getPrediction(String zoneId) async {
    try {
      final response = await _dio.post('/api/v1/agent3/predict/$zoneId');
      if (response.statusCode == 200) {
        return ZonePrediction.fromJson(response.data);
      }
    } catch (e) {
      print('Prediction error: $e');
    }
    return null;
  }

  /// Trigger data fetch (Agent 2)
  Future<bool> triggerFetch() async {
    try {
      final response = await _dio.post('/api/v1/agent2/fetch');
      return response.statusCode == 200;
    } catch (e) {
      print('Fetch error: $e');
      return false;
    }
  }

  /// Get satellite analysis (Agent 1)
  Future<Map<String, dynamic>?> getSatelliteAnalysis(String zoneId) async {
    try {
      final response = await _dio.get('/api/v1/agent1/latest/$zoneId');
      if (response.statusCode == 200) {
        return response.data;
      }
    } catch (e) {
      print('Satellite error: $e');
    }
    return null;
  }

  /// Trigger satellite analysis for a zone
  Future<Map<String, dynamic>?> analyzeSatellite(String zoneId) async {
    try {
      final response = await _dio.post('/api/v1/agent1/analyze/$zoneId');
      if (response.statusCode == 200) {
        return response.data;
      }
    } catch (e) {
      print('Analyze satellite error: $e');
    }
    return null;
  }

  /// Health check
  Future<bool> isHealthy() async {
    try {
      final response = await _dio.get('/health');
      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  /// Run AI debate for a zone (3 personas argue about crisis)
  Future<Map<String, dynamic>?> runDebate(String zoneId) async {
    try {
      final response = await _dio.post('/api/v1/debater/debate/$zoneId',
        options: Options(receiveTimeout: const Duration(seconds: 90)),
      );
      if (response.statusCode == 200) return response.data;
    } catch (e) {
      print('Debate error: $e');
    }
    return null;
  }

  /// Get full Agent 4 response plan (debate → plan → simulate)
  Future<Map<String, dynamic>?> getResponsePlan(String zoneId) async {
    try {
      final response = await _dio.post('/api/v1/agent4/respond/$zoneId',
        options: Options(receiveTimeout: const Duration(seconds: 120)),
      );
      if (response.statusCode == 200) return response.data;
    } catch (e) {
      print('Response plan error: $e');
    }
    return null;
  }

  /// Get reasoning trace for judges
  Future<Map<String, dynamic>?> getTrace(String zoneId) async {
    try {
      final response = await _dio.get('/api/v1/agent4/trace/$zoneId');
      if (response.statusCode == 200) return response.data;
    } catch (e) {
      print('Trace error: $e');
    }
    return null;
  }

  /// Run full orchestrator cycle (evaluate all zones → debate high-risk → queue for Agent 4)
  Future<Map<String, dynamic>?> runOrchestrator() async {
    try {
      final response = await _dio.post('/api/v1/orchestrator/run',
        options: Options(receiveTimeout: const Duration(seconds: 180)),
      );
      if (response.statusCode == 200) return response.data;
    } catch (e) {
      print('Orchestrator error: $e');
    }
    return null;
  }

  /// Get orchestrator status (last run info)
  Future<Map<String, dynamic>?> getOrchestratorStatus() async {
    try {
      final response = await _dio.get('/api/v1/orchestrator/status');
      if (response.statusCode == 200) return response.data;
    } catch (e) { print('Orchestrator status error: $e'); }
    return null;
  }
}
