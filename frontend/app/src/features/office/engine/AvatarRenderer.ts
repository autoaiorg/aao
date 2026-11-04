/**
 * Humanoid Worker Avatar Renderer for AAO Living Office 3D.
 *
 * Implements stylized architectural realism with natural human proportions (1:7.5),
 * professional attire, deterministic identity hashing, procedural hairstyles,
 * corporate AAO lanyards/badges, and anatomical kinematics.
 *
 * Architecture strictly separates:
 * 1. Visual appearance (deterministic per agent ID hash)
 * 2. Enterprise authority & permissions (governed solely by AAO backend)
 * 3. Activity telemetry & provenance (reflects verified work from API)
 *
 * Preserves exact scene graph compatibility:
 * - children[0]: Telemetry halo ring (RingGeometry)
 * - children[1]: Primary agent geometry (pedestal / ephemeral crystal for Defect 2 contracts)
 * - children[2]: Articulated character rig (humanoid worker model)
 * - children[3]: Speech bubble sprite (active during CONVERSING)
 * - children[4]: Name & provenance badge sprite
 */

import * as THREE from 'three';
import type { AgentIdentity } from '../../../domain/models';
import type { PlannedAgentPlacement, ProjectedAgentActivity } from './officeLifeEngine';

export type HairStyleId = 'SHORT_CLASSIC' | 'EXECUTIVE_SIDE_PART' | 'CROP_TEXTURED' | 'MODERN_MID';

export interface AvatarClothingPalette {
  suitOrJacket: number;
  shirt: number;
  trousers: number;
  shoes: number;
}

export interface AvatarAppearanceProfile {
  clothingPalette: AvatarClothingPalette;
  skinTone: number;
  hairStyle: HairStyleId;
  hairColor: number;
  badgeDepartmentCode: string;
  badgeAccentHex: string;
}

export interface AvatarSemanticParts {
  halo: THREE.Mesh;
  primaryGeometry: THREE.Mesh;
  characterRig: THREE.Group;
  torso?: THREE.Object3D;
  head?: THREE.Object3D;
  neck?: THREE.Object3D;
  hair?: THREE.Object3D;
  badge?: THREE.Object3D;
  leftArm?: THREE.Object3D;
  rightArm?: THREE.Object3D;
  leftForearm?: THREE.Object3D;
  rightForearm?: THREE.Object3D;
  leftHand?: THREE.Object3D;
  rightHand?: THREE.Object3D;
  coffeeCup?: THREE.Group;
  leftLeg?: THREE.Object3D;
  rightLeg?: THREE.Object3D;
  leftShin?: THREE.Object3D;
  rightShin?: THREE.Object3D;
  leftShoe?: THREE.Object3D;
  rightShoe?: THREE.Object3D;
  speechBubble?: THREE.Sprite;
  nameLabel: THREE.Sprite;
}

export interface AgentAnimatedRuntimeState {
  currentX: number;
  currentZ: number;
  currentAngle: number;
  placement: PlannedAgentPlacement;
}

// Professional corporate clothing palettes (business casual & executive tailored tones)
const CORPORATE_PALETTES: readonly AvatarClothingPalette[] = [
  { suitOrJacket: 0x242a38, shirt: 0xf1f5f9, trousers: 0x1e2430, shoes: 0x12151c }, // Charcoal Navy
  { suitOrJacket: 0x1d2e4a, shirt: 0xdbeafe, trousers: 0x2b3442, shoes: 0x201a17 }, // Classic Blue / Oxford
  { suitOrJacket: 0x364152, shirt: 0xf8fafc, trousers: 0x1f2937, shoes: 0x181a1f }, // Slate Tailored
  { suitOrJacket: 0x2c3b32, shirt: 0xf1f5f9, trousers: 0x252e28, shoes: 0x1a1a1a }, // Forest Olive Tech
  { suitOrJacket: 0x47392b, shirt: 0xfef3c7, trousers: 0x262b36, shoes: 0x29160e }, // Warm Espresso / Camel
  { suitOrJacket: 0x3f3d56, shirt: 0xe2e8f0, trousers: 0x232333, shoes: 0x141419 }, // Deep Twilight Grey
  { suitOrJacket: 0x2a3d45, shirt: 0xe0f2fe, trousers: 0x1b282e, shoes: 0x161c20 }, // Steel Petrol
  { suitOrJacket: 0x383431, shirt: 0xf5f5f4, trousers: 0x292524, shoes: 0x1c1917 }, // Warm Stone / Umber
];

const NATURAL_SKIN_TONES: readonly number[] = [
  0xf6d6be, // Warm fair
  0xecba9d, // Light peach
  0xdfb18b, // Neutral beige
  0xc6966f, // Warm honey
  0xb27c54, // Warm tan
  0x8f5d3a, // Chestnut
  0x633d23, // Deep rich espresso
];

const NATURAL_HAIR_COLORS: readonly number[] = [
  0x1a1a1c, // Jet black
  0x2b1e17, // Dark chocolate
  0x463223, // Warm hazelnut
  0x5c3d28, // Chestnut auburn
  0x785a3d, // Ash brown
  0x9c7f55, // Dark blonde
  0x59595f, // Steel slate / mature grey
];

const HAIR_STYLES: readonly HairStyleId[] = [
  'SHORT_CLASSIC',
  'EXECUTIVE_SIDE_PART',
  'CROP_TEXTURED',
  'MODERN_MID',
];

/**
 * Pure deterministic hash from string to positive 32-bit integer.
 */
