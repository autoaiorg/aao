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
class SharedFurniturePool {
  public readonly deskTopGeo = new THREE.BoxGeometry(0.95, 0.06, 0.48);
  public readonly deskLegGeo = new THREE.BoxGeometry(0.06, 0.42, 0.44);
  public readonly monitorPanelGeo = new THREE.BoxGeometry(0.36, 0.24, 0.03);
  public readonly monitorStandGeo = new THREE.BoxGeometry(0.06, 0.12, 0.06);
  public readonly keyboardGeo = new THREE.BoxGeometry(0.28, 0.02, 0.11);
  public readonly mouseGeo = new THREE.BoxGeometry(0.05, 0.02, 0.08);

  public readonly chairBaseGeo = new THREE.CylinderGeometry(0.18, 0.2, 0.05, 12);
  public readonly chairStemGeo = new THREE.CylinderGeometry(0.035, 0.035, 0.2, 10);
  public readonly chairSeatGeo = new THREE.BoxGeometry(0.34, 0.05, 0.34);
  public readonly chairBackGeo = new THREE.BoxGeometry(0.32, 0.36, 0.05);
  public readonly chairArmGeo = new THREE.BoxGeometry(0.04, 0.14, 0.22);

  public readonly meetingTableTopGeo = new THREE.CylinderGeometry(0.46, 0.46, 0.05, 20);
  public readonly meetingTablePedGeo = new THREE.CylinderGeometry(0.12, 0.22, 0.4, 14);

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

  private readonly allGeometries: THREE.BufferGeometry[];
  private readonly allMaterials: THREE.Material[];

