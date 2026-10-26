export type View = 'chat' | 'knowledge' | 'evaluations' | 'tuning';
export type Collection = {
  id: string;
  name: string;
  description: string;
  color: string;
  document_count: number;
};
export type Workspace = {
  name: string;
  identity: { user: string; role: string; auth_mode: string };
  collections: Collection[];
  stats: { documents: number; ready_documents: number; chunks: number; answers: number };
  models: {
    ready: boolean;
    error: string;
    base: string;
    base_revision: string;
    embedding: string;
    reranker: string;
    adapted_available: boolean;
    backend: string;
  };
};
export type Document = {
  id: string;
  collection_id: string;
  title: string;
  filename: string;
  status: string;
  bytes: number;
  pages: number;
  chunk_count: number;
  error: string;
  created_at: number;
  updated_at: number;
};
export type Citation = {
  ref: number;
  chunk_id: string;
  document_id: string;
  title: string;
  filename: string;
  page: number;
  heading: string;
  text: string;
  rerank_score: number;
  available: boolean;
};
export type Trace = {
  mode?: string;
  model?: string;
  retrieval_query?: string;
  total_ms?: number;
  retrieval_ms?: number;
  generation_ms?: number;
  ttft_ms?: number;
  prompt_tokens?: number;
  abstained?: boolean;
  citation_count?: number;
  candidate_count?: number;
  candidates?: {
    chunk_id: string;
    title: string;
    dense_score: number;
    lexical_score: number;
    fusion_score: number;
    rerank_score: number;
  }[];
};
export type Message = {
  id: string;
  role: string;
  content: string;
  state: string;
  citations: Citation[];
  trace: Trace;
  feedback?: string | null;
  created_at?: number;
};
export type Conversation = { id: string; title: string; updated_at: number };
export type Metrics = {
  recall_at_5?: number;
  mrr?: number;
  citation_validity?: number;
  fact_coverage?: number;
  abstention_accuracy?: number;
  latency_ms?: number;
  samples?: number;
};
export type Report = {
  dataset_counts?: Record<string, number>;
  dataset_hashes?: Record<string, string>;
  method?: string;
  steps?: number;
  trainable_parameters?: number;
  examples_seen?: number;
  seed?: number;
  losses?: number[];
  validation_loss?: number;
  base_validation_loss?: number;
  model?: string;
  limitation?: string;
  retrieval?: Record<string, Metrics>;
  generation?: Record<string, Metrics>;
  sample_count?: number;
  examples?: {
    question: string;
    expected: string;
    answer?: string;
    mode?: string;
    citation_valid?: boolean;
    fact_coverage?: number;
  }[];
};
export type Experiment = {
  id: string;
  name: string;
  kind: string;
  report: Report;
  created_at: number;
};
export type TrainingSummary = {
  counts: Record<string, number>;
  method: string;
  base_model: string;
  adapter_loaded: boolean;
  command: string;
  purpose: string;
  data_provenance: string;
};
