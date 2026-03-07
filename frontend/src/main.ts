import Phaser from 'phaser';
import { SwarmApiClient } from './api';
import { GameScene } from './game-scene';
import './styles.css';
import type {
  AckMessage,
  CommandAppliedMessage,
  CommandQueuedMessage,
  Difficulty,
  EventPublic,
  GameStateMessage,
  ProfileName,
  UnitPublicState,
} from './types';

type LocalTone = 'warning' | 'command' | 'success' | 'system' | 'info';

interface LocalEvent {
  id: string;
  tickLabel: string;
  tone: LocalTone;
  text: string;
}

interface StoredSettings {
  profile: ProfileName;
  base_url: string;
  model: string;
  api_key: string;
  timeout_ms: number;
  max_retries: number;
  artificial_delay_ms: number;
  difficulty: Difficulty;
}

interface QueueEntry {
  id: string;
  rawText: string;
  profile: ProfileName;
  queuedAtMs: number;
  etaMs: number;
  applied: boolean;
  parseLatencyMs?: number;
  latencyMs?: number;
  parsedIntent?: string;
}

const STORAGE_KEY = 'tiny-swarm-maze.settings.v1';
const MAX_LOCAL_EVENTS = 30;

const root = getRequiredElement<HTMLDivElement>('game-root');
const commandInput = getRequiredElement<HTMLInputElement>('command-input');
const sendButton = getRequiredElement<HTMLButtonElement>('send-command');
const eventLog = getRequiredElement<HTMLDivElement>('event-log');
const selectedUnitContainer = getRequiredElement<HTMLDivElement>('selected-unit');
const statusPills = getRequiredElement<HTMLDivElement>('status-pills');
const metricsPanel = getRequiredElement<HTMLDivElement>('metrics-panel');
const queuePanel = getRequiredElement<HTMLDivElement>('queued-commands');
const parseResult = getRequiredElement<HTMLDivElement>('parse-result');
const profileSelect = getRequiredElement<HTMLSelectElement>('profile-select');
const baseUrlInput = getRequiredElement<HTMLInputElement>('base-url-input');
const modelInput = getRequiredElement<HTMLInputElement>('model-input');
const apiKeyInput = getRequiredElement<HTMLInputElement>('api-key-input');
const timeoutInput = getRequiredElement<HTMLInputElement>('timeout-input');
const retriesInput = getRequiredElement<HTMLInputElement>('retries-input');
const delayInput = getRequiredElement<HTMLInputElement>('delay-input');
const applySettingsButton = getRequiredElement<HTMLButtonElement>('apply-settings');
const clearApiKeyButton = getRequiredElement<HTMLButtonElement>('clear-api-key');
const difficultySelect = getRequiredElement<HTMLSelectElement>('difficulty-select');
const seedInput = getRequiredElement<HTMLInputElement>('seed-input');
const resetRunButton = getRequiredElement<HTMLButtonElement>('reset-run');
const pauseToggleButton = getRequiredElement<HTMLButtonElement>('pause-toggle');
const quickButtons = Array.from(document.querySelectorAll<HTMLButtonElement>('[data-quick]'));

let selectedUnitId: string | null = null;
let currentState: GameStateMessage | null = null;
let localEvents: LocalEvent[] = [];
const queuedCommands = new Map<string, QueueEntry>();
let initialSettingsApplied = false;

const scene = new GameScene();
const game = new Phaser.Game({
  type: Phaser.AUTO,
  width: 960,
  height: 720,
  parent: root,
  backgroundColor: '#06090d',
  scene: [scene],
  antialias: false,
});

scene.setSelectionHandler((unitId) => {
  selectedUnitId = unitId;
  renderSelectedUnit(currentState?.units ?? []);
});

