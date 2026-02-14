export type SourceType = "internal" | "erp" | "psp";

export type Role = "analyst" | "supervisor" | "admin";

export interface Run {
  id: string;
  status: string;
  stage: string;
  initiated_by: string;
  counters: {
    total: number;
    good: number;
    doubtful: number;
    exceptions: number;
  };
}

export interface StageResults {
  exact_hash: boolean;
  fuzzy: boolean;
  three_way: boolean;
  backdated: boolean;
  fx_handled: boolean;
}

export interface MatchDecision {
  run_id: string;
  merchant_ref: string;
  final_status: "good_transaction" | "doubtful_transaction";
  reason_codes: string[];
  stage_results: StageResults;
  fuzzy_score?: number | null;
  backdated_gap_days?: number | null;
  fx_detail?: string | null;
  trace_json?: Record<string, unknown> | null;
}

export interface ExceptionItem {
  id: string;
  run_id: string;
  merchant_ref: string;
  severity: string;
  reason_codes: string[];
  state: string;
}

export interface Announcement {
  id: string;
  run_id: string;
  level: string;
  title: string;
  message: string;
  payload_json: Record<string, unknown>;
}

export interface AIReview {
  exception_id: string;
  stage: "intern" | "manager" | "supervisor" | "announcer" | string;
  confidence: number;
  output_json: Record<string, unknown>;
}

export interface MonthlySubmission {
  run_id: string;
  month: string;
  total_transactions: number;
  good_transactions: number;
  doubtful_transactions: number;
  addressed_doubtful: number;
  unresolved_doubtful: number;
  ready_for_submission: boolean;
  notified_to_source: boolean;
  journal_created: boolean;
  submitted_to_erp: boolean;
  next_action: string;
  notified_at?: string | null;
  journal_created_at?: string | null;
  submitted_at?: string | null;
  alert_recipients: MonthlyAlertRecipient[];
  doubtful_details: MonthlyDoubtfulDetail[];
}

export interface MonthlyAlertRecipient {
  recipient_key: string;
  recipient_label: string;
  reason: string;
  count: number;
  merchant_refs: string[];
}

export interface MonthlyDoubtfulDetail {
  merchant_ref: string;
  state: string;
  reason_codes: string[];
  missing_sources: string[];
  recipients: string[];
}

export interface DailyNotificationTarget {
  recipient_key: string;
  recipient_label: string;
  count: number;
  merchant_refs: string[];
}

export interface DailyOpsSummary {
  run_id: string;
  run_status: string;
  business_date: string;
  total_transactions: number;
  good_transactions: number;
  doubtful_transactions: number;
  unresolved_doubtful: number;
  addressed_doubtful: number;
  notifications_required: number;
  notifications_sent: number;
  close_state: "open" | "ready_to_close" | "closed" | string;
  next_action: string;
  closed_at?: string | null;
  notification_targets: DailyNotificationTarget[];
  monthly_items: MonthlySubmission[];
}

export interface MonthlyCloseBatch {
  month: string;
  source_run_ids: string[];
  source_runs: MonthlyCloseSourceRun[];
  source_run_count: number;
  total_transactions: number;
  good_transactions: number;
  doubtful_transactions: number;
  doubtful_notification_required: number;
  doubtful_notification_sent: number;
  ready_for_erp: boolean;
  journal_created: boolean;
  submitted_to_erp: boolean;
  next_action: string;
  journal_created_at?: string | null;
  submitted_at?: string | null;
}

export interface MonthlyCloseSourceRun {
  run_id: string;
  run_number: string;
  business_date: string;
  close_state: string;
  doubtful_transactions: number;
  notified_to_source: boolean;
}

export interface AIFeedback {
  id: string;
  exception_id: string;
  run_id: string;
  user_id: string;
  stage: string;
  feedback_type: "accept" | "reject" | "edit_apply" | "needs_evidence" | string;
  reason_codes: string[];
  edited_action?: string | null;
  comment?: string | null;
  created_at: string;
}

export interface FeedbackMetrics {
  total_feedback: number;
  acceptance_rate: number;
  by_type: Record<string, number>;
  top_reject_reasons: { reason: string; count: number }[];
}
