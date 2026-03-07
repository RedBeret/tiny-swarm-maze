import type {
  AckMessage,
  CommandAppliedMessage,
  CommandQueuedMessage,
  Difficulty,
  GameStateMessage,
  ProfileName,
  SessionCreateResponse,
  SetProviderConfigMessage,
  SubmitCommandMessage,
  WsServerMessage,
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

interface ApiHandlers {
  onOpen: () => void;
  onState: (message: GameStateMessage) => void;
  onAck: (message: AckMessage) => void;
  onQueued: (message: CommandQueuedMessage) => void;
  onApplied: (message: CommandAppliedMessage) => void;
  onWarning: (message: string) => void;
  onError: (message: string) => void;
}

export class SwarmApiClient {
  private socket: WebSocket | null = null;
  private readonly apiBaseUrl: string;
  private sessionId: string | null = null;
  private readonly handlers: ApiHandlers;

  constructor(handlers: ApiHandlers) {
    this.apiBaseUrl = API_BASE_URL.replace(/\/$/, '');
    this.handlers = handlers;
  }

  async createSession(seed?: number, difficulty?: Difficulty): Promise<SessionCreateResponse> {
    const body: Record<string, unknown> = {};
    if (typeof seed === 'number') body.seed = seed;
    if (difficulty) body.difficulty = difficulty;

    const response = await fetch(`${this.apiBaseUrl}/api/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`failed to create session: ${response.status} ${text}`);
    }

    return (await response.json()) as SessionCreateResponse;
  }

  connect(sessionId: string): void {
    this.sessionId = sessionId;
    const wsUrl = this.apiBaseUrl.replace(/^http/, 'ws') + `/ws/${sessionId}`;
    this.socket = new WebSocket(wsUrl);
    this.socket.onopen = () => {
      this.handlers.onOpen();
    };

    this.socket.onmessage = (event) => {
      let payload: WsServerMessage;
      try {
        payload = JSON.parse(event.data) as WsServerMessage;
      } catch {
        this.handlers.onError('invalid websocket payload');
        return;
      }

      if (payload.type === 'state') {
        this.handlers.onState(payload);
      } else if (payload.type === 'ack') {
        this.handlers.onAck(payload);
      } else if (payload.type === 'command_queued') {
        this.handlers.onQueued(payload);
      } else if (payload.type === 'command_applied') {
        this.handlers.onApplied(payload);
      } else if (payload.type === 'warning') {
        this.handlers.onWarning(`${payload.code}: ${payload.message}`);
      } else if (payload.type === 'error') {
        this.handlers.onError(payload.message);
      }
    };

    this.socket.onerror = () => {
      this.handlers.onError('websocket error');
    };

    this.socket.onclose = () => {
      this.handlers.onError('websocket closed');
    };
  }

  isConnected(): boolean {
    return Boolean(this.socket && this.socket.readyState === WebSocket.OPEN);
  }

  sendCommand(text: string, selectedUnitId: string | null): string | null {
    if (!this.isConnected()) {
      this.handlers.onError('websocket not connected');
      return null;
    }

    const clientCommandId =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    const message: SubmitCommandMessage = {
      type: 'submit_command',
      raw_text: text,
      selected_unit_id: selectedUnitId,
      issued_at_ms: Date.now(),
      client_command_id: clientCommandId,
    };

    this.socket?.send(JSON.stringify(message));
    return clientCommandId;
  }

  setProfile(profile: ProfileName): void {
    this.send({ type: 'set_profile', profile });
  }

  setProviderConfig(config: SetProviderConfigMessage): void {
    this.send({ ...config, type: 'set_provider_config' });
  }

  pause(): void {
    this.send({ type: 'pause' });
  }

  resume(): void {
    this.send({ type: 'resume' });
  }

  reset(seed: number | undefined, difficulty: Difficulty): void {
    this.send({ type: 'reset', seed, difficulty });
  }

  private send(payload: Record<string, unknown>): void {
    if (!this.isConnected()) {
      this.handlers.onError('websocket not connected');
      return;
    }
    this.socket?.send(JSON.stringify(payload));
  }
}