const api = new SwarmApiClient({
  onOpen: () => {
    if (initialSettingsApplied) return;
    initialSettingsApplied = true;
    applySettingsToServer();
  },
  onState: (message) => {
    currentState = message;
    if (!selectedUnitId && message.units.length > 0) {
      selectedUnitId = message.units[0].id;
    }
    scene.setSelectedUnitId(selectedUnitId);
    scene.setState(message);

    if (difficultySelect.value !== message.difficulty) {
      difficultySelect.value = message.difficulty;
    }
    if (profileSelect.value !== message.profile) {
      profileSelect.value = message.profile;
    }

    pauseToggleButton.textContent = message.paused ? 'Resume' : 'Pause';

    renderStatus(message);
    renderMetrics(message);
    renderQueue();
    renderEvents(message.events);
    renderSelectedUnit(message.units);
  },
  onAck: (ack: AckMessage) => {
    if (!ack.ok) {
      appendSyntheticEvent('warning', ack.reason ?? 'Command rejected');
      return;
    }
    if (ack.reason) {
      appendSyntheticEvent('info', ack.reason);
    }
  },
  onQueued: (queued: CommandQueuedMessage) => {
    queuedCommands.set(queued.command_id, {
      id: queued.command_id,
      rawText: queued.raw_text,
      profile: queued.profile,
      queuedAtMs: queued.queued_at_ms,
      etaMs: queued.eta_ms,
      applied: false,
    });
    renderQueue();
  },
  onApplied: (applied: CommandAppliedMessage) => {
    const existing = queuedCommands.get(applied.command_id);
    queuedCommands.set(applied.command_id, {
      id: applied.command_id,
      rawText: existing?.rawText ?? applied.parsed.intent,
      profile: applied.profile,
      queuedAtMs: existing?.queuedAtMs ?? Date.now(),
      etaMs: existing?.etaMs ?? 0,
      applied: true,
      parseLatencyMs: applied.parse_latency_ms,
      latencyMs: applied.latency_ms,
      parsedIntent: applied.parsed.intent,
    });

    parseResult.textContent = `Parsed: ${applied.parsed.intent} -> ${applied.parsed.target_ids.join(', ')} (${applied.parse_latency_ms}ms parse)`;
    appendSyntheticEvent('success', `Applied ${applied.parsed.intent} (${applied.latency_ms}ms)`);
    renderQueue();

    setTimeout(() => {
      queuedCommands.delete(applied.command_id);
      renderQueue();
    }, 6000);
  },
  onWarning: (message: string) => {
    appendSyntheticEvent('warning', message);
  },
  onError: (message: string) => {
    appendSyntheticEvent('warning', message);
  },
});

void bootstrap();

async function bootstrap(): Promise<void> {
  const stored = loadSettings();
  hydrateSettingsUI(stored);

  const session = await api.createSession(undefined, stored.difficulty);
  api.connect(session.session_id);
}

function renderStatus(state: GameStateMessage): void {
  const pills = [
    pill(`Tick ${state.tick}`),
    pill(`Keys ${state.objectives.delivered_keys}/${state.objectives.total_keys}`),
    pill(`Fog ${state.metrics.fog_percent}%`),
    pill(`Queue ${state.queue_depth}`),
    pill(`Profile ${state.profile}`),
    pill(state.paused ? 'Paused' : `Seed ${state.seed}`),
  ];
  statusPills.replaceChildren(...pills);
}

function renderSelectedUnit(units: UnitPublicState[]): void {
  selectedUnitContainer.innerHTML = '';

  const unit = units.find((entry) => entry.id === selectedUnitId) ?? units[0];
  if (!unit) return;
  selectedUnitId = unit.id;
  scene.setSelectedUnitId(selectedUnitId);

  const card = document.createElement('div');
  card.className = 'unit-card';

  const title = document.createElement('div');
  title.className = 'title';
  title.innerHTML = `<strong>${escapeHtml(unit.id)}</strong><span>${escapeHtml(unit.role)}</span>`;

  const badges = document.createElement('div');
  badges.className = 'badge-row';
  badges.append(
    badge(`color ${unit.color}`),
    badge(`mood ${unit.mood}`),
    badge(`vision ${unit.vision}`),
    badge(`hearing ${unit.hearing}`),
  );
  if (unit.carrying_key_id) {
    badges.append(badge(`carrying ${unit.carrying_key_id}`));
  }
  if (unit.active_command) {
    badges.append(badge(`cmd ${unit.active_command}`));
  }
  if (currentState && unit.stunned_until_tick > currentState.tick) {
    badges.append(badge(`stunned ${unit.stunned_until_tick - currentState.tick}t`));
  }

  const position = document.createElement('div');
  position.textContent = `position ${unit.x},${unit.y}`;

  const target = document.createElement('div');
  target.textContent = `goal ${unit.target ? `${unit.target.x},${unit.target.y}` : 'idle'}`;

  card.append(title, badges, position, target);
  selectedUnitContainer.append(card);
}

