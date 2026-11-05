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

  // High-fidelity MMORPG anatomical & sartorial geometries
  public readonly chinGeo: THREE.BufferGeometry;
  public readonly hairBangsSideGeo: THREE.BufferGeometry;
  public readonly hairBangsCropGeo: THREE.BufferGeometry;
  public readonly hairBangsMidGeo: THREE.BufferGeometry;
  public readonly suitLapelGeo: THREE.BufferGeometry;
  public readonly beltBuckleGeo: THREE.BufferGeometry;
  public readonly pocketSquareGeo: THREE.BufferGeometry;
  public readonly cuffGeo: THREE.BufferGeometry;
  public readonly watchGeo: THREE.BufferGeometry;
  public readonly shoeSoleGeo: THREE.BufferGeometry;
  public readonly shoeHeelGeo: THREE.BufferGeometry;
  public readonly eyePupilGeo: THREE.BufferGeometry;
  public readonly eyeGlintGeo: THREE.BufferGeometry;
  public readonly eyelashGeo: THREE.BufferGeometry;
  public readonly mouthGeo: THREE.BufferGeometry;
  public readonly thumbGeo: THREE.BufferGeometry;
  public readonly hairSideburnGeo: THREE.BufferGeometry;
  public readonly lanyardStrapGeo: THREE.BufferGeometry;

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
    this.neckGeo = new THREE.CylinderGeometry(0.032, 0.038, 0.065, 12);

    // Head (Refined anatomical scale for realistic 7.5-head human proportions)
    this.headGeo = new THREE.SphereGeometry(0.082, 16, 14);
    this.headGeo.scale(0.86, 1.06, 0.94);

    // Hairstyle variants: anatomically full cranium coverage (crown, temples, back of skull down to nape)
    // 1. Short classic: compact skull contour with full occipital and temple wrap
    this.hairShortGeo = new THREE.SphereGeometry(0.088, 16, 14, 0, Math.PI * 2, 0, Math.PI * 0.78);
    this.hairShortGeo.scale(0.96, 1.05, 1.02);

    // 2. Executive side part: elegant side part with swept asymmetric fullness
    this.hairSidePartGeo = new THREE.SphereGeometry(0.089, 16, 14, 0, Math.PI * 2, 0, Math.PI * 0.76);
    this.hairSidePartGeo.scale(0.98, 1.03, 1.01);

    // 3. Crop textured: modern forward crop with full temporal coverage
    this.hairCropGeo = new THREE.SphereGeometry(0.087, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.74);
    this.hairCropGeo.scale(0.96, 1.04, 1.01);

    // 4. Modern mid-length: frames temples with gentle cheek drop and collar drape
    this.hairMidGeo = new THREE.SphereGeometry(0.091, 16, 14, 0, Math.PI * 2, 0, Math.PI * 0.84);
    this.hairMidGeo.scale(1.01, 1.06, 1.03);

    // Arms: tailored sleeve cap, upper arm, forearm, hand & thumb
    this.shoulderGeo = new THREE.SphereGeometry(0.038, 10, 8);
    this.shoulderGeo.scale(1.05, 0.75, 0.95);
    this.upperArmGeo = new THREE.CapsuleGeometry(0.038, 0.13, 4, 10);
    this.forearmGeo = new THREE.CapsuleGeometry(0.034, 0.11, 4, 10);
    this.handGeo = new THREE.SphereGeometry(1, 10, 8);
    this.handGeo.scale(0.025, 0.034, 0.018);
    this.thumbGeo = new THREE.BoxGeometry(0.012, 0.022, 0.012);

    // Legs: pelvis, thigh, shin, executive shoe
    this.hipPelvisGeo = new THREE.BoxGeometry(0.24, 0.09, 0.14);
    this.thighGeo = new THREE.CapsuleGeometry(0.044, 0.13, 3, 8);
    this.shinGeo = new THREE.CapsuleGeometry(0.039, 0.14, 3, 8);
    this.shoeGeo = new THREE.CapsuleGeometry(0.04, 0.065, 3, 8);
    this.shoeGeo.rotateX(Math.PI / 2);

    // Lanyard & Badge: flat woven fabric straps and vertical card
    this.lanyardGeo = new THREE.TorusGeometry(0.09, 0.007, 8, 20);
    this.lanyardStrapGeo = new THREE.BoxGeometry(0.011, 0.17, 0.002);
    this.badgeCardGeo = new THREE.BoxGeometry(0.058, 0.088, 0.004);
    this.badgeClipGeo = new THREE.BoxGeometry(0.018, 0.014, 0.008);

    // High-fidelity MMORPG anatomical & sartorial geometries
    this.chinGeo = new THREE.ConeGeometry(0.046, 0.048, 10);
    this.chinGeo.rotateX(Math.PI);

    this.hairBangsSideGeo = new THREE.BoxGeometry(0.05, 0.04, 0.03);
    this.hairBangsCropGeo = new THREE.BoxGeometry(0.06, 0.025, 0.025);
    this.hairBangsMidGeo = new THREE.BoxGeometry(0.035, 0.07, 0.03);
    this.hairSideburnGeo = new THREE.BoxGeometry(0.014, 0.048, 0.022);

    this.suitLapelGeo = new THREE.BoxGeometry(0.038, 0.22, 0.016);
    this.beltBuckleGeo = new THREE.BoxGeometry(0.038, 0.022, 0.014);
    this.pocketSquareGeo = new THREE.BoxGeometry(0.03, 0.02, 0.01);
    this.cuffGeo = new THREE.CylinderGeometry(0.036, 0.038, 0.025, 8);
    this.watchGeo = new THREE.BoxGeometry(0.022, 0.022, 0.012);
    this.shoeSoleGeo = new THREE.BoxGeometry(0.078, 0.018, 0.15);
    this.shoeHeelGeo = new THREE.BoxGeometry(0.072, 0.022, 0.05);

    this.eyePupilGeo = new THREE.SphereGeometry(0.005, 6, 6);
    this.eyeGlintGeo = new THREE.SphereGeometry(0.0028, 4, 4);
    this.eyelashGeo = new THREE.BoxGeometry(0.026, 0.004, 0.008);
    this.mouthGeo = new THREE.BoxGeometry(0.024, 0.004, 0.005);

    // Compatibility primitives (Preserve Defect 2 tests)
    this.haloGeo = new THREE.RingGeometry(0.26, 0.275, 24);
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
      this.chinGeo,
      this.hairBangsSideGeo,
      this.hairBangsCropGeo,
      this.hairBangsMidGeo,
      this.suitLapelGeo,
      this.beltBuckleGeo,
      this.pocketSquareGeo,
      this.cuffGeo,
      this.watchGeo,
      this.shoeSoleGeo,
      this.shoeHeelGeo,
      this.eyePupilGeo,
      this.eyeGlintGeo,
      this.eyelashGeo,
      this.mouthGeo,
      this.thumbGeo,
      this.hairSideburnGeo,
      this.lanyardStrapGeo,
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
      this.chinGeo,
      this.hairBangsSideGeo,
      this.hairBangsCropGeo,
      this.hairBangsMidGeo,
      this.suitLapelGeo,
      this.beltBuckleGeo,
      this.pocketSquareGeo,
      this.cuffGeo,
      this.watchGeo,
      this.shoeSoleGeo,
      this.shoeHeelGeo,
      this.eyePupilGeo,
      this.eyeGlintGeo,
      this.eyelashGeo,
      this.mouthGeo,
      this.thumbGeo,
      this.hairSideburnGeo,
      this.lanyardStrapGeo,
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

  // Sartorial Tailored Lapels (diagonal V-contour characteristic of enterprise blazers)
  const lapelLeft = new THREE.Mesh(pool.suitLapelGeo, suitMat);
  lapelLeft.position.set(-0.046, 0.11, 0.082);
  lapelLeft.rotation.z = -0.2;
  lapelLeft.castShadow = true;
  torsoGroup.add(lapelLeft);

  const lapelRight = new THREE.Mesh(pool.suitLapelGeo, suitMat);
  lapelRight.position.set(0.046, 0.11, 0.082);
  lapelRight.rotation.z = 0.2;
  lapelRight.castShadow = true;
  torsoGroup.add(lapelRight);

  // Breast pocket square with department accent color
  const pocketSquareMat = pool.getMaterial(`pocket-square-${profile.badgeAccentHex}`, () =>
    new THREE.MeshStandardMaterial({
      color: profile.badgeAccentHex,
      roughness: 0.45,
      metalness: 0.1,
    })
  );
  const pocketSquare = new THREE.Mesh(pool.pocketSquareGeo, pocketSquareMat);
  pocketSquare.position.set(-0.07, 0.135, 0.082);
  torsoGroup.add(pocketSquare);

  // Belt & Metallic Buckle separating upper torso from trousers
  const beltMat = pool.getMaterial('avatar-leather-belt', () =>
    new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.42, metalness: 0.25 })
  );
  const buckleMat = pool.getMaterial('avatar-belt-buckle', () =>
    new THREE.MeshStandardMaterial({ color: 0xd4d4d8, roughness: 0.2, metalness: 0.9 })
  );
  const belt = new THREE.Mesh(new THREE.BoxGeometry(0.245, 0.024, 0.145), beltMat);
  belt.position.set(0, -0.125, 0);
  torsoGroup.add(belt);
  const buckle = new THREE.Mesh(pool.beltBuckleGeo, buckleMat);
  buckle.position.set(0, -0.125, 0.075);
  torsoGroup.add(buckle);

  // Pelvis / Belt zone
  const pelvisMesh = new THREE.Mesh(pool.hipPelvisGeo, trouserMat);
  pelvisMesh.position.set(0, -0.16, 0);
  pelvisMesh.castShadow = true;
  torsoGroup.add(pelvisMesh);

  // Executive necktie / accent ribbon
  const tieMat = pool.getMaterial(`tie-${profile.badgeAccentHex}`, () =>
    new THREE.MeshStandardMaterial({
      color: profile.badgeAccentHex,
      roughness: 0.65,
      metalness: 0.1,
    })
  );
  const tieGeo = new THREE.BoxGeometry(0.032, 0.14, 0.012);
  const tieMesh = new THREE.Mesh(tieGeo, tieMat);
  tieMesh.position.set(0, 0.08, 0.08);
  torsoGroup.add(tieMesh);

  rig.add(torsoGroup);

  // 2. Neck & Head with Realistic Facial Features
  const neckMesh = new THREE.Mesh(pool.neckGeo, skinMat);
  neckMesh.position.set(0, 0.74, 0.01);
  neckMesh.castShadow = true;
  rig.add(neckMesh);

  const headGroup = new THREE.Group();
  headGroup.name = 'head-group';
  headGroup.position.set(0, 0.83, 0.02);

  const headMesh = new THREE.Mesh(pool.headGeo, skinMat);
  headMesh.castShadow = true;
  headGroup.add(headMesh);

  // Anatomical chin & jaw contour: transforms spherical head into realistic human jawline
  const chinMesh = new THREE.Mesh(pool.chinGeo, skinMat);
  chinMesh.position.set(0, -0.054, 0.022);
  chinMesh.castShadow = true;
  headGroup.add(chinMesh);

  // Stylized realistic facial features
  const eyeWhiteMat = pool.getMaterial('avatar-eye-white', () =>
    new THREE.MeshBasicMaterial({ color: 0xffffff })
  );
  const eyeMat = pool.getMaterial('avatar-eye-iris', () =>
    new THREE.MeshBasicMaterial({ color: 0x243c5a })
  );
  const pupilMat = pool.getMaterial('avatar-eye-pupil', () =>
    new THREE.MeshBasicMaterial({ color: 0x09090b })
  );
  const glintMat = pool.getMaterial('avatar-eye-glint', () =>
    new THREE.MeshBasicMaterial({ color: 0xffffff })
  );
  const lashMat = pool.getMaterial('avatar-eye-lash', () =>
    new THREE.MeshBasicMaterial({ color: 0x0f172a })
  );
  const browMat = pool.getMaterial(`avatar-brow-${hairColor}`, () =>
    new THREE.MeshBasicMaterial({ color: hairColor })
  );

  const eyeWhiteGeo = new THREE.SphereGeometry(0.012, 6, 6);
  const eyeGeo = new THREE.SphereGeometry(0.008, 6, 6);
  const browGeo = new THREE.BoxGeometry(0.018, 0.005, 0.008);

  for (const side of [-1, 1]) {
    // Sclera (eye white)
    const eyeWhite = new THREE.Mesh(eyeWhiteGeo, eyeWhiteMat);
    eyeWhite.position.set(side * 0.025, 0.008, 0.065);
    headGroup.add(eyeWhite);

    // Iris (colored)
    const eye = new THREE.Mesh(eyeGeo, eyeMat);
    eye.position.set(side * 0.025, 0.008, 0.073);
    headGroup.add(eye);

    // Dark inner pupil
    const pupil = new THREE.Mesh(pool.eyePupilGeo, pupilMat);
    pupil.position.set(side * 0.025, 0.008, 0.078);
    headGroup.add(pupil);

    // Specular catchlight / glint (gives eyes lifelike MMORPG expression)
    const glint = new THREE.Mesh(pool.eyeGlintGeo, glintMat);
    glint.position.set(side * 0.025 + 0.003, 0.011, 0.081);
    headGroup.add(glint);

    // Upper eyelash contour
    const lash = new THREE.Mesh(pool.eyelashGeo, lashMat);
    lash.position.set(side * 0.025, 0.017, 0.072);
    headGroup.add(lash);

    // Eyebrow
    const brow = new THREE.Mesh(browGeo, browMat);
    brow.position.set(side * 0.025, 0.025, 0.07);
    brow.rotation.z = side * -0.06;
    headGroup.add(brow);

    // Subtle ear definition
    const ear = new THREE.Mesh(new THREE.SphereGeometry(0.013, 6, 6), skinMat);
    ear.scale.set(0.4, 1.1, 0.7);
    ear.position.set(side * 0.068, 0.005, -0.008);
    headGroup.add(ear);
  }

  // Architectural nose bridge contour
  const nose = new THREE.Mesh(new THREE.BoxGeometry(0.01, 0.018, 0.012), skinMat);
  nose.position.set(0, 0.004, 0.071);
  headGroup.add(nose);

  // Subtle mouth expression
  const mouthMat = pool.getMaterial('avatar-mouth-tint', () =>
    new THREE.MeshBasicMaterial({ color: 0x9e6758 })
  );
  const mouth = new THREE.Mesh(pool.mouthGeo, mouthMat);
  mouth.position.set(0, -0.034, 0.066);
  headGroup.add(mouth);

  // Professional glasses on intellectual/executive profiles
  const hasGlasses = (hashStringSeed(agent.id) % 3) === 0;
  if (hasGlasses) {
    const glassesFrameMat = pool.getMaterial('avatar-glasses-frame', () =>
      new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.25, metalness: 0.85 })
    );
    const rimGeo = new THREE.TorusGeometry(0.016, 0.0024, 6, 12);
    for (const side of [-1, 1]) {
      const rim = new THREE.Mesh(rimGeo, glassesFrameMat);
      rim.position.set(side * 0.025, 0.008, 0.076);
      headGroup.add(rim);
    }
    const bridge = new THREE.Mesh(new THREE.BoxGeometry(0.016, 0.003, 0.003), glassesFrameMat);
    bridge.position.set(0, 0.01, 0.077);
    headGroup.add(bridge);
  }

  // Hair according to deterministic style: full cranial dome covering temples and back of head
  let hairGeo: THREE.BufferGeometry;
  let hairOffsetY = 0.006;
  let hairOffsetZ = -0.005;
  switch (hairStyle) {
    case 'EXECUTIVE_SIDE_PART':
      hairGeo = pool.hairSidePartGeo;
      hairOffsetY = 0.008;
      hairOffsetZ = -0.004;
      break;
    case 'CROP_TEXTURED':
      hairGeo = pool.hairCropGeo;
      hairOffsetY = 0.008;
      hairOffsetZ = -0.004;
      break;
    case 'MODERN_MID':
      hairGeo = pool.hairMidGeo;
      hairOffsetY = 0.004;
      hairOffsetZ = -0.006;
      break;
    case 'SHORT_CLASSIC':
    default:
      hairGeo = pool.hairShortGeo;
      hairOffsetY = 0.006;
      hairOffsetZ = -0.005;
      break;
  }
  const hairMesh = new THREE.Mesh(hairGeo, hairMat);
  hairMesh.position.set(0, hairOffsetY, hairOffsetZ);
  hairMesh.castShadow = true;
  headGroup.add(hairMesh);

  // Anatomical sideburns framing both temples down to the ear
  for (const side of [-1, 1]) {
    const sideburn = new THREE.Mesh(pool.hairSideburnGeo, hairMat);
    sideburn.position.set(side * 0.076, 0.015, 0.018);
    headGroup.add(sideburn);
  }

  // Stylized 3D hair bangs / locks framing forehead and temples for MMORPG depth
  if (hairStyle === 'EXECUTIVE_SIDE_PART') {
    const bangs = new THREE.Mesh(pool.hairBangsSideGeo, hairMat);
    bangs.position.set(-0.025, 0.048, 0.068);
    bangs.rotation.z = -0.25;
    bangs.rotation.y = 0.15;
    headGroup.add(bangs);
  } else if (hairStyle === 'CROP_TEXTURED') {
    const bangs = new THREE.Mesh(pool.hairBangsCropGeo, hairMat);
    bangs.position.set(0, 0.046, 0.068);
    headGroup.add(bangs);
  } else if (hairStyle === 'MODERN_MID') {
    for (const side of [-1, 1]) {
      const strand = new THREE.Mesh(pool.hairBangsMidGeo, hairMat);
      strand.position.set(side * 0.068, 0.005, 0.025);
      strand.rotation.z = side * 0.12;
      headGroup.add(strand);
    }
  } else {
    // SHORT_CLASSIC bangs framing the forehead hairline
    const bangs = new THREE.Mesh(pool.hairBangsCropGeo, hairMat);
    bangs.position.set(0, 0.048, 0.068);
    headGroup.add(bangs);
  }

  rig.add(headGroup);

  // 3. Corporate Lanyard & Identification Badge: sleek woven fabric straps flush to chest
  const badgeGroup = new THREE.Group();
  badgeGroup.name = 'badge-group';
  badgeGroup.position.set(0, 0.52, 0.076);

  const lanyardMat = pool.getMaterial(`lanyard-${profile.badgeAccentHex}`, () =>
    new THREE.MeshStandardMaterial({
      color: profile.badgeAccentHex,
      roughness: 0.65,
      metalness: 0.08,
    })
  );

  const leftStrap = new THREE.Mesh(pool.lanyardStrapGeo, lanyardMat);
  leftStrap.position.set(-0.032, 0.09, -0.008);
  leftStrap.rotation.z = -0.28;
  badgeGroup.add(leftStrap);

  const rightStrap = new THREE.Mesh(pool.lanyardStrapGeo, lanyardMat);
  rightStrap.position.set(0.032, 0.09, -0.008);
  rightStrap.rotation.z = 0.28;
  badgeGroup.add(rightStrap);

  const clipMat = pool.getMaterial('badge-clip-metal', () =>
    new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.25, metalness: 0.85 })
  );
  const badgeClipMesh = new THREE.Mesh(pool.badgeClipGeo, clipMat);
  badgeClipMesh.position.set(0, 0.052, 0.001);
  badgeGroup.add(badgeClipMesh);

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
  const badgeHeaderGeo = new THREE.BoxGeometry(0.058, 0.024, 0.006);
  const badgeHeaderMesh = new THREE.Mesh(
    badgeHeaderGeo,
    pool.getMaterial(`badge-header-${profile.badgeAccentHex}`, () =>
      new THREE.MeshBasicMaterial({ color: profile.badgeAccentHex })
    )
  );
  badgeHeaderMesh.position.set(0, 0.032, 0.001);
  badgeGroup.add(badgeHeaderMesh);

  // Status indicator dot on badge (Health status telemetry dot)
  let statusColor = 0x94a3b8;
  if (agent.heartbeatStatus === 'HEALTHY') statusColor = 0x22c55e;
  else if (agent.heartbeatStatus === 'STALE') statusColor = 0xeab308;
  else if (agent.heartbeatStatus === 'UNAVAILABLE') statusColor = 0xef4444;

  const statusDotGeo = new THREE.BoxGeometry(0.012, 0.012, 0.008);
  const statusDotMesh = new THREE.Mesh(
    statusDotGeo,
    pool.getMaterial(`badge-status-${statusColor}`, () =>
      new THREE.MeshBasicMaterial({ color: statusColor })
    )
  );
  statusDotMesh.position.set(0.018, -0.026, 0.002);
  badgeGroup.add(statusDotMesh);

  rig.add(badgeGroup);

  // 4. Arms with Anatomical Tailored Hierarchy (Shoulder cap -> Upper Arm -> Forearm -> Hand)
  // Left Arm Group (pivot at shoulder joint y = 0.72, x = -0.19)
  const leftArmGroup = new THREE.Group();
  leftArmGroup.name = 'left-arm-group';
  leftArmGroup.position.set(-0.20, 0.71, 0);

  const leftShoulder = new THREE.Mesh(pool.shoulderGeo, suitMat);
  leftShoulder.position.set(0, 0, 0);
  leftArmGroup.add(leftShoulder);

  const leftUpperArm = new THREE.Mesh(pool.upperArmGeo, suitMat);
  leftUpperArm.position.set(0, -0.065, 0);
  leftUpperArm.castShadow = true;
  leftArmGroup.add(leftUpperArm);

  const leftForearmGroup = new THREE.Group();
  leftForearmGroup.position.set(0, -0.155, 0);

  const leftForearm = new THREE.Mesh(pool.forearmGeo, suitMat);
  leftForearm.position.set(0, -0.07, 0.025);
  leftForearm.rotation.x = -0.35;
  leftForearm.castShadow = true;
  leftForearmGroup.add(leftForearm);

  const leftHand = new THREE.Mesh(pool.handGeo, skinMat);
  leftHand.position.set(0, -0.15, 0.05);
  leftHand.castShadow = true;
  leftForearmGroup.add(leftHand);

  const leftThumb = new THREE.Mesh(pool.thumbGeo, skinMat);
  leftThumb.position.set(0.018, -0.145, 0.055);
  leftThumb.rotation.z = 0.35;
  leftForearmGroup.add(leftThumb);

  // Sartorial sleeve cuff & executive wristwatch
  const leftCuff = new THREE.Mesh(pool.cuffGeo, suitMat);
  leftCuff.position.set(0, -0.12, 0.04);
  leftCuff.rotation.x = -0.35;
  leftForearmGroup.add(leftCuff);

  const watchMat = pool.getMaterial('avatar-watch-metal', () =>
    new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.25, metalness: 0.9 })
  );
  const watch = new THREE.Mesh(pool.watchGeo, watchMat);
  watch.position.set(-0.038, -0.12, 0.04);
  leftForearmGroup.add(watch);

  leftArmGroup.add(leftForearmGroup);
  rig.add(leftArmGroup);

  // Right Arm Group (pivot at shoulder joint y = 0.72, x = 0.19)
  const rightArmGroup = new THREE.Group();
  rightArmGroup.name = 'right-arm-group';
  rightArmGroup.position.set(0.20, 0.71, 0);

  const rightShoulder = new THREE.Mesh(pool.shoulderGeo, suitMat);
  rightShoulder.position.set(0, 0, 0);
  rightArmGroup.add(rightShoulder);

  const rightUpperArm = new THREE.Mesh(pool.upperArmGeo, suitMat);
  rightUpperArm.position.set(0, -0.065, 0);
  rightUpperArm.castShadow = true;
  rightArmGroup.add(rightUpperArm);

  const rightForearmGroup = new THREE.Group();
  rightForearmGroup.position.set(0, -0.155, 0);

  const rightForearm = new THREE.Mesh(pool.forearmGeo, suitMat);
  rightForearm.position.set(0, -0.07, 0.025);
  rightForearm.rotation.x = -0.35;
  rightForearm.castShadow = true;
  rightForearmGroup.add(rightForearm);

  const rightCuff = new THREE.Mesh(pool.cuffGeo, suitMat);
  rightCuff.position.set(0, -0.12, 0.04);
  rightCuff.rotation.x = -0.35;
  rightForearmGroup.add(rightCuff);

  const rightHand = new THREE.Mesh(pool.handGeo, skinMat);
  rightHand.position.set(0, -0.15, 0.05);
  rightHand.castShadow = true;
  rightForearmGroup.add(rightHand);

  const rightThumb = new THREE.Mesh(pool.thumbGeo, skinMat);
  rightThumb.position.set(-0.018, -0.145, 0.055);
  rightThumb.rotation.z = -0.35;
  rightForearmGroup.add(rightThumb);

  // Small reusable prop, shown only during explicitly ambient walking. It is
  // visual storytelling, never a claim about real agent activity.
  const coffeeCup = new THREE.Group();
  coffeeCup.name = 'ambient-coffee-cup';
  const cup = new THREE.Mesh(
    new THREE.CylinderGeometry(0.043, 0.036, 0.09, 12),
    new THREE.MeshStandardMaterial({ color: 0xf5f1e8, roughness: 0.65 }),
  );
  cup.position.set(0, -0.015, 0.025);
  coffeeCup.add(cup);
  const coffee = new THREE.Mesh(
    new THREE.CircleGeometry(0.039, 12),
    new THREE.MeshStandardMaterial({ color: 0x53321f, roughness: 0.8, side: THREE.DoubleSide }),
  );
  coffee.rotation.x = -Math.PI / 2;
  coffee.position.set(0, 0.032, 0.025);
  coffeeCup.add(coffee);
  const rim = new THREE.Mesh(
    new THREE.TorusGeometry(0.043, 0.0035, 6, 14),
    new THREE.MeshStandardMaterial({ color: 0xe2ded4, roughness: 0.6 }),
  );
  rim.rotation.x = Math.PI / 2;
  rim.position.set(0, 0.032, 0.025);
  coffeeCup.add(rim);
  const handle = new THREE.Mesh(
    new THREE.TorusGeometry(0.027, 0.006, 6, 10, Math.PI * 1.5),
    new THREE.MeshStandardMaterial({ color: 0xf5f1e8, roughness: 0.65 }),
  );
  handle.position.set(0.049, -0.008, 0.025);
  handle.rotation.z = -Math.PI / 2;
  coffeeCup.add(handle);
  // Keep the cup centered in the palm's grasp. The previous -0.17 m offset
  // placed it below the hand, making the small mug read like a dangling prop.
  coffeeCup.position.set(0, -0.045, 0.09);
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

  const soleMat = pool.getMaterial('avatar-shoe-sole-mat', () =>
    new THREE.MeshStandardMaterial({ color: 0x09090b, roughness: 0.85, metalness: 0.1 })
  );

  const leftShoe = new THREE.Mesh(pool.shoeGeo, shoeMat);
  leftShoe.position.set(0, -0.17, 0.035);
  leftShoe.castShadow = true;
  leftShinGroup.add(leftShoe);

  const leftSole = new THREE.Mesh(pool.shoeSoleGeo, soleMat);
  leftSole.position.set(0, -0.19, 0.035);
  leftSole.castShadow = true;
  leftShinGroup.add(leftSole);

  const leftHeel = new THREE.Mesh(pool.shoeHeelGeo, soleMat);
  leftHeel.position.set(0, -0.20, -0.015);
  leftHeel.castShadow = true;
  leftShinGroup.add(leftHeel);

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

  const rightSole = new THREE.Mesh(pool.shoeSoleGeo, soleMat);
  rightSole.position.set(0, -0.19, 0.035);
  rightSole.castShadow = true;
  rightShinGroup.add(rightSole);

  const rightHeel = new THREE.Mesh(pool.shoeHeelGeo, soleMat);
  rightHeel.position.set(0, -0.20, -0.015);
  rightHeel.castShadow = true;
  rightShinGroup.add(rightHeel);

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
 * Builds an articulated enterprise humanoid NPC for ambient office world operations
 * (Receptionist, Runner, Copy-Room Courier) adhering to the naturalistic 3D quality standard.
 * Strictly separates ambient visual presence from authorized agent identity and business evidence.
 */
