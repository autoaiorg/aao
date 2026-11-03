import * as THREE from 'three';
import type { AgentIdentity } from '../../../domain/models';
import {
  OFFICE_ROOMS,
  type CameraViewState,
  type OfficeCameraPreset,
  type OfficeRoomConfig,
} from '../types';
import {
  buildDepartmentInteriorLayout,
  planOfficeLifePlacements,
  sampleWaypointRoute,
  stableAgentHash,
  type PlannedAgentPlacement,
  type ProjectedAgentActivity,
} from './officeLifeEngine';

export interface ThreeSceneCallbacks {
  onSelectRoom: (roomId: string) => void;
  onSelectAgent: (agentId: string) => void;
  onHoverObject: (info: { type: 'room' | 'agent'; id: string } | null) => void;
  onCameraChange?: (state: CameraViewState) => void;
}

export interface ThreeSceneOptions {
  reducedMotion?: boolean;
  callbacks: ThreeSceneCallbacks;
  renderer?: THREE.WebGLRenderer;
  rooms?: OfficeRoomConfig[];
  demoFurniture?: boolean;
  activeCoordinationAgentIds?: ReadonlySet<string>;
}

export interface AvatarSemanticParts {
  halo: THREE.Mesh;
  primaryGeometry: THREE.Mesh;
  characterRig: THREE.Group;
  torso?: THREE.Mesh;
  head?: THREE.Mesh;
  visor?: THREE.Mesh;
  leftArm?: THREE.Mesh;
  rightArm?: THREE.Mesh;
  leftLeg?: THREE.Mesh;
  rightLeg?: THREE.Mesh;
  speechBubble?: THREE.Sprite;
  nameLabel: THREE.Sprite;
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
      this.metalLegMat,
      this.chairCushionMat,
      this.keyboardMat,
      this.meetingTableMat,
    ];
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

  // Interaction & Raycasting
  private raycaster = new THREE.Raycaster();
  private mouse = new THREE.Vector2();
  private pointerDownPos = new THREE.Vector2();
  private isDragging = false;

  // Camera Orbit & Smart Zoom parameters
  private cameraAngle = 35; // degrees around Y
  private cameraElevation = 42; // degrees tilt
  private cameraDistance = 24; // distance from target
  private desiredDistance = 24; // smart zoom destination
  private minDistance = 8;
  private maxDistance = 38;
  private cameraTarget = new THREE.Vector3(0, 0, 0);
  private desiredTarget = new THREE.Vector3(0, 0, 0);

  // Groups and Interactive Meshes
  private roomsGroup = new THREE.Group();
  private agentsGroup = new THREE.Group();
  private lightsGroup = new THREE.Group();
  private walkwaysGroup = new THREE.Group();
  private interactiveMeshes: THREE.Object3D[] = [];
  private roomPlatforms: Map<string, THREE.Mesh> = new Map();
  private agentMeshes: Map<string, THREE.Group> = new Map();
  private agentRuntimeStates: Map<string, AgentAnimatedRuntimeState> = new Map();
  private currentAgents: AgentIdentity[] = [];
  private lastStateEvaluationMs = 0;

  private roomSpotlight: THREE.SpotLight | null = null;
  private activeRoomId: string = 'unit-exec';
  private activeAgentId: string | null = null;

  // Selected agent selection ring
  private selectionRing: THREE.Mesh | null = null;
  private groundGroup = new THREE.Group();

  constructor(container: HTMLElement, options: ThreeSceneOptions) {
    this.container = container;
    // Keep direct scene consumers/tests compatible; the LIVE view always passes
    // its persisted room projection explicitly.
    this.options = { ...options, demoFurniture: options.demoFurniture ?? true };
    this.rooms = options.rooms ?? OFFICE_ROOMS;

    // 1. Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a1628);
    this.scene.fog = new THREE.FogExp2(0x0a1628, 0.018);

    // 2. Camera
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;
    this.camera = new THREE.PerspectiveCamera(40, width / height, 0.5, 200);
    this.updateCameraPosition();

    // 3. Renderer (supports injected renderer for testing)
    this.renderer =
      options.renderer ||
      new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setSize(width, height);
    if (!options.renderer) {
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFShadowMap;
    }
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

    // 6. Event Listeners
    this.bindEvents();

    // 7. Render Loop
    this.animate = this.animate.bind(this);
    this.animFrameId = requestAnimationFrame(this.animate);
  }

  private setupLighting(): void {
    const ambient = new THREE.AmbientLight(0x2d3e58, 2.1);
    this.lightsGroup.add(ambient);

    const dirLight = new THREE.DirectionalLight(0xffffff, 2.4);
    dirLight.position.set(18, 32, 16);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    dirLight.shadow.camera.near = 0.5;
    dirLight.shadow.camera.far = 80;
    const d = 16;
    dirLight.shadow.camera.left = -d;
    dirLight.shadow.camera.right = d;
    dirLight.shadow.camera.top = d;
    dirLight.shadow.camera.bottom = -d;
    this.lightsGroup.add(dirLight);

    const fillLight = new THREE.DirectionalLight(0x38bdf8, 1.2);
    fillLight.position.set(-20, 15, -15);
    this.lightsGroup.add(fillLight);

    this.roomSpotlight = new THREE.SpotLight(0x60a5fa, 4, 30, Math.PI / 4, 0.35, 1);
    this.roomSpotlight.position.set(-5, 12, -3.1);
    this.roomSpotlight.castShadow = true;
    this.lightsGroup.add(this.roomSpotlight);
  }

  private buildWorld(): void {
    this.rebuildGround();

    // Central Connecting Atrium Walkway & Hub
    const atriumGeo = new THREE.CylinderGeometry(3.6, 3.6, 0.1, 32);
    const atriumMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.4,
      metalness: 0.5,
    });
    const atrium = new THREE.Mesh(atriumGeo, atriumMat);
    atrium.position.y = 0.05;
    atrium.receiveShadow = true;
    this.scene.add(atrium);

    // Center Logo / Compass Marker
    const compassGeo = new THREE.RingGeometry(1.0, 1.25, 32);
    compassGeo.rotateX(-Math.PI / 2);
    const compassMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide });
    const compass = new THREE.Mesh(compassGeo, compassMat);
    compass.position.y = 0.11;
    this.scene.add(compass);

    // 2. Circulation Walkways connecting central hub to all departments
    this.buildWalkways();

    // 3. Department Pavilions with complete office interior (desks, chairs, monitors, meeting zone)
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
    const halfWidth = Math.max(14, ...this.rooms.map((room) => Math.abs(room.x) + room.width / 2 + 2));
    const halfDepth = Math.max(11, ...this.rooms.map((room) => Math.abs(room.z) + room.depth / 2 + 2));
    const width = halfWidth * 2;
    const depth = halfDepth * 2;
    const ground = new THREE.Mesh(
      new THREE.BoxGeometry(width, 0.4, depth),
      new THREE.MeshStandardMaterial({ color: 0x0d1829, roughness: 0.85, metalness: 0.15 })
    );
    ground.position.y = -0.2;
    ground.receiveShadow = true;
    this.groundGroup.add(ground);

    const gridSize = Math.max(width, depth);
    const grid = new THREE.GridHelper(gridSize, Math.ceil(gridSize), 0x38bdf8, 0x1e3a5f);
    grid.position.y = 0.01;
    this.groundGroup.add(grid);
  }

  private buildWalkways(): void {
    const walkwayMat = new THREE.MeshStandardMaterial({
      color: 0x142238,
      roughness: 0.6,
      metalness: 0.3,
    });

    this.rooms.forEach((room) => {
      const target = new THREE.Vector3(room.x, 0, room.z);
      const distance = target.length();
      const angle = Math.atan2(room.x, room.z);

      const pathGeo = new THREE.BoxGeometry(1.1, 0.06, distance);
      const path = new THREE.Mesh(pathGeo, walkwayMat);
      path.position.set(room.x * 0.5, 0.03, room.z * 0.5);
      path.rotation.y = angle;
      path.receiveShadow = true;
      this.walkwaysGroup.add(path);

      const stripGeo = new THREE.BoxGeometry(0.08, 0.08, distance);
      const stripMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(room.accentColor).multiplyScalar(0.7) });
      const stripLeft = new THREE.Mesh(stripGeo, stripMat);
      stripLeft.position.set(room.x * 0.5 - Math.cos(angle) * 0.55, 0.04, room.z * 0.5 + Math.sin(angle) * 0.55);
      stripLeft.rotation.y = angle;
      this.walkwaysGroup.add(stripLeft);
    });
  }

  private buildRoom(room: OfficeRoomConfig): void {
    const roomGroup = new THREE.Group();
    roomGroup.position.set(room.x, 0, room.z);

    // Platform Slab (Interactive room target)
    const platGeo = new THREE.BoxGeometry(room.width, 0.35, room.depth);
    const platMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(room.color).multiplyScalar(0.7),
      roughness: 0.6,
      metalness: 0.3,
    });
    const platform = new THREE.Mesh(platGeo, platMat);
    platform.position.y = 0.175;
    platform.receiveShadow = true;
    platform.castShadow = true;
    platform.userData = { type: 'room', id: room.id, name: room.name, code: room.code };
    roomGroup.add(platform);

    this.roomPlatforms.set(room.id, platform);
    this.interactiveMeshes.push(platform);

    // Perimeter Accent Border
    const borderGeo = new THREE.BoxGeometry(room.width + 0.1, 0.06, room.depth + 0.1);
    const borderMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(room.accentColor),
    });
    const border = new THREE.Mesh(borderGeo, borderMat);
    border.position.y = 0.38;
    roomGroup.add(border);

    // Interior Carpet Flooring Pad (recognizably an office department floor)
    const carpetGeo = new THREE.BoxGeometry(room.width - 0.35, 0.02, room.depth - 0.35);
    const carpetMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(room.color).multiplyScalar(0.45),
      roughness: 0.9,
      metalness: 0.05,
    });
    const carpet = new THREE.Mesh(carpetGeo, carpetMat);
    carpet.position.y = 0.36;
    carpet.receiveShadow = true;
    roomGroup.add(carpet);

    // Translucent Corner Glass Pillars
    const pillarGeo = new THREE.BoxGeometry(0.18, 1.8, 0.18);
    const pillarMat = new THREE.MeshStandardMaterial({
      color: 0x93c5fd,
      transparent: true,
      opacity: 0.45,
      roughness: 0.1,
      metalness: 0.9,
    });
    const hw = room.width / 2 - 0.15;
    const hd = room.depth / 2 - 0.15;
    const corners = [
      [-hw, -hd],
      [hw, -hd],
      [hw, hd],
      [-hw, hd],
    ];
    corners.forEach(([cx, cz]) => {
      const p = new THREE.Mesh(pillarGeo, pillarMat);
      p.position.set(cx, 1.1, cz);
      p.castShadow = true;
      roomGroup.add(p);
    });

    // Architectural Perimeter Half-Walls & Glass Dividers
    this.buildRoomArchitecture(roomGroup, room);

    // Complete Office Workstations (Desks, Ergonomic Chairs, Monitors, Keyboards) + Meeting Table
    this.buildOfficeWorkstationsAndMeetingZone(roomGroup, room);

    // Department Specific Accent Equipment
    if (this.options.demoFurniture ?? true) {
      this.buildDepartmentAccentEquipment(roomGroup, room);
    }

    // Floating Department Label Sprite
    const labelSprite = this.createDepartmentLabelSprite(room.code, room.name, room.accentColor);
    labelSprite.position.set(0, 2.45, 0);
    roomGroup.add(labelSprite);

    this.roomsGroup.add(roomGroup);
  }

  /**
   * Builds 4 complete workstation islands (desk + ergonomic office chair + dual monitors + keyboard + mouse)
   * and a collaborative meeting table with chairs inside every department room.
   * Uses SharedFurniturePool geometries and materials for scalability.
   */
  private buildOfficeWorkstationsAndMeetingZone(group: THREE.Group, room: OfficeRoomConfig): void {
    const layout = buildDepartmentInteriorLayout(room);
    const screenMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(room.accentColor).multiplyScalar(1.15),
    });
    const chairAccentMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(room.accentColor).multiplyScalar(0.75),
      roughness: 0.5,
      metalness: 0.25,
    });

    for (const slot of layout.workstations) {
      // 1. Office Desk (tabletop + 2 side legs + dual monitors + keyboard + mouse)
      const deskGroup = new THREE.Group();
      deskGroup.position.set(slot.deskLocalX, 0.36, slot.deskLocalZ);

      const top = new THREE.Mesh(this.furniturePool.deskTopGeo, this.furniturePool.deskWoodMat);
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

      // Dual Monitors on stands
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

      // Keyboard & Mouse facing the chair (+Z side of desk)
      const keyboard = new THREE.Mesh(this.furniturePool.keyboardGeo, this.furniturePool.keyboardMat);
      keyboard.position.set(-0.04, 0.48, 0.1);
      deskGroup.add(keyboard);

      const mouse = new THREE.Mesh(this.furniturePool.mouseGeo, this.furniturePool.keyboardMat);
      mouse.position.set(0.2, 0.48, 0.1);
      deskGroup.add(mouse);

      group.add(deskGroup);

      // 2. Ergonomic Office Chair at (slot.chairLocalX, slot.chairLocalZ) facing -Z (toward desk)
      const chairGroup = this.buildErgonomicChair(chairAccentMat);
      chairGroup.position.set(slot.chairLocalX, 0.36, slot.chairLocalZ);
      chairGroup.rotation.y = slot.facingAngle;
      group.add(chairGroup);
    }

    // 3. Collaborative Meeting Table + 2 Facing Chairs in the central front nook
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

    // Backrest on the back of the seat (-Z in local space when rotation.y = Math.PI means +Z in world)
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

  private buildRoomArchitecture(group: THREE.Group, room: OfficeRoomConfig): void {
    const wallMat = new THREE.MeshStandardMaterial({
      color: 0x1b283d,
      roughness: 0.6,
      metalness: 0.3,
    });
    const glassMat = new THREE.MeshStandardMaterial({
      color: 0x60a5fa,
      transparent: true,
      opacity: 0.35,
      roughness: 0.1,
      metalness: 0.9,
    });

    const isTopRow = room.z < 0;
    const backZ = isTopRow ? -room.depth / 2 + 0.12 : room.depth / 2 - 0.12;

    // Back Solid Architectural Wall (low profile)
    const backWallGeo = new THREE.BoxGeometry(room.width - 0.6, 0.95, 0.14);
    const backWall = new THREE.Mesh(backWallGeo, wallMat);
    backWall.position.set(0, 0.82, backZ);
    backWall.castShadow = true;
    backWall.receiveShadow = true;
    group.add(backWall);

    // Wall Presentation Board / Screen on Back Wall
    const boardGeo = new THREE.BoxGeometry(1.5, 0.52, 0.04);
    const boardMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(room.accentColor).multiplyScalar(0.95),
    });
    const board = new THREE.Mesh(boardGeo, boardMat);
    board.position.set(0, 1.05, backZ + (isTopRow ? 0.09 : -0.09));
    group.add(board);

    // Translucent Glass Acoustic Partitions on Sides
    const sideGlassGeo = new THREE.BoxGeometry(0.08, 0.85, room.depth * 0.55);
    const sideGlassLeft = new THREE.Mesh(sideGlassGeo, glassMat);
    sideGlassLeft.position.set(-room.width / 2 + 0.14, 0.78, 0);
    group.add(sideGlassLeft);

    const sideGlassRight = new THREE.Mesh(sideGlassGeo, glassMat);
    sideGlassRight.position.set(room.width / 2 - 0.14, 0.78, 0);
    group.add(sideGlassRight);
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

  private createDepartmentLabelSprite(code: string, name: string, accentColor: string): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 96;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = 'rgba(10, 22, 40, 0.9)';
      ctx.strokeStyle = accentColor;
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.roundRect(6, 6, 244, 84, 16);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = 'bold 34px sans-serif';
      ctx.fillStyle = accentColor;
      ctx.fillText(code, 128, 44);

      ctx.font = '500 19px sans-serif';
      ctx.fillStyle = '#ffffff';
      ctx.fillText(name.slice(0, 18), 128, 72);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(3.0, 1.1, 1);
    return sprite;
  }

  public updateAgents(agents: AgentIdentity[], nowMs = Date.now()): void {
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
      agentGroup.position.set(startX, 0.35, startZ);
      agentGroup.userData = {
        ...agentGroup.userData,
        type: 'agent',
        id: agent.id,
        unitId: agent.unitId,
        name: agent.name,
        agentType: agent.type,
        activity: placement.activity,
        workstationSlotIndex: placement.workstationSlot.slotIndex,
      };

      const parts = agentGroup.userData.parts as AvatarSemanticParts | undefined;
      if (parts?.characterRig) {
        parts.characterRig.rotation.y = startAngle;
      }

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

    // Update selection ring if active agent exists
    if (this.activeAgentId) {
      this.selectAgent(this.activeAgentId);
    }
  }

  /**
   * Re-evaluates operational evidence and lease expiration at a decoupled interval
   * without recreating meshes, allowing smooth transitions when leases expire or states change.
   */
  public refreshAgentActivities(nowMs = Date.now()): void {
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

  private buildAgentAvatar(agent: AgentIdentity, activity: ProjectedAgentActivity): THREE.Group {
    const group = new THREE.Group();

    const isStanding = agent.type === 'STANDING';
    const isEphemeral = agent.type === 'EPHEMERAL';
    const bodyColor = isStanding ? 0x2563eb : isEphemeral ? 0x0891b2 : 0x64748b;

    let haloColor = 0x64748b; // UNKNOWN
    if (agent.heartbeatStatus === 'HEALTHY') haloColor = 0x22c55e;
    else if (agent.heartbeatStatus === 'STALE') haloColor = 0xeab308;
    else if (agent.heartbeatStatus === 'UNAVAILABLE') haloColor = 0xef4444;

    // children[0]: Base Telemetry Halo Ring
    const haloGeo = new THREE.RingGeometry(0.24, 0.36, 16);
    haloGeo.rotateX(-Math.PI / 2);
    const haloMat = new THREE.MeshBasicMaterial({
      color: haloColor,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
    });
    const halo = new THREE.Mesh(haloGeo, haloMat);
    halo.position.y = 0.02;
    group.add(halo);

    // children[1]: Primary Type Geometry (Preserves exact Defect 2 test contract!)
    let primaryGeometry: THREE.Mesh;
    if (isStanding) {
      const pedGeo = new THREE.CylinderGeometry(0.22, 0.26, 0.12, 16);
      const pedMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5 });
      primaryGeometry = new THREE.Mesh(pedGeo, pedMat);
      primaryGeometry.position.y = 0.06;
      group.add(primaryGeometry);
    } else if (isEphemeral) {
      const crystalGeo = new THREE.OctahedronGeometry(0.28, 0);
      const crystalMat = new THREE.MeshStandardMaterial({
        color: bodyColor,
        roughness: 0.1,
        metalness: 0.8,
        transparent: true,
        opacity: 0.88,
      });
      primaryGeometry = new THREE.Mesh(crystalGeo, crystalMat);
      primaryGeometry.position.y = 0.58;
      primaryGeometry.castShadow = true;
      group.add(primaryGeometry);
    } else {
      const unknownGeo = new THREE.BoxGeometry(0.32, 0.55, 0.32);
      const unknownMat = new THREE.MeshStandardMaterial({
        color: 0x64748b,
        roughness: 0.5,
        metalness: 0.2,
      });
      primaryGeometry = new THREE.Mesh(unknownGeo, unknownMat);
      primaryGeometry.position.y = 0.38;
      primaryGeometry.castShadow = true;
      group.add(primaryGeometry);
    }

    // children[2]: Articulated Character Rig (Torso, Head, Visor, Arms, Legs)
    const characterRig = new THREE.Group();
    const limbMat = new THREE.MeshStandardMaterial({
      color: bodyColor,
      roughness: 0.38,
      metalness: 0.3,
    });
    const headMat = new THREE.MeshStandardMaterial({
      color: 0xf1f5f9,
      roughness: 0.2,
      metalness: 0.5,
    });
    const visorMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });

    // Torso
    const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.18, 0.44, 14), limbMat);
    torso.position.y = 0.48;
    torso.castShadow = true;
    characterRig.add(torso);

    // Head + Directional Visor
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.14, 14, 14), headMat);
    head.position.y = 0.82;
    head.castShadow = true;
    characterRig.add(head);

    const visor = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.05, 0.06), visorMat);
    visor.position.set(0, 0.83, 0.12);
    characterRig.add(visor);

    // Articulated Left & Right Arms (for typing & conversation gestures)
    const armGeo = new THREE.BoxGeometry(0.07, 0.3, 0.07);
    const leftArm = new THREE.Mesh(armGeo, limbMat);
    leftArm.position.set(-0.21, 0.46, 0.06);
    characterRig.add(leftArm);

    const rightArm = new THREE.Mesh(armGeo, limbMat);
    rightArm.position.set(0.21, 0.46, 0.06);
    characterRig.add(rightArm);

    // Articulated Left & Right Legs (for seated chair posture & corridor walking)
    const legGeo = new THREE.BoxGeometry(0.08, 0.26, 0.08);
    const leftLeg = new THREE.Mesh(legGeo, limbMat);
    leftLeg.position.set(-0.08, 0.18, 0);
    characterRig.add(leftLeg);

    const rightLeg = new THREE.Mesh(legGeo, limbMat);
    rightLeg.position.set(0.08, 0.18, 0);
    characterRig.add(rightLeg);

    group.add(characterRig);

    // children[3]: Speech / Conversation Bubble Sprite (visible when CONVERSING)
    const speechBubble = this.createSpeechBubbleSprite();
    speechBubble.position.set(0, 1.56, 0);
    speechBubble.visible = activity.kind === 'CONVERSING';
    group.add(speechBubble);

    // children[4]: Name & Activity Badge Sprite
    const nameLabel = this.createAgentNameSprite(
      agent.name.split(' ')[0],
      activity.shortBadge,
      haloColor
    );
    nameLabel.position.set(0, 1.24, 0);
    group.add(nameLabel);

    const semanticParts: AvatarSemanticParts = {
      halo,
      primaryGeometry,
      characterRig,
      torso,
      head,
      visor,
      leftArm,
      rightArm,
      leftLeg,
      rightLeg,
      speechBubble,
      nameLabel,
    };
    group.userData.parts = semanticParts;

    return group;
  }

  private createSpeechBubbleSprite(): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 96;
    canvas.height = 48;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = 'rgba(15, 23, 42, 0.94)';
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.roundRect(6, 4, 84, 36, 12);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = 'bold 20px sans-serif';
      ctx.fillStyle = '#f8fafc';
      ctx.fillText('💬 ...', 48, 28);
    }
    const texture = new THREE.CanvasTexture(canvas);
    const mat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
    const sprite = new THREE.Sprite(mat);
    sprite.scale.set(0.85, 0.42, 1);
    return sprite;
  }

  private createAgentNameSprite(
    shortName: string,
    activityBadge: string,
    borderColor: number
  ): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 192;
    canvas.height = 60;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      const hex = '#' + borderColor.toString(16).padStart(6, '0');
      ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
      ctx.strokeStyle = hex;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.roundRect(4, 4, 184, 52, 10);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = 'bold 18px sans-serif';
      ctx.fillStyle = '#ffffff';
      ctx.fillText(shortName.slice(0, 11), 96, 25);

      ctx.font = '600 13px sans-serif';
      ctx.fillStyle = '#7dd3fc';
      ctx.fillText(activityBadge.slice(0, 16), 96, 45);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(1.55, 0.48, 1);
    return sprite;
  }

  public selectRoom(roomId: string, animate = true): void {
    this.activeRoomId = roomId;
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
  }

  public selectAgent(agentId: string | null): void {
    this.activeAgentId = agentId;
    if (!this.selectionRing) return;

    if (!agentId) {
      this.selectionRing.visible = false;
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
  }

  public rotateCamera(deltaAngleDegrees: number): void {
    this.cameraAngle = (this.cameraAngle + deltaAngleDegrees) % 360;
    this.updateCameraPosition();
  }

  public zoomCamera(deltaFactor: number): void {
    this.desiredDistance = Math.max(this.minDistance, Math.min(this.maxDistance, this.desiredDistance * deltaFactor));
    if (this.options.reducedMotion) {
      this.cameraDistance = this.desiredDistance;
      this.updateCameraPosition();
    }
  }

  public resetCamera(): void {
    this.cameraAngle = 35;
    this.cameraElevation = 42;
    this.desiredDistance = 24;
    this.desiredTarget.set(0, 0, 0);

    if (this.options.reducedMotion) {
      this.cameraTarget.set(0, 0, 0);
      this.cameraDistance = 24;
      this.updateCameraPosition();
    }
  }

  public setCameraPreset(preset: OfficeCameraPreset): void {
    if (preset === 'overview') {
      this.resetCamera();
      return;
    }
    if (preset === 'isometric') {
      this.cameraAngle = 45;
      this.cameraElevation = 40;
      this.desiredDistance = 20;
      this.desiredTarget.set(0, 0, 0);
    } else if (preset === 'top-down') {
      this.cameraAngle = 0;
      this.cameraElevation = 78;
      this.desiredDistance = 25;
      this.desiredTarget.set(0, 0, 0);
    } else if (preset === 'agent-focus') {
      this.cameraElevation = 34;
      if (this.activeAgentId) {
        const agentGroup = this.agentMeshes.get(this.activeAgentId);
        if (agentGroup) {
          this.desiredTarget.set(agentGroup.position.x, 0, agentGroup.position.z);
          this.desiredDistance = 10;
        }
      } else {
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
  }

  public getCameraState(): CameraViewState {
    return {
      angle: this.cameraAngle,
      elevation: this.cameraElevation,
      distance: this.cameraDistance,
      targetX: this.cameraTarget.x,
      targetZ: this.cameraTarget.z,
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
    dom.addEventListener('wheel', this.handleWheel, { passive: false });
    dom.addEventListener('webglcontextlost', this.handleContextLost as EventListener);
    dom.addEventListener('webglcontextrestored', this.handleContextRestored as EventListener);
  }

  private handleContextLost = (e: Event): void => {
    e.preventDefault();
    this.contextLost = true;
  };

  private handleContextRestored = (): void => {
    this.contextLost = false;
    this.updateCameraPosition();
    this.renderer.render(this.scene, this.camera);
  };

  private handlePointerDown = (e: PointerEvent): void => {
    this.pointerDownPos.set(e.clientX, e.clientY);
    this.isDragging = false;
    this.renderer.domElement.setPointerCapture(e.pointerId);
  };

  private handlePointerMove = (e: PointerEvent): void => {
    const deltaX = e.clientX - this.pointerDownPos.x;
    const deltaY = e.clientY - this.pointerDownPos.y;

    if (e.buttons === 1) {
      if (Math.abs(deltaX) > 4 || Math.abs(deltaY) > 4) {
        this.isDragging = true;
      }
      if (this.isDragging) {
        this.cameraAngle = (this.cameraAngle - deltaX * 0.3) % 360;
        this.cameraElevation = Math.max(15, Math.min(80, this.cameraElevation + deltaY * 0.25));
        this.pointerDownPos.set(e.clientX, e.clientY);
        this.updateCameraPosition();
        return;
      }
    }

    if (!this.isDragging) {
      const rect = this.renderer.domElement.getBoundingClientRect();
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
  };

  private handlePointerUp = (e: PointerEvent): void => {
    this.renderer.domElement.releasePointerCapture(e.pointerId);

    if (!this.isDragging) {
      const rect = this.renderer.domElement.getBoundingClientRect();
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

    this.isDragging = false;
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

    // Decoupled state evaluation every 2000ms (separates state frequency from render frame frequency)
    if (time - this.lastStateEvaluationMs >= 2000 && this.currentAgents.length > 0) {
      this.lastStateEvaluationMs = time;
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
      }
    }

    // 2. Agent Animations (Preserving Defect 2 contract on children[1] + Articulating characterRig)
    if (!this.options.reducedMotion) {
      const t = time * 0.002;

      this.agentMeshes.forEach((group, agentId) => {
        const parts = group.userData?.parts as AvatarSemanticParts | undefined;
        const runtime = this.agentRuntimeStates.get(agentId);

        // Enforce Defect 2 invariant: ONLY EPHEMERAL primaryGeometry (children[1]) animates directly,
        // NEVER STANDING primaryGeometry (children[1] remains at y = 0.06, rotation.y = 0)
        if (group.userData?.agentType === 'EPHEMERAL' && parts?.primaryGeometry) {
          parts.primaryGeometry.position.y = 0.58 + Math.sin(t + group.position.x) * 0.04;
          parts.primaryGeometry.rotation.y = t * 0.5;
        }

        if (!parts?.characterRig || !runtime) return;

        const { placement } = runtime;
        const kind = placement.activity.kind;
        const phase = (stableAgentHash(agentId) % 100) * 0.1;

        // Compute target coordinates (waypoint route when WALKING, workstation/meeting spot otherwise)
        let destX = placement.targetWorldX;
        let destZ = placement.targetWorldZ;
        let destAngle = placement.targetFacingAngle;

        if (kind === 'WALKING') {
          const sampled = sampleWaypointRoute(
            placement.waypoints,
            time,
            stableAgentHash(agentId) % 7
          );
          destX = sampled.x;
          destZ = sampled.z;
          destAngle = sampled.facingAngle;
        }

        // Smooth position & orientation interpolation (prevents abrupt visual jumps on state transitions)
        runtime.currentX += (destX - runtime.currentX) * 0.12;
        runtime.currentZ += (destZ - runtime.currentZ) * 0.12;
        runtime.currentAngle += (destAngle - runtime.currentAngle) * 0.15;

        group.position.x = runtime.currentX;
        group.position.z = runtime.currentZ;
        parts.characterRig.rotation.y = runtime.currentAngle;

        // Articulated limb kinematics by activity kind
        if (kind === 'TYPING_DEV' || kind === 'TYPING_AUDIT' || kind === 'TYPING_DOCS') {
          // Seated in chair facing desk monitors, typing with both arms
          parts.characterRig.position.y = -0.06;
          if (parts.leftLeg) parts.leftLeg.rotation.x = -Math.PI / 2.5;
          if (parts.rightLeg) parts.rightLeg.rotation.x = -Math.PI / 2.5;
          if (parts.leftArm) {
            parts.leftArm.rotation.x = -0.85 + Math.sin(time * 0.022 + phase) * 0.22;
          }
          if (parts.rightArm) {
            parts.rightArm.rotation.x = -0.85 + Math.cos(time * 0.022 + phase) * 0.22;
          }
          if (parts.head) {
            parts.head.rotation.y = Math.sin(time * 0.004 + phase) * 0.1;
          }
          if (parts.speechBubble) parts.speechBubble.visible = false;
        } else if (kind === 'CONVERSING') {
          // Standing facing conversation partner with expressive arm gestures & speech bubble
          parts.characterRig.position.y = 0;
          if (parts.leftLeg) parts.leftLeg.rotation.x = 0;
          if (parts.rightLeg) parts.rightLeg.rotation.x = 0;
          if (parts.leftArm) {
            parts.leftArm.rotation.x = -0.45 + Math.sin(time * 0.008 + phase) * 0.25;
          }
          if (parts.rightArm) {
            parts.rightArm.rotation.x = -0.35 + Math.cos(time * 0.007 + phase) * 0.22;
          }
          if (parts.head) {
            parts.head.rotation.y = Math.sin(time * 0.005 + phase) * 0.08;
          }
          if (parts.speechBubble) {
            parts.speechBubble.visible = true;
            parts.speechBubble.position.y = 1.56 + Math.sin(time * 0.006 + phase) * 0.04;
          }
        } else if (kind === 'WALKING') {
          // Walking along corridor waypoints with natural stride
          parts.characterRig.position.y = Math.abs(Math.sin(time * 0.01 + phase)) * 0.03;
          const stride = Math.sin(time * 0.01 + phase);
          if (parts.leftLeg) parts.leftLeg.rotation.x = stride * 0.45;
          if (parts.rightLeg) parts.rightLeg.rotation.x = -stride * 0.45;
          if (parts.leftArm) parts.leftArm.rotation.x = -stride * 0.32;
          if (parts.rightArm) parts.rightArm.rotation.x = stride * 0.32;
          if (parts.head) parts.head.rotation.y = 0;
          if (parts.speechBubble) parts.speechBubble.visible = false;
        } else if (kind === 'IDLE_DESK') {
          // Seated calmly in workstation chair without typing
          parts.characterRig.position.y = -0.06;
          if (parts.leftLeg) parts.leftLeg.rotation.x = -Math.PI / 2.5;
          if (parts.rightLeg) parts.rightLeg.rotation.x = -Math.PI / 2.5;
          if (parts.leftArm) parts.leftArm.rotation.x = -0.3;
          if (parts.rightArm) parts.rightArm.rotation.x = -0.3;
          if (parts.head) parts.head.rotation.y = 0;
          if (parts.speechBubble) parts.speechBubble.visible = false;
        } else {
          // DISCONNECTED or UNKNOWN_NEUTRAL: completely neutral stationary pose
          parts.characterRig.position.y = 0;
          if (parts.leftLeg) parts.leftLeg.rotation.x = 0;
          if (parts.rightLeg) parts.rightLeg.rotation.x = 0;
          if (parts.leftArm) parts.leftArm.rotation.x = 0;
          if (parts.rightArm) parts.rightArm.rotation.x = 0;
          if (parts.head) parts.head.rotation.y = 0;
          if (parts.speechBubble) parts.speechBubble.visible = false;
        }
      });

      // Keep selection ring synced with active agent position
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
        if (child.geometry && !this.furniturePool.ownsGeometry(child.geometry)) {
          child.geometry.dispose();
        }
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => {
            if (!this.furniturePool.ownsMaterial(m)) m.dispose();
          });
        } else if (child.material && !this.furniturePool.ownsMaterial(child.material)) {
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
      dom.removeEventListener('wheel', this.handleWheel);
      dom.removeEventListener('webglcontextlost', this.handleContextLost as EventListener);
      dom.removeEventListener('webglcontextrestored', this.handleContextRestored as EventListener);
    }

    this.disposeHierarchy(this.scene);
    this.furniturePool.dispose();
    if (this.renderer && typeof this.renderer.dispose === 'function') {
      this.renderer.dispose();
    }
    if (dom && typeof dom.remove === 'function') {
      dom.remove();
    }
  }
}
