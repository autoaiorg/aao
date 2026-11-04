/**
 * Tests for Stylized Humanoid Worker Avatar Renderer.
 *
 * Verifies:
 * 1. Strict separation of identity from authority (appearance derived deterministically from ID,
 *    never coupled to permissions, capabilities, or administrative rank).
 * 2. Visual diversity across natural skin tones, professional clothing palettes, and procedural hairstyles.
 * 3. Scene graph compatibility:
 *    - children[0]: Telemetry halo ring
 *    - children[1]: Primary geometry (strictly preserves Defect 2 invariants for STANDING / EPHEMERAL)
 *    - children[2]: Articulated humanoid character rig
 *    - children[3]: Speech bubble sprite
 *    - children[4]: Name & provenance badge sprite
 * 4. Resource pooling: geometry & PBR material sharing without leaks or redundant allocations.
 * 5. Kinematics for typing, conversing, walking, and idle desk postures.
 * 6. Level of Detail (LOD) distance-based throttling.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as THREE from 'three';
import {
  AvatarResourcePool,
  buildAgentAvatar,
  getAvatarAppearanceProfile,
  hashStringSeed,
  stepAvatarKinematics,
  type AgentAnimatedRuntimeState,
} from '../features/office/engine/AvatarRenderer';
import type { AgentIdentity } from '../domain/models';
import type { ProjectedAgentActivity } from '../features/office/engine/officeLifeEngine';

describe('Stylized Humanoid Worker Avatar Renderer (PR A)', () => {
  let pool: AvatarResourcePool;

  beforeEach(() => {
    pool = new AvatarResourcePool();
  });

  afterEach(() => {
    pool.dispose();
  });

  const baseAgent: AgentIdentity = {
    id: 'agent-core-01',
    name: 'Ada Lovelace',
    type: 'STANDING',
    roleTitle: 'Core Systems Architect',
    unitId: 'unit-arch',
    unitName: 'Arquitectura de Sistemas',
    capabilities: [
      { id: 'cap-arch', name: 'System Design', level: 'CERTIFIED', verified: true },
    ],
    heartbeatStatus: 'HEALTHY',
    lastHeartbeatAt: new Date().toISOString(),
    status: 'BUSY',
    currentAssignments: [],
    authorityBoundary: 'Bounded by architecture domain',
  };

  function createMockActivity(
    kind: ProjectedAgentActivity['kind'],
    shortBadge: string
  ): ProjectedAgentActivity {
    return {
      agentId: 'agent-core-01',
      kind,
      shortBadge,
      provenance: 'LIVE_VERIFIED_EVIDENCE',
      label: shortBadge,
      detail: `Activity detail for ${kind}`,
      isLeaseExpired: false,
      activeTaskId: null,
      activeProjectId: null,
      conversationPartnerId: null,
    };
  }

  const idleActivity = createMockActivity('IDLE_DESK', 'EN PUESTO');
  const typingActivity = createMockActivity('TYPING_DEV', 'DESARROLLO');
  const conversingActivity = createMockActivity('CONVERSING', 'COORDINANDO');
  const walkingActivity = createMockActivity('WALKING', 'EN TRÁNSITO');

  function mockCreateSprite(): THREE.Sprite {
    return new THREE.Sprite(new THREE.SpriteMaterial());
  }

  describe('1. Identity & Appearance Hashing vs Authority Separation', () => {
    it('generates consistent, deterministic appearance for the same agent ID', () => {
      const p1 = getAvatarAppearanceProfile(baseAgent, '#10b981');
      const p2 = getAvatarAppearanceProfile(baseAgent, '#10b981');

      expect(p1.clothingPalette).toEqual(p2.clothingPalette);
      expect(p1.skinTone).toBe(p2.skinTone);
      expect(p1.hairStyle).toBe(p2.hairStyle);
      expect(p1.hairColor).toBe(p2.hairColor);
      expect(p1.badgeDepartmentCode).toBe('ARCH');
      expect(p1.badgeAccentHex).toBe('#10b981');
    });

    it('strictly separates identity appearance from authority boundaries, type, and capabilities', () => {
      const baseProfile = getAvatarAppearanceProfile(baseAgent, '#38bdf8');

      // Alter authority, type, capabilities, and status: appearance MUST remain strictly identical
      const modifiedAgent: AgentIdentity = {
        ...baseAgent,
        type: 'EPHEMERAL',
        roleTitle: 'Temporary Auditor',
        status: 'IDLE',
        authorityBoundary: 'Global CEO Overrides Authorized',
        capabilities: [],
      };

      const modifiedProfile = getAvatarAppearanceProfile(modifiedAgent, '#38bdf8');

      expect(modifiedProfile.clothingPalette).toEqual(baseProfile.clothingPalette);
      expect(modifiedProfile.skinTone).toBe(baseProfile.skinTone);
      expect(modifiedProfile.hairStyle).toBe(baseProfile.hairStyle);
      expect(modifiedProfile.hairColor).toBe(baseProfile.hairColor);
    });

    it('produces diverse profiles across different agent IDs', () => {
      const ids = [
        'agent-arch-lead',
        'agent-eng-frontend',
        'agent-ops-sre',
        'agent-gov-custodian',
        'agent-audit-lead',
        'agent-exec-chair',
      ];
      const profiles = ids.map((id) =>
        getAvatarAppearanceProfile({ ...baseAgent, id }, '#38bdf8')
      );

      const uniqueSuits = new Set(profiles.map((p) => p.clothingPalette.suitOrJacket));
      const uniqueSkinTones = new Set(profiles.map((p) => p.skinTone));
      const uniqueHairstyles = new Set(profiles.map((p) => p.hairStyle));

      // With 6 distinct IDs, hashing yields variety across traits
      expect(uniqueSuits.size).toBeGreaterThan(1);
      expect(uniqueSkinTones.size).toBeGreaterThan(1);
      expect(uniqueHairstyles.size).toBeGreaterThan(1);
    });

    it('always generates valid non-negative indices regardless of hash 32-bit sign', () => {
      // Test string with MSB set in 32-bit FNV-1a hash
      const extremeHash = hashStringSeed('test-high-bit-seed');
      expect(extremeHash).toBeGreaterThanOrEqual(0);

      const profile = getAvatarAppearanceProfile({ ...baseAgent, id: 'test-high-bit-seed' });
      expect(profile.skinTone).toBeDefined();
      expect(profile.clothingPalette.suitOrJacket).toBeDefined();
      expect(profile.hairColor).toBeDefined();
      expect(profile.hairStyle).toBeDefined();
    });
  });

  describe('2. Avatar Resource Pooling & Disposal', () => {
    it('reuses materials in cache for identical keys', () => {
      let createCallCount = 0;
      const createMat = () => {
        createCallCount++;
        return new THREE.MeshStandardMaterial({ color: 0x123456 });
      };

      const m1 = pool.getMaterial('custom-key-1', createMat);
      const m2 = pool.getMaterial('custom-key-1', createMat);

      expect(m1).toBe(m2);
      expect(createCallCount).toBe(1);
      expect(pool.ownsMaterial(m1)).toBe(true);
    });

    it('correctly tracks shared geometries and prevents false ownership', () => {
      expect(pool.ownsGeometry(pool.headGeo)).toBe(true);
      expect(pool.ownsGeometry(pool.upperArmGeo)).toBe(true);

      const foreignGeo = new THREE.BoxGeometry(1, 1, 1);
      expect(pool.ownsGeometry(foreignGeo)).toBe(false);
      foreignGeo.dispose();
    });

    it('uses pooled rounded body and limb volumes instead of block-like box segments', () => {
      expect(pool.torsoUpperGeo).toBeInstanceOf(THREE.CapsuleGeometry);
      expect(pool.torsoLowerGeo).toBeInstanceOf(THREE.CapsuleGeometry);
      expect(pool.upperArmGeo).toBeInstanceOf(THREE.CapsuleGeometry);
      expect(pool.forearmGeo).toBeInstanceOf(THREE.CapsuleGeometry);
      expect(pool.thighGeo).toBeInstanceOf(THREE.CapsuleGeometry);
      expect(pool.shinGeo).toBeInstanceOf(THREE.CapsuleGeometry);
      expect(pool.handGeo).toBeInstanceOf(THREE.SphereGeometry);
    });

    it('uses domed cap geometry for non-short hairstyles instead of rectangular hair blocks', () => {
      expect(pool.hairSidePartGeo).toBeInstanceOf(THREE.SphereGeometry);
      expect(pool.hairMidGeo).toBeInstanceOf(THREE.SphereGeometry);
    });

    it('cleans up all geometries and cached materials upon disposal', () => {
      const mat = pool.getMaterial('temp-mat', () => new THREE.MeshBasicMaterial());
      expect(pool.ownsMaterial(mat)).toBe(true);

      pool.dispose();
      // After dispose, cache is cleared
      expect(pool.ownsMaterial(mat)).toBe(false);
    });
  });

  describe('3. Scene Graph Hierarchy & Defect 2 Test Invariants', () => {
    it('builds top-level group with exact 5 children conforming to scene graph contract', () => {
      const group = buildAgentAvatar(baseAgent, idleActivity, pool, {
        departmentAccentHex: '#10b981',
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });

      expect(group.children.length).toBe(5);

      // children[0]: Halo
      expect(group.children[0]).toBeInstanceOf(THREE.Mesh);
      expect(group.children[0].position.y).toBeCloseTo(0.02);

      // children[1]: Primary geometry (STANDING pedestal)
      expect(group.children[1]).toBeInstanceOf(THREE.Mesh);
      expect(group.children[1].position.y).toBeCloseTo(0.06);
      expect(group.children[1].visible).toBe(false);

      // children[2]: Character Rig
      expect(group.children[2]).toBeInstanceOf(THREE.Group);

      // children[3]: Speech Bubble
      expect(group.children[3]).toBeInstanceOf(THREE.Sprite);

      // children[4]: Name & Provenance Label
      expect(group.children[4]).toBeInstanceOf(THREE.Sprite);

      // Semantic parts are exposed in userData.parts
      const parts = group.userData.parts;
      expect(parts).toBeDefined();
      expect(parts.halo).toBe(group.children[0]);
      expect(parts.primaryGeometry).toBe(group.children[1]);
      expect(parts.characterRig).toBe(group.children[2]);
      expect(parts.speechBubble).toBe(group.children[3]);
      expect(parts.nameLabel).toBe(group.children[4]);
      expect(parts.torso).toBeDefined();
      expect(parts.head).toBeDefined();
      expect(parts.neck).toBeDefined();
      expect(parts.hair).toBeDefined();
      expect(parts.badge).toBeDefined();
      expect(parts.leftArm).toBeDefined();
      expect(parts.rightArm).toBeDefined();
      expect(parts.leftLeg).toBeDefined();
      expect(parts.rightLeg).toBeDefined();
    });

    it('renders the ground telemetry halo with a subdued status tint', () => {
      const group = buildAgentAvatar(baseAgent, idleActivity, pool, {
        departmentAccentHex: '#10b981',
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });

      const haloMaterial = (group.userData.parts.halo as THREE.Mesh)
        .material as THREE.MeshBasicMaterial;
      expect(haloMaterial.color.getHex()).toBe(0x668b70);
      expect(haloMaterial.transparent).toBe(true);
      expect(haloMaterial.opacity).toBe(0.24);
      expect(haloMaterial.depthWrite).toBe(false);
    });

    it('creates EPHEMERAL primary geometry at y = 0.58 for ephemeral agents', () => {
      const ephemeralAgent: AgentIdentity = {
        ...baseAgent,
        id: 'agent-bot-ephemeral',
        type: 'EPHEMERAL',
      };

      const group = buildAgentAvatar(ephemeralAgent, idleActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });

      expect(group.children[1].position.y).toBeCloseTo(0.58);
      expect(group.children[1].visible).toBe(false);
      expect(group.userData.agentType).toBe('EPHEMERAL');
    });
  });

  describe('4. Kinematics & Posture States', () => {
    function createRuntime(
      activity: ProjectedAgentActivity,
      agentId: string = baseAgent.id
    ): AgentAnimatedRuntimeState {
      return {
        currentX: 0,
        currentZ: 0,
        currentAngle: 0,
        placement: {
          agentId,
          unitId: 'unit-arch',
          workstationSlot: {
            slotIndex: 0,
            deskLocalX: 0,
            deskLocalZ: 0,
            chairLocalX: 0,
            chairLocalZ: 0.8,
            deskWorldX: 2,
            deskWorldZ: 4,
            chairWorldX: 2,
            chairWorldZ: 4.8,
            facingAngle: 0,
          },
          targetWorldX: 2,
          targetWorldZ: 4,
          targetFacingAngle: Math.PI / 4,
          isSeated: activity.kind !== 'WALKING' && activity.kind !== 'CONVERSING',
          waypoints: [{ x: 0, z: 0 }, { x: 2, z: 4 }],
          activity,
        },
      };
    }

    it('articulates typing kinematics: arms raised over desk, legs seated, speech bubble hidden', () => {
      const group = buildAgentAvatar(baseAgent, typingActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });
      const runtime = createRuntime(typingActivity);

      stepAvatarKinematics(group, runtime, 1000, 15);

      const parts = group.userData.parts;
      // Invariant: arms raised over keyboard (rotation.x < -0.5)
      expect(parts.leftArm.rotation.x).toBeLessThan(-0.5);
      expect(parts.rightArm.rotation.x).toBeLessThan(-0.5);
      // Legs horizontal in chair
      expect(parts.leftLeg.rotation.x).toBeCloseTo(-Math.PI / 2.3, 1);
      expect(parts.rightLeg.rotation.x).toBeCloseTo(-Math.PI / 2.3, 1);
      // Speech bubble hidden
      expect(parts.speechBubble.visible).toBe(false);
      // STANDING pedestal invariant: stays stationary at 0.06
      expect(group.children[1].position.y).toBeCloseTo(0.06);
    });

    it('articulates conversing kinematics: speech bubble visible and animated, conversational arm gestures', () => {
      const group = buildAgentAvatar(baseAgent, conversingActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });
      const runtime = createRuntime(conversingActivity);

      stepAvatarKinematics(group, runtime, 1200, 15);

      const parts = group.userData.parts;
      // Speech bubble is visible
      expect(parts.speechBubble.visible).toBe(true);
      expect(parts.speechBubble.position.y).toBeGreaterThan(1.5);
      // Legs upright
      expect(parts.leftLeg.rotation.x).toBe(0);
      expect(parts.rightLeg.rotation.x).toBe(0);
    });

    it('articulates walking kinematics: leg swing with knee flexion and counter-arm swing', () => {
      const group = buildAgentAvatar(baseAgent, walkingActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });
      const runtime = createRuntime(walkingActivity);

      stepAvatarKinematics(group, runtime, 500, 15);

      const parts = group.userData.parts;
      // Counter-phase arms and legs
      expect(parts.leftLeg.rotation.x).toBeCloseTo(-parts.rightLeg.rotation.x, 2);
      expect(parts.leftArm.rotation.x).toBeCloseTo(-parts.rightArm.rotation.x, 2);
      expect(parts.speechBubble.visible).toBe(false);
    });

    it('preserves Defect 2 invariant: EPHEMERAL crystal animates while STANDING pedestal does not', () => {
      const ephemeralAgent: AgentIdentity = {
        ...baseAgent,
        id: 'agent-ephemeral-test',
        type: 'EPHEMERAL',
      };
      const standingAgent: AgentIdentity = {
        ...baseAgent,
        id: 'agent-standing-test',
        type: 'STANDING',
      };

      const ephGroup = buildAgentAvatar(ephemeralAgent, idleActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });
      const stGroup = buildAgentAvatar(standingAgent, idleActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });

      const ephRuntime = createRuntime(idleActivity);
      const stRuntime = createRuntime(idleActivity);

      stepAvatarKinematics(ephGroup, ephRuntime, 2500, 15);
      stepAvatarKinematics(stGroup, stRuntime, 2500, 15);

      // Ephemeral geometry rotated and bobbed
      expect(ephGroup.children[1].rotation.y).not.toBe(0);
      expect(ephGroup.children[1].position.y).not.toBe(0.58);

      // Standing pedestal strictly remained at 0.06 and rotation 0
      expect(stGroup.children[1].position.y).toBeCloseTo(0.06);
      expect(stGroup.children[1].rotation.y).toBe(0);
    });

    it('respects reducedMotion by disabling continuous oscillations', () => {
      const group = buildAgentAvatar(baseAgent, typingActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });
      const runtime = createRuntime(typingActivity);

      stepAvatarKinematics(group, runtime, 1000, 15, { reducedMotion: true });

      // In reducedMotion mode, coordinates are set statically to target
      expect(group.position.x).toBe(2);
      expect(group.position.z).toBe(4);
    });

    it('throttles secondary jitter when camera distance > 26 (LOD optimization)', () => {
      const groupClose = buildAgentAvatar(baseAgent, typingActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });
      const groupFar = buildAgentAvatar(baseAgent, typingActivity, pool, {
        createSpeechBubbleSprite: mockCreateSprite,
        createAgentNameSprite: mockCreateSprite,
      });

      const runtimeClose = createRuntime(typingActivity);
      const runtimeFar = createRuntime(typingActivity);

      stepAvatarKinematics(groupClose, runtimeClose, 777, 15); // camera close (< 26)
      stepAvatarKinematics(groupFar, runtimeFar, 777, 35); // camera far (> 26)

      const partsFar = groupFar.userData.parts;
      // When far away, typing arm jitter is 0, so rotation.x is exactly base posture -0.82
      expect(partsFar.leftArm.rotation.x).toBeCloseTo(-0.82, 4);
      expect(partsFar.head.rotation.y).toBe(0);
    });
  });
});
