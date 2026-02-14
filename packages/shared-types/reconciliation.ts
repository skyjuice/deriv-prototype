export type SourceType = "internal" | "erp" | "psp";

export type RunStatus =
  | "draft"
  | "ready"
  | "queued"
  | "running"
  | "completed"
  | "format_failed"
  | "failed";

export type FinalStatus = "good_transaction" | "doubtful_transaction";

export interface ReconciliationRun {
  id: string;
  status: RunStatus;
  stage: string;
  initiatedBy: string;
  createdAt: string;
  updatedAt: string;
  counters: {
    total: number;
    good: number;
    doubtful: number;
    exceptions: number;
  };
}

export interface SourceFile {
  id: string;
  runId: string;
  sourceType: SourceType;
  formatType: "csv" | "xlsx" | "pdf";
  filename: string;
  checksum: string;
  parseStatus: "pending" | "parsed" | "failed";
  mapping?: Record<string, string>;
}

export interface NormalizedTransaction {
  psp_txn_id: string;
  merchant_ref: string;
  gross_amount: number;
  currency: string;
  processing_fee: number;
  net_payout: number;
  transaction_date: string;
  settlement_date: string;
  client_id: string;
  client_name: string;
  description: string;
  status: string;
  payment_method: string;
  settlement_bank: string;
  bank_country: string;
  fx_rate?: number | null;
}

export interface MatchDecision {
  runId: string;
  merchantRef: string;
  finalStatus: FinalStatus;
  reasonCodes: string[];
  transactionMonth?: string | null;
  stageResults: {
    exactHash: boolean;
    fuzzy: boolean;
    threeWay: boolean;
    backdated: boolean;
    fxHandled: boolean;
  };
}

export interface ExceptionCase {
  id: string;
  runId: string;
  merchantRef: string;
  severity: "low" | "medium" | "high";
  reasonCodes: string[];
  state: "open" | "verified" | "approved" | "rejected" | "resolved";
}

export interface AIReviewStep {
  exceptionId: string;
  stage: "intern" | "manager" | "supervisor" | "announcer";
  confidence: number;
  output: Record<string, unknown>;
}

export interface AnnouncementItem {
  id: string;
  runId: string;
  level: "good" | "doubtful";
  title: string;
  message: string;
  createdAt: string;
}

export interface AuditEvent {
  id: string;
  actorId: string;
  action: string;
  entityType: string;
  entityId: string;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  timestamp: string;
}

export interface MonthlySubmissionSummary {
  runId: string;
  month: string;
  totalTransactions: number;
  goodTransactions: number;
  doubtfulTransactions: number;
  addressedDoubtful: number;
  unresolvedDoubtful: number;
  readyForSubmission: boolean;
  notifiedToSource: boolean;
  journalCreated: boolean;
  submittedToErp: boolean;
  nextAction: string;
  notifiedAt?: string | null;
  journalCreatedAt?: string | null;
  submittedAt?: string | null;
  alertRecipients: MonthlyAlertRecipient[];
  doubtfulDetails: MonthlyDoubtfulDetail[];
}

export interface MonthlyAlertRecipient {
  recipientKey: string;
  recipientLabel: string;
  reason: string;
  count: number;
  merchantRefs: string[];
}

export interface MonthlyDoubtfulDetail {
  merchantRef: string;
  state: string;
  reasonCodes: string[];
  missingSources: string[];
  recipients: string[];
}

export interface DailyNotificationTarget {
  recipientKey: string;
  recipientLabel: string;
  count: number;
  merchantRefs: string[];
}

export interface DailyOpsSummary {
  runId: string;
  runStatus: string;
  businessDate: string;
  totalTransactions: number;
  goodTransactions: number;
  doubtfulTransactions: number;
  unresolvedDoubtful: number;
  addressedDoubtful: number;
  notificationsRequired: number;
  notificationsSent: number;
  closeState: "open" | "ready_to_close" | "closed" | string;
  nextAction: string;
  closedAt?: string | null;
  notificationTargets: DailyNotificationTarget[];
  monthlyItems: MonthlySubmissionSummary[];
}

export interface MonthlyCloseBatch {
  month: string;
  sourceRunIds: string[];
  sourceRunCount: number;
  totalTransactions: number;
  goodTransactions: number;
  doubtfulTransactions: number;
  readyForErp: boolean;
  journalCreated: boolean;
  submittedToErp: boolean;
  nextAction: string;
  journalCreatedAt?: string | null;
  submittedAt?: string | null;
}
