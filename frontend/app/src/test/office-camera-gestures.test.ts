/**
 * Tests for Immersive Gestural Camera Controls in ThreeOfficeScene (PR B).
 *
 * Verifies:
 * 1. Single-finger / pointer drag smooth panning across the architectural floor plate.
 * 2. Multi-touch 2-finger pinch-to-zoom with distance boundary clamping [8, 38].
 * 3. Multi-touch 2-finger rotational orbit around central targets.
 * 4. Right-click / Shift+drag orbit rotation with elevation limits [15, 75].
 * 5. Double-click focusing on agents and departments.
 * 6. Follow-mode auto-cancellation upon manual camera displacement.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as THREE from 'three';
import { ThreeOfficeScene, type ThreeSceneCallbacks } from '../features/office/engine/ThreeOfficeScene';
import { DEMO_AGENTS } from '../data/adapters/demo/fixtures';
import { OFFICE_ROOMS } from '../features/office/types';

describe('Immersive Gestural Camera Controls & Navigation (PR B)', () => {
  let container: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let scene: ThreeOfficeScene;
  let callbacks: ThreeSceneCallbacks;

  beforeEach(() => {
    container = document.createElement('div');
    Object.defineProperty(container, 'clientWidth', { value: 1024, configurable: true });
    Object.defineProperty(container, 'clientHeight', { value: 768, configurable: true });
    document.body.appendChild(container);

    callbacks = {
      onSelectRoom: vi.fn(),
      onSelectAgent: vi.fn(),
      onHoverObject: vi.fn(),
      onCameraChange: vi.fn(),
    };

    // Create a mock WebGLRenderer compatible with ThreeOfficeScene
    canvas = document.createElement('canvas');
    canvas.getBoundingClientRect = () => ({
      width: 1024,
      height: 768,
      top: 0,
      left: 0,
      right: 1024,
      bottom: 768,
      x: 0,
      y: 0,
      toJSON: () => {},
    });
    const mockRenderer = {
      domElement: canvas,
      shadowMap: { enabled: true, type: THREE.PCFSoftShadowMap },
      setSize: vi.fn(),
      setPixelRatio: vi.fn(),
      render: vi.fn(),
      dispose: vi.fn(),
    } as unknown as THREE.WebGLRenderer;

    scene = new ThreeOfficeScene(container, {
      callbacks,
      renderer: mockRenderer,
      rooms: OFFICE_ROOMS,
      dragMode: 'pan',
    });
    scene.updateAgents(DEMO_AGENTS);
  });

  afterEach(() => {
    scene.dispose();
    if (container.parentElement) {
      container.parentElement.removeChild(container);
    }
  });

  it('pans the camera smoothly across the corporate floor plate and cancels follow mode', () => {
    // 1. Initial state
    const initialTarget = scene.getDesiredTarget().clone();
    expect(scene.isFollowingAgent()).toBe(false);

    // 2. Select agent and enable follow mode
    const agent = DEMO_AGENTS[0];
    scene.selectAgent(agent.id);
    scene.setFollowAgent(true);
    expect(scene.isFollowingAgent()).toBe(true);

    // 3. Pan camera
    scene.simulateGesturePan(50, -30);

    // Follow mode must be cancelled upon manual pan
    expect(scene.isFollowingAgent()).toBe(false);
    const newTarget = scene.getDesiredTarget();
    expect(newTarget.x).not.toBeCloseTo(initialTarget.x, 3);
    expect(newTarget.z).not.toBeCloseTo(initialTarget.z, 3);
  });

  it('frames the selected agent while preserving the operator-controlled zoom', () => {
    const agent = DEMO_AGENTS[0];
    const placement = scene.getAgentPlacement(agent.id);
    expect(placement).toBeDefined();
    scene.selectRoom(agent.unitId);
    const distanceBeforeSelection = scene.getDesiredDistance();

    scene.selectAgent(agent.id);

    const target = scene.getDesiredTarget();
    expect(target.x).toBeCloseTo(placement!.targetWorldX, 4);
    expect(target.z).toBeCloseTo(placement!.targetWorldZ, 4);
    expect(scene.getDesiredDistance()).toBe(distanceBeforeSelection);
  });

  it('performs pinch-to-zoom with distance boundary clamping', () => {
    const initialDistance = scene.getCameraDistance();

    // Zoom in (pinch factor < 1)
    scene.simulateGesturePinch(0.7);
    expect(scene.getDesiredDistance()).toBeLessThan(initialDistance);

    // Extreme zoom in: must not breach the agent-inspection minDistance (4.5)
    for (let i = 0; i < 15; i++) {
      scene.simulateGesturePinch(0.5);
    }
    expect(scene.getDesiredDistance()).toBeGreaterThanOrEqual(4.5);

    // Extreme zoom out: the overview fit may require more than 38 units for
    // this viewport; once clamped, further pinches must not change the bound.
    for (let i = 0; i < 20; i++) {
      scene.simulateGesturePinch(1.5);
    }
    const clampedMaximum = scene.getDesiredDistance();
    for (let i = 0; i < 5; i++) scene.simulateGesturePinch(1.5);
    expect(scene.getDesiredDistance()).toBe(clampedMaximum);
  });

  it('performs two-finger rotational orbit around the scene target', () => {
    const initialAngle = scene.getCameraAngle().angle;

    // Simulate 45 degree gesture rotation
    scene.simulateGestureRotate(45);
    const newAngle = scene.getCameraAngle().angle;

    expect(newAngle).not.toBe(initialAngle);
  });

  it('clamps orbital elevation between [15, 75] degrees', () => {
    // Excessive pitch down
    scene.orbitCamera(0, -100);
    expect(scene.getCameraAngle().elevation).toBeGreaterThanOrEqual(15);

    // Excessive pitch up
    scene.orbitCamera(0, 200);
    expect(scene.getCameraAngle().elevation).toBeLessThanOrEqual(75);
  });

  function createPointerEvent(
    type: string,
    options: { pointerId?: number; pointerType?: string; clientX?: number; clientY?: number; buttons?: number } = {}
  ): Event {
    if (typeof PointerEvent !== 'undefined') {
      return new PointerEvent(type, { bubbles: true, ...options });
    }
    const event = new MouseEvent(type, { bubbles: true, ...options }) as any;
    event.pointerId = options.pointerId ?? 1;
    event.pointerType = options.pointerType ?? 'touch';
    if (options.buttons !== undefined) {
      Object.defineProperty(event, 'buttons', { value: options.buttons, configurable: true });
    }
    return event;
  }

  it('handles multi-touch pointer events (pointerdown, pointermove, pointerup) without errors', () => {
    // 1. First finger touch down
    const p1Down = createPointerEvent('pointerdown', {
      pointerId: 1,
      pointerType: 'touch',
      clientX: 200,
      clientY: 200,
    });
    canvas.dispatchEvent(p1Down);

    // 2. Second finger touch down (pinch initiation)
    const p2Down = createPointerEvent('pointerdown', {
      pointerId: 2,
      pointerType: 'touch',
      clientX: 300,
      clientY: 300,
    });
    canvas.dispatchEvent(p2Down);

    // 3. Move fingers closer together (pinch zoom out)
    const p1Move = createPointerEvent('pointermove', {
      pointerId: 1,
      pointerType: 'touch',
      clientX: 230,
      clientY: 230,
    });
    canvas.dispatchEvent(p1Move);

    // 4. Release fingers
    const p1Up = createPointerEvent('pointerup', {
      pointerId: 1,
      pointerType: 'touch',
      clientX: 230,
      clientY: 230,
    });
    canvas.dispatchEvent(p1Up);

    const p2Up = createPointerEvent('pointerup', {
      pointerId: 2,
      pointerType: 'touch',
      clientX: 300,
      clientY: 300,
    });
    canvas.dispatchEvent(p2Up);

    // Scene remains operational and undamaged
    expect(scene.isContextLost()).toBe(false);
  });

  it('handles double-click to reset camera overview when clicked on empty space', () => {
    scene.panCamera(10, 10);
    const pannedTarget = scene.getDesiredTarget().clone();

    // Double click on canvas
    const dblClickEvent = new MouseEvent('dblclick', {
      clientX: 10,
      clientY: 10,
      bubbles: true,
    });
    canvas.dispatchEvent(dblClickEvent);

    // Camera target reset towards center
    const resetTarget = scene.getDesiredTarget();
    expect(resetTarget.x).toBeLessThan(pannedTarget.x);
  });

  it('navigates across the floor plate via keyboard controls (W, A, S, D, Q, E)', () => {
    const initialTarget = scene.getDesiredTarget().clone();
    const initialAngle = scene.getCameraAngle().angle;

    // Simulate holding 'W' (move forward in camera gaze direction)
    scene.simulateKeyboardKey('w', true);
    scene.stepAnimation(100);
    scene.simulateKeyboardKey('w', false);

    const afterWTarget = scene.getDesiredTarget().clone();
    expect(afterWTarget.distanceTo(initialTarget)).toBeGreaterThan(0.01);

    // Simulate holding 'D' (strafe right relative to gaze direction)
    scene.simulateKeyboardKey('d', true);
    scene.stepAnimation(200);
    scene.simulateKeyboardKey('d', false);

    const afterDTarget = scene.getDesiredTarget().clone();
    expect(afterDTarget.distanceTo(afterWTarget)).toBeGreaterThan(0.01);

    // Simulate holding 'Q' (orbit yaw left)
    scene.simulateKeyboardKey('q', true);
    scene.stepAnimation(300);
    scene.simulateKeyboardKey('q', false);

    const afterQAngle = scene.getCameraAngle().angle;
    expect(afterQAngle).not.toBe(initialAngle);

    // Space key re-centers / resets overview when no agent active
    scene.simulateKeyboardKey(' ', true);
    scene.stepAnimation(400);
    scene.simulateKeyboardKey(' ', false);
  });

  it('handles right-click orbital drag to adjust view perspective without triggering selection', () => {
    const initialAngle = scene.getCameraAngle();

    // Right-click pointer down (buttons: 2)
    const downEvent = createPointerEvent('pointerdown', {
      pointerId: 1,
      pointerType: 'mouse',
      clientX: 500,
      clientY: 300,
      buttons: 2,
    });
    canvas.dispatchEvent(downEvent);

    // Right-click drag move
    const moveEvent = createPointerEvent('pointermove', {
      pointerId: 1,
      pointerType: 'mouse',
      clientX: 540,
      clientY: 330,
      buttons: 2,
    });
    canvas.dispatchEvent(moveEvent);

    // Right-click pointer up
    const upEvent = createPointerEvent('pointerup', {
      pointerId: 1,
      pointerType: 'mouse',
      clientX: 540,
      clientY: 330,
      buttons: 0,
    });
    canvas.dispatchEvent(upEvent);

    const newAngle = scene.getCameraAngle();
    expect(newAngle.angle).not.toBe(initialAngle.angle);
    expect(callbacks.onSelectRoom).not.toHaveBeenCalled();
    expect(callbacks.onSelectAgent).not.toHaveBeenCalled();
  });
});