  constructor() {
    this.allGeometries = [
      this.deskTopGeo,
      this.deskLegGeo,
      this.monitorPanelGeo,
      this.monitorStandGeo,
      this.keyboardGeo,
      this.mouseGeo,
      this.chairBaseGeo,
      this.chairStemGeo,
      this.chairSeatGeo,
      this.chairBackGeo,
      this.chairArmGeo,
      this.meetingTableTopGeo,
      this.meetingTablePedGeo,
    ];
    this.allMaterials = [
      this.deskWoodMat,
      this.holdingDeskMat,
      this.metalLegMat,
      this.chairCushionMat,
      this.keyboardMat,
      this.meetingTableMat,
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
  private cameraElevation = 42; // degrees tilt
  private cameraDistance = 24; // distance from target
  private desiredDistance = 24; // smart zoom destination
  private minDistance = 8;
  private maxDistance = 38;
  private cameraTarget = new THREE.Vector3(0, 0, 0);
  private desiredTarget = new THREE.Vector3(0, 0, 0);
  private followSelectedAgent = false;

  // Groups and Interactive Meshes
  private roomsGroup = new THREE.Group();
  private agentsGroup = new THREE.Group();
  private lightsGroup = new THREE.Group();
  private walkwaysGroup = new THREE.Group();
  private interactiveMeshes: THREE.Object3D[] = [];
  private roomPlatforms: Map<string, THREE.Mesh> = new Map();
  private roomLabels: Map<string, THREE.Sprite> = new Map();
  private agentMeshes: Map<string, THREE.Group> = new Map();
  private agentRuntimeStates: Map<string, AgentAnimatedRuntimeState> = new Map();
  private currentAgents: AgentIdentity[] = [];
  private lastStateEvaluationMs = 0;

  // Performance & Adaptive Label Telemetry
  private lastFrameTimestampMs = 0;
  private lastFrameDurationMs = 16.6;
  private smoothedFps = 60;
  private lastStateUpdateDurationMs = 0;
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
    this.cameraDistance = bounds.recommendedOverviewDistance;
    this.desiredDistance = bounds.recommendedOverviewDistance;
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
    this.setupLighting();
    this.buildWorld();
    this.syncAdaptiveLabels();

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
    return {
      qualityProfile: this.qualityProfile,
      fpsEstimate: Math.round(this.smoothedFps),
      lastFrameTimeMs: Number(this.lastFrameDurationMs.toFixed(2)),
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
    const ambient = new THREE.AmbientLight(0x334766, 2.25);
    this.lightsGroup.add(ambient);

    const dirLight = new THREE.DirectionalLight(0xf8fafc, 2.5);
    dirLight.position.set(18, 32, 16);
    dirLight.castShadow = this.qualityProfile !== 'low';
    const shadowSize = this.qualityProfile === 'high' ? 2048 : 1024;
    dirLight.shadow.mapSize.width = shadowSize;
    dirLight.shadow.mapSize.height = shadowSize;
    dirLight.shadow.camera.near = 0.5;
    dirLight.shadow.camera.far = 90;
    const d = 18;
    dirLight.shadow.camera.left = -d;
    dirLight.shadow.camera.right = d;
    dirLight.shadow.camera.top = d;
    dirLight.shadow.camera.bottom = -d;
    this.mainDirLight = dirLight;
    this.lightsGroup.add(dirLight);

    const fillLight = new THREE.DirectionalLight(0x38bdf8, 1.15);
    fillLight.position.set(-20, 15, -15);
    this.lightsGroup.add(fillLight);

    this.roomSpotlight = new THREE.SpotLight(0x60a5fa, 3.8, 32, Math.PI / 4, 0.4, 1);
    this.roomSpotlight.position.set(-5, 12, -3.1);
    this.roomSpotlight.castShadow = this.qualityProfile === 'high';
    this.lightsGroup.add(this.roomSpotlight);
  }

  private buildWorld(): void {
    this.rebuildGround();

    // 1. Central Coordination Atrium Hub (Radius 3.4, connected to all department corridors)
    const atriumGeo = new THREE.CylinderGeometry(3.4, 3.55, 0.14, 36);
    const atriumMat = new THREE.MeshStandardMaterial({
      color: 0x17253b,
      roughness: 0.35,
      metalness: 0.45,
    });
    const atrium = new THREE.Mesh(atriumGeo, atriumMat);
    atrium.position.y = 0.07;
    atrium.receiveShadow = true;
    this.scene.add(atrium);

    // Atrium Perimeter Ring Curb
    const outerRingGeo = new THREE.RingGeometry(3.25, 3.45, 36);
    outerRingGeo.rotateX(-Math.PI / 2);
    const outerRingMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.55,
    });
    const outerRing = new THREE.Mesh(outerRingGeo, outerRingMat);
    outerRing.position.y = 0.145;
    this.scene.add(outerRing);

    // Center Compass / Coordination Table Hub
    const compassGeo = new THREE.RingGeometry(0.95, 1.2, 32);
    compassGeo.rotateX(-Math.PI / 2);
    const compassMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide });
    const compass = new THREE.Mesh(compassGeo, compassMat);
    compass.position.y = 0.15;
    this.scene.add(compass);

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
    this.selectionRing.position.y = 0.22;
    this.scene.add(this.selectionRing);
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

    // Continuous Corporate Campus Floor Slab
    const campusSlab = new THREE.Mesh(
      new THREE.BoxGeometry(width - 1.5, 0.12, depth - 1.5),
      new THREE.MeshStandardMaterial({ color: 0x111c2e, roughness: 0.65, metalness: 0.25 })
    );
    campusSlab.position.y = -0.04;
    campusSlab.receiveShadow = true;
    this.groundGroup.add(campusSlab);

    // Polished Central Circulation Spine (terrazzo plaza connecting campus corridors)
    const centralPlaza = new THREE.Mesh(
      new THREE.BoxGeometry(Math.min(width - 3, 7.2), 0.02, Math.min(depth - 3, 7.2)),
      new THREE.MeshStandardMaterial({ color: 0x18283e, roughness: 0.35, metalness: 0.45 })
    );
    centralPlaza.position.y = 0.022;
    centralPlaza.receiveShadow = true;
    this.groundGroup.add(centralPlaza);

    const ground = new THREE.Mesh(
      new THREE.BoxGeometry(width + 6, 0.4, depth + 6),
      new THREE.MeshStandardMaterial({ color: 0x091322, roughness: 0.9, metalness: 0.1 })
    );
    ground.position.y = -0.26;
    ground.receiveShadow = true;
    this.groundGroup.add(ground);

    const gridSize = Math.max(width, depth);
    const grid = new THREE.GridHelper(gridSize, Math.ceil(gridSize), 0x2563eb, 0x172b47);
    grid.position.y = 0.025;
    this.groundGroup.add(grid);
  }

  private buildWalkways(): void {
    const walkwayMat = new THREE.MeshStandardMaterial({
      color: 0x16263f,
      roughness: 0.55,
      metalness: 0.3,
    });
    const holdingWalkwayMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.75,
      metalness: 0.15,
    });

    const navGraph = buildCampusNavGraph(this.rooms);

    for (const seg of navGraph.corridors) {
      const room = this.rooms.find((r) => r.id === seg.fromRoomId);
      const dx = seg.endX - seg.startX;
      const dz = seg.endZ - seg.startZ;
      const distance = Math.max(0.6, Math.hypot(dx, dz));
      const midX = (seg.startX + seg.endX) * 0.5;
      const midZ = (seg.startZ + seg.endZ) * 0.5;
      const angle = Math.atan2(dx, dz);

      const pathGeo = new THREE.BoxGeometry(seg.width, 0.08, distance + 0.5);
      const path = new THREE.Mesh(
        pathGeo,
        seg.isUnassignedWing ? holdingWalkwayMat : walkwayMat
      );
      path.position.set(midX, 0.04, midZ);
      path.rotation.y = angle;
      path.receiveShadow = true;
      this.walkwaysGroup.add(path);

      // Side Guide Strips along the corridor
      const accentHex = room?.accentColor || '#38bdf8';
      const stripGeo = new THREE.BoxGeometry(0.06, 0.09, distance + 0.4);
      const stripMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(accentHex).multiplyScalar(seg.isUnassignedWing ? 0.55 : 0.75),
      });

      const offset = seg.width * 0.46;
      const stripLeft = new THREE.Mesh(stripGeo, stripMat);
      stripLeft.position.set(
        midX - Math.cos(angle) * offset,
        0.05,
        midZ + Math.sin(angle) * offset
      );
      stripLeft.rotation.y = angle;
      this.walkwaysGroup.add(stripLeft);

      const stripRight = new THREE.Mesh(stripGeo, stripMat);
      stripRight.position.set(
        midX + Math.cos(angle) * offset,
        0.05,
        midZ - Math.sin(angle) * offset
      );
      stripRight.rotation.y = angle;
      this.walkwaysGroup.add(stripRight);
    }
  }

  private buildRoom(room: OfficeRoomConfig): void {
    const roomGroup = new THREE.Group();
    roomGroup.position.set(room.x, 0, room.z);
    const isUnassignedHolding =
      room.kind === 'unassigned-holding' || room.id === 'unit-unassigned';

    // Platform Slab (Interactive room target — ONLY mesh added to interactiveMeshes for rooms)
    const platGeo = new THREE.BoxGeometry(room.width, 0.35, room.depth);
    let platColor = new THREE.Color(room.color).multiplyScalar(isUnassignedHolding ? 0.55 : 0.72);
    let platRoughness = isUnassignedHolding ? 0.8 : 0.58;
    let platMetalness = isUnassignedHolding ? 0.15 : 0.3;

    if (room.floorFinish === 'hardwood-walnut' || room.kind === 'executive-suite') {
      platColor = new THREE.Color(0x2a1c14);
      platRoughness = 0.38;
      platMetalness = 0.18;
    } else if (room.floorFinish === 'high-security-frosted' || room.kind === 'audit-enclave') {
      platColor = new THREE.Color(0x0e2620);
      platRoughness = 0.46;
      platMetalness = 0.26;
    } else if (room.kind === 'agile-squad-pod') {
      platColor = new THREE.Color(0x13283a);
      platRoughness = 0.62;
      platMetalness = 0.22;
    }

    const platMat = new THREE.MeshStandardMaterial({
      color: platColor,
      roughness: platRoughness,
      metalness: platMetalness,
    });
    const platform = new THREE.Mesh(platGeo, platMat);
    platform.position.y = 0.175;
    platform.receiveShadow = true;
    platform.castShadow = true;
    platform.userData = {
      type: 'room',
      id: room.id,
      name: room.name,
      code: room.code,
      kind: room.kind ?? 'canonical-department',
    };
    roomGroup.add(platform);

    this.roomPlatforms.set(room.id, platform);
    this.interactiveMeshes.push(platform);

    // Perimeter Accent Border (dashed/muted for unassigned holding wing vs crisp accent for canonical departments)
    const borderGeo = new THREE.BoxGeometry(room.width + 0.08, 0.06, room.depth + 0.08);
    const borderMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(room.accentColor).multiplyScalar(isUnassignedHolding ? 0.7 : 1.0),
    });
    const border = new THREE.Mesh(borderGeo, borderMat);
    border.position.y = 0.37;
    roomGroup.add(border);

    // Interior Flooring Pad
    const carpetGeo = new THREE.BoxGeometry(room.width - 0.32, 0.02, room.depth - 0.32);
    const carpetMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(room.color).multiplyScalar(isUnassignedHolding ? 0.38 : 0.48),
      roughness: 0.88,
      metalness: 0.06,
    });
    const carpet = new THREE.Mesh(carpetGeo, carpetMat);
    carpet.position.y = 0.36;
    carpet.receiveShadow = true;
    roomGroup.add(carpet);

    // Translucent Corner Structural Columns
    const pillarGeo = new THREE.BoxGeometry(0.16, 1.75, 0.16);
    const pillarMat = new THREE.MeshStandardMaterial({
      color: isUnassignedHolding ? 0x94a3b8 : 0x93c5fd,
      transparent: true,
      opacity: isUnassignedHolding ? 0.3 : 0.45,
      roughness: 0.15,
      metalness: 0.85,
    });
    const hw = room.width / 2 - 0.14;
    const hd = room.depth / 2 - 0.14;
    const corners = [
      [-hw, -hd],
      [hw, -hd],
      [hw, hd],
      [-hw, hd],
    ];
    corners.forEach(([cx, cz]) => {
      const p = new THREE.Mesh(pillarGeo, pillarMat);
      p.position.set(cx, 1.08, cz);
      p.castShadow = true;
      roomGroup.add(p);
    });

    // Architectural Perimeter Walls & Open Doorway Entrance
    this.buildRoomArchitecture(roomGroup, room, isUnassignedHolding);

    // Office Workstations / Holding Stations + Meeting Zone
    this.buildOfficeWorkstationsAndMeetingZone(roomGroup, room, isUnassignedHolding);

    // Department Specific Accent Equipment
    if (!isUnassignedHolding && (this.options.demoFurniture ?? true)) {
      this.buildDepartmentAccentEquipment(roomGroup, room);
    }

    // Floating Department Label Sprite (managed by Adaptive Label System)
    const labelSprite = this.createDepartmentLabelSprite(
      room.code,
      room.name,
      room.accentColor,
      isUnassignedHolding
    );
    labelSprite.position.set(0, 2.38, 0);
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
      color: new THREE.Color(room.accentColor).multiplyScalar(isUnassignedHolding ? 0.45 : 1.15),
    });
    const chairAccentMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(room.accentColor).multiplyScalar(isUnassignedHolding ? 0.5 : 0.75),
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
        // Canonical Department: Dual Monitors + Keyboard + Mouse
        const monLeft = new THREE.Mesh(this.furniturePool.monitorPanelGeo, screenMat);
        monLeft.position.set(-0.2, 0.64, -0.1);
        monLeft.rotation.y = 0.14;
        deskGroup.add(monLeft);

        const standLeft = new THREE.Mesh(this.furniturePool.monitorStandGeo, this.furniturePool.metalLegMat);
        standLeft.position.set(-0.2, 0.51, -0.12);
        deskGroup.add(standLeft);

        const monRight = new THREE.Mesh(this.furniturePool.monitorPanelGeo, screenMat);
        monRight.position.set(0.2, 0.64, -0.1);
        monRight.rotation.y = -0.14;
        deskGroup.add(monRight);

        const standRight = new THREE.Mesh(this.furniturePool.monitorStandGeo, this.furniturePool.metalLegMat);
        standRight.position.set(0.2, 0.51, -0.12);
        deskGroup.add(standRight);

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
    const wallMat = new THREE.MeshStandardMaterial({
      color: isUnassignedHolding ? 0x1e293b : 0x1b283d,
      roughness: 0.6,
      metalness: 0.3,
    });
    const glassMat = new THREE.MeshStandardMaterial({
      color: isUnassignedHolding ? 0x94a3b8 : 0x60a5fa,
      transparent: true,
      opacity: isUnassignedHolding ? 0.22 : 0.32,
      roughness: 0.12,
      metalness: 0.85,
    });

    const isTopRow = room.z < 0;
    const backZ = isTopRow ? -room.depth / 2 + 0.12 : room.depth / 2 - 0.12;
    const frontZ = isTopRow ? room.depth / 2 - 0.1 : -room.depth / 2 + 0.1;

    // 1. Back Solid Architectural Wall
    const backWallGeo = new THREE.BoxGeometry(room.width - 0.5, 0.95, 0.14);
    const backWall = new THREE.Mesh(backWallGeo, wallMat);
    backWall.position.set(0, 0.82, backZ);
    backWall.castShadow = true;
    backWall.receiveShadow = true;
    group.add(backWall);

    // Wall Presentation Board / Status Header on Back Wall
    const boardGeo = new THREE.BoxGeometry(1.5, 0.48, 0.04);
    const boardMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(room.accentColor).multiplyScalar(isUnassignedHolding ? 0.65 : 0.95),
    });
    const board = new THREE.Mesh(boardGeo, boardMat);
    board.position.set(0, 1.02, backZ + (isTopRow ? 0.09 : -0.09));
    group.add(board);

    // 2. Side Translucent Glass Acoustic Partitions
    const sideGlassGeo = new THREE.BoxGeometry(0.08, 0.88, room.depth * 0.68);
    const sideGlassLeft = new THREE.Mesh(sideGlassGeo, glassMat);
    sideGlassLeft.position.set(-room.width / 2 + 0.12, 0.8, 0);
    group.add(sideGlassLeft);

    const sideGlassRight = new THREE.Mesh(sideGlassGeo, glassMat);
    sideGlassRight.position.set(room.width / 2 - 0.12, 0.8, 0);
    group.add(sideGlassRight);

    // 3. Front Entrance Wall with Open Central Doorway (1.4u gap so agents walk through cleanly)
    const doorwayWidth = 1.4;
    const frontPanelWidth = Math.max(0.5, (room.width - doorwayWidth - 0.4) / 2);
    const frontGlassGeo = new THREE.BoxGeometry(frontPanelWidth, 0.85, 0.08);

    const frontLeft = new THREE.Mesh(frontGlassGeo, glassMat);
    frontLeft.position.set(-doorwayWidth / 2 - frontPanelWidth / 2, 0.78, frontZ);
    group.add(frontLeft);

    const frontRight = new THREE.Mesh(frontGlassGeo, glassMat);
    frontRight.position.set(doorwayWidth / 2 + frontPanelWidth / 2, 0.78, frontZ);
    group.add(frontRight);

    // Doorway Header Portal Arch
    const lintelGeo = new THREE.BoxGeometry(doorwayWidth + 0.2, 0.1, 0.14);
    const lintelMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(room.accentColor),
    });
    const lintel = new THREE.Mesh(lintelGeo, lintelMat);
    lintel.position.set(0, 1.26, frontZ);
    group.add(lintel);

    // 4. Acoustic Manifestation Band for Audit Enclave (eye level 0.85m)
    const isAuditEnclave = room.kind === 'audit-enclave' || room.id === 'unit-audit';
    if (isAuditEnclave) {
      const manifestSideGeo = new THREE.BoxGeometry(0.088, 0.14, room.depth * 0.68 + 0.02);
      const manifestFrontGeo = new THREE.BoxGeometry(frontPanelWidth + 0.02, 0.14, 0.088);
      const manifestMat = new THREE.MeshBasicMaterial({
        color: 0x34d399,
        transparent: true,
        opacity: 0.65,
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
    accentColor: string,
    isUnassignedHolding = false
  ): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 280;
    canvas.height = 96;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = isUnassignedHolding ? 'rgba(30, 41, 59, 0.92)' : 'rgba(10, 22, 40, 0.92)';
      ctx.strokeStyle = accentColor;
      ctx.lineWidth = isUnassignedHolding ? 3 : 4;
      if (isUnassignedHolding && typeof ctx.setLineDash === 'function') {
        ctx.setLineDash([8, 5]);
      }
      ctx.beginPath();
      ctx.roundRect(6, 6, 268, 84, 14);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = 'bold 30px sans-serif';
      ctx.fillStyle = accentColor;
      ctx.fillText(isUnassignedHolding ? `⚠ ${code}` : code, 140, 42);

      ctx.font = '600 17px sans-serif';
      ctx.fillStyle = '#f8fafc';
      ctx.fillText(name.slice(0, 22), 140, 72);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthTest: false,
    });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(2.9, 1.02, 1);
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
      sprite.scale.set(2.9 * state.scale, 1.02 * state.scale, 1);
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
    this.cameraAngle = (this.cameraAngle + deltaAngle) % 360;
    this.cameraElevation = Math.max(15, Math.min(75, this.cameraElevation + deltaElevation));
    this.updateCameraPosition();
    this.syncAdaptiveLabels();
  }

  public getCameraAngle(): { angle: number; elevation: number } {
    return { angle: this.cameraAngle, elevation: this.cameraElevation };
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

    this.roomPlatforms.forEach((plat, id) => {
      const mat = plat.material as THREE.MeshStandardMaterial;
      const conf = this.rooms.find((r) => r.id === id);
      if (conf) {
        if (id === roomId) {
          mat.color.set(conf.accentColor).multiplyScalar(0.9);
          mat.emissive.set(conf.accentColor).multiplyScalar(0.25);
        } else {
          mat.color.set(conf.color).multiplyScalar(0.7);
          mat.emissive.set(0x000000);
        }
      }
    });

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
    this.cameraAngle = (this.cameraAngle + deltaAngleDegrees) % 360;
    this.updateCameraPosition();
    this.syncAdaptiveLabels();
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
    this.cameraElevation = 42;
    this.desiredDistance = bounds.recommendedOverviewDistance;
    this.desiredTarget.set(bounds.centerX, 0, bounds.centerZ);

    if (this.options.reducedMotion) {
      this.cameraTarget.set(bounds.centerX, 0, bounds.centerZ);
      this.cameraDistance = bounds.recommendedOverviewDistance;
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
      this.cameraElevation = 40;
      this.desiredDistance = 20;
      this.desiredTarget.set(bounds.centerX, 0, bounds.centerZ);
    } else if (preset === 'top-down') {
      this.followSelectedAgent = false;
      this.cameraAngle = 0;
      this.cameraElevation = 78;
      this.desiredDistance = Math.max(25, bounds.recommendedOverviewDistance);
      this.desiredTarget.set(bounds.centerX, 0, bounds.centerZ);
    } else if (preset === 'agent-focus') {
      this.cameraElevation = 34;
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
  }

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
        // Orbit on right-click, Shift+drag, or if dragMode === 'orbit'
        const isOrbitDrag =
          e.buttons === 2 || e.shiftKey || e.altKey || this.options.dragMode === 'orbit';

        if (isOrbitDrag) {
          this.orbitCamera(-deltaX * 0.3, deltaY * 0.25);
          this.pointerDownPos.set(e.clientX, e.clientY);
          return;
        }

        // Default: Smooth architectural pan across campus floor plate
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
      if (!this.isDragging) {
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
      if (dt <= 50) {
        const instFps = 1000 / Math.max(1, dt);
        this.smoothedFps = this.smoothedFps * 0.85 + Math.min(120, instFps) * 0.15;
      }
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

    // 1. Smooth camera panning and smart zooming
    if (!this.options.reducedMotion) {
      let needsCameraUpdate = false;
      if (this.cameraTarget.distanceTo(this.desiredTarget) > 0.02) {
        this.cameraTarget.lerp(this.desiredTarget, 0.08);
        needsCameraUpdate = true;
      }
      if (Math.abs(this.cameraDistance - this.desiredDistance) > 0.05) {
        this.cameraDistance += (this.desiredDistance - this.cameraDistance) * 0.08;
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
    this.lastFrameDurationMs = Number(Math.max(0.01, stepEndMs - stepStartMs).toFixed(2));
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

    this.stepAnimation(time);

    this.renderer.render(this.scene, this.camera);
    this.animFrameId = requestAnimationFrame(this.animate);
  }

  private disposeHierarchy(obj: THREE.Object3D): void {
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
              m.dispose();
            }
          });
        } else if (
          child.material &&
          !this.furniturePool.ownsMaterial(child.material) &&
          !this.avatarPool.ownsMaterial(child.material)
        ) {
          child.material.dispose();
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
