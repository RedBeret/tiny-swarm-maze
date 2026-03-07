export type Tone = 'system' | 'command' | 'speech' | 'success' | 'warning' | 'info';
export type Difficulty = 'starter' | 'standard' | 'dense';
export type ProfileName = 'rules' | 'ollama_fast' | 'ollama_slow' | 'ollama_cloud_kimi';

export interface Point {
  x: number;
  y: number;
}

export interface UnitPublicState {
  id: string;
  color: string;
  role: string;
  x: number;
  y: number;
  vision: number;
  hearing: number;
  mood: string;
  target: Point | null;
  bubble: string | null;
  carrying_key_id: string | null;
  active_command: string | null;
  stunned_until_tick: number;
}

export interface KeyPublicState {
  id: string;
  x: number;
  y: number;
  found: boolean;
  delivered: boolean;
  carried_by: string | null;
}

export interface TrapPublicState {
  id: string;
  x: number;
  y: number;
  revealed: boolean;
  active: boolean;
}

export interface EventPublic {
  id: string;
  tick: number;
  tone: Tone;
  text: string;
}

export interface ObjectivePublic {
  delivered_keys: number;
  total_keys: number;
  maze_clear: boolean;
}

export interface MetricsPublic {
  fog_percent: number;
  stuns: number;
  reroutes: number;
  commands_queued: number;
  commands_applied: number;
  parser_latency_last_ms: number;
  parser_latency_avg_ms: number;
  planner_latency_last_ms: number;
  planner_latency_avg_ms: number;
  timeout_count: number;
  model_error_count: number;
}

export interface GameStateMessage {
  type: 'state';
  session_id: string;
  seed: number;
  tick: number;
  width: number;
  height: number;
  difficulty: Difficulty;
  profile: ProfileName;
  paused: boolean;
  queue_depth: number;
  grid: number[][];
  discovered_tiles: string[];
  exit: Point;
  units: UnitPublicState[];
  keys: KeyPublicState[];
  traps: TrapPublicState[];
  objectives: ObjectivePublic;
  metrics: MetricsPublic;
  events: EventPublic[];
  selected_unit_id: string | null;
}

export interface SessionCreateResponse {
  session_id: string;
  seed: number;
  tick_rate_hz: number;
  ws_path: string;
  difficulty: Difficulty;
}

export interface AckMessage {
  type: 'ack';
  ok: boolean;
  client_command_id?: string | null;
  reason?: string | null;
}

export interface WarningMessage {
  type: 'warning';
  code: string;
  message: string;
}

export interface ErrorMessage {
  type: 'error';
  message: string;
}

export interface ParsedCommand {
  target_ids: string[];
  intent: string;
  arguments: Record<string, unknown>;
  priority: 'low' | 'normal' | 'high';
  ttl_ticks: number;
  source: 'player' | 'planner';
  confidence: number;
  rationale?: string | null;
  direction?: 'north' | 'south' | 'east' | 'west' | null;
}

export interface CommandQueuedMessage {
  type: 'command_queued';
  command_id: string;
  raw_text: string;
  profile: ProfileName;
  eta_ms: number;
  queued_at_ms: number;
}

export interface CommandAppliedMessage {
  type: 'command_applied';
  command_id: string;
  profile: ProfileName;
  latency_ms: number;
  parse_latency_ms: number;
  parsed: ParsedCommand;
}

export type WsServerMessage =
  | GameStateMessage
  | AckMessage
  | WarningMessage
  | ErrorMessage
  | CommandQueuedMessage
  | CommandAppliedMessage;

export interface SubmitCommandMessage {
  type: 'submit_command';
  raw_text: string;
  selected_unit_id: string | null;
  issued_at_ms: number;
  client_command_id: string;
}

export interface SetProfileMessage {
  type: 'set_profile';
  profile: ProfileName;
}

export interface SetProviderConfigMessage {
  type: 'set_provider_config';
  base_url?: string;
  model?: string;
  api_key?: string;
  timeout_ms?: number;
  max_retries?: number;
  backoff_ms?: number;
  artificial_delay_ms?: number;
}

export interface PauseMessage {
  type: 'pause';
}

export interface ResumeMessage {
  type: 'resume';
}

export interface ResetMessage {
  type: 'reset';
  seed?: number;
  difficulty?: Difficulty;
}
