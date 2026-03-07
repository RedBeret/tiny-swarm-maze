import Phaser from 'phaser';
import type { GameStateMessage, TrapPublicState, UnitPublicState } from './types';

const TILE = 24;
const MAP_MARGIN_X = 18;
const MAP_MARGIN_Y = 18;

const UNIT_COLORS: Record<string, number> = {
  blue: 0x5ca8ff,
  red: 0xff7979,
  yellow: 0xffd166,
  green: 0x63e6be,
  purple: 0xcba6f7,
  cyan: 0x7dd3fc,
};

export class GameScene extends Phaser.Scene {
  private state: GameStateMessage | null = null;
  private mapGraphics!: Phaser.GameObjects.Graphics;
  private overlayGraphics!: Phaser.GameObjects.Graphics;
  private unitGraphics!: Phaser.GameObjects.Graphics;
  private readonly bubbleTexts: Phaser.GameObjects.Text[] = [];
  private selectedUnitId: string | null = null;
  private onSelectUnit: (unitId: string | null) => void = () => {};
  private lastSize: { w: number; h: number } = { w: 0, h: 0 };

  constructor() {
    super('game');
  }

  create(): void {
    this.mapGraphics = this.add.graphics();
    this.overlayGraphics = this.add.graphics();
    this.unitGraphics = this.add.graphics();

    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      if (!this.state) return;
      const cellX = Math.floor((pointer.x - MAP_MARGIN_X) / TILE);
      const cellY = Math.floor((pointer.y - MAP_MARGIN_Y) / TILE);
      const hit = this.state.units.find((unit) => unit.x === cellX && unit.y === cellY);
      this.selectedUnitId = hit?.id ?? null;
      this.onSelectUnit(this.selectedUnitId);
      this.renderState();
    });
  }

  public setSelectionHandler(handler: (unitId: string | null) => void): void {
    this.onSelectUnit = handler;
  }

  public setSelectedUnitId(unitId: string | null): void {
    this.selectedUnitId = unitId;
    this.renderState();
  }

  public setState(state: GameStateMessage): void {
    this.state = state;
    this.resizeToBoard(state);
    if (!this.selectedUnitId && state.units.length > 0) {
      this.selectedUnitId = state.units[0].id;
      this.onSelectUnit(this.selectedUnitId);
    }
    this.renderState();
  }

  private resizeToBoard(state: GameStateMessage): void {
    const width = state.width * TILE + MAP_MARGIN_X * 2;
    const height = state.height * TILE + MAP_MARGIN_Y * 2;
    if (width === this.lastSize.w && height === this.lastSize.h) {
      return;
    }
    this.lastSize = { w: width, h: height };
    this.scale.resize(width, height);
  }

  private renderState(): void {
    if (!this.mapGraphics || !this.overlayGraphics || !this.unitGraphics) return;

    this.mapGraphics.clear();
    this.overlayGraphics.clear();
    this.unitGraphics.clear();
    this.bubbleTexts.forEach((bubble) => bubble.destroy());
    this.bubbleTexts.length = 0;

    if (!this.state) return;

    const discovered = new Set(this.state.discovered_tiles);

    for (let y = 0; y < this.state.height; y += 1) {
      for (let x = 0; x < this.state.width; x += 1) {
        const drawX = MAP_MARGIN_X + x * TILE;
        const drawY = MAP_MARGIN_Y + y * TILE;
        const key = `${x},${y}`;

        if (!discovered.has(key)) {
          this.mapGraphics.fillStyle(0x06090d, 1);
          this.mapGraphics.fillRect(drawX, drawY, TILE - 1, TILE - 1);
          continue;
        }

        if (this.state.grid[y][x] === 1) {
          this.mapGraphics.fillStyle(0x3a4254, 1);
          this.mapGraphics.fillRect(drawX, drawY, TILE - 1, TILE - 1);
          this.mapGraphics.fillStyle(0x232936, 1);
          this.mapGraphics.fillRect(drawX + 4, drawY + 4, TILE - 9, TILE - 9);
        } else {
          this.mapGraphics.fillStyle(0x151925, 1);
          this.mapGraphics.fillRect(drawX, drawY, TILE - 1, TILE - 1);
        }
      }
    }

    this.drawExit(discovered);
    this.drawKeys(discovered);
    this.drawTraps(discovered, this.state.traps);
    this.drawUnits();
  }

  private drawExit(discovered: Set<string>): void {
    if (!this.state) return;
    const key = `${this.state.exit.x},${this.state.exit.y}`;
    if (!discovered.has(key)) return;

    const drawX = MAP_MARGIN_X + this.state.exit.x * TILE + TILE / 2;
    const drawY = MAP_MARGIN_Y + this.state.exit.y * TILE + TILE / 2;
    this.overlayGraphics.fillStyle(0x48bb78, 1);
    this.overlayGraphics.fillTriangle(drawX - 7, drawY + 7, drawX - 7, drawY - 8, drawX + 8, drawY - 1);
    this.overlayGraphics.fillStyle(0xe6fffa, 1);
    this.overlayGraphics.fillRect(drawX - 10, drawY + 7, 3, 9);
  }

  private drawKeys(discovered: Set<string>): void {
    if (!this.state) return;

    for (const keyItem of this.state.keys) {
      if (keyItem.delivered || keyItem.carried_by || !keyItem.found) continue;
      const key = `${keyItem.x},${keyItem.y}`;
      if (!discovered.has(key)) continue;

      const drawX = MAP_MARGIN_X + keyItem.x * TILE + TILE / 2;
      const drawY = MAP_MARGIN_Y + keyItem.y * TILE + TILE / 2;
      this.overlayGraphics.fillStyle(0xf6c85f, 1);
      this.overlayGraphics.fillRect(drawX - 4, drawY - 4, 8, 8);
      this.overlayGraphics.fillStyle(0xfff4cf, 1);
      this.overlayGraphics.fillRect(drawX - 1, drawY - 1, 2, 2);
    }
  }

  private drawTraps(discovered: Set<string>, traps: TrapPublicState[]): void {
    for (const trap of traps) {
      if (!trap.revealed) continue;
      const key = `${trap.x},${trap.y}`;
      if (!discovered.has(key)) continue;

      const drawX = MAP_MARGIN_X + trap.x * TILE + TILE / 2;
      const drawY = MAP_MARGIN_Y + trap.y * TILE + TILE / 2;
      const color = trap.active ? 0xff6b6b : 0x718096;
      this.overlayGraphics.lineStyle(2, color, 1);
      this.overlayGraphics.strokeCircle(drawX, drawY, 7);
      this.overlayGraphics.beginPath();
      this.overlayGraphics.moveTo(drawX - 4, drawY - 4);
      this.overlayGraphics.lineTo(drawX + 4, drawY + 4);
      this.overlayGraphics.moveTo(drawX + 4, drawY - 4);
      this.overlayGraphics.lineTo(drawX - 4, drawY + 4);
      this.overlayGraphics.strokePath();
    }
  }

  private drawUnits(): void {
    if (!this.state) return;

    for (const unit of this.state.units) {
      this.drawUnit(unit);
    }
  }

  private drawUnit(unit: UnitPublicState): void {
    const drawX = MAP_MARGIN_X + unit.x * TILE + 3;
    const drawY = MAP_MARGIN_Y + unit.y * TILE + 3;
    const color = UNIT_COLORS[unit.color] ?? 0xffffff;

    if (this.selectedUnitId === unit.id) {
      this.unitGraphics.lineStyle(2, 0xf8fafc, 1);
      this.unitGraphics.strokeRoundedRect(drawX - 3, drawY - 3, TILE - 1, TILE - 1, 6);
    }

    this.unitGraphics.fillStyle(color, 1);
    this.unitGraphics.fillRoundedRect(drawX, drawY, TILE - 6, TILE - 6, 5);

    this.unitGraphics.fillStyle(0x0f172a, 1);
    this.unitGraphics.fillRect(drawX + 5, drawY + 4, 2, 2);
    this.unitGraphics.fillRect(drawX + 11, drawY + 4, 2, 2);

    if (unit.stunned_until_tick > (this.state?.tick ?? 0)) {
      this.unitGraphics.fillStyle(0xffe066, 1);
      this.unitGraphics.fillCircle(drawX + 8, drawY - 2, 3);
    }

    if (unit.carrying_key_id) {
      this.unitGraphics.fillStyle(0xf6c85f, 1);
      this.unitGraphics.fillRect(drawX + 7, drawY - 3, 6, 3);
    }

    if (unit.target) {
      this.unitGraphics.lineStyle(1, color, 0.5);
      this.unitGraphics.lineBetween(
        drawX + 8,
        drawY + 8,
        MAP_MARGIN_X + unit.target.x * TILE + TILE / 2,
        MAP_MARGIN_Y + unit.target.y * TILE + TILE / 2,
      );
    }

    if (unit.bubble) {
      const bubble = this.add.text(drawX - 2, drawY - 17, unit.bubble, {
        color: '#f8fafc',
        backgroundColor: '#111827dd',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: '10px',
        padding: { left: 5, right: 5, top: 3, bottom: 3 },
      });
      this.bubbleTexts.push(bubble);
    }
  }

  public getSelectedUnit(state: GameStateMessage | null): UnitPublicState | null {
    if (!state || !this.selectedUnitId) return null;
    return state.units.find((unit) => unit.id === this.selectedUnitId) ?? null;
  }
}