function renderEvents(events: EventPublic[]): void {
  eventLog.innerHTML = '';

  const items = [
    ...localEvents,
    ...events.map((event) => ({
      id: event.id,
      tickLabel: `${event.tick}`,
      tone: event.tone as LocalTone,
      text: event.text,
    })),
  ].slice(0, 80);

  for (const event of items) {
    const row = document.createElement('div');
    row.className = `event ${event.tone}`;
    row.textContent = `[${event.tickLabel}] ${event.text}`;
    eventLog.append(row);
  }
}

function renderMetrics(state: GameStateMessage): void {
  const metrics = state.metrics;
  metricsPanel.innerHTML = '';

  const entries: Array<[string, string]> = [
    ['Parser last', `${metrics.parser_latency_last_ms}ms`],
    ['Parser avg', `${metrics.parser_latency_avg_ms}ms`],
    ['Planner last', `${metrics.planner_latency_last_ms}ms`],
    ['Planner avg', `${metrics.planner_latency_avg_ms}ms`],
    ['Stuns', `${metrics.stuns}`],
    ['Reroutes', `${metrics.reroutes}`],
    ['Queued', `${metrics.commands_queued}`],
    ['Applied', `${metrics.commands_applied}`],
    ['Timeouts', `${metrics.timeout_count}`],
    ['Model errors', `${metrics.model_error_count}`],
  ];

  entries.forEach(([label, value]) => {
    const node = document.createElement('div');
    node.className = 'metric-item';
    node.innerHTML = `<strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span>`;
    metricsPanel.append(node);
  });
}

function renderQueue(): void {
  queuePanel.innerHTML = '';
  const items = Array.from(queuedCommands.values()).sort((a, b) => b.queuedAtMs - a.queuedAtMs);
  if (items.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'queue-item';
    empty.textContent = 'No queued commands';
    queuePanel.append(empty);
    return;
  }

  for (const item of items.slice(0, 20)) {
    const row = document.createElement('div');
    row.className = `queue-item ${item.applied ? 'done' : ''}`;
    const status = item.applied
      ? `applied ${item.latencyMs ?? 0}ms`
      : `pending ~${Math.max(0, item.etaMs - (Date.now() - item.queuedAtMs))}ms`;
    row.innerHTML = `<strong>${escapeHtml(item.rawText)}</strong><div>${escapeHtml(item.profile)} | ${escapeHtml(status)}${
      item.parsedIntent ? ` | ${escapeHtml(item.parsedIntent)}` : ''
    }</div>`;
    queuePanel.append(row);
  }
}

function appendSyntheticEvent(tone: LocalTone, text: string): void {
  localEvents.unshift({
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    tickLabel: '-',
    tone,
    text,
  });
  if (localEvents.length > MAX_LOCAL_EVENTS) {
    localEvents = localEvents.slice(0, MAX_LOCAL_EVENTS);
  }
  renderEvents(currentState?.events ?? []);
}

function submitCommand(): void {
  const text = commandInput.value.trim();
  if (!text) return;
  api.sendCommand(text, selectedUnitId);
  appendSyntheticEvent('command', `> ${text}`);
  commandInput.value = '';
}

