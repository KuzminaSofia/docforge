// Enums

export type UserRole = "user" | "admin";

export type TaskStatus =
  | "created"
  | "queued"
  | "validating"
  | "processing"
  | "completed"
  | "failed";

export type TransactionType = "credit" | "debit";

export type DocumentType =
  | "technical_passport"
  | "quality_passport"
  | "lab_protocol"
  | "certificate"
  | "unknown";

// Users

export interface UserResponse {
  id: string;
  email: string;
  role: UserRole;
  /** Decimal as string */
  balance_credits: string;
  is_active: boolean;
  created_at: string;
}

// Auth

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  message: string;
  user: UserResponse;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user: UserResponse;
}

export interface LogoutResponse {
  message: string;
}

// Balance

export interface BalanceResponse {
  user_id: string;
  balance_credits: string;
}

export interface TopUpBalanceRequest {
  amount: string;
}

export interface TopUpBalanceResponse {
  user_id: string;
  balance_credits: string;
  transaction: TransactionHistoryItemResponse;
}

// History

export interface TransactionHistoryItemResponse {
  id: string;
  user_id: string;
  task_id: string | null;
  transaction_type: TransactionType;
  /** Decimal as string */
  amount: string;
  created_at: string;
}

export interface PredictionHistoryItemResponse {
  id: string;
  user_id: string;
  task_id: string | null;
  model_id: string;
  result_id: string | null;
  status: TaskStatus;
  spent_credits: string;
  created_at: string;
  completed_at: string | null;
}

export interface TransactionsHistoryResponse {
  items: TransactionHistoryItemResponse[];
  limit: number | null;
  offset: number;
}

export interface PredictionsHistoryResponse {
  items: PredictionHistoryItemResponse[];
  limit: number | null;
  offset: number;
}

// Tasks

export interface TaskStatusResponse {
  id: string;
  status: TaskStatus;
  error_message: string | null;
  spent_credits: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface TaskDocumentResponse {
  id: string;
  owner_id: string;
  original_filename: string;
  storage_path: string;
  mime_type: string;
  document_type: DocumentType;
  size_bytes: number;
  uploaded_at: string;
}

export interface TaskListItemResponse {
  id: string;
  model_id: string;
  model_name: string;
  backend_name: string;
  target_schema: string | null;
  status: TaskStatus;
  error_message: string | null;
  spent_credits: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result_id: string | null;
  documents_count: number;
  first_document_name: string | null;
}

export interface TasksListResponse {
  items: TaskListItemResponse[];
  limit: number;
  offset: number;
  status: TaskStatus | null;
}

export interface TaskDetailsResponse {
  id: string;
  user_id: string;
  model_id: string;
  model_name: string;
  backend_name: string;
  target_schema: string | null;
  status: TaskStatus;
  error_message: string | null;
  spent_credits: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result_id: string | null;
  documents: TaskDocumentResponse[];
}

export interface ValidationIssueResponse {
  field_name: string;
  message: string;
  raw_value: unknown;
}

export interface PredictionResultDetailsResponse {
  id: string;
  task_id: string;
  extracted_data: Record<string, unknown>;
  validation_issues: ValidationIssueResponse[];
  output_path: string | null;
  artifacts_dir: string | null;
  created_at: string;
}

export interface ResultArtifactResponse {
  name: string;
  path: string;
  kind: string;
  mime_type: string | null;
  description: string | null;
  metadata: Record<string, unknown>;
}

export interface TaskResultResponse {
  task: TaskDetailsResponse;
  result: PredictionResultDetailsResponse | null;
  artifacts: ResultArtifactResponse[];
  has_result: boolean;
}

// Models

export interface MLModelResponse {
  id: string;
  name: string;
  description: string;
  /** Decimal as string */
  prediction_cost: string;
  backend_name: string;
  model_kind: string;
}

// Predict

export interface PredictAcceptedResponse {
  task_id: string;
  model_id: string;
  model_name: string;
  status: TaskStatus;
  created_at: string;
  callback_url: string | null;
  message: string;
}

// API error shape from FastAPI
export interface ApiErrorBody {
  detail: string | { msg: string; type: string }[];
}
