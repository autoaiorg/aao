import * as THREE from 'three';
import type { AgentIdentity } from '../../../domain/models';
import {
  OFFICE_ROOMS,
  type CameraViewState,
  type OfficeCameraPreset,
  type OfficeGraphicsQuality,
  type OfficeLabelLodTier,
  type OfficeRoomConfig,
  type OfficeScenePerfMetrics,
} from '../types';
import { buildCampusNavGraph, computeCampusBounds } from '../liveOfficeLayout';
import {
  AvatarResourcePool,
  buildAgentAvatar as buildHumanoidAgentAvatar,
  stepAvatarKinematics,
  type AvatarSemanticParts,
} from './AvatarRenderer';
import {
  buildDepartmentInteriorLayout,
  computeAdaptiveLabelStates,
  deriveLabelLodTier,
  planOfficeLifePlacements,
  sampleWaypointRoute,
  type PlannedAgentPlacement,
  type ProjectedAgentActivity,
} from './officeLifeEngine';

export type { AvatarSemanticParts };

export interface ThreeSceneCallbacks {
  onSelectRoom: (roomId: string) => void;
  onSelectAgent: (agentId: string) => void;
  onHoverObject: (info: { type: 'room' | 'agent'; id: string } | null) => void;
  onCameraChange?: (state: CameraViewState) => void;
}

export interface ThreeSceneOptions {
  reducedMotion?: boolean;
  qualityProfile?: OfficeGraphicsQuality;
  callbacks: ThreeSceneCallbacks;
  renderer?: THREE.WebGLRenderer;
  rooms?: OfficeRoomConfig[];
  demoFurniture?: boolean;
  dragMode?: 'pan' | 'orbit';
  activeCoordinationAgentIds?: ReadonlySet<string>;
}

interface AgentAnimatedRuntimeState {
  currentX: number;
  currentZ: number;
  currentAngle: number;
  placement: PlannedAgentPlacement;
}

/**
 * Shared geometry and material pool for repetitive office furniture
 * (desks, chairs, monitors, keyboards) to minimize GPU memory footprint and draw overhead.
 */
export function createProceduralIdeTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 128;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    // Dark editor background
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, 256, 128);

    // Sidebar panel
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, 48, 128);

    // Sidebar file tree lines
    ctx.fillStyle = '#64748b';
    for (let y = 14; y < 110; y += 14) {
      ctx.fillRect(8, y, 28, 4);
    }

    // Tab bar
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(48, 0, 208, 18);
    ctx.fillStyle = '#38bdf8';
    ctx.fillRect(52, 4, 46, 10);

    // Code lines in editor area with syntax colors
    const colors = ['#f43f5e', '#38bdf8', '#a855f7', '#22c55e', '#f59e0b', '#e2e8f0'];
    let lineY = 28;
    for (let i = 0; i < 7; i++) {
      let lineX = 56 + (i % 3 === 0 ? 0 : (i % 2) * 12);
      const segments = 2 + (i % 4);
      for (let s = 0; s < segments; s++) {
        const segWidth = 14 + ((i * 7 + s * 13) % 26);
        ctx.fillStyle = colors[(i + s) % colors.length];
        ctx.fillRect(lineX, lineY, segWidth, 5);
        lineX += segWidth + 6;
      }
      lineY += 12;
    }

    // Status bar at bottom
    ctx.fillStyle = '#2563eb';
    ctx.fillRect(48, 116, 208, 12);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(54, 120, 24, 4);
    ctx.fillRect(84, 120, 36, 4);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.generateMipmaps = true;
  return texture;
}

export class SharedFurniturePool {
  public readonly deskTopGeo = new THREE.BoxGeometry(0.95, 0.06, 0.48);
  public readonly deskLegGeo = new THREE.BoxGeometry(0.06, 0.42, 0.44);
  public readonly monitorPanelGeo = new THREE.BoxGeometry(0.36, 0.24, 0.03);
  public readonly ultrawideMonitorGeo = new THREE.BoxGeometry(0.58, 0.26, 0.03);
  public readonly monitorStandGeo = new THREE.BoxGeometry(0.06, 0.12, 0.06);
  public readonly keyboardGeo = new THREE.BoxGeometry(0.28, 0.02, 0.11);
  public readonly mouseGeo = new THREE.BoxGeometry(0.05, 0.02, 0.08);
  public readonly deskGrommetGeo = new THREE.CylinderGeometry(0.035, 0.035, 0.07, 12);

  public readonly chairBaseGeo = new THREE.CylinderGeometry(0.18, 0.2, 0.05, 12);
  public readonly chairStemGeo = new THREE.CylinderGeometry(0.035, 0.035, 0.2, 10);
  public readonly chairSeatGeo = new THREE.BoxGeometry(0.34, 0.05, 0.34);
  public readonly chairBackGeo = new THREE.BoxGeometry(0.32, 0.36, 0.05);
  public readonly chairArmGeo = new THREE.BoxGeometry(0.04, 0.14, 0.22);

  public readonly meetingTableTopGeo = new THREE.CylinderGeometry(0.46, 0.46, 0.05, 20);
  public readonly meetingTablePedGeo = new THREE.CylinderGeometry(0.12, 0.22, 0.4, 14);

  public readonly planterPotGeo = new THREE.CylinderGeometry(0.18, 0.14, 0.36, 14);
  public readonly plantFoliageGeo = new THREE.DodecahedronGeometry(0.24, 1);

  public readonly ideTexture = createProceduralIdeTexture();
  public readonly monitorIdeMat = new THREE.MeshBasicMaterial({
    map: this.ideTexture,
  });

  public readonly deskWoodMat = new THREE.MeshStandardMaterial({
    color: 0x1e293b,
    roughness: 0.45,
    metalness: 0.35,
  });
  public readonly holdingDeskMat = new THREE.MeshStandardMaterial({
    color: 0x334155,
    roughness: 0.65,
    metalness: 0.2,
  });
  public readonly metalLegMat = new THREE.MeshStandardMaterial({
    color: 0x0f172a,
    roughness: 0.3,
    metalness: 0.7,
  });
  public readonly chairCushionMat = new THREE.MeshStandardMaterial({
    color: 0x334155,
    roughness: 0.65,
    metalness: 0.15,
  });
  public readonly keyboardMat = new THREE.MeshStandardMaterial({
    color: 0xcbd5e1,
    roughness: 0.4,
    metalness: 0.4,
  });
  public readonly meetingTableMat = new THREE.MeshStandardMaterial({
    color: 0x273549,
    roughness: 0.4,
    metalness: 0.4,
  });
  public readonly plantPotMat = new THREE.MeshStandardMaterial({
    color: 0xe2e8f0,
    roughness: 0.45,
    metalness: 0.1,
  });
  public readonly plantLeafMat = new THREE.MeshStandardMaterial({
    color: 0x225e3b,
    roughness: 0.65,
    metalness: 0.1,
  });
  public readonly deskTrimMat = new THREE.MeshStandardMaterial({
    color: 0x334155,
    roughness: 0.4,
    metalness: 0.5,
  });

  private readonly allGeometries: THREE.BufferGeometry[];
  private readonly allMaterials: THREE.Material[];

  constructor() {
    this.allGeometries = [
      this.deskTopGeo,
      this.deskLegGeo,
      this.monitorPanelGeo,
      this.ultrawideMonitorGeo,
      this.monitorStandGeo,
      this.keyboardGeo,
      this.mouseGeo,
      this.deskGrommetGeo,
      this.chairBaseGeo,
      this.chairStemGeo,
      this.chairSeatGeo,
      this.chairBackGeo,
      this.chairArmGeo,
      this.meetingTableTopGeo,
      this.meetingTablePedGeo,
      this.planterPotGeo,
      this.plantFoliageGeo,
    ];
    this.allMaterials = [
      this.deskWoodMat,
      this.holdingDeskMat,
      this.metalLegMat,
      this.chairCushionMat,
      this.keyboardMat,
      this.meetingTableMat,
      this.monitorIdeMat,
      this.plantPotMat,
      this.plantLeafMat,
      this.deskTrimMat,
    ];
  }

  public getGeometriesCount(): number {
    return this.allGeometries.length;
  }

  public getMaterialsCount(): number {
    return this.allMaterials.length;
  }

  public ownsGeometry(geo: THREE.BufferGeometry): boolean {
    return this.allGeometries.includes(geo);
  }

  public ownsMaterial(mat: THREE.Material): boolean {
    return this.allMaterials.includes(mat);
  }

  public dispose(): void {
    this.allGeometries.forEach((g) => g.dispose());
    this.allMaterials.forEach((m) => m.dispose());
    this.ideTexture.dispose();
  }
}

export class ThreeOfficeScene {
  private container: HTMLElement;
  private options: ThreeSceneOptions;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private rooms: OfficeRoomConfig[];
  private animFrameId: number | null = null;
  private isDisposed = false;
  private contextLost = false;
  private furniturePool = new SharedFurniturePool();
  private avatarPool = new AvatarResourcePool();
  private qualityProfile: OfficeGraphicsQuality = 'balanced';

  // Interaction & Raycasting
  private raycaster = new THREE.Raycaster();
  private mouse = new THREE.Vector2();
  private pointerDownPos = new THREE.Vector2();
  private isDragging = false;
  private readonly activePointers = new Map<number, { x: number; y: number }>();
  private lastPinchDistance: number | null = null;
  private lastTwoFingerAngle: number | null = null;
  private gestureDragDistance = 0;

  // Camera Orbit, Smart Zoom & Follow parameters
  private cameraAngle = 35; // degrees around Y
  private desiredAngle = 35;
  private cameraElevation = 42; // degrees tilt
  private desiredElevation = 42;
  private cameraDistance = 24; // distance from target
  private desiredDistance = 24; // smart zoom destination
  private minDistance = 8;
  private maxDistance = 38;
  private cameraTarget = new THREE.Vector3(0, 0, 0);
  private desiredTarget = new THREE.Vector3(0, 0, 0);
  private followSelectedAgent = false;
  private readonly pressedKeys = new Set<string>();

  // Groups and Interactive Meshes
  private roomsGroup = new THREE.Group();
  private agentsGroup = new THREE.Group();
  private lightsGroup = new THREE.Group();
  private walkwaysGroup = new THREE.Group();
  private interactiveMeshes: THREE.Object3D[] = [];
  private roomLabels: Map<string, THREE.Sprite> = new Map();
  private agentMeshes: Map<string, THREE.Group> = new Map();
  private agentRuntimeStates: Map<string, AgentAnimatedRuntimeState> = new Map();
  private currentAgents: AgentIdentity[] = [];
  private lastStateEvaluationMs = 0;

  // Performance & Adaptive Label Telemetry
  private lastFrameTimestampMs = 0;
  private lastFrameIntervalMs = 16.6;
  private lastFrameWorkDurationMs = 0;
  private lastSimulationUpdateDurationMs = 0;
  private smoothedFps = 60;
  private lastStateUpdateDurationMs = 0;
  private sceneBuildDurationMs = 0;
  private visibleDepartmentLabelsCount = 0;
  private visibleAgentLabelsCount = 0;
  private suppressedOverlapLabelsCount = 0;

  private roomSpotlight: THREE.SpotLight | null = null;
  private mainDirLight: THREE.DirectionalLight | null = null;
  private activeRoomId: string = 'unit-exec';
  private activeAgentId: string | null = null;

  // Selected agent selection ring
  private selectionRing: THREE.Mesh | null = null;
  private groundGroup = new THREE.Group();