function applySettingsToServer(): void {
  const settings = collectSettingsFromUI();
  persistSettings(settings);

  api.setProfile(settings.profile);
  api.setProviderConfig({
    type: 'set_provider_config',
    base_url: settings.base_url,
    model: settings.model,
    api_key: settings.api_key,
    timeout_ms: settings.timeout_ms,
    max_retries: settings.max_retries,
    artificial_delay_ms: settings.artificial_delay_ms,
  });

  appendSyntheticEvent('system', `Applied settings for ${settings.profile}`);
}

function collectSettingsFromUI(): StoredSettings {
  return {
    profile: profileSelect.value as ProfileName,
    base_url: baseUrlInput.value.trim(),
    model: modelInput.value.trim(),
    api_key: apiKeyInput.value,
    timeout_ms: numberOrDefault(timeoutInput.value, 5000),
    max_retries: numberOrDefault(retriesInput.value, 2),
    artificial_delay_ms: numberOrDefault(delayInput.value, 0),
    difficulty: difficultySelect.value as Difficulty,
  };
}

function hydrateSettingsUI(settings: StoredSettings): void {
  profileSelect.value = settings.profile;
  baseUrlInput.value = settings.base_url;
  modelInput.value = settings.model;
  apiKeyInput.value = settings.api_key;
  timeoutInput.value = String(settings.timeout_ms);
  retriesInput.value = String(settings.max_retries);
  delayInput.value = String(settings.artificial_delay_ms);
  difficultySelect.value = settings.difficulty;
}

function loadSettings(): StoredSettings {
  const fallback: StoredSettings = {
    profile: 'rules',
    base_url: 'http://localhost:11434',
    model: 'llama3.1',
    api_key: '',
    timeout_ms: 5000,
    max_retries: 2,
    artificial_delay_ms: 0,
    difficulty: 'standard',
  };

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<StoredSettings>;
    return {
      profile: (parsed.profile as ProfileName) ?? fallback.profile,
      base_url: parsed.base_url ?? fallback.base_url,
      model: parsed.model ?? fallback.model,
      api_key: parsed.api_key ?? fallback.api_key,
      timeout_ms: parsed.timeout_ms ?? fallback.timeout_ms,
      max_retries: parsed.max_retries ?? fallback.max_retries,
      artificial_delay_ms: parsed.artificial_delay_ms ?? fallback.artificial_delay_ms,
      difficulty: (parsed.difficulty as Difficulty) ?? fallback.difficulty,
    };
  } catch {
    return fallback;
  }
}

function persistSettings(settings: StoredSettings): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

function numberOrDefault(value: string, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

sendButton.addEventListener('click', submitCommand);
commandInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    submitCommand();
  }
});

quickButtons.forEach((button) => {
  button.addEventListener('click', () => {
    commandInput.value = button.dataset.quick ?? '';
    submitCommand();
  });
});

applySettingsButton.addEventListener('click', () => {
  applySettingsToServer();
});

clearApiKeyButton.addEventListener('click', () => {
  apiKeyInput.value = '';
  applySettingsToServer();
  appendSyntheticEvent('system', 'API key cleared from browser storage');
});

resetRunButton.addEventListener('click', () => {
  const seed = seedInput.value.trim() ? numberOrDefault(seedInput.value, Date.now()) : undefined;
  const difficulty = difficultySelect.value as Difficulty;
  api.reset(seed, difficulty);
  queuedCommands.clear();
  renderQueue();
  appendSyntheticEvent('system', `Reset requested (${difficulty}${seed ? `, seed ${seed}` : ''})`);
});

pauseToggleButton.addEventListener('click', () => {
  if (currentState?.paused) {
    api.resume();
  } else {
    api.pause();
  }
});

function pill(text: string): HTMLDivElement {
  const node = document.createElement('div');
  node.className = 'pill';
  node.textContent = text;
  return node;
}

function badge(text: string): HTMLDivElement {
  const node = document.createElement('div');
  node.className = 'badge';
  node.textContent = text;
  return node;
}

function getRequiredElement<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) {
    throw new Error(`missing required element: ${id}`);
  }
  return el as T;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

window.addEventListener('beforeunload', () => {
  game.destroy(true);
});

setInterval(() => {
  renderQueue();
}, 250);