export function hashStringSeed(str: string): number {
  let hash = 2166136261;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

/**
 * Computes a stable visual profile from agent identity.
 * Strictly separates appearance from authority: hair, skin, and clothing are
 * randomly-uniform hashes of ID, never tied to permissions or capabilities.
 */
export function getAvatarAppearanceProfile(
  agent: AgentIdentity,
  departmentAccentHex: string = '#38bdf8'
): AvatarAppearanceProfile {
  const seed = hashStringSeed(agent.id);
  const paletteIdx = Math.abs(seed) % CORPORATE_PALETTES.length;
  const skinIdx = Math.abs(seed >>> 3) % NATURAL_SKIN_TONES.length;
  const hairStyleIdx = Math.abs(seed >>> 6) % HAIR_STYLES.length;
  const hairColorIdx = Math.abs(seed >>> 9) % NATURAL_HAIR_COLORS.length;

  return {
    clothingPalette: CORPORATE_PALETTES[paletteIdx],
    skinTone: NATURAL_SKIN_TONES[skinIdx],
    hairStyle: HAIR_STYLES[hairStyleIdx],
    hairColor: NATURAL_HAIR_COLORS[hairColorIdx],
    badgeDepartmentCode: agent.unitId ? agent.unitId.replace(/^unit-/, '').toUpperCase() : 'AAO',
    badgeAccentHex: departmentAccentHex,
  };
}

/**
 * Centralized pool of reusable Three.js geometries and standard PBR materials
 * to maximize GPU instancing and avoid allocations in the render loop.
 */
export class AvatarResourcePool {
  // Shared limb & torso geometries
  public readonly torsoUpperGeo: THREE.BufferGeometry;
  public readonly torsoLowerGeo: THREE.BufferGeometry;
  public readonly neckGeo: THREE.BufferGeometry;
  public readonly headGeo: THREE.BufferGeometry;
  public readonly hairShortGeo: THREE.BufferGeometry;
  public readonly hairSidePartGeo: THREE.BufferGeometry;
  public readonly hairCropGeo: THREE.BufferGeometry;
  public readonly hairMidGeo: THREE.BufferGeometry;

  public readonly shoulderGeo: THREE.BufferGeometry;
  public readonly upperArmGeo: THREE.BufferGeometry;
  public readonly forearmGeo: THREE.BufferGeometry;
  public readonly handGeo: THREE.BufferGeometry;

  public readonly hipPelvisGeo: THREE.BufferGeometry;
  public readonly thighGeo: THREE.BufferGeometry;
  public readonly shinGeo: THREE.BufferGeometry;
  public readonly shoeGeo: THREE.BufferGeometry;

  // Lanyard & Badge
  public readonly lanyardGeo: THREE.BufferGeometry;
  public readonly badgeCardGeo: THREE.BufferGeometry;
  public readonly badgeClipGeo: THREE.BufferGeometry;

  // Backward-compatibility primary geometries
  public readonly haloGeo: THREE.BufferGeometry;
  public readonly standingPedestalGeo: THREE.BufferGeometry;
  public readonly ephemeralCrystalGeo: THREE.BufferGeometry;
  public readonly neutralPedestalGeo: THREE.BufferGeometry;

  // Materials cache
  private readonly materialsCache = new Map<string, THREE.Material>();
  private readonly allGeometries = new Set<THREE.BufferGeometry>();

  constructor() {
    // Upper torso (Chest & broad shoulders, tapered)
    this.torsoUpperGeo = new THREE.CapsuleGeometry(0.1, 0.12, 4, 12);
    this.torsoUpperGeo.scale(1.55, 0.72, 0.82);

    // Lower torso (Waist & jacket hem)
    this.torsoLowerGeo = new THREE.CapsuleGeometry(0.075, 0.08, 4, 10);
    this.torsoLowerGeo.scale(1.7, 0.7, 1);

    // Neck
    this.neckGeo = new THREE.CylinderGeometry(0.045, 0.052, 0.07, 12);

    // Head (Subtly anatomical proportion, scaled sphere)
    this.headGeo = new THREE.SphereGeometry(0.115, 16, 14);
    this.headGeo.scale(0.88, 1.05, 0.96);

    // Hairstyle variants
    // 1. Short classic: compact skull cap with side burns
    this.hairShortGeo = new THREE.SphereGeometry(0.122, 14, 12, 0, Math.PI * 2, 0, Math.PI * 0.58);
    this.hairShortGeo.scale(0.92, 1.08, 0.98);

    // 2. Executive side part: slightly raised volume with swept asymmetry
    this.hairSidePartGeo = new THREE.SphereGeometry(0.12, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.56);
    this.hairSidePartGeo.scale(0.98, 0.78, 0.92);

    // 3. Crop textured: clean modern crop with forward crown
    this.hairCropGeo = new THREE.CylinderGeometry(0.11, 0.124, 0.07, 12);

    // 4. Modern mid-length: frames temples with gentle cheek drop
    this.hairMidGeo = new THREE.SphereGeometry(0.12, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.62);
    this.hairMidGeo.scale(1, 1.04, 0.98);

    // Arms: shoulder pivot, upper arm, forearm, hand
    this.shoulderGeo = new THREE.SphereGeometry(0.048, 10, 8);
    this.upperArmGeo = new THREE.CapsuleGeometry(0.035, 0.12, 3, 8);
    this.forearmGeo = new THREE.CapsuleGeometry(0.032, 0.11, 3, 8);
    this.handGeo = new THREE.SphereGeometry(1, 10, 8);
    this.handGeo.scale(0.026, 0.034, 0.019);

    // Legs: pelvis, thigh, shin, executive shoe
    this.hipPelvisGeo = new THREE.BoxGeometry(0.24, 0.09, 0.14);
    this.thighGeo = new THREE.CapsuleGeometry(0.044, 0.13, 3, 8);
    this.shinGeo = new THREE.CapsuleGeometry(0.039, 0.14, 3, 8);
    this.shoeGeo = new THREE.CapsuleGeometry(0.04, 0.065, 3, 8);
    this.shoeGeo.rotateX(Math.PI / 2);

    // Lanyard & Badge
    this.lanyardGeo = new THREE.TorusGeometry(0.09, 0.007, 8, 20);
    this.badgeCardGeo = new THREE.BoxGeometry(0.065, 0.095, 0.006);
    this.badgeClipGeo = new THREE.BoxGeometry(0.02, 0.015, 0.01);

    // Compatibility primitives (Preserve Defect 2 tests)
    this.haloGeo = new THREE.RingGeometry(0.24, 0.36, 16);
    this.haloGeo.rotateX(-Math.PI / 2);

    this.standingPedestalGeo = new THREE.CylinderGeometry(0.24, 0.28, 0.1, 16);
    this.ephemeralCrystalGeo = new THREE.OctahedronGeometry(0.28, 0);
    this.neutralPedestalGeo = new THREE.CylinderGeometry(0.2, 0.2, 0.1, 12);

    const geos = [
      this.torsoUpperGeo,
      this.torsoLowerGeo,
      this.neckGeo,
      this.headGeo,
      this.hairShortGeo,
      this.hairSidePartGeo,
      this.hairCropGeo,
      this.hairMidGeo,
      this.shoulderGeo,
      this.upperArmGeo,
      this.forearmGeo,
      this.handGeo,
      this.hipPelvisGeo,
      this.thighGeo,
      this.shinGeo,
      this.shoeGeo,
      this.lanyardGeo,
      this.badgeCardGeo,
      this.badgeClipGeo,
      this.haloGeo,
      this.standingPedestalGeo,
      this.ephemeralCrystalGeo,
      this.neutralPedestalGeo,
    ];
    for (const g of geos) {
      this.allGeometries.add(g);
    }
  }

  public ownsGeometry(geo: THREE.BufferGeometry): boolean {
    return this.allGeometries.has(geo);
  }

  public ownsMaterial(mat: THREE.Material): boolean {
    for (const cached of this.materialsCache.values()) {
      if (cached === mat) return true;
    }
    return false;
  }

  public getMaterial(
    key: string,
    createFn: () => THREE.Material
  ): THREE.Material {
    let mat = this.materialsCache.get(key);
    if (!mat) {
      mat = createFn();
      this.materialsCache.set(key, mat);
    }
    return mat;
  }

  public dispose(): void {
    const geos = [
      this.torsoUpperGeo,
      this.torsoLowerGeo,
      this.neckGeo,
      this.headGeo,
      this.hairShortGeo,
      this.hairSidePartGeo,
      this.hairCropGeo,
      this.hairMidGeo,
      this.shoulderGeo,
      this.upperArmGeo,
      this.forearmGeo,
      this.handGeo,
      this.hipPelvisGeo,
      this.thighGeo,
      this.shinGeo,
      this.shoeGeo,
      this.lanyardGeo,
      this.badgeCardGeo,
      this.badgeClipGeo,
      this.haloGeo,
      this.standingPedestalGeo,
      this.ephemeralCrystalGeo,
      this.neutralPedestalGeo,
    ];
    for (const g of geos) {
      g.dispose();
    }
    for (const mat of this.materialsCache.values()) {
      mat.dispose();
    }
    this.materialsCache.clear();
  }
}

/**
 * Builds the complete humanoid character rig with realistic proportions,
 * professional attire, hair, badge, and anatomical pivot hierarchies.
 */
export function buildHumanoidCharacterRig(
  agent: AgentIdentity,
  _activity: ProjectedAgentActivity,
  profile: AvatarAppearanceProfile,
  pool: AvatarResourcePool
): { rig: THREE.Group; parts: Partial<AvatarSemanticParts> } {
  const rig = new THREE.Group();
  rig.name = `character-rig-${agent.id}`;

  const { clothingPalette, skinTone, hairStyle, hairColor } = profile;

  // Materials with PBR properties (subtle roughness & cloth micro-sheen)
  const suitMat = pool.getMaterial(`suit-${clothingPalette.suitOrJacket}`, () =>
    new THREE.MeshStandardMaterial({
      color: clothingPalette.suitOrJacket,
      roughness: 0.72,
      metalness: 0.12,
    })
  );

  const shirtMat = pool.getMaterial(`shirt-${clothingPalette.shirt}`, () =>
    new THREE.MeshStandardMaterial({
      color: clothingPalette.shirt,
      roughness: 0.65,
      metalness: 0.05,
    })
  );

  const trouserMat = pool.getMaterial(`trouser-${clothingPalette.trousers}`, () =>
    new THREE.MeshStandardMaterial({
      color: clothingPalette.trousers,
      roughness: 0.78,
      metalness: 0.08,
    })
  );

  const shoeMat = pool.getMaterial(`shoe-${clothingPalette.shoes}`, () =>
    new THREE.MeshStandardMaterial({
      color: clothingPalette.shoes,
      roughness: 0.42,
      metalness: 0.35,
    })
  );

  const skinMat = pool.getMaterial(`skin-${skinTone}`, () =>
    new THREE.MeshStandardMaterial({
      color: skinTone,
      roughness: 0.58,
      metalness: 0.04,
    })
  );

  const hairMat = pool.getMaterial(`hair-${hairColor}`, () =>
    new THREE.MeshStandardMaterial({
      color: hairColor,
      roughness: 0.85,
      metalness: 0.05,
    })
  );

  // 1. Torso Root Group (center y = 0.52 above ground)
  const torsoGroup = new THREE.Group();
  torsoGroup.name = 'torso-group';
  torsoGroup.position.set(0, 0.52, 0);

  // Upper chest
  const chestMesh = new THREE.Mesh(pool.torsoUpperGeo, suitMat);
  chestMesh.position.set(0, 0.12, 0);
  chestMesh.castShadow = true;
  chestMesh.receiveShadow = true;
  torsoGroup.add(chestMesh);

  // Shirt collar insert visible at front
  const collarGeo = new THREE.BoxGeometry(0.11, 0.08, 0.04);
  const collarMesh = new THREE.Mesh(collarGeo, shirtMat);
  collarMesh.position.set(0, 0.18, 0.075);
  torsoGroup.add(collarMesh);

  // Lower waist
  const waistMesh = new THREE.Mesh(pool.torsoLowerGeo, suitMat);
  waistMesh.position.set(0, -0.06, 0);
  waistMesh.castShadow = true;
  torsoGroup.add(waistMesh);

  // Pelvis / Belt zone
  const pelvisMesh = new THREE.Mesh(pool.hipPelvisGeo, trouserMat);
  pelvisMesh.position.set(0, -0.16, 0);
  pelvisMesh.castShadow = true;
  torsoGroup.add(pelvisMesh);

  rig.add(torsoGroup);

  // 2. Neck & Head
  const neckMesh = new THREE.Mesh(pool.neckGeo, skinMat);
  neckMesh.position.set(0, 0.76, 0.01);
  neckMesh.castShadow = true;
  rig.add(neckMesh);

  const headGroup = new THREE.Group();
  headGroup.name = 'head-group';
  headGroup.position.set(0, 0.88, 0.02);

  const headMesh = new THREE.Mesh(pool.headGeo, skinMat);
  headMesh.castShadow = true;
  headGroup.add(headMesh);

  // Hair according to deterministic style
  let hairGeo: THREE.BufferGeometry;
  let hairOffsetY = 0.04;
  let hairOffsetZ = -0.01;
  switch (hairStyle) {
    case 'EXECUTIVE_SIDE_PART':
      hairGeo = pool.hairSidePartGeo;
      hairOffsetY = 0.07;
      break;
    case 'CROP_TEXTURED':
      hairGeo = pool.hairCropGeo;
      hairOffsetY = 0.06;
      break;
    case 'MODERN_MID':
      hairGeo = pool.hairMidGeo;
      hairOffsetY = 0.04;
      hairOffsetZ = -0.015;
      break;
    case 'SHORT_CLASSIC':
    default:
      hairGeo = pool.hairShortGeo;
      hairOffsetY = 0.04;
      break;
  }
  const hairMesh = new THREE.Mesh(hairGeo, hairMat);
  hairMesh.position.set(0, hairOffsetY, hairOffsetZ);
  hairMesh.castShadow = true;
  headGroup.add(hairMesh);

  rig.add(headGroup);

  // 3. Corporate Lanyard & Identification Badge
  const badgeGroup = new THREE.Group();
  badgeGroup.name = 'badge-group';
  badgeGroup.position.set(0, 0.62, 0.095);

  const lanyardMesh = new THREE.Mesh(
    pool.lanyardGeo,
    pool.getMaterial(`lanyard-${profile.badgeAccentHex}`, () =>
      new THREE.MeshBasicMaterial({ color: profile.badgeAccentHex })
    )
  );
  lanyardMesh.rotation.x = Math.PI / 2.3;
  lanyardMesh.position.set(0, 0.12, -0.02);
  badgeGroup.add(lanyardMesh);

  const badgeCardMesh = new THREE.Mesh(
    pool.badgeCardGeo,
    pool.getMaterial('badge-white-base', () =>
      new THREE.MeshStandardMaterial({
        color: 0xf8fafc,
        roughness: 0.35,
        metalness: 0.1,
      })
    )
  );
  badgeGroup.add(badgeCardMesh);

  // Badge header strip showing department accent
  const badgeHeaderGeo = new THREE.BoxGeometry(0.065, 0.026, 0.007);
  const badgeHeaderMesh = new THREE.Mesh(
    badgeHeaderGeo,
    pool.getMaterial(`badge-header-${profile.badgeAccentHex}`, () =>
      new THREE.MeshBasicMaterial({ color: profile.badgeAccentHex })
    )
  );
  badgeHeaderMesh.position.set(0, 0.034, 0.001);
  badgeGroup.add(badgeHeaderMesh);

  // Status indicator dot on badge (Health status telemetry dot)
  let statusColor = 0x94a3b8;
  if (agent.heartbeatStatus === 'HEALTHY') statusColor = 0x22c55e;
  else if (agent.heartbeatStatus === 'STALE') statusColor = 0xeab308;
  else if (agent.heartbeatStatus === 'UNAVAILABLE') statusColor = 0xef4444;

  const statusDotGeo = new THREE.BoxGeometry(0.014, 0.014, 0.008);
  const statusDotMesh = new THREE.Mesh(
    statusDotGeo,
    pool.getMaterial(`badge-status-${statusColor}`, () =>
      new THREE.MeshBasicMaterial({ color: statusColor })
    )
  );
  statusDotMesh.position.set(0.02, -0.03, 0.002);
  badgeGroup.add(statusDotMesh);

  rig.add(badgeGroup);

  // 4. Arms with Anatomical Hierarchy (Shoulder joint -> Upper Arm -> Elbow -> Forearm -> Hand)
  // Left Arm Group (pivot at shoulder joint y = 0.72, x = -0.19)
  const leftArmGroup = new THREE.Group();
  leftArmGroup.name = 'left-arm-group';
  leftArmGroup.position.set(-0.20, 0.71, 0);

  const leftShoulder = new THREE.Mesh(pool.shoulderGeo, suitMat);
  leftArmGroup.add(leftShoulder);

  const leftUpperArm = new THREE.Mesh(pool.upperArmGeo, suitMat);
  leftUpperArm.position.set(0, -0.09, 0);
  leftUpperArm.castShadow = true;
  leftArmGroup.add(leftUpperArm);

  const leftForearmGroup = new THREE.Group();
  leftForearmGroup.position.set(0, -0.18, 0);

  const leftForearm = new THREE.Mesh(pool.forearmGeo, suitMat);
  leftForearm.position.set(0, -0.08, 0.03);
  leftForearm.rotation.x = -0.35;
  leftForearm.castShadow = true;
  leftForearmGroup.add(leftForearm);

  const leftHand = new THREE.Mesh(pool.handGeo, skinMat);
  leftHand.position.set(0, -0.17, 0.06);
  leftHand.castShadow = true;
  leftForearmGroup.add(leftHand);

  leftArmGroup.add(leftForearmGroup);
  rig.add(leftArmGroup);

  // Right Arm Group (pivot at shoulder joint y = 0.72, x = 0.19)
  const rightArmGroup = new THREE.Group();
  rightArmGroup.name = 'right-arm-group';
  rightArmGroup.position.set(0.20, 0.71, 0);

  const rightShoulder = new THREE.Mesh(pool.shoulderGeo, suitMat);
  rightArmGroup.add(rightShoulder);

  const rightUpperArm = new THREE.Mesh(pool.upperArmGeo, suitMat);
  rightUpperArm.position.set(0, -0.09, 0);
  rightUpperArm.castShadow = true;
  rightArmGroup.add(rightUpperArm);

  const rightForearmGroup = new THREE.Group();
  rightForearmGroup.position.set(0, -0.18, 0);

  const rightForearm = new THREE.Mesh(pool.forearmGeo, suitMat);
  rightForearm.position.set(0, -0.08, 0.03);
  rightForearm.rotation.x = -0.35;
  rightForearm.castShadow = true;
  rightForearmGroup.add(rightForearm);

  const rightHand = new THREE.Mesh(pool.handGeo, skinMat);
  rightHand.position.set(0, -0.17, 0.06);
  rightHand.castShadow = true;
  rightForearmGroup.add(rightHand);

  // Small reusable prop, shown only during explicitly ambient walking. It is
  // visual storytelling, never a claim about real agent activity.
  const coffeeCup = new THREE.Group();
  coffeeCup.name = 'ambient-coffee-cup';
  const cup = new THREE.Mesh(
    new THREE.CylinderGeometry(0.035, 0.028, 0.07, 8),
    new THREE.MeshStandardMaterial({ color: 0xf5f1e8, roughness: 0.65 }),
  );
  cup.position.set(0, -0.015, 0.025);
  coffeeCup.add(cup);
  const coffee = new THREE.Mesh(
    new THREE.CircleGeometry(0.027, 8),
    new THREE.MeshStandardMaterial({ color: 0x53321f, roughness: 0.8, side: THREE.DoubleSide }),
  );
  coffee.rotation.x = -Math.PI / 2;
  coffee.position.set(0, 0.021, 0.025);
  coffeeCup.add(coffee);
  const handle = new THREE.Mesh(
    new THREE.TorusGeometry(0.022, 0.006, 5, 8, Math.PI),
    new THREE.MeshStandardMaterial({ color: 0xf5f1e8, roughness: 0.65 }),
  );
  handle.position.set(0.039, -0.012, 0.025);
  handle.rotation.z = -Math.PI / 2;
  coffeeCup.add(handle);
  coffeeCup.position.set(0, -0.17, 0.09);
  rightHand.add(coffeeCup);

  rightArmGroup.add(rightForearmGroup);
  rig.add(rightArmGroup);

  // 5. Legs with Anatomical Pivot (Hip joint -> Thigh -> Knee -> Shin -> Shoe)
  // Left Leg Group (pivot at hip y = 0.38, x = -0.075)
  const leftLegGroup = new THREE.Group();
  leftLegGroup.name = 'left-leg-group';
  leftLegGroup.position.set(-0.075, 0.38, 0);

  const leftThigh = new THREE.Mesh(pool.thighGeo, trouserMat);
  leftThigh.position.set(0, -0.10, 0);
  leftThigh.castShadow = true;
  leftLegGroup.add(leftThigh);

  const leftShinGroup = new THREE.Group();
  leftShinGroup.position.set(0, -0.19, 0);

  const leftShin = new THREE.Mesh(pool.shinGeo, trouserMat);
  leftShin.position.set(0, -0.09, 0);
  leftShin.castShadow = true;
  leftShinGroup.add(leftShin);

  const leftShoe = new THREE.Mesh(pool.shoeGeo, shoeMat);
  leftShoe.position.set(0, -0.17, 0.035);
  leftShoe.castShadow = true;
  leftShinGroup.add(leftShoe);

  leftLegGroup.add(leftShinGroup);
  rig.add(leftLegGroup);

  // Right Leg Group (pivot at hip y = 0.38, x = 0.075)
  const rightLegGroup = new THREE.Group();
  rightLegGroup.name = 'right-leg-group';
  rightLegGroup.position.set(0.075, 0.38, 0);

  const rightThigh = new THREE.Mesh(pool.thighGeo, trouserMat);
  rightThigh.position.set(0, -0.10, 0);
  rightThigh.castShadow = true;
  rightLegGroup.add(rightThigh);

  const rightShinGroup = new THREE.Group();
  rightShinGroup.position.set(0, -0.19, 0);

  const rightShin = new THREE.Mesh(pool.shinGeo, trouserMat);
  rightShin.position.set(0, -0.09, 0);
  rightShin.castShadow = true;
  rightShinGroup.add(rightShin);

  const rightShoe = new THREE.Mesh(pool.shoeGeo, shoeMat);
  rightShoe.position.set(0, -0.17, 0.035);
  rightShoe.castShadow = true;
  rightShinGroup.add(rightShoe);

  rightLegGroup.add(rightShinGroup);
  rig.add(rightLegGroup);

  const semanticParts: Partial<AvatarSemanticParts> = {
    characterRig: rig,
    torso: torsoGroup,
    head: headGroup,
    neck: neckMesh,
    hair: hairMesh,
    badge: badgeGroup,
    leftArm: leftArmGroup,
    rightArm: rightArmGroup,
    leftForearm: leftForearmGroup,
    rightForearm: rightForearmGroup,
    leftHand,
    rightHand,
    coffeeCup,
    leftLeg: leftLegGroup,
    rightLeg: rightLegGroup,
    leftShin: leftShinGroup,
    rightShin: rightShinGroup,
    leftShoe,
    rightShoe,
  };

  return { rig, parts: semanticParts };
}

/**
 * Builds the top-level agent group conforming strictly to all required contracts:
 * children[0]: Telemetry Halo
 * children[1]: Primary geometry (satisfies Defect 2 test assertions)
 * children[2]: Character Rig
 * children[3]: Speech Bubble
 * children[4]: Name & Provenance Sprite
 */
export function buildAgentAvatar(
  agent: AgentIdentity,
  activity: ProjectedAgentActivity,
  pool: AvatarResourcePool,
  options: {
    departmentAccentHex?: string;
    createSpeechBubbleSprite: () => THREE.Sprite;
    createAgentNameSprite: (name: string, roleBadge: string, haloColor: number) => THREE.Sprite;
  }
): THREE.Group {
  const group = new THREE.Group();
  group.name = `agent-${agent.id}`;
  group.userData = {
    agentId: agent.id,
    agentType: agent.type,
    agentStatus: agent.status,
    agentName: agent.name,
    unitId: agent.unitId,
  };

  const isStanding = agent.type === 'STANDING';
  const isEphemeral = agent.type === 'EPHEMERAL';

  let haloColor = 0x64748b; // UNKNOWN
  if (agent.heartbeatStatus === 'HEALTHY') haloColor = 0x22c55e;
  else if (agent.heartbeatStatus === 'STALE') haloColor = 0xeab308;
  else if (agent.heartbeatStatus === 'UNAVAILABLE') haloColor = 0xef4444;

  // Keep status color on the nameplate, but render the ground ring as a quiet
  // material cue rather than a luminous arcade-style outline.
  const haloRingColor =
    agent.heartbeatStatus === 'HEALTHY'
      ? 0x668b70
      : agent.heartbeatStatus === 'STALE'
      ? 0x9a8458
      : agent.heartbeatStatus === 'UNAVAILABLE'
      ? 0x9a625c
      : 0x727b83;

  // children[0]: Telemetry Halo Ring
  const haloMat = pool.getMaterial(`halo-${haloRingColor}`, () =>
    new THREE.MeshBasicMaterial({
      color: haloRingColor,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.24,
      depthWrite: false,
    })
  );
  const halo = new THREE.Mesh(pool.haloGeo, haloMat);
  halo.position.y = 0.02;
  group.add(halo);

  // children[1]: Primary Agent Geometry (Exact Defect 2 test invariant: standing stays at 0.06, ephemeral bobs at 0.58)
  let primaryGeometry: THREE.Mesh;
  if (isStanding) {
    const pedMat = pool.getMaterial('standing-pedestal-mat', () =>
      new THREE.MeshStandardMaterial({
        color: 0x1e293b,
        roughness: 0.4,
        metalness: 0.6,
      })
    );
    primaryGeometry = new THREE.Mesh(pool.standingPedestalGeo, pedMat);
    primaryGeometry.position.y = 0.06;
    primaryGeometry.castShadow = true;
    group.add(primaryGeometry);
  } else if (isEphemeral) {
    const bodyMat = pool.getMaterial('ephemeral-crystal-mat', () =>
      new THREE.MeshStandardMaterial({
        color: 0x0891b2,
        roughness: 0.15,
        metalness: 0.75,
        emissive: new THREE.Color(0x0891b2).multiplyScalar(0.35),
      })
    );
    primaryGeometry = new THREE.Mesh(pool.ephemeralCrystalGeo, bodyMat);
    primaryGeometry.position.y = 0.58;
    primaryGeometry.castShadow = true;
    group.add(primaryGeometry);
  } else {
    const bodyMat = pool.getMaterial('neutral-pedestal-mat', () =>
      new THREE.MeshStandardMaterial({
        color: 0x475569,
        roughness: 0.6,
        metalness: 0.2,
      })
    );
    primaryGeometry = new THREE.Mesh(pool.neutralPedestalGeo, bodyMat);
    primaryGeometry.position.y = 0.06;
    primaryGeometry.castShadow = true;
    group.add(primaryGeometry);
  }

  // The primary meshes are retained for the legacy scene-graph/kinematics
  // contract, but the articulated humanoid is the visible agent. Rendering a
  // pedestal or crystal under every person makes the avatar read as a robot or
  // game token, so keep these compatibility meshes out of the scene image.
  primaryGeometry.visible = false;

  // children[2]: Articulated Humanoid Character Rig
  const appearanceProfile = getAvatarAppearanceProfile(
    agent,
    options.departmentAccentHex ?? '#38bdf8'
  );
  const { rig: characterRig, parts: rigParts } = buildHumanoidCharacterRig(
    agent,
    activity,
    appearanceProfile,
    pool
  );
  group.add(characterRig);

  // children[3]: Speech Bubble
  const speechBubble = options.createSpeechBubbleSprite();
  // Keep conversation markers above the name badge footprint. The prior
  // 1.56m anchor overlapped the 1.24m-high label sprite whenever both were
  // visible in a close camera view.
  speechBubble.position.set(0, 2.02, 0);
  speechBubble.visible = activity.kind === 'CONVERSING';
  group.add(speechBubble);

  // children[4]: Name & Provenance Badge
  const provTag =
    activity.provenance === 'LIVE_VERIFIED_EVIDENCE'
      ? 'LIVE'
      : activity.provenance === 'DEMO_SIMULATION'
      ? 'DEMO'
      : activity.provenance === 'AMBIENT_ANIMATION'
      ? 'AMB'
      : 'UNK';

  const nameLabel = options.createAgentNameSprite(
    agent.name.split(' ')[0],
    agent.coordinatorState
      ? `${agent.coordinatorState === 'COORDINATING' ? 'COORDINANDO · NO EJECUTA TAREA' : agent.coordinatorState === 'WAITING' ? 'EN ESPERA' : 'ESTADO DESACTUALIZADO'} · ${provTag}`
      : `${activity.shortBadge} · ${provTag}`,
    haloColor
  );
  nameLabel.position.set(0, 1.24, 0);
  group.add(nameLabel);

  const semanticParts: AvatarSemanticParts = {
    halo,
    primaryGeometry,
    characterRig,
    torso: rigParts.torso,
    head: rigParts.head,
    neck: rigParts.neck,
    hair: rigParts.hair,
    badge: rigParts.badge,
    leftArm: rigParts.leftArm,
    rightArm: rigParts.rightArm,
    leftForearm: rigParts.leftForearm,
    rightForearm: rigParts.rightForearm,
    leftHand: rigParts.leftHand,
    rightHand: rigParts.rightHand,
    coffeeCup: rigParts.coffeeCup,
    leftLeg: rigParts.leftLeg,
    rightLeg: rigParts.rightLeg,
    leftShin: rigParts.leftShin,
    rightShin: rigParts.rightShin,
    leftShoe: rigParts.leftShoe,
    rightShoe: rigParts.rightShoe,
    speechBubble,
    nameLabel,
  };
  group.userData.parts = semanticParts;

  return group;
}

/**
 * Executes anatomical kinematics, posture transitions, and LOD throttling
 * for a single humanoid avatar.
 */
export function stepAvatarKinematics(
  group: THREE.Group,
  runtime: AgentAnimatedRuntimeState,
  time: number,
  cameraDistance: number,
  options: {
    reducedMotion?: boolean;
    sampleWaypointRoute?: (
      waypoints: ReadonlyArray<{ x: number; z: number }>,
      time: number,
      offsetSec: number
    ) => { x: number; z: number; facingAngle: number };
  } = {}
): void {
  const parts = group.userData?.parts as AvatarSemanticParts | undefined;
  if (!parts?.characterRig || !runtime) return;

  const agentType = group.userData?.agentType as string | undefined;
  const agentId = (group.userData?.agentId as string) || '';
  const t = time * 0.002;

  // Defect 2 invariant: strictly animate EPHEMERAL crystal geometry at children[1]
  if (agentType === 'EPHEMERAL' && parts.primaryGeometry) {
    parts.primaryGeometry.position.y = 0.58 + Math.sin(t + group.position.x) * 0.04;
    parts.primaryGeometry.rotation.y = t * 0.5;
  }

  if (options.reducedMotion) {
    // Static placement without oscillatory kinematics
    group.position.x = runtime.placement.targetWorldX;
    group.position.z = runtime.placement.targetWorldZ;
    parts.characterRig.rotation.y = runtime.placement.targetFacingAngle;
    return;
  }

  const { placement } = runtime;
  const kind = placement.activity.kind;
  if (parts.coffeeCup) {
    parts.coffeeCup.visible =
      kind === 'WALKING' && placement.activity.provenance !== 'LIVE_VERIFIED_EVIDENCE';
  }
  const phaseSeed = hashStringSeed(agentId) % 100;
  const phase = phaseSeed * 0.1;

  let destX = placement.targetWorldX;
  let destZ = placement.targetWorldZ;
  let destAngle = placement.targetFacingAngle;

  if (kind === 'WALKING' && options.sampleWaypointRoute && placement.waypoints) {
    const sampled = options.sampleWaypointRoute(placement.waypoints, time, phaseSeed % 7);
    destX = sampled.x;
    destZ = sampled.z;
    destAngle = sampled.facingAngle;
  }

  // Smooth position & orientation interpolation
  runtime.currentX += (destX - runtime.currentX) * 0.12;
  runtime.currentZ += (destZ - runtime.currentZ) * 0.12;
  runtime.currentAngle += (destAngle - runtime.currentAngle) * 0.15;

  group.position.x = runtime.currentX;
  group.position.z = runtime.currentZ;
  parts.characterRig.rotation.y = runtime.currentAngle;

  // Level of Detail (LOD) check: suppress subtle secondary kinematics at long distance (> 26 units)
  const isFarDistance = cameraDistance > 26;

  if (kind === 'TYPING_DEV' || kind === 'TYPING_AUDIT' || kind === 'TYPING_DOCS') {
    // Natural seated typing kinematics
    // Avatar root is at world y=0.37 and seat is at world y=0.45. Align the
    // pelvis/hips with the cushion rather than leaving the torso perched above.
    parts.characterRig.position.y = -0.28;

    // Thighs horizontal in chair
    if (parts.leftLeg) parts.leftLeg.rotation.x = -Math.PI / 2.3;
    if (parts.rightLeg) parts.rightLeg.rotation.x = -Math.PI / 2.3;

    // Knees bent 90 degrees downward to floor
    if (parts.leftShin) parts.leftShin.rotation.x = Math.PI / 2.2;
    if (parts.rightShin) parts.rightShin.rotation.x = Math.PI / 2.2;
    if (parts.leftShin) parts.leftShin.scale.y = 2;
    if (parts.rightShin) parts.rightShin.scale.y = 2;

    // Arms raised onto desk keyboard with natural elbow hinge
    const typingJitterL = isFarDistance ? 0 : Math.sin(time * 0.024 + phase) * 0.14;
    const typingJitterR = isFarDistance ? 0 : Math.cos(time * 0.024 + phase) * 0.14;

    if (parts.leftArm) parts.leftArm.rotation.x = -0.82 + typingJitterL;
    if (parts.rightArm) parts.rightArm.rotation.x = -0.82 + typingJitterR;

    // Inward hand convergence towards keyboard center
    if (parts.leftArm) parts.leftArm.rotation.z = -0.12;
    if (parts.rightArm) parts.rightArm.rotation.z = 0.12;

    // Head tilted attentively forward towards screen
    if (parts.head) {
      parts.head.rotation.x = 0.18;
      parts.head.rotation.y = isFarDistance ? 0 : Math.sin(time * 0.003 + phase) * 0.06;
    }

    if (parts.speechBubble) parts.speechBubble.visible = false;
  } else if (kind === 'CONVERSING') {
    // Standing or seated collaborative conversation
    parts.characterRig.position.y = 0;
    if (parts.leftShin) parts.leftShin.scale.y = 1;
    if (parts.rightShin) parts.rightShin.scale.y = 1;

    if (parts.leftLeg) parts.leftLeg.rotation.x = 0;
    if (parts.rightLeg) parts.rightLeg.rotation.x = 0;
    if (parts.leftShin) parts.leftShin.rotation.x = 0;
    if (parts.rightShin) parts.rightShin.rotation.x = 0;

    // Expressive conversational arm gestures
    const gestureL = isFarDistance ? 0 : Math.sin(time * 0.007 + phase) * 0.22;
    const gestureR = isFarDistance ? 0 : Math.cos(time * 0.006 + phase) * 0.20;

    if (parts.leftArm) {
      parts.leftArm.rotation.x = -0.42 + gestureL;
      parts.leftArm.rotation.z = -0.18;
    }
    if (parts.rightArm) {
      parts.rightArm.rotation.x = -0.36 + gestureR;
      parts.rightArm.rotation.z = 0.18;
    }

    if (parts.head) {
      parts.head.rotation.x = 0;
      parts.head.rotation.y = isFarDistance ? 0 : Math.sin(time * 0.005 + phase) * 0.12;
    }

    if (parts.speechBubble) {
      parts.speechBubble.visible = true;
      parts.speechBubble.position.y = 2.02 + Math.sin(time * 0.006 + phase) * 0.03;
    }
  } else if (kind === 'WALKING') {
    // Sinusoidal walking stride with counter-swinging arms and vertical bob
    const walkCycle = time * 0.01 + phase;
    const stride = Math.sin(walkCycle);

    parts.characterRig.position.y = isFarDistance ? 0 : Math.abs(stride) * 0.025;
    if (parts.leftShin) parts.leftShin.scale.y = 1;
    if (parts.rightShin) parts.rightShin.scale.y = 1;

    // Alternating leg swing with knee flexion on back-step
    if (parts.leftLeg) parts.leftLeg.rotation.x = stride * 0.44;
    if (parts.rightLeg) parts.rightLeg.rotation.x = -stride * 0.44;

    if (parts.leftShin) {
      parts.leftShin.rotation.x = stride > 0 ? stride * 0.35 : 0;
    }
    if (parts.rightShin) {
      parts.rightShin.rotation.x = stride < 0 ? -stride * 0.35 : 0;
    }

    // Counter-swinging arms
    if (parts.leftArm) {
      parts.leftArm.rotation.x = -stride * 0.34;
      parts.leftArm.rotation.z = -0.06;
    }
    if (parts.rightArm) {
      parts.rightArm.rotation.x = stride * 0.34;
      parts.rightArm.rotation.z = 0.06;
    }

    if (parts.head) {
      parts.head.rotation.x = 0;
      parts.head.rotation.y = 0;
    }

    if (parts.speechBubble) parts.speechBubble.visible = false;
  } else if (kind === 'IDLE_DESK') {
    // Relaxed seated posture
    parts.characterRig.position.y = -0.28;
    if (parts.coffeeCup) parts.coffeeCup.visible = false;

    if (parts.leftLeg) parts.leftLeg.rotation.x = -Math.PI / 2.3;
    if (parts.rightLeg) parts.rightLeg.rotation.x = -Math.PI / 2.3;
    if (parts.leftShin) parts.leftShin.rotation.x = Math.PI / 2.2;
    if (parts.rightShin) parts.rightShin.rotation.x = Math.PI / 2.2;
    if (parts.leftShin) parts.leftShin.scale.y = 2;
    if (parts.rightShin) parts.rightShin.scale.y = 2;

    if (parts.leftArm) {
      parts.leftArm.rotation.x = -0.28;
      parts.leftArm.rotation.z = -0.08;
    }
    if (parts.rightArm) {
      parts.rightArm.rotation.x = -0.28;
      parts.rightArm.rotation.z = 0.08;
    }

    if (parts.head) {
      parts.head.rotation.x = 0.05;
      parts.head.rotation.y = isFarDistance ? 0 : Math.sin(time * 0.002 + phase) * 0.04;
    }

    if (parts.speechBubble) parts.speechBubble.visible = false;
  } else {
    // Default neutral standing posture
    parts.characterRig.position.y = 0;

    if (parts.leftLeg) parts.leftLeg.rotation.x = 0;
    if (parts.rightLeg) parts.rightLeg.rotation.x = 0;
    if (parts.leftShin) parts.leftShin.rotation.x = 0;
    if (parts.rightShin) parts.rightShin.rotation.x = 0;

    if (parts.leftArm) {
      parts.leftArm.rotation.x = 0;
      parts.leftArm.rotation.z = -0.06;
    }
    if (parts.rightArm) {
      parts.rightArm.rotation.x = 0;
      parts.rightArm.rotation.z = 0.06;
    }

    if (parts.head) {
      parts.head.rotation.x = 0;
      parts.head.rotation.y = 0;
    }

    if (parts.speechBubble) parts.speechBubble.visible = false;
  }
}
