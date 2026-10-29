// Mirrors services/api/app/models/evaluation.py.

export type EvaluationCategory =
  | "capacity"
  | "scheduling"
  | "conflict_detection"
  | "repair_validation";

export interface EvaluationCaseResult {
  id: string;
  category: EvaluationCategory;
  name: string;
  passed: boolean;
  duration_ms: number;
  checks_passed: number;
  checks_total: number;
  summary: string;
}

export interface EvaluationSummary {
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  pass_rate_percent: number;
  total_checks: number;
  passed_checks: number;
  total_duration_ms: number;
}

export interface EvaluationReport {
  status: "passed" | "failed";
  suite_name: "Room for Both deterministic reliability suite";
  /** UTC ISO timestamp. */
  generated_at: string;
  model_calls_made: 0;
  summary: EvaluationSummary;
  cases: EvaluationCaseResult[];
  architecture_guarantees: string[];
}