export function buildAmbientHumanoidNpc(
  npcId: string,
  profile: AvatarAppearanceProfile,
  pool: AvatarResourcePool,
  accessory?: 'runner-tablet' | 'copy-documents' | 'reception-folder'
): { group: THREE.Group; swingParts: THREE.Object3D[] } {
  const syntheticAgent: AgentIdentity = {
    id: npcId,
    name:
      npcId === 'npc:receptionist'
        ? 'Recepción AAO'
        : npcId === 'npc:office-runner'
        ? 'Mensajería Interna'
        : 'Centro de Documentación',
    type: 'STANDING',
    status: 'IDLE',
    unitId: 'unit-amenities',
    currentAssignments: [],
    authorityBoundary: 'AMBIENT_SIMULATION',
    heartbeatStatus: 'HEALTHY',
    lastHeartbeatAt: null,
    roleTitle: 'Servicios de Edificio',
    capabilities: [],
  };
  const syntheticActivity: ProjectedAgentActivity = {
    agentId: npcId,
    kind: 'WALKING',
    provenance: 'AMBIENT_ANIMATION',
    label: 'Servicio General',
    shortBadge: profile.badgeDepartmentCode,
    detail: 'Movimiento ambiental de edificio',
    isLeaseExpired: false,
    activeTaskId: null,
    activeProjectId: null,
    conversationPartnerId: null,
  };

  const { rig, parts } = buildHumanoidCharacterRig(syntheticAgent, syntheticActivity, profile, pool);
  const group = new THREE.Group();
  group.name = npcId;
  group.add(rig);

  if (accessory === 'runner-tablet' && parts.rightHand) {
    const tabletGeo = new THREE.BoxGeometry(0.14, 0.012, 0.2);
    const tabletMat = pool.getMaterial('npc-tablet-mat', () =>
      new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.35, metalness: 0.6 })
    );
    const tabletScreenMat = pool.getMaterial('npc-tablet-screen-mat', () =>
      new THREE.MeshBasicMaterial({ color: 0x38bdf8 })
    );
    const tablet = new THREE.Mesh(tabletGeo, tabletMat);
    tablet.position.set(0, -0.04, 0.08);
    const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.11, 0.16), tabletScreenMat);
    screen.rotation.x = -Math.PI / 2;
    screen.position.set(0, 0.007, 0);
    tablet.add(screen);
    parts.rightHand.add(tablet);
  } else if (accessory === 'copy-documents' && parts.leftForearm) {
    const docGeo = new THREE.BoxGeometry(0.16, 0.03, 0.22);
    const docMat = pool.getMaterial('npc-documents-mat', () =>
      new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.85, metalness: 0.02 })
    );
    const docs = new THREE.Mesh(docGeo, docMat);
    docs.position.set(0.06, -0.08, 0.06);
    parts.leftForearm.add(docs);
  }

  // swingParts: [leftLeg, rightLeg, leftArm, rightArm]
  const swingParts: THREE.Object3D[] = [];
  if (parts.leftLeg) swingParts.push(parts.leftLeg);
  if (parts.rightLeg) swingParts.push(parts.rightLeg);
  if (parts.leftArm) swingParts.push(parts.leftArm);
  if (parts.rightArm) swingParts.push(parts.rightArm);

  group.userData = { parts: swingParts, semanticParts: parts };
  return { group, swingParts };
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
    authoritativePosition?: { x: number; z: number; facingAngle: number };
    /** Presentation-only gesture override for an ambient NPC encounter. */
    ambientInteraction?: boolean;
    sampleWaypointRoute?: (
      waypoints: ReadonlyArray<{ x: number; z: number }>,
      time: number,
      offsetSec: number
    ) => { x: number; z: number; facingAngle: number };
    obstacleAvoidance?: { x: number; z: number };
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
  const kind = options.ambientInteraction ? 'CONVERSING' : placement.activity.kind;
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
  if (options.authoritativePosition) {
    destX = options.authoritativePosition.x;
    destZ = options.authoritativePosition.z;
    destAngle = options.authoritativePosition.facingAngle;
  }
  if (options.obstacleAvoidance) {
    destX += options.obstacleAvoidance.x;
    destZ += options.obstacleAvoidance.z;
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
    group.position.y = 0.37;
    parts.characterRig.position.y = -0.28;
    if (parts.halo) parts.halo.visible = false;

    // Thighs horizontal in chair
    if (parts.leftLeg) parts.leftLeg.rotation.x = -Math.PI / 2.3;
    if (parts.rightLeg) parts.rightLeg.rotation.x = -Math.PI / 2.3;

    // Knees bent 90 degrees downward to floor with grounded feet
    if (parts.leftShin) parts.leftShin.rotation.x = Math.PI / 2.2;
    if (parts.rightShin) parts.rightShin.rotation.x = Math.PI / 2.2;
    if (parts.leftShin) parts.leftShin.scale.y = 1.95;
    if (parts.rightShin) parts.rightShin.scale.y = 1.95;
    if (parts.leftShoe) parts.leftShoe.scale.y = 1 / 1.95;
    if (parts.rightShoe) parts.rightShoe.scale.y = 1 / 1.95;

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
    if (placement.isSeated) {
      group.position.y = 0.37;
      parts.characterRig.position.y = -0.28;
      if (parts.halo) parts.halo.visible = false;

      if (parts.leftLeg) parts.leftLeg.rotation.x = -Math.PI / 2.3;
      if (parts.rightLeg) parts.rightLeg.rotation.x = -Math.PI / 2.3;
      if (parts.leftShin) parts.leftShin.rotation.x = Math.PI / 2.2;
      if (parts.rightShin) parts.rightShin.rotation.x = Math.PI / 2.2;
      if (parts.leftShin) parts.leftShin.scale.y = 1.95;
      if (parts.rightShin) parts.rightShin.scale.y = 1.95;
      if (parts.leftShoe) parts.leftShoe.scale.y = 1 / 1.95;
      if (parts.rightShoe) parts.rightShoe.scale.y = 1 / 1.95;
    } else {
      group.position.y = 0.02;
      parts.characterRig.position.y = 0;
      if (parts.halo) parts.halo.visible = true;

      if (parts.leftLeg) parts.leftLeg.rotation.x = 0;
      if (parts.rightLeg) parts.rightLeg.rotation.x = 0;
      if (parts.leftShin) parts.leftShin.rotation.x = 0;
      if (parts.rightShin) parts.rightShin.rotation.x = 0;
      if (parts.leftShin) parts.leftShin.scale.y = 1;
      if (parts.rightShin) parts.rightShin.scale.y = 1;
      if (parts.leftShoe) parts.leftShoe.scale.y = 1;
      if (parts.rightShoe) parts.rightShoe.scale.y = 1;
    }

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
      parts.speechBubble.visible = !options.ambientInteraction;
      if (!options.ambientInteraction) {
        parts.speechBubble.position.y = 2.02 + Math.sin(time * 0.006 + phase) * 0.03;
      }
    }
  } else if (kind === 'WALKING') {
    // Sinusoidal walking stride with counter-swinging arms and vertical bob
    group.position.y = 0.02;
    if (parts.halo) parts.halo.visible = true;
    const walkCycle = time * 0.01 + phase;
    const stride = Math.sin(walkCycle);

    parts.characterRig.position.y = isFarDistance ? 0 : Math.abs(stride) * 0.025;
    if (parts.leftShin) parts.leftShin.scale.y = 1;
    if (parts.rightShin) parts.rightShin.scale.y = 1;
    if (parts.leftShoe) parts.leftShoe.scale.y = 1;
    if (parts.rightShoe) parts.rightShoe.scale.y = 1;

    // Alternating leg swing with knee flexion on back-step
    if (parts.leftLeg) parts.leftLeg.rotation.x = stride * 0.44;
    if (parts.rightLeg) parts.rightLeg.rotation.x = -stride * 0.44;

    if (parts.leftShin) {
      parts.leftShin.rotation.x = stride > 0 ? stride * 0.48 : 0;
    }
    if (parts.rightShin) {
      parts.rightShin.rotation.x = stride < 0 ? -stride * 0.48 : 0;
    }

    // Counter-swinging arms with natural elbow flexion
    if (parts.leftArm) {
      parts.leftArm.rotation.x = -stride * 0.34;
      parts.leftArm.rotation.z = -0.06;
    }
    if (parts.rightArm) {
      parts.rightArm.rotation.x = stride * 0.34;
      parts.rightArm.rotation.z = 0.06;
    }
    if (parts.leftForearm) {
      parts.leftForearm.rotation.x = -0.35 + Math.max(0, -stride * 0.2);
    }
    if (parts.rightForearm) {
      parts.rightForearm.rotation.x = -0.35 + Math.max(0, stride * 0.2);
    }

    if (parts.head) {
      parts.head.rotation.x = 0;
      parts.head.rotation.y = 0;
    }

    if (parts.speechBubble) parts.speechBubble.visible = false;
  } else if (kind === 'IDLE_DESK') {
    // Relaxed seated posture
    group.position.y = 0.37;
    parts.characterRig.position.y = -0.28;
    if (parts.coffeeCup) parts.coffeeCup.visible = false;
    if (parts.halo) parts.halo.visible = false;

    if (parts.leftLeg) parts.leftLeg.rotation.x = -Math.PI / 2.3;
    if (parts.rightLeg) parts.rightLeg.rotation.x = -Math.PI / 2.3;
    if (parts.leftShin) parts.leftShin.rotation.x = Math.PI / 2.2;
    if (parts.rightShin) parts.rightShin.rotation.x = Math.PI / 2.2;
    if (parts.leftShin) parts.leftShin.scale.y = 1.95;
    if (parts.rightShin) parts.rightShin.scale.y = 1.95;
    if (parts.leftShoe) parts.leftShoe.scale.y = 1 / 1.95;
    if (parts.rightShoe) parts.rightShoe.scale.y = 1 / 1.95;

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
    // Default neutral standing posture with natural idle breathing & weight shift
    group.position.y = 0.02;
    parts.characterRig.position.y = 0;

    if (parts.torso) {
      parts.torso.position.y = 0.52 + (isFarDistance ? 0 : Math.sin(time * 0.003 + phase) * 0.004);
      parts.torso.rotation.z = isFarDistance ? 0 : Math.sin(time * 0.0015 + phase) * 0.012;
    }

    if (parts.leftLeg) parts.leftLeg.rotation.x = 0;
    if (parts.rightLeg) parts.rightLeg.rotation.x = 0;
    if (parts.leftShin) parts.leftShin.rotation.x = 0;
    if (parts.rightShin) parts.rightShin.rotation.x = 0;
    if (parts.leftShin) parts.leftShin.scale.y = 1;
    if (parts.rightShin) parts.rightShin.scale.y = 1;
    if (parts.leftShoe) parts.leftShoe.scale.y = 1;
    if (parts.rightShoe) parts.rightShoe.scale.y = 1;

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
      parts.head.rotation.y = isFarDistance ? 0 : Math.sin(time * 0.002 + phase) * 0.04;
      parts.head.rotation.z = isFarDistance ? 0 : -Math.sin(time * 0.0015 + phase) * 0.008;
    }

    if (parts.speechBubble) parts.speechBubble.visible = false;
  }
}