  constructor(container: HTMLElement, options: ThreeSceneOptions) {
    this.container = container;
    this.options = { ...options, demoFurniture: options.demoFurniture ?? true };
    this.rooms = options.rooms ?? OFFICE_ROOMS;
    this.qualityProfile = options.qualityProfile ?? 'balanced';

    // 1. Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a1628);
    this.scene.fog = new THREE.FogExp2(0x0a1628, 0.016);

    // 2. Camera framed to campus bounds
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;
    this.camera = new THREE.PerspectiveCamera(40, width / height, 0.5, 220);
    const bounds = computeCampusBounds(this.rooms);
    this.cameraTarget.set(bounds.centerX, 0, bounds.centerZ);
    this.desiredTarget.set(bounds.centerX, 0, bounds.centerZ);
    this.cameraDistance = this.computeOverviewDistance(bounds, this.camera.aspect);
    this.desiredDistance = this.cameraDistance;
    this.maxDistance = Math.max(this.maxDistance, this.cameraDistance * 2.5);
    this.camera.far = Math.max(this.camera.far, this.cameraDistance * 3 + 50);
    this.camera.updateProjectionMatrix();
    this.updateCameraPosition();

    // 3. Renderer (supports injected renderer for testing)
    this.renderer =
      options.renderer ||
      new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setSize(width, height);
    this.applyQualityProfileToRenderer();
    this.renderer.domElement.style.display = 'block';
    this.renderer.domElement.style.width = '100%';
    this.renderer.domElement.style.height = '100%';

    // Ensure container is clean before appending new canvas
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
    container.appendChild(this.renderer.domElement);

    // 4. Hierarchy Groups
    this.scene.add(this.walkwaysGroup);
    this.scene.add(this.roomsGroup);
    this.scene.add(this.agentsGroup);
    this.scene.add(this.lightsGroup);
    this.scene.add(this.groundGroup);

    // 5. Build Environment
    const sceneBuildStartedAt = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.setupLighting();
    this.buildWorld();
    this.syncAdaptiveLabels();
    this.sceneBuildDurationMs = Math.max(0, (typeof performance !== 'undefined' ? performance.now() : Date.now()) - sceneBuildStartedAt);

    // 6. Event Listeners
    this.bindEvents();

    // 7. Render Loop
    this.animate = this.animate.bind(this);
    this.animFrameId = requestAnimationFrame(this.animate);
  }

  private applyQualityProfileToRenderer(): void {
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
    if (typeof this.renderer.setPixelRatio === 'function') {
      const targetRatio =
        this.qualityProfile === 'low'
          ? 1
          : this.qualityProfile === 'balanced'
          ? Math.min(dpr, 1.5)
          : Math.min(dpr, 2);
      this.renderer.setPixelRatio(targetRatio);
    }
    if (this.renderer.shadowMap) {
      this.renderer.shadowMap.enabled = this.qualityProfile !== 'low';
      this.renderer.shadowMap.type =
        this.qualityProfile === 'high' ? THREE.PCFSoftShadowMap : THREE.PCFShadowMap;
    }
    if (this.mainDirLight) {
      this.mainDirLight.castShadow = this.qualityProfile !== 'low';
      const shadowSize = this.qualityProfile === 'high' ? 2048 : 1024;
      this.mainDirLight.shadow.mapSize.width = shadowSize;
      this.mainDirLight.shadow.mapSize.height = shadowSize;
    }
    if (this.roomSpotlight) {
      this.roomSpotlight.castShadow = this.qualityProfile === 'high';
    }
  }

  public setQualityProfile(profile: OfficeGraphicsQuality): void {
    this.qualityProfile = profile;
    this.applyQualityProfileToRenderer();
  }

  public getQualityProfile(): OfficeGraphicsQuality {
    return this.qualityProfile;
  }

  public getPerformanceMetrics(): OfficeScenePerfMetrics {
    let geometryBytesApprox = 0;
    let textureBytesApprox = 0;
    const geometries = new Set<THREE.BufferGeometry>();
    const textures = new Set<THREE.Texture>();
    const addMaterialTextures = (material: THREE.Material) => {
      for (const value of Object.values(material as unknown as Record<string, unknown>)) {
        if (value instanceof THREE.Texture) textures.add(value);
      }
    };
    this.scene.traverse((object) => {
      const renderable = object as THREE.Object3D & { geometry?: THREE.BufferGeometry; material?: THREE.Material | THREE.Material[] };
      if (renderable.geometry) geometries.add(renderable.geometry);
      if (Array.isArray(renderable.material)) renderable.material.forEach(addMaterialTextures);
      else if (renderable.material) addMaterialTextures(renderable.material);
    });
    for (const geometry of geometries) {
      for (const attribute of Object.values(geometry.attributes)) {
        geometryBytesApprox += attribute.array.byteLength;
      }
      if (geometry.index) geometryBytesApprox += geometry.index.array.byteLength;
    }
    for (const texture of textures) {
      const image = texture.image as { width?: number; height?: number; naturalWidth?: number; naturalHeight?: number } | undefined;
      const width = image?.width || image?.naturalWidth || 0;
      const height = image?.height || image?.naturalHeight || 0;
      textureBytesApprox += Math.ceil(width * height * 4 * (texture.generateMipmaps ? 4 / 3 : 1));
    }
    const renderInfo = this.renderer.info;
    return {
      qualityProfile: this.qualityProfile,
      fpsEstimate: Math.round(this.smoothedFps),
      lastFrameTimeMs: Number(this.lastFrameIntervalMs.toFixed(2)),
      frameWorkTimeMs: Number(this.lastFrameWorkDurationMs.toFixed(2)),
      simulationUpdateTimeMs: Number(this.lastSimulationUpdateDurationMs.toFixed(2)),
      drawCalls: renderInfo?.render.calls ?? 0,
      triangleCount: renderInfo?.render.triangles ?? 0,
      rendererGeometryCount: renderInfo?.memory.geometries ?? 0,
      rendererTextureCount: renderInfo?.memory.textures ?? 0,
      geometryBytesApprox,
      textureBytesApprox,
      sceneBuildDurationMs: Number(this.sceneBuildDurationMs.toFixed(2)),
      lastStateUpdateMs: Number(this.lastStateUpdateDurationMs.toFixed(2)),
      interactiveMeshesCount: this.interactiveMeshes.length,
      roomsCount: this.rooms.length,
      agentsCount: this.currentAgents.length,
      visibleDepartmentLabelsCount: this.visibleDepartmentLabelsCount,
      visibleAgentLabelsCount: this.visibleAgentLabelsCount,
      suppressedOverlapLabelsCount: this.suppressedOverlapLabelsCount,
      sharedGeometriesCount: this.furniturePool.getGeometriesCount(),
      sharedMaterialsCount: this.furniturePool.getMaterialsCount(),
    };
  }

  private setupLighting(): void {
    const ambient = new THREE.AmbientLight(0xe5ddcc, 1.25);
    this.lightsGroup.add(ambient);

    const dirLight = new THREE.DirectionalLight(0xfff2dc, 2.0);
    dirLight.position.set(18, 32, 16);
    dirLight.castShadow = this.qualityProfile !== 'low';
    const shadowSize = this.qualityProfile === 'high' ? 2048 : 1024;
    dirLight.shadow.mapSize.width = shadowSize;
    dirLight.shadow.mapSize.height = shadowSize;
    dirLight.shadow.bias = -0.0004; // Architectural soft contact shadow bias
    dirLight.shadow.camera.near = 0.5;
    dirLight.shadow.camera.far = 90;
    const d = 18;
    dirLight.shadow.camera.left = -d;
    dirLight.shadow.camera.right = d;
    dirLight.shadow.camera.top = d;
    dirLight.shadow.camera.bottom = -d;
    this.mainDirLight = dirLight;
    this.lightsGroup.add(dirLight);

    const hemiLight = new THREE.HemisphereLight(0xfff7e8, 0x5b554c, 0.9);
    this.lightsGroup.add(hemiLight);

    const fillLight = new THREE.DirectionalLight(0xdce9f2, 0.55);
    fillLight.position.set(-20, 15, -15);
    this.lightsGroup.add(fillLight);

    this.roomSpotlight = new THREE.SpotLight(0xffe6bd, 1.6, 32, Math.PI / 4, 0.4, 1);
    this.roomSpotlight.position.set(-5, 12, -3.1);
    this.roomSpotlight.castShadow = this.qualityProfile === 'high';
    this.lightsGroup.add(this.roomSpotlight);
  }

  public buildBiophilicOfficePlant(x: number, z: number): THREE.Group {
    const plantGroup = new THREE.Group();
    plantGroup.position.set(x, 0.04, z);

    // Matte ceramic cylindrical planter
    const pot = new THREE.Mesh(this.furniturePool.planterPotGeo, this.furniturePool.plantPotMat);
    pot.position.y = 0.18;
    pot.castShadow = true;
    pot.receiveShadow = true;
    plantGroup.add(pot);

    // Architectural botanical foliage
    const foliage = new THREE.Mesh(this.furniturePool.plantFoliageGeo, this.furniturePool.plantLeafMat);
    foliage.position.y = 0.44;
    foliage.scale.set(1.15, 1.25, 1.15);
    foliage.castShadow = true;
    plantGroup.add(foliage);

    return plantGroup;
  }

  public getFurniturePool(): SharedFurniturePool {
    return this.furniturePool;
  }

  private buildWorld(): void {
    this.rebuildGround();
    this.buildReception();

    // 1. Central Coordination Atrium Hub (Radius 3.4, connected to all department corridors)
    const atriumGeo = new THREE.CylinderGeometry(3.4, 3.55, 0.025, 36);
    const atriumMat = new THREE.MeshStandardMaterial({
      color: 0xb7b0a3,
      roughness: 0.72,
      metalness: 0.03,
    });
    const atrium = new THREE.Mesh(atriumGeo, atriumMat);
    atrium.position.y = 0.012;
    atrium.receiveShadow = true;
    this.scene.add(atrium);
    this.buildArchitecturalLounge();

    // Atrium Perimeter Ring Curb
    const outerRingGeo = new THREE.RingGeometry(3.25, 3.45, 36);
    outerRingGeo.rotateX(-Math.PI / 2);
    const outerRingMat = new THREE.MeshBasicMaterial({
      color: 0x817b70,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.28,
    });
    const outerRing = new THREE.Mesh(outerRingGeo, outerRingMat);
    outerRing.position.y = 0.026;
    this.scene.add(outerRing);

    // Biophilic Office Plants around Central Atrium Perimeter
    const plantCorners: [number, number][] = [
      [-3.4, -3.4],
      [3.4, -3.4],
      [3.4, 3.4],
      [-3.4, 3.4],
    ];
    for (const [px, pz] of plantCorners) {
      this.groundGroup.add(this.buildBiophilicOfficePlant(px, pz));
    }

    // 2. Connected Architectural Corridors linking the Central Atrium to each Department Doorway
    this.buildWalkways();

    // 3. Department Pavilions with complete office interior (desks, chairs, monitors, meeting zone, open doorways)
    this.rooms.forEach((room) => {
      this.buildRoom(room);
    });

    // 4. Selection Ring (for active agent)
    const ringGeo = new THREE.RingGeometry(0.55, 0.75, 32);
    ringGeo.rotateX(-Math.PI / 2);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.9,
    });
    this.selectionRing = new THREE.Mesh(ringGeo, ringMat);
    this.selectionRing.visible = false;
    this.selectionRing.position.y = 0.025;
    this.scene.add(this.selectionRing);
  }

  private buildArchitecturalLounge(): void {
    const lounge = new THREE.Group();
    lounge.name = 'architectural-central-lounge';
    lounge.userData = { role: 'architectural-common-space', zone: 'central-lounge', sourceNeutral: true };

    const upholstery = new THREE.MeshStandardMaterial({ color: 0x77766f, roughness: 0.88 });
    const timber = new THREE.MeshStandardMaterial({ color: 0x76533b, roughness: 0.72 });
    for (const side of [-1, 1]) {
      const sofa = new THREE.Group();
      sofa.name = `central-lounge-sofa-${side < 0 ? 'west' : 'east'}`;
      sofa.position.set(side * 1.12, 0, 0);
      sofa.rotation.y = side < 0 ? Math.PI / 2 : -Math.PI / 2;

      const base = new THREE.Mesh(new THREE.BoxGeometry(1.65, 0.22, 0.72), timber);
      base.position.y = 0.28;
      base.castShadow = true;
      sofa.add(base);
      const seat = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.19, 0.68), upholstery);
      seat.position.y = 0.49;
      seat.castShadow = true;
      sofa.add(seat);
      const back = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.62, 0.16), upholstery);
      back.position.set(0, 0.79, -0.27);
      back.castShadow = true;
      sofa.add(back);
      for (const end of [-1, 1]) {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.44, 0.74), timber);
        arm.position.set(end * 0.75, 0.5, 0);
        sofa.add(arm);
      }
      lounge.add(sofa);
    }

    const coffeeTop = new THREE.Mesh(
      new THREE.CylinderGeometry(0.57, 0.57, 0.08, 24),
      new THREE.MeshStandardMaterial({ color: 0xd0c7b8, roughness: 0.58 }),
    );
    coffeeTop.name = 'central-lounge-coffee-table';
    coffeeTop.position.set(0, 0.45, 0);
    coffeeTop.castShadow = true;
    lounge.add(coffeeTop);
    const coffeeBase = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.22, 0.42, 16), timber);
    coffeeBase.position.set(0, 0.22, 0);
    lounge.add(coffeeBase);
    this.scene.add(lounge);
  }

  private buildReception(): void {
    const reception = new THREE.Group();
    reception.name = 'architectural-reception';
    // Reserve a recognizable lobby position just inside the south entrance. The
    // former hard-coded atrium position put the counter directly in the common
    // circulation area and made it read as a decorative island.
    const halfDepth = Math.max(11, ...this.rooms.map((room) => Math.abs(room.z) + room.depth / 2 + 2.5));
    const entranceInteriorZ = halfDepth - 1.5 - 2.0;
    reception.userData = { role: 'architectural-common-space', zone: 'reception', sourceNeutral: true };
    reception.position.set(-2.1, 0, entranceInteriorZ);

    // A compact architectural backdrop gives the lobby a recognizable arrival
    // point even when LIVE has no declared units or active agents.
    const backdrop = new THREE.Mesh(
      new THREE.BoxGeometry(3.2, 1.9, 0.12),
      new THREE.MeshStandardMaterial({ color: 0xd8d2c6, roughness: 0.84 }),
    );
    backdrop.name = 'reception-welcome-backdrop';
    backdrop.position.set(0, 1.05, -0.72);
    backdrop.receiveShadow = true;
    reception.add(backdrop);
    const backdropTrim = new THREE.Mesh(
      new THREE.BoxGeometry(3.24, 0.055, 0.14),
      new THREE.MeshStandardMaterial({ color: 0x88735e, roughness: 0.62 }),
    );
    backdropTrim.position.set(0, 2.03, -0.72);
    reception.add(backdropTrim);

    const base = new THREE.Mesh(new THREE.BoxGeometry(2.25, 0.72, 0.68), new THREE.MeshStandardMaterial({ color: 0x76533b, roughness: 0.62 }));
    base.position.set(0, 0.38, 0);
    base.castShadow = true;
    reception.add(base);
    const top = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.09, 0.78), new THREE.MeshStandardMaterial({ color: 0xd0c7b8, roughness: 0.5 }));
    top.position.set(0, 0.78, 0);
    top.castShadow = true;
    reception.add(top);
    const signCanvas = document.createElement('canvas');
    signCanvas.width = 512;
    signCanvas.height = 160;
    const signContext = signCanvas.getContext('2d');
    if (signContext) {
      signContext.fillStyle = '#34434a';
      signContext.fillRect(0, 0, signCanvas.width, signCanvas.height);
      signContext.fillStyle = '#f3eee3';
      signContext.font = '600 34px sans-serif';
      signContext.fillText('AAO  ·  RECEPCIÓN', 24, 66);
      signContext.font = '22px sans-serif';
      signContext.fillStyle = '#d5d0c6';
      signContext.fillText('OFICINA VIVA', 24, 112);
    }
    const sign = new THREE.Mesh(
      new THREE.PlaneGeometry(1.42, 0.48),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(signCanvas), toneMapped: false }),
    );
    sign.position.set(0, 1.15, 0.43);
    reception.add(sign);

    // Quiet visitor seating is part of the fixed building, not a fabricated
    // operational team or agent. Keep it outside the clear entrance approach.
    const lounge = new THREE.Group();
    lounge.name = 'reception-visitor-lounge';
    lounge.userData = { role: 'architectural-common-space', zone: 'visitor-lounge', sourceNeutral: true };
    const upholstery = new THREE.MeshStandardMaterial({ color: 0x77766f, roughness: 0.88 });
    const darkWood = new THREE.MeshStandardMaterial({ color: 0x76533b, roughness: 0.72 });
    const buildVisitorChair = (x: number) => {
      const chair = new THREE.Group();
      chair.position.set(x, 0, 0.15);
      const seat = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.16, 0.72), upholstery);
      seat.position.y = 0.47;
      seat.castShadow = true;
      chair.add(seat);
      const back = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.72, 0.14), upholstery);
      back.position.set(0, 0.86, -0.29);
      back.castShadow = true;
      chair.add(back);
      for (const side of [-1, 1]) {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.22, 0.66), darkWood);
        arm.position.set(side * 0.43, 0.62, 0.02);
        chair.add(arm);
      }
      lounge.add(chair);
    };
    buildVisitorChair(4.35);
    buildVisitorChair(6.05);
    const sideTable = new THREE.Mesh(
      new THREE.CylinderGeometry(0.38, 0.38, 0.06, 20),
      new THREE.MeshStandardMaterial({ color: 0xd0c7b8, roughness: 0.56 }),
    );
    sideTable.position.set(5.2, 0.5, 0.15);
    sideTable.castShadow = true;
    lounge.add(sideTable);
    const tableBase = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.12, 0.48, 12), darkWood);
    tableBase.position.set(5.2, 0.24, 0.15);
    lounge.add(tableBase);
    reception.add(lounge);
    this.scene.add(reception);
  }

  private rebuildGround(): void {
    for (const child of [...this.groundGroup.children]) {
      this.groundGroup.remove(child);
      this.disposeHierarchy(child);
    }
    const halfWidth = Math.max(14, ...this.rooms.map((room) => Math.abs(room.x) + room.width / 2 + 2.5));
    const halfDepth = Math.max(11, ...this.rooms.map((room) => Math.abs(room.z) + room.depth / 2 + 2.5));
    const width = halfWidth * 2;
    const depth = halfDepth * 2;

    // Subtle, locally generated stone aggregate gives the shared floor a physical
    // finish without a network asset or a high-resolution texture dependency.
    const stoneCanvas = document.createElement('canvas');
    stoneCanvas.width = 256;
    stoneCanvas.height = 256;
    const stoneContext = stoneCanvas.getContext('2d');
    if (stoneContext) {
      stoneContext.fillStyle = '#a9a69d';
      stoneContext.fillRect(0, 0, 256, 256);
      let seed = 0x41a0;
      const next = () => {
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        return seed / 0x1_0000_0000;
      };
      for (let index = 0; index < 1400; index += 1) {
        const shade = next() > 0.5 ? '#d0ccc2' : '#8f8c84';
        const size = 0.5 + next() * 1.4;
        stoneContext.globalAlpha = 0.05 + next() * 0.08;
        stoneContext.fillStyle = shade;
        stoneContext.fillRect(next() * 256, next() * 256, size, size);
      }
      stoneContext.globalAlpha = 0.12;
      stoneContext.fillStyle = '#77746d';
      stoneContext.fillRect(0, 0, 256, 1);
      stoneContext.fillRect(0, 0, 1, 256);
      stoneContext.globalAlpha = 1;
    }
    const stoneTexture = new THREE.CanvasTexture(stoneCanvas);
    stoneTexture.colorSpace = THREE.SRGBColorSpace;
    stoneTexture.wrapS = THREE.RepeatWrapping;
    stoneTexture.wrapT = THREE.RepeatWrapping;
    // Apply a single continuous stone finish across the slab. Repeating a small
    // texture on a 5 m grid made its tile boundaries read as room-sized floor pads.
    stoneTexture.repeat.set(1, 1);

    // Continuous Corporate Campus Floor Slab
    const campusSlab = new THREE.Mesh(
      new THREE.BoxGeometry(width - 1.5, 0.12, depth - 1.5),
      // Keep the continuous slab visibly distinct from the lighter circulation paths.
      new THREE.MeshStandardMaterial({ map: stoneTexture, color: 0xffffff, roughness: 0.9, metalness: 0.01 })
    );
    campusSlab.position.y = -0.04;
    campusSlab.receiveShadow = true;
    this.groundGroup.add(campusSlab);

    // Polished Central Circulation Spine (terrazzo plaza connecting campus corridors)
    const centralPlaza = new THREE.Mesh(
      new THREE.BoxGeometry(Math.min(width - 3, 7.2), 0.02, Math.min(depth - 3, 7.2)),
      // The atrium is distinguished by its geometry and furnishing, not by a
      // high-contrast square of different flooring across the continuous slab.
      new THREE.MeshStandardMaterial({ color: 0xaaa79e, roughness: 0.82, metalness: 0.01 })
    );
    centralPlaza.position.y = 0.022;
    centralPlaza.receiveShadow = true;
    this.groundGroup.add(centralPlaza);

    const ground = new THREE.Mesh(
      new THREE.BoxGeometry(width + 6, 0.4, depth + 6),
      new THREE.MeshStandardMaterial({ color: 0x8c877d, roughness: 0.92, metalness: 0.01 })
    );
    ground.position.y = -0.26;
    ground.receiveShadow = true;
    this.groundGroup.add(ground);

    // Roofless cutaway curtain wall: the building reads as one continuous structure while
    // remaining open enough for the isometric camera and ordinary GPU budgets.
    const facadeWidth = width - 1.5;
    const facadeDepth = depth - 1.5;
    const facadeY = 1.42;
    const glassMaterial = new THREE.MeshStandardMaterial({
      color: 0xc3d0d0,
      transparent: true,
      opacity: 0.12,
      roughness: 0.32,
      metalness: 0.04,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const frameMaterial = new THREE.MeshStandardMaterial({ color: 0x777b78, roughness: 0.62, metalness: 0.12 });
    const facadeGroup = new THREE.Group();
    facadeGroup.name = 'architectural-curtain-facade';
    this.groundGroup.add(facadeGroup);
    const addFacadeRun = (length: number, x: number, z: number, rotationY: number, mullionAxis: 'x' | 'z') => {
      const glass = new THREE.Mesh(new THREE.BoxGeometry(length, 2.65, 0.055), glassMaterial);
      glass.position.set(x, facadeY, z);
      glass.rotation.y = rotationY;
      facadeGroup.add(glass);
      const base = new THREE.Mesh(new THREE.BoxGeometry(length, 0.1, 0.12), frameMaterial);
      base.position.set(x, 0.1, z);
      base.rotation.y = rotationY;
      facadeGroup.add(base);
      const head = new THREE.Mesh(new THREE.BoxGeometry(length, 0.1, 0.12), frameMaterial);
      head.position.set(x, 2.75, z);
      head.rotation.y = rotationY;
      facadeGroup.add(head);
      for (let offset = -length / 2 + 2; offset < length / 2; offset += 3.6) {
        const mullion = new THREE.Mesh(new THREE.BoxGeometry(0.065, 2.7, 0.12), frameMaterial);
        if (mullionAxis === 'x') mullion.position.set(x + offset, facadeY, z);
        else mullion.position.set(x, facadeY, z + offset);
        facadeGroup.add(mullion);
      }
    };
    const halfFacadeWidth = facadeWidth / 2;
    const halfFacadeDepth = facadeDepth / 2;
    addFacadeRun(facadeWidth, 0, -halfFacadeDepth, 0, 'x');
    // Keep a real entrance opening in the south curtain wall instead of sealing
    // the cutaway building inside an uninterrupted ring of glass.
    const entranceWidth = Math.min(3.4, facadeWidth * 0.22);
    facadeGroup.userData = { entranceWidth, facadeWidth, facadeDepth };
    const facadeWingWidth = (facadeWidth - entranceWidth) / 2;
    const facadeWingOffset = (entranceWidth + facadeWingWidth) / 2;
    addFacadeRun(facadeWingWidth, -facadeWingOffset, halfFacadeDepth, 0, 'x');
    addFacadeRun(facadeWingWidth, facadeWingOffset, halfFacadeDepth, 0, 'x');
    addFacadeRun(facadeDepth, -halfFacadeWidth, 0, Math.PI / 2, 'z');
    addFacadeRun(facadeDepth, halfFacadeWidth, 0, Math.PI / 2, 'z');

    // A quiet, accessible canopy marks the entrance without obstructing the
    // isometric cutaway. The opening remains clear at ground level.
    const entranceFrame = new THREE.MeshStandardMaterial({ color: 0x686d69, roughness: 0.58, metalness: 0.16 });
    const entranceGroup = new THREE.Group();
    entranceGroup.name = 'architectural-main-entrance';
    entranceGroup.userData = { clearWidth: entranceWidth, accessible: true };
    this.groundGroup.add(entranceGroup);
    for (const side of [-1, 1]) {
      const jamb = new THREE.Mesh(new THREE.BoxGeometry(0.11, 2.55, 0.14), entranceFrame);
      jamb.position.set(side * entranceWidth / 2, 1.35, halfFacadeDepth);
      entranceGroup.add(jamb);
    }
    const canopy = new THREE.Mesh(
      new THREE.BoxGeometry(entranceWidth + 1.1, 0.12, 1.25),
      new THREE.MeshStandardMaterial({ color: 0x8b8981, roughness: 0.74, metalness: 0.08 }),
    );
    canopy.position.set(0, 2.82, halfFacadeDepth + 0.52);
    canopy.castShadow = true;
    entranceGroup.add(canopy);
    const threshold = new THREE.Mesh(
      new THREE.BoxGeometry(entranceWidth, 0.025, 1.1),
      new THREE.MeshStandardMaterial({ color: 0xc0b9ad, roughness: 0.78 }),
    );
    threshold.position.set(0, 0.035, halfFacadeDepth + 0.48);
    threshold.receiveShadow = true;
    entranceGroup.add(threshold);


  }

  private buildWalkways(): void {
    const walkwayMat = new THREE.MeshStandardMaterial({
      color: 0xaaa79e,
      roughness: 0.88,
      metalness: 0.02,
    });
    const holdingWalkwayMat = new THREE.MeshStandardMaterial({
      color: 0xaaa79e,
      roughness: 0.88,
      metalness: 0.02,
    });

    const navGraph = buildCampusNavGraph(this.rooms);

    for (const seg of navGraph.corridors) {
      for (let index = 1; index < seg.points.length; index += 1) {
        const start = seg.points[index - 1];
        const end = seg.points[index];
        const dx = end.x - start.x;
        const dz = end.z - start.z;
        const distance = Math.max(0.6, Math.hypot(dx, dz));
        const midX = (start.x + end.x) * 0.5;
        const midZ = (start.z + end.z) * 0.5;
        const angle = Math.atan2(dx, dz);

        const pathGeo = new THREE.BoxGeometry(seg.width, 0.02, distance + 0.35);
        const path = new THREE.Mesh(
          pathGeo,
          seg.isUnassignedWing ? holdingWalkwayMat : walkwayMat
        );
        path.position.set(midX, 0.03, midZ);
        path.rotation.y = angle;
        path.receiveShadow = true;
        this.walkwaysGroup.add(path);
      }
    }
  }

  private buildRoom(room: OfficeRoomConfig): void {
    const roomGroup = new THREE.Group();
    roomGroup.name = `room-${room.id}`;
    roomGroup.userData = { room };
    roomGroup.position.set(room.x, -0.35, room.z);
    const isUnassignedHolding =
      room.kind === 'unassigned-holding' || room.id === 'unit-unassigned';

    // Keep a room-sized raycast target for selection without rendering a room-sized
    // colored sheet. Visible zoning comes from partitions, furniture and signage;
    // drawing one plane per unit made the continuous campus read as floating pads.
    const floorMaterial = new THREE.MeshBasicMaterial({
      transparent: true,
      opacity: 0,
      colorWrite: false,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(Math.max(0.5, room.width - 0.24), Math.max(0.5, room.depth - 0.24)),
      floorMaterial,
    );
    floor.rotation.x = -Math.PI / 2;
    // Align the hit target exactly to the top of the shared campus floor slab.
    floor.position.y = 0.37;
    floor.userData = {
      type: 'room',
      id: room.id,
      name: room.name,
      code: room.code,
      kind: room.kind ?? 'canonical-department',
    };
    roomGroup.add(floor);

    this.interactiveMeshes.push(floor);

    // Architectural Perimeter Walls & Open Doorway Entrance
    this.buildRoomArchitecture(roomGroup, room, isUnassignedHolding);

    // Office Workstations / Holding Stations + Meeting Zone
    this.buildOfficeWorkstationsAndMeetingZone(roomGroup, room, isUnassignedHolding);

    // Department Specific Accent Equipment
    if (!isUnassignedHolding && (this.options.demoFurniture ?? true)) {
      this.buildDepartmentAccentEquipment(roomGroup, room);
    }

    // Biophilic Plant in rear corner of canonical departments
    if (!isUnassignedHolding) {
      const plantX = room.width / 2 - 0.42;
      const plantZ = (room.z < 0 ? -room.depth / 2 : room.depth / 2) + (room.z < 0 ? 0.42 : -0.42);
      roomGroup.add(this.buildBiophilicOfficePlant(plantX, plantZ));
    }

    // Pin the label above the back partition instead of over the center of the
    // workstation island, where a department header can obscure a person.
    const labelSprite = this.createDepartmentLabelSprite(
      room.code,
      room.name,
      isUnassignedHolding
    );
    const labelBackZ = room.z < 0 ? -room.depth / 2 + 0.42 : room.depth / 2 - 0.42;
    labelSprite.position.set(0, 1.82, labelBackZ);
    roomGroup.add(labelSprite);
    this.roomLabels.set(room.id, labelSprite);

    this.roomsGroup.add(roomGroup);
  }

  /**
   * Builds workstation islands inside canonical departments, or neutral holding stations
   * inside the `unit-unassigned` holding bay so unassigned agents are visually differentiated
   * from active corporate departments.
   */
  private buildOfficeWorkstationsAndMeetingZone(
    group: THREE.Group,
    room: OfficeRoomConfig,
    isUnassignedHolding: boolean
  ): void {
    const layout = buildDepartmentInteriorLayout(room);
    const screenMat = new THREE.MeshBasicMaterial({
      color: 0x747e82,
    });
    const chairAccentMat = new THREE.MeshStandardMaterial({
      color: 0x8f877a,
      roughness: 0.55,
      metalness: 0.2,
    });

    for (const slot of layout.workstations) {
      const deskGroup = new THREE.Group();
      deskGroup.position.set(slot.deskLocalX, 0.36, slot.deskLocalZ);

      const top = new THREE.Mesh(
        this.furniturePool.deskTopGeo,
        isUnassignedHolding ? this.furniturePool.holdingDeskMat : this.furniturePool.deskWoodMat
      );
      top.position.y = 0.44;
      top.castShadow = true;
      top.receiveShadow = true;
      deskGroup.add(top);

      const leftLeg = new THREE.Mesh(this.furniturePool.deskLegGeo, this.furniturePool.metalLegMat);
      leftLeg.position.set(-0.42, 0.21, 0);
      deskGroup.add(leftLeg);

      const rightLeg = new THREE.Mesh(this.furniturePool.deskLegGeo, this.furniturePool.metalLegMat);
      rightLeg.position.set(0.42, 0.21, 0);
      deskGroup.add(rightLeg);

      if (!isUnassignedHolding) {
        // Modern Ergonomic Workstation: Ultrawide Curved Monitor with procedural IDE code display + cable grommet
        const mon = new THREE.Mesh(this.furniturePool.ultrawideMonitorGeo, this.furniturePool.monitorIdeMat);
        mon.position.set(0, 0.65, -0.09);
        deskGroup.add(mon);

        const stand = new THREE.Mesh(this.furniturePool.monitorStandGeo, this.furniturePool.metalLegMat);
        stand.position.set(0, 0.51, -0.12);
        deskGroup.add(stand);

        const grommet = new THREE.Mesh(this.furniturePool.deskGrommetGeo, this.furniturePool.deskTrimMat);
        grommet.position.set(0.32, 0.45, -0.15);
        deskGroup.add(grommet);

        const keyboard = new THREE.Mesh(this.furniturePool.keyboardGeo, this.furniturePool.keyboardMat);
        keyboard.position.set(-0.04, 0.48, 0.1);
        deskGroup.add(keyboard);

        const mouse = new THREE.Mesh(this.furniturePool.mouseGeo, this.furniturePool.keyboardMat);
        mouse.position.set(0.2, 0.48, 0.1);
        deskGroup.add(mouse);
      } else {
        // Unassigned Holding Station: Single standby terminal in sleep mode
        const standbyMon = new THREE.Mesh(this.furniturePool.monitorPanelGeo, screenMat);
        standbyMon.position.set(0, 0.62, -0.1);
        deskGroup.add(standbyMon);

        const standbyStand = new THREE.Mesh(this.furniturePool.monitorStandGeo, this.furniturePool.metalLegMat);
        standbyStand.position.set(0, 0.5, -0.12);
        deskGroup.add(standbyStand);
      }

      group.add(deskGroup);

      // Ergonomic Chair at (slot.chairLocalX, slot.chairLocalZ)
      const chairGroup = this.buildErgonomicChair(chairAccentMat);
      chairGroup.position.set(slot.chairLocalX, 0.36, slot.chairLocalZ);
      chairGroup.rotation.y = slot.facingAngle;
      group.add(chairGroup);
    }

    // Collaborative Meeting Table in canonical departments
    if (!isUnassignedHolding) {
      const meetingGroup = new THREE.Group();
      meetingGroup.position.set(layout.meetingTableLocal.x, 0.36, layout.meetingTableLocal.z);

      const tableTop = new THREE.Mesh(
        this.furniturePool.meetingTableTopGeo,
        this.furniturePool.meetingTableMat
      );
      tableTop.position.y = 0.42;
      tableTop.castShadow = true;
      meetingGroup.add(tableTop);

      const tablePed = new THREE.Mesh(
        this.furniturePool.meetingTablePedGeo,
        this.furniturePool.metalLegMat
      );
      tablePed.position.y = 0.2;
      meetingGroup.add(tablePed);

      group.add(meetingGroup);
    }
  }

  private buildErgonomicChair(backrestAccentMat: THREE.Material): THREE.Group {
    const chair = new THREE.Group();

    const base = new THREE.Mesh(this.furniturePool.chairBaseGeo, this.furniturePool.metalLegMat);
    base.position.y = 0.03;
    chair.add(base);

    const stem = new THREE.Mesh(this.furniturePool.chairStemGeo, this.furniturePool.metalLegMat);
    stem.position.y = 0.14;
    chair.add(stem);

    const seat = new THREE.Mesh(this.furniturePool.chairSeatGeo, this.furniturePool.chairCushionMat);
    seat.position.y = 0.26;
    seat.castShadow = true;
    chair.add(seat);

    const back = new THREE.Mesh(this.furniturePool.chairBackGeo, backrestAccentMat);
    back.position.set(0, 0.46, -0.15);
    back.castShadow = true;
    chair.add(back);

    const leftArm = new THREE.Mesh(this.furniturePool.chairArmGeo, this.furniturePool.metalLegMat);
    leftArm.position.set(-0.17, 0.34, -0.02);
    chair.add(leftArm);

    const rightArm = new THREE.Mesh(this.furniturePool.chairArmGeo, this.furniturePool.metalLegMat);
    rightArm.position.set(0.17, 0.34, -0.02);
    chair.add(rightArm);

    return chair;
  }

  /**
   * Builds perimeter walls, acoustic glass partitions, and an open architectural doorway
   * on the entrance side facing the Central Coordination Atrium.
   */
  private buildRoomArchitecture(
    group: THREE.Group,
    room: OfficeRoomConfig,
    isUnassignedHolding: boolean
  ): void {
    const wallMat = new THREE.MeshStandardMaterial({ color: isUnassignedHolding ? 0x85837b : 0x77766f, roughness: 0.76, metalness: 0.01 });
    const glassMat = new THREE.MeshStandardMaterial({
      color: isUnassignedHolding ? 0xb4b1aa : 0xc5d0d2,
      transparent: true,
      opacity: isUnassignedHolding ? 0.13 : 0.12,
      roughness: 0.32,
      metalness: 0.12,
      depthWrite: false,
    });

    const isTopRow = room.z < 0;
    const backZ = isTopRow ? -room.depth / 2 + 0.12 : room.depth / 2 - 0.12;
    const frontZ = isTopRow ? room.depth / 2 - 0.1 : -room.depth / 2 + 0.1;

    // 1. Low acoustic partition: retain room identity while keeping long views
    // across the single floor plate. Full-height-looking bay walls were making
    // departments read as separate kiosks rather than open-plan work zones.
    const backWallGeo = new THREE.BoxGeometry(room.width - 0.5, 0.58, 0.1);
    const backWall = new THREE.Mesh(backWallGeo, wallMat);
    backWall.name = 'department-back-partition';
    backWall.position.set(0, 0.66, backZ);
    backWall.castShadow = true;
    backWall.receiveShadow = true;
    group.add(backWall);

    // Wall Presentation Board / Status Header on Back Wall
    const boardGeo = new THREE.BoxGeometry(1.2, 0.2, 0.025);
    const boardMat = new THREE.MeshBasicMaterial({
      color: 0x9a9285,
    });
    const board = new THREE.Mesh(boardGeo, boardMat);
    board.name = 'department-wall-sign';
    board.position.set(0, 0.79, backZ + (isTopRow ? 0.065 : -0.065));
    group.add(board);

    // 2. Side Translucent Glass Acoustic Partitions
    const sideGlassGeo = new THREE.BoxGeometry(0.055, 0.58, room.depth * 0.68);
    const sideGlassLeft = new THREE.Mesh(sideGlassGeo, glassMat);
    sideGlassLeft.name = 'department-side-glass-left';
    sideGlassLeft.position.set(-room.width / 2 + 0.12, 0.66, 0);
    group.add(sideGlassLeft);

    const sideGlassRight = new THREE.Mesh(sideGlassGeo, glassMat);
    sideGlassRight.name = 'department-side-glass-right';
    sideGlassRight.position.set(room.width / 2 - 0.12, 0.66, 0);
    group.add(sideGlassRight);

    // 3. Front Entrance Wall with Open Central Doorway (1.4u gap so agents walk through cleanly)
    const doorwayWidth = 1.4;
    const frontPanelWidth = Math.max(0.5, (room.width - doorwayWidth - 0.4) / 2);
    const frontGlassGeo = new THREE.BoxGeometry(frontPanelWidth, 0.58, 0.055);

    const frontLeft = new THREE.Mesh(frontGlassGeo, glassMat);
    frontLeft.name = 'department-front-glass-left';
    frontLeft.position.set(-doorwayWidth / 2 - frontPanelWidth / 2, 0.66, frontZ);
    group.add(frontLeft);

    const frontRight = new THREE.Mesh(frontGlassGeo, glassMat);
    frontRight.name = 'department-front-glass-right';
    frontRight.position.set(doorwayWidth / 2 + frontPanelWidth / 2, 0.66, frontZ);
    group.add(frontRight);

    // 4. Acoustic Manifestation Band for Audit Enclave (eye level 0.85m)
    const isAuditEnclave = room.kind === 'audit-enclave' || room.id === 'unit-audit';
    if (isAuditEnclave) {
      const manifestSideGeo = new THREE.BoxGeometry(0.088, 0.14, room.depth * 0.68 + 0.02);
      const manifestFrontGeo = new THREE.BoxGeometry(frontPanelWidth + 0.02, 0.14, 0.088);
      const manifestMat = new THREE.MeshBasicMaterial({
        color: 0x9dbaa8,
        transparent: true,
        opacity: 0.22,
      });

      const mLeft = new THREE.Mesh(manifestSideGeo, manifestMat);
      mLeft.position.set(-room.width / 2 + 0.12, 0.85, 0);
      group.add(mLeft);

      const mRight = new THREE.Mesh(manifestSideGeo, manifestMat);
      mRight.position.set(room.width / 2 - 0.12, 0.85, 0);
      group.add(mRight);

      const mFrontL = new THREE.Mesh(manifestFrontGeo, manifestMat);
      mFrontL.position.set(-doorwayWidth / 2 - frontPanelWidth / 2, 0.85, frontZ);
      group.add(mFrontL);

      const mFrontR = new THREE.Mesh(manifestFrontGeo, manifestMat);
      mFrontR.position.set(doorwayWidth / 2 + frontPanelWidth / 2, 0.85, frontZ);
      group.add(mFrontR);
    }
  }

  private buildDepartmentAccentEquipment(group: THREE.Group, room: OfficeRoomConfig): void {
    const towerMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.3, metalness: 0.6 });
    if (room.id === 'unit-ops' || room.id === 'unit-eng' || room.id === 'unit-audit') {
      const towerGeo = new THREE.BoxGeometry(0.32, 1.05, 0.32);
      const tower = new THREE.Mesh(towerGeo, towerMat);
      tower.position.set(-room.width / 2 + 0.42, 0.88, -room.depth / 2 + 0.45);
      group.add(tower);
    }
  }

  private createDepartmentLabelSprite(
    code: string,
    name: string,
    isUnassignedHolding = false
  ): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 240;
    canvas.height = 68;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = 'rgba(54, 61, 62, 0.9)';
      ctx.strokeStyle = '#a59d8f';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(4, 4, 232, 60, 9);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = '600 24px sans-serif';
      ctx.fillStyle = '#e4ddd0';
      ctx.fillText(isUnassignedHolding ? 'SIN ADSCRIPCIÓN' : code, 120, 29);

      ctx.font = '15px sans-serif';
      ctx.fillStyle = '#c5c0b6';
      ctx.fillText(name.slice(0, 26), 120, 51);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthTest: false,
    });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(1.9, 0.54, 1);
    return sprite;
  }

  public updateAgents(agents: AgentIdentity[], nowMs = Date.now()): void {
    const t0 = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.currentAgents = [...agents];
    this.lastStateEvaluationMs = nowMs;

    // 1. Remove old agent meshes from interactive raycast array to avoid stale objects and cumulative growth
    this.interactiveMeshes = this.interactiveMeshes.filter(
      (mesh) => mesh.userData?.type !== 'agent'
    );

    // 2. Clear old agents from 3D hierarchy and GPU memory
    this.agentMeshes.forEach((group) => {
      this.agentsGroup.remove(group);
      this.disposeHierarchy(group);
    });
    this.agentMeshes.clear();

    // 3. Plan deterministic workstation assignments, activities, and obstacle-free routes
    const placements = planOfficeLifePlacements(agents, this.rooms, {
      isDemo: Boolean(this.options.demoFurniture),
      nowMs,
      activeCoordinationAgentIds: this.options.activeCoordinationAgentIds,
      ambientWalkEnabled: !this.options.reducedMotion,
    });

    // Clean up removed agents from runtime state map
    const activeIds = new Set(agents.map((a) => a.id));
    for (const existingId of this.agentRuntimeStates.keys()) {
      if (!activeIds.has(existingId)) {
        this.agentRuntimeStates.delete(existingId);
      }
    }

    // 4. Instantiate articulated 3D avatars at their planned or smoothly preserved positions
    agents.forEach((agent) => {
      const placement = placements.get(agent.id);
      if (!placement) return;

      const previousState = this.agentRuntimeStates.get(agent.id);
      const startX = previousState ? previousState.currentX : placement.targetWorldX;
      const startZ = previousState ? previousState.currentZ : placement.targetWorldZ;
      const startAngle = previousState ? previousState.currentAngle : placement.targetFacingAngle;

      this.agentRuntimeStates.set(agent.id, {
        currentX: startX,
        currentZ: startZ,
        currentAngle: startAngle,
        placement,
      });

      const agentGroup = this.buildAgentAvatar(agent, placement.activity);
      agentGroup.position.set(startX, 0.37, startZ);
      const parts = agentGroup.userData.parts as AvatarSemanticParts;
      if (parts?.characterRig) {
        parts.characterRig.rotation.y = startAngle;
      }

      agentGroup.userData = {
        ...agentGroup.userData,
        type: 'agent',
        id: agent.id,
        unitId: agent.unitId,
        agentType: agent.type,
        activity: placement.activity,
      };

      this.agentsGroup.add(agentGroup);
      this.agentMeshes.set(agent.id, agentGroup);

      // Register all meshes inside the avatar for raycast selection
      agentGroup.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          child.userData = agentGroup.userData;
          this.interactiveMeshes.push(child);
        }
      });
    });

    if (this.activeAgentId) {
      this.selectAgent(this.activeAgentId);
    }

    this.syncAdaptiveLabels();
    const t1 = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.lastStateUpdateDurationMs = Math.max(0, t1 - t0);
  }

  /**
   * Synchronizes department and agent 3D labels with the Adaptive Label LOD & De-overlapping Engine.
   */
  public syncAdaptiveLabels(): void {
    const placementCoords = new Map<string, { x: number; z: number; activity: ProjectedAgentActivity }>();
    this.agentRuntimeStates.forEach((rt, id) => {
      placementCoords.set(id, {
        x: rt.currentX,
        z: rt.currentZ,
        activity: rt.placement.activity,
      });
    });

    const labelResult = computeAdaptiveLabelStates({
      rooms: this.rooms,
      agents: this.currentAgents,
      placements: placementCoords,
      cameraDistance: this.cameraDistance,
      cameraAngleDeg: this.cameraAngle,
      cameraTargetX: this.cameraTarget.x,
      cameraTargetZ: this.cameraTarget.z,
      selectedRoomId: this.activeRoomId,
      selectedAgentId: this.activeAgentId,
    });

    this.visibleDepartmentLabelsCount = labelResult.visibleDepartmentCount;
    this.visibleAgentLabelsCount = labelResult.visibleAgentCount;
    this.suppressedOverlapLabelsCount = labelResult.suppressedOverlapCount;

    this.roomLabels.forEach((sprite, roomId) => {
      const state = labelResult.departments.get(roomId);
      if (!state) return;
      sprite.visible = state.visible;
      sprite.position.y = state.yOffset;
      sprite.scale.set(1.9 * state.scale, 0.54 * state.scale, 1);
    });

    this.agentMeshes.forEach((group, agentId) => {
      const parts = group.userData?.parts as AvatarSemanticParts | undefined;
      if (!parts?.nameLabel) return;
      const state = labelResult.agents.get(agentId);
      if (!state) {
        parts.nameLabel.visible = false;
        return;
      }
      parts.nameLabel.visible = state.visible;
      parts.nameLabel.position.y = state.yOffset;
      parts.nameLabel.scale.set(1.58 * state.scale, 0.5 * state.scale, 1);
    });
  }

  /**
   * Re-evaluates operational evidence and lease expiration at a decoupled interval
   * without recreating meshes, allowing smooth transitions when leases expire or states change.
   */
  public refreshAgentActivities(nowMs = Date.now()): void {
    const t0 = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.lastStateEvaluationMs = nowMs;
    if (this.currentAgents.length === 0) return;

    const placements = planOfficeLifePlacements(this.currentAgents, this.rooms, {
      isDemo: Boolean(this.options.demoFurniture),
      nowMs,
      activeCoordinationAgentIds: this.options.activeCoordinationAgentIds,
      ambientWalkEnabled: !this.options.reducedMotion,
    });

    for (const [agentId, placement] of placements.entries()) {
      const runtime = this.agentRuntimeStates.get(agentId);
      const group = this.agentMeshes.get(agentId);
      if (runtime && group) {
        runtime.placement = placement;
        group.userData.activity = placement.activity;
        const parts = group.userData.parts as AvatarSemanticParts | undefined;
        if (parts?.speechBubble) {
          parts.speechBubble.visible = placement.activity.kind === 'CONVERSING';
        }
      }
    }
    this.syncAdaptiveLabels();
    const t1 = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.lastStateUpdateDurationMs = Math.max(0, t1 - t0);
  }

  public getInteractiveMeshesCount(): number {
    return this.interactiveMeshes.length;
  }

  public getAgentMeshGroup(agentId: string): THREE.Group | undefined {
    return this.agentMeshes.get(agentId);
  }

  public getAgentSemanticParts(agentId: string): AvatarSemanticParts | undefined {
    const group = this.agentMeshes.get(agentId);
    return group?.userData?.parts as AvatarSemanticParts | undefined;
  }

  public getAgentPlacement(agentId: string): PlannedAgentPlacement | undefined {
    return this.agentRuntimeStates.get(agentId)?.placement;
  }

  public isContextLost(): boolean {
    return this.contextLost;
  }

  public getCameraDistance(): number {
    return this.cameraDistance;
  }

  public getDesiredDistance(): number {
    return this.desiredDistance;
  }

  public getDesiredTarget(): THREE.Vector3 {
    return this.desiredTarget.clone();
  }

  public getCurrentLodTier(): OfficeLabelLodTier {
    return deriveLabelLodTier(this.cameraDistance);
  }

  public setFollowAgent(enabled: boolean): void {
    this.followSelectedAgent = enabled;
    if (enabled && this.activeAgentId) {
      const group = this.agentMeshes.get(this.activeAgentId);
      if (group) {
        this.desiredTarget.set(group.position.x, 0, group.position.z);
        this.updateCameraPosition();
      }
    }
  }

  public orbitCamera(deltaAngle: number, deltaElevation = 0): void {
    this.followSelectedAgent = false;
    this.desiredAngle = (this.desiredAngle + deltaAngle) % 360;
    if (this.desiredAngle < 0) this.desiredAngle += 360;
    this.desiredElevation = Math.max(15, Math.min(75, this.desiredElevation + deltaElevation));
    this.cameraAngle = this.desiredAngle;
    this.cameraElevation = this.desiredElevation;
    this.updateCameraPosition();
    this.syncAdaptiveLabels();
  }

  public getCameraAngle(): { angle: number; elevation: number } {
    return { angle: this.cameraAngle, elevation: this.cameraElevation };
  }

  public getDesiredAngle(): { angle: number; elevation: number } {
    return { angle: this.desiredAngle, elevation: this.desiredElevation };
  }

  public simulateKeyboardKey(key: string, isDown: boolean): void {
    if (isDown) {
      this.pressedKeys.add(key.toLowerCase());
    } else {
      this.pressedKeys.delete(key.toLowerCase());
    }
  }

  public simulateGesturePan(deltaScreenX: number, deltaScreenY: number): void {
    const rad = (this.cameraAngle * Math.PI) / 180;
    const panSensitivity = 0.024 * (this.cameraDistance / 24);
    const worldDeltaX = (-deltaScreenX * Math.cos(rad) + deltaScreenY * Math.sin(rad)) * panSensitivity;
    const worldDeltaZ = (-deltaScreenX * Math.sin(rad) - deltaScreenY * Math.cos(rad)) * panSensitivity;
    this.panCamera(worldDeltaX, worldDeltaZ);
  }

  public simulateGesturePinch(scaleFactor: number): void {
    this.zoomCamera(scaleFactor);
  }

  public simulateGestureRotate(deltaDegrees: number): void {
    this.orbitCamera(-deltaDegrees);
  }

  public isFollowingAgent(): boolean {
    return this.followSelectedAgent;
  }

  public panCamera(deltaX: number, deltaZ: number): void {
    this.followSelectedAgent = false;
    const bounds = computeCampusBounds(this.rooms);
    this.desiredTarget.x = Math.max(
      bounds.minX,
      Math.min(bounds.maxX, this.desiredTarget.x + deltaX)
    );
    this.desiredTarget.z = Math.max(
      bounds.minZ,
      Math.min(bounds.maxZ, this.desiredTarget.z + deltaZ)
    );
    if (this.options.reducedMotion) {
      this.cameraTarget.copy(this.desiredTarget);
    }
    this.updateCameraPosition();
    this.syncAdaptiveLabels();
  }

  private getDepartmentAccentHex(unitId?: string): string | undefined {
    if (!unitId) return undefined;
    return this.rooms.find((r) => r.id === unitId)?.color;
  }

  private buildAgentAvatar(agent: AgentIdentity, activity: ProjectedAgentActivity): THREE.Group {
    const departmentAccentHex = this.getDepartmentAccentHex(agent.unitId);
    return buildHumanoidAgentAvatar(agent, activity, this.avatarPool, {
      departmentAccentHex,
      createSpeechBubbleSprite: () => this.createSpeechBubbleSprite(),
      createAgentNameSprite: (name, roleBadge, haloColor) =>
        this.createAgentNameSprite(name, roleBadge, haloColor),
    });
  }

  private createSpeechBubbleSprite(): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = 'rgba(254, 243, 199, 0.96)';
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.roundRect(8, 6, 112, 44, 14);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = 'bold 22px sans-serif';
      ctx.fillStyle = '#92400e';
      ctx.fillText('💬 ...', 64, 35);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const mat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: true });
    const sprite = new THREE.Sprite(mat);
    sprite.scale.set(0.95, 0.48, 1);
    return sprite;
  }

  private createAgentNameSprite(
    shortName: string,
    activityBadge: string,
    borderColor: number
  ): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 216;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      const hex = '#' + borderColor.toString(16).padStart(6, '0');
      ctx.fillStyle = 'rgba(10, 18, 34, 0.94)';
      ctx.strokeStyle = hex;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.roundRect(4, 4, 208, 56, 10);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = 'bold 17px sans-serif';
      ctx.fillStyle = '#ffffff';
      ctx.fillText(shortName.slice(0, 14), 108, 25);

      ctx.font = '600 12px sans-serif';
      ctx.fillStyle = '#7dd3fc';
      ctx.fillText(activityBadge.slice(0, 22), 108, 46);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthTest: true,
    });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(1.58, 0.5, 1);
    return sprite;
  }

  public selectRoom(roomId: string, animate = true): void {
    this.activeRoomId = roomId;
    this.followSelectedAgent = false;
    const roomConfig = this.rooms.find((r) => r.id === roomId);
    if (!roomConfig) return;

    if (this.roomSpotlight) {
      this.roomSpotlight.position.set(roomConfig.x, 12, roomConfig.z);
      this.roomSpotlight.target.position.set(roomConfig.x, 0, roomConfig.z);
      this.scene.add(this.roomSpotlight.target);
    }

    this.desiredTarget.set(roomConfig.x, 0, roomConfig.z);
    this.desiredDistance = 14.5;

    if (!animate || this.options.reducedMotion) {
      this.cameraTarget.copy(this.desiredTarget);
      this.cameraDistance = this.desiredDistance;
      this.updateCameraPosition();
    }
    this.syncAdaptiveLabels();
  }

  public selectAgent(agentId: string | null): void {
    this.activeAgentId = agentId;
    if (!this.selectionRing) {
      this.syncAdaptiveLabels();
      return;
    }

    if (!agentId) {
      this.selectionRing.visible = false;
      this.followSelectedAgent = false;
      this.syncAdaptiveLabels();
      return;
    }

    const agentGroup = this.agentMeshes.get(agentId);
    if (agentGroup) {
      this.selectionRing.position.set(agentGroup.position.x, 0.38, agentGroup.position.z);
      this.selectionRing.visible = true;

      const unitId = agentGroup.userData.unitId;
      if (unitId && unitId !== this.activeRoomId) {
        this.selectRoom(unitId);
      }
    } else {
      this.selectionRing.visible = false;
    }
    this.syncAdaptiveLabels();
  }

  public rotateCamera(deltaAngleDegrees: number): void {
    this.orbitCamera(deltaAngleDegrees, 0);
  }

  public zoomCamera(deltaFactor: number): void {
    this.desiredDistance = Math.max(
      this.minDistance,
      Math.min(this.maxDistance, this.desiredDistance * deltaFactor)
    );
    if (this.options.reducedMotion) {
      this.cameraDistance = this.desiredDistance;
      this.updateCameraPosition();
    }
    this.syncAdaptiveLabels();
  }

  public resetCamera(): void {
    this.followSelectedAgent = false;
    const bounds = computeCampusBounds(this.rooms);
    this.cameraAngle = 35;
    this.desiredAngle = 35;
    this.cameraElevation = 42;
    this.desiredElevation = 42;
    this.desiredDistance = this.computeOverviewDistance(bounds, this.camera.aspect);
    this.desiredTarget.set(bounds.centerX, 0, bounds.centerZ);

    if (this.options.reducedMotion) {
      this.cameraTarget.set(bounds.centerX, 0, bounds.centerZ);
      this.cameraDistance = this.desiredDistance;
      this.updateCameraPosition();
    }
    this.syncAdaptiveLabels();
  }

  public setCameraPreset(preset: OfficeCameraPreset): void {
    if (preset === 'overview') {
      this.resetCamera();
      return;
    }
    const bounds = computeCampusBounds(this.rooms);
    if (preset === 'isometric') {
      this.followSelectedAgent = false;
      this.cameraAngle = 45;
      this.desiredAngle = 45;
      this.cameraElevation = 40;
      this.desiredElevation = 40;
      this.desiredDistance = 20;
      this.desiredTarget.set(bounds.centerX, 0, bounds.centerZ);
    } else if (preset === 'top-down') {
      this.followSelectedAgent = false;
      this.cameraAngle = 0;
      this.desiredAngle = 0;
      this.cameraElevation = 78;
      this.desiredElevation = 78;
      this.desiredDistance = Math.max(25, bounds.recommendedOverviewDistance);
      this.desiredTarget.set(bounds.centerX, 0, bounds.centerZ);
    } else if (preset === 'agent-focus') {
      this.cameraElevation = 34;
      this.desiredElevation = 34;
      if (this.activeAgentId) {
        const agentGroup = this.agentMeshes.get(this.activeAgentId);
        if (agentGroup) {
          this.followSelectedAgent = true;
          this.desiredTarget.set(agentGroup.position.x, 0, agentGroup.position.z);
          this.desiredDistance = 10;
        }
      } else {
        this.followSelectedAgent = false;
        const roomConfig = this.rooms.find((r) => r.id === this.activeRoomId);
        if (roomConfig) {
          this.desiredTarget.set(roomConfig.x, 0, roomConfig.z);
          this.desiredDistance = 13.5;
        }
      }
    }

    if (this.options.reducedMotion) {
      this.cameraTarget.copy(this.desiredTarget);
      this.cameraDistance = this.desiredDistance;
    }
    this.updateCameraPosition();
    this.syncAdaptiveLabels();
  }

  public getCameraState(): CameraViewState {
    return {
      angle: this.cameraAngle,
      elevation: this.cameraElevation,
      distance: this.cameraDistance,
      targetX: this.cameraTarget.x,
      targetZ: this.cameraTarget.z,
      lodTier: deriveLabelLodTier(this.cameraDistance),
      followAgentId: this.followSelectedAgent ? this.activeAgentId : null,
    };
  }

  private updateCameraPosition(): void {
    const radY = THREE.MathUtils.degToRad(this.cameraAngle);
    const radX = THREE.MathUtils.degToRad(this.cameraElevation);

    const x = this.cameraTarget.x + this.cameraDistance * Math.sin(radY) * Math.cos(radX);
    const y = this.cameraTarget.y + this.cameraDistance * Math.sin(radX);
    const z = this.cameraTarget.z + this.cameraDistance * Math.cos(radY) * Math.cos(radX);

    this.camera.position.set(x, y, z);
    this.camera.lookAt(this.cameraTarget);
    this.options.callbacks.onCameraChange?.(this.getCameraState());
  }

  /** Fit the entire cutaway building inside the actual viewport, not only its
   * organizational bounds. The shared slab/facade are larger than room bounds,
   * and a 40-degree perspective camera needs substantial framing margin. */
  private computeOverviewDistance(
    bounds: ReturnType<typeof computeCampusBounds>,
    aspect: number,
  ): number {
    const spanX = Math.max(bounds.spanX, 26.5);
    const spanZ = Math.max(bounds.spanZ, 20.5);
    const azimuth = THREE.MathUtils.degToRad(35);
    const elevation = THREE.MathUtils.degToRad(42);
    const verticalFov = THREE.MathUtils.degToRad(this.camera.fov);
    const rightSpan = Math.abs(Math.cos(azimuth)) * spanX + Math.abs(Math.sin(azimuth)) * spanZ;
    const upSpan = Math.sin(elevation) * (
      Math.abs(Math.sin(azimuth)) * spanX + Math.abs(Math.cos(azimuth)) * spanZ
    ) + Math.cos(elevation) * 3.0;
    const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * Math.max(0.5, aspect));
    const verticalDistance = upSpan / (2 * Math.tan(verticalFov / 2));
    const horizontalDistance = rightSpan / (2 * Math.tan(horizontalFov / 2));
    return Math.max(bounds.recommendedOverviewDistance, Math.ceil(Math.max(verticalDistance, horizontalDistance) * 1.4));
  }

  private bindEvents(): void {
    const dom = this.renderer.domElement;
    if (!dom || !dom.addEventListener) return;

    dom.addEventListener('pointerdown', this.handlePointerDown);
    dom.addEventListener('pointermove', this.handlePointerMove);
    dom.addEventListener('pointerup', this.handlePointerUp);
    dom.addEventListener('pointercancel', this.handlePointerCancel);
    dom.addEventListener('dblclick', this.handleDblClick);
    dom.addEventListener('contextmenu', this.handleContextMenu);
    dom.addEventListener('wheel', this.handleWheel, { passive: false });
    dom.addEventListener('touchstart', this.handleTouchStart, { passive: false });
    dom.addEventListener('touchmove', this.handleTouchMove, { passive: false });
    dom.addEventListener('webglcontextlost', this.handleContextLost as EventListener);
    dom.addEventListener('webglcontextrestored', this.handleContextRestored as EventListener);

    if (typeof window !== 'undefined' && window.addEventListener) {
      window.addEventListener('keydown', this.handleKeyDown);
      window.addEventListener('keyup', this.handleKeyUp);
    }
  }

  private handleKeyDown = (e: KeyboardEvent): void => {
    const activeEl = typeof document !== 'undefined' ? document.activeElement : null;
    if (
      activeEl &&
      (activeEl.tagName === 'INPUT' ||
        activeEl.tagName === 'TEXTAREA' ||
        activeEl.tagName === 'SELECT' ||
        (activeEl as HTMLElement).isContentEditable)
    ) {
      return;
    }
    const key = e.key.toLowerCase();
    if (
      ['w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].includes(
        key
      )
    ) {
      this.pressedKeys.add(key);
      if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].includes(key)) {
        e.preventDefault();
      }
    }
  };

  private handleKeyUp = (e: KeyboardEvent): void => {
    this.pressedKeys.delete(e.key.toLowerCase());
  };

  private handleContextLost = (e: Event): void => {
    e.preventDefault();
    this.contextLost = true;
  };

  private handleContextRestored = (): void => {
    this.contextLost = false;
    this.applyQualityProfileToRenderer();
    this.updateCameraPosition();
    this.syncAdaptiveLabels();
    this.renderer.render(this.scene, this.camera);
  };

  private handlePointerDown = (e: PointerEvent): void => {
    this.activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    this.pointerDownPos.set(e.clientX, e.clientY);
    this.isDragging = false;
    this.gestureDragDistance = 0;

    if (this.activePointers.size === 2) {
      const [p1, p2] = Array.from(this.activePointers.values());
      this.lastPinchDistance = Math.hypot(p2.x - p1.x, p2.y - p1.y);
      this.lastTwoFingerAngle = Math.atan2(p2.y - p1.y, p2.x - p1.x);
    }

    if (typeof this.renderer.domElement.setPointerCapture === 'function') {
      try {
        this.renderer.domElement.setPointerCapture(e.pointerId);
      } catch {
        // Safe fallback in test environments
      }
    }
  };

  private handlePointerMove = (e: PointerEvent): void => {
    if (this.activePointers.has(e.pointerId)) {
      this.activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    }

    // 1. Two-finger Gestures: Pinch-to-zoom & Two-finger Orbit
    if (this.activePointers.size === 2) {
      const [p1, p2] = Array.from(this.activePointers.values());
      const currentDistance = Math.hypot(p2.x - p1.x, p2.y - p1.y);
      const currentAngle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

      if (this.lastPinchDistance && this.lastPinchDistance > 10) {
        const pinchRatio = this.lastPinchDistance / Math.max(10, currentDistance);
        this.zoomCamera(1 + (pinchRatio - 1) * 0.75);
      }
      this.lastPinchDistance = currentDistance;

      if (this.lastTwoFingerAngle !== null) {
        let deltaAngleRad = currentAngle - this.lastTwoFingerAngle;
        if (deltaAngleRad > Math.PI) deltaAngleRad -= Math.PI * 2;
        if (deltaAngleRad < -Math.PI) deltaAngleRad += Math.PI * 2;
        const deltaDeg = (deltaAngleRad * 180) / Math.PI;
        this.orbitCamera(-deltaDeg * 0.9);
      }
      this.lastTwoFingerAngle = currentAngle;
      this.isDragging = true;
      return;
    }

    // 2. Single-finger / Single-pointer Drag
    const deltaX = e.clientX - this.pointerDownPos.x;
    const deltaY = e.clientY - this.pointerDownPos.y;

    if (e.buttons !== 0 || e.pointerType === 'touch') {
      this.gestureDragDistance += Math.hypot(deltaX, deltaY);
      if (this.gestureDragDistance > 4) {
        this.isDragging = true;
      }

      if (this.isDragging) {
        const isRightClick = (e.buttons & 2) !== 0;
        const isLeftClick = (e.buttons & 1) !== 0;

        // 1. Orbital View Rotation (Yaw & Pitch):
        // Right-Click Drag, or Left-Click with Orbit mode / Shift / Alt
        const isOrbitDrag =
          isRightClick ||
          e.shiftKey ||
          e.altKey ||
          (isLeftClick && this.options.dragMode === 'orbit');

        if (isOrbitDrag) {
          this.renderer.domElement.style.cursor = 'all-scroll';
          this.orbitCamera(-deltaX * 0.35, deltaY * 0.25);
          this.pointerDownPos.set(e.clientX, e.clientY);
          return;
        }

        // 2. Planar Floor Panning:
        // Middle-Click (wheel click), Left-Click (default dragMode 'pan'), or touch drag
        this.renderer.domElement.style.cursor = 'grabbing';
        const rad = (this.cameraAngle * Math.PI) / 180;
        const panSensitivity = 0.024 * (this.cameraDistance / 24);
        const worldDeltaX = (-deltaX * Math.cos(rad) + deltaY * Math.sin(rad)) * panSensitivity;
        const worldDeltaZ = (-deltaX * Math.sin(rad) - deltaY * Math.cos(rad)) * panSensitivity;

        this.panCamera(worldDeltaX, worldDeltaZ);
        this.pointerDownPos.set(e.clientX, e.clientY);
        return;
      }
    }

    // 3. Hover Raycasting (when not dragging)
    if (!this.isDragging) {
      const rect = this.renderer.domElement.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);
        const intersects = this.raycaster.intersectObjects(this.interactiveMeshes, false);

        if (intersects.length > 0) {
          const hit = intersects[0].object;
          this.renderer.domElement.style.cursor = 'pointer';
          if (hit.userData?.type === 'agent') {
            this.options.callbacks.onHoverObject({ type: 'agent', id: hit.userData.id });
          } else if (hit.userData?.type === 'room') {
            this.options.callbacks.onHoverObject({ type: 'room', id: hit.userData.id });
          }
        } else {
          this.renderer.domElement.style.cursor = 'grab';
          this.options.callbacks.onHoverObject(null);
        }
      }
    }
  };

  private handlePointerUp = (e: PointerEvent): void => {
    this.activePointers.delete(e.pointerId);
    if (typeof this.renderer.domElement.releasePointerCapture === 'function') {
      try {
        this.renderer.domElement.releasePointerCapture(e.pointerId);
      } catch {
        // Safe fallback in test environments
      }
    }

    if (this.activePointers.size === 0) {
      if (!this.isDragging && (e.button === 0 || e.pointerType === 'touch')) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
          this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

          this.raycaster.setFromCamera(this.mouse, this.camera);
          const intersects = this.raycaster.intersectObjects(this.interactiveMeshes, false);

          if (intersects.length > 0) {
            const hit = intersects[0].object;
            if (hit.userData?.type === 'agent') {
              this.options.callbacks.onSelectAgent(hit.userData.id);
            } else if (hit.userData?.type === 'room') {
              this.options.callbacks.onSelectRoom(hit.userData.id);
            }
          }
        }
      }

      this.isDragging = false;
      this.renderer.domElement.style.cursor = 'grab';
      this.lastPinchDistance = null;
      this.lastTwoFingerAngle = null;
    }
  };

  private handlePointerCancel = (e: PointerEvent): void => {
    this.activePointers.delete(e.pointerId);
    if (this.activePointers.size === 0) {
      this.isDragging = false;
      this.lastPinchDistance = null;
      this.lastTwoFingerAngle = null;
    }
  };

  private handleContextMenu = (e: MouseEvent): void => {
    e.preventDefault();
  };

  private handleDblClick = (e: MouseEvent): void => {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const width = rect.width > 0 ? rect.width : 1024;
    const height = rect.height > 0 ? rect.height : 768;

    this.mouse.x = ((e.clientX - (rect.left || 0)) / width) * 2 - 1;
    this.mouse.y = -((e.clientY - (rect.top || 0)) / height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.interactiveMeshes, false);
    if (intersects.length > 0) {
      const hit = intersects[0].object;
      if (hit.userData?.type === 'agent') {
        this.selectAgent(hit.userData.id);
        this.setFollowAgent(true);
      } else if (hit.userData?.type === 'room') {
        this.selectRoom(hit.userData.id);
      }
    } else {
      this.resetCamera();
    }
  };

  private handleTouchStart = (e: TouchEvent): void => {
    if (e.cancelable) e.preventDefault();
  };

  private handleTouchMove = (e: TouchEvent): void => {
    if (e.cancelable) e.preventDefault();
  };

  private handleWheel = (e: WheelEvent): void => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 1.08 : 0.92;
    this.zoomCamera(factor);
  };

  public resize(): void {
    if (!this.container || this.isDisposed) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (width === 0 || height === 0) return;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  public stepAnimation(time: number): void {
    if (this.isDisposed || this.contextLost) return;
    const stepStartMs = typeof performance !== 'undefined' ? performance.now() : Date.now();

    if (this.lastFrameTimestampMs > 0 && time > this.lastFrameTimestampMs) {
      const dt = time - this.lastFrameTimestampMs;
      this.lastFrameIntervalMs = dt;
      const instFps = 1000 / dt;
      this.smoothedFps = this.smoothedFps * 0.85 + Math.min(120, instFps) * 0.15;
    }
    if (this.lastFrameTimestampMs === 0 && time > 0) {
      this.lastFrameIntervalMs = 1000 / 60;
    }
    this.lastFrameTimestampMs = time;

    let shouldRefreshLabels = false;
    // Decoupled state & label evaluation every 1500ms
    if (time - this.lastStateEvaluationMs >= 1500 && this.currentAgents.length > 0) {
      this.lastStateEvaluationMs = time;
      shouldRefreshLabels = true;
    }

    // Optional Agent Follow Mode: smoothly track activeAgentId position
    if (this.followSelectedAgent && this.activeAgentId) {
      const followedGroup = this.agentMeshes.get(this.activeAgentId);
      if (followedGroup) {
        this.desiredTarget.set(followedGroup.position.x, 0, followedGroup.position.z);
      }
    }

    // 1. Keyboard Navigation across campus floor plate (W, A, S, D, Q, E, Space)
    if (this.pressedKeys.size > 0 && !this.options.reducedMotion) {
      const dtSec = 0.016;
      const moveSpeed = 16 * (this.cameraDistance / 24);
      const rad = THREE.MathUtils.degToRad(this.cameraAngle);

      let forward = 0;
      let strafe = 0;

      if (this.pressedKeys.has('w') || this.pressedKeys.has('arrowup')) forward += 1;
      if (this.pressedKeys.has('s') || this.pressedKeys.has('arrowdown')) forward -= 1;
      if (this.pressedKeys.has('d') || this.pressedKeys.has('arrowright')) strafe += 1;
      if (this.pressedKeys.has('a') || this.pressedKeys.has('arrowleft')) strafe -= 1;

      if (forward !== 0 || strafe !== 0) {
        this.followSelectedAgent = false;
        const mag = Math.hypot(forward, strafe);
        const normForward = forward / mag;
        const normStrafe = strafe / mag;

        const fx = -Math.sin(rad);
        const fz = -Math.cos(rad);
        const sx = Math.cos(rad);
        const sz = -Math.sin(rad);

        const deltaX = (fx * normForward + sx * normStrafe) * moveSpeed * dtSec;
        const deltaZ = (fz * normForward + sz * normStrafe) * moveSpeed * dtSec;
        this.panCamera(deltaX, deltaZ);
      }

      const turnSpeed = 90; // degrees per second
      if (this.pressedKeys.has('q')) {
        this.orbitCamera(-turnSpeed * dtSec, 0);
      }
      if (this.pressedKeys.has('e')) {
        this.orbitCamera(turnSpeed * dtSec, 0);
      }
      if (this.pressedKeys.has(' ')) {
        this.pressedKeys.delete(' ');
        if (this.activeAgentId) {
          this.setFollowAgent(true);
        } else {
          this.resetCamera();
        }
      }
    }

    // 2. Smooth camera tracking, smart zooming and angular damping
    if (!this.options.reducedMotion) {
      let needsCameraUpdate = false;
      if (this.cameraTarget.distanceTo(this.desiredTarget) > 0.02) {
        this.cameraTarget.lerp(this.desiredTarget, 0.12);
        needsCameraUpdate = true;
      }
      if (Math.abs(this.cameraDistance - this.desiredDistance) > 0.05) {
        this.cameraDistance += (this.desiredDistance - this.cameraDistance) * 0.12;
        needsCameraUpdate = true;
      }
      let angleDiff = (this.desiredAngle - this.cameraAngle) % 360;
      if (angleDiff > 180) angleDiff -= 360;
      if (angleDiff < -180) angleDiff += 360;
      if (Math.abs(angleDiff) > 0.05) {
        this.cameraAngle = (this.cameraAngle + angleDiff * 0.2) % 360;
        if (this.cameraAngle < 0) this.cameraAngle += 360;
        needsCameraUpdate = true;
      }
      if (Math.abs(this.desiredElevation - this.cameraElevation) > 0.05) {
        this.cameraElevation += (this.desiredElevation - this.cameraElevation) * 0.2;
        needsCameraUpdate = true;
      }
      if (needsCameraUpdate) {
        this.updateCameraPosition();
        shouldRefreshLabels = true;
      }
    }

    // 2. Agent Animations (Preserving Defect 2 contract on children[1] + Articulating characterRig)
    if (!this.options.reducedMotion) {
      this.agentMeshes.forEach((group, agentId) => {
        const runtime = this.agentRuntimeStates.get(agentId);
        if (!runtime) return;

        stepAvatarKinematics(group, runtime, time, this.cameraDistance, {
          reducedMotion: false,
          sampleWaypointRoute,
        });
      });

      if (this.selectionRing && this.selectionRing.visible && this.activeAgentId) {
        const activeGroup = this.agentMeshes.get(this.activeAgentId);
        if (activeGroup) {
          this.selectionRing.position.x = activeGroup.position.x;
          this.selectionRing.position.z = activeGroup.position.z;
        }
        const s = 1.0 + Math.sin(time * 0.006) * 0.08;
        this.selectionRing.scale.set(s, s, s);
      }
    }

    if (shouldRefreshLabels) {
      this.syncAdaptiveLabels();
    }
    const stepEndMs = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.lastSimulationUpdateDurationMs = Number(Math.max(0.01, stepEndMs - stepStartMs).toFixed(2));
  }

  private animate(time: number): void {
    if (this.isDisposed) return;

    if (
      this.contextLost ||
      (typeof document !== 'undefined' && document.visibilityState === 'hidden')
    ) {
      this.animFrameId = requestAnimationFrame(this.animate);
      return;
    }

    const frameWorkStartMs = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.stepAnimation(time);
    this.renderer.render(this.scene, this.camera);
    const frameWorkEndMs = typeof performance !== 'undefined' ? performance.now() : Date.now();
    this.lastFrameWorkDurationMs = Number(Math.max(0.01, frameWorkEndMs - frameWorkStartMs).toFixed(2));
    this.animFrameId = requestAnimationFrame(this.animate);
  }

  private disposeHierarchy(obj: THREE.Object3D): void {
    const disposedTextures = new Set<THREE.Texture>();
    const disposeMaterial = (material: THREE.Material) => {
      for (const value of Object.values(material as unknown as Record<string, unknown>)) {
        if (value instanceof THREE.Texture && !disposedTextures.has(value)) {
          disposedTextures.add(value);
          value.dispose();
        }
      }
      material.dispose();
    };
    obj.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        if (
          child.geometry &&
          !this.furniturePool.ownsGeometry(child.geometry) &&
          !this.avatarPool.ownsGeometry(child.geometry)
        ) {
          child.geometry.dispose();
        }
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => {
            if (
              !this.furniturePool.ownsMaterial(m) &&
              !this.avatarPool.ownsMaterial(m)
            ) {
              disposeMaterial(m);
            }
          });
        } else if (
          child.material &&
          !this.furniturePool.ownsMaterial(child.material) &&
          !this.avatarPool.ownsMaterial(child.material)
        ) {
          disposeMaterial(child.material);
        }
      } else if (child instanceof THREE.Sprite) {
        if (child.material.map) child.material.map.dispose();
        child.material.dispose();
      }
    });
  }

  public dispose(): void {
    this.isDisposed = true;
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }

    const dom = this.renderer.domElement;
    if (dom && dom.removeEventListener) {
      dom.removeEventListener('pointerdown', this.handlePointerDown);
      dom.removeEventListener('pointermove', this.handlePointerMove);
      dom.removeEventListener('pointerup', this.handlePointerUp);
      dom.removeEventListener('pointercancel', this.handlePointerCancel);
      dom.removeEventListener('dblclick', this.handleDblClick);
      dom.removeEventListener('contextmenu', this.handleContextMenu);
      dom.removeEventListener('wheel', this.handleWheel);
      dom.removeEventListener('touchstart', this.handleTouchStart);
      dom.removeEventListener('touchmove', this.handleTouchMove);
      dom.removeEventListener('webglcontextlost', this.handleContextLost as EventListener);
      dom.removeEventListener('webglcontextrestored', this.handleContextRestored as EventListener);
    }

    if (typeof window !== 'undefined' && window.removeEventListener) {
      window.removeEventListener('keydown', this.handleKeyDown);
      window.removeEventListener('keyup', this.handleKeyUp);
    }

    this.disposeHierarchy(this.scene);
    this.furniturePool.dispose();
    this.avatarPool.dispose();
    if (this.renderer && typeof this.renderer.dispose === 'function') {
      this.renderer.dispose();
    }
    if (dom && typeof dom.remove === 'function') {
      dom.remove();
    }
  }
}
