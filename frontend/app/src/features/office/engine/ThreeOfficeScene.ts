import * as THREE from 'three';
import type { AgentIdentity } from '../../../domain/models';
import { OFFICE_ROOMS, type OfficeRoomConfig } from '../types';

export interface ThreeSceneCallbacks {
  onSelectRoom: (roomId: string) => void;
  onSelectAgent: (agentId: string) => void;
  onHoverObject: (info: { type: 'room' | 'agent'; id: string } | null) => void;
}

export interface ThreeSceneOptions {
  reducedMotion?: boolean;
  callbacks: ThreeSceneCallbacks;
  renderer?: THREE.WebGLRenderer;
  rooms?: OfficeRoomConfig[];
  demoFurniture?: boolean;
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
    // Ambient light for base illumination
    const ambient = new THREE.AmbientLight(0x2d3e58, 2.0);
    this.lightsGroup.add(ambient);

    // Main Sun Key Light
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

    // Fill Light for deep cyber/corporate ambiance
    const fillLight = new THREE.DirectionalLight(0x38bdf8, 1.2);
    fillLight.position.set(-20, 15, -15);
    this.lightsGroup.add(fillLight);

    // Dynamic Spotlight focused on active department
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

    // 2. Circulation Walkways connecting central hub to all 6 departments
    this.buildWalkways();

    // 3. Department Pavilions with interior architecture
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
      // Vector from (0, 0, 0) to (room.x, 0, room.z)
      const target = new THREE.Vector3(room.x, 0, room.z);
      const distance = target.length();
      const angle = Math.atan2(room.x, room.z);

      const pathGeo = new THREE.BoxGeometry(1.1, 0.06, distance);
      const path = new THREE.Mesh(pathGeo, walkwayMat);
      path.position.set(room.x * 0.5, 0.03, room.z * 0.5);
      path.rotation.y = angle;
      path.receiveShadow = true;
      this.walkwaysGroup.add(path);

      // Light strip guide along walkway
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

    // Platform Slab
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

    // Translucent Corner Glass Pillars
    const pillarGeo = new THREE.BoxGeometry(0.2, 1.8, 0.2);
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

    // Architectural Perimeter Half-Walls & Dividers (Recognizable Office Structure)
    this.buildRoomArchitecture(roomGroup, room);

    // Department Specific Furniture & Interior Layout
    if (this.options.demoFurniture ?? true) {
      this.buildDepartmentFurniture(roomGroup, room);
    } else {
      this.buildGenericFurniture(roomGroup, room);
    }

    // Floating Department Label Sprite
    const labelSprite = this.createDepartmentLabelSprite(room.code, room.name, room.accentColor);
    labelSprite.position.set(0, 2.4, 0);
    roomGroup.add(labelSprite);

    this.roomsGroup.add(roomGroup);
  }

  private buildGenericFurniture(group: THREE.Group, room: OfficeRoomConfig): void {
    const desk = new THREE.Mesh(
      new THREE.BoxGeometry(Math.min(1.8, room.width * 0.55), 0.45, Math.min(0.6, room.depth * 0.25)),
      new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5, metalness: 0.25 })
    );
    desk.position.set(0, 0.58, 0);
    desk.castShadow = true;
    group.add(desk);
    const display = new THREE.Mesh(
      new THREE.BoxGeometry(0.55, 0.34, 0.04),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(room.accentColor).multiplyScalar(1.1) })
    );
    display.position.set(0, 1.02, -0.14);
    group.add(display);
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
    const backWallGeo = new THREE.BoxGeometry(room.width - 0.6, 0.85, 0.14);
    const backWall = new THREE.Mesh(backWallGeo, wallMat);
    backWall.position.set(0, 0.77, backZ);
    backWall.castShadow = true;
    backWall.receiveShadow = true;
    group.add(backWall);

    // Translucent Glass Acoustic Partition on Side
    const sideGlassGeo = new THREE.BoxGeometry(0.1, 0.8, room.depth * 0.45);
    const sideGlass = new THREE.Mesh(sideGlassGeo, glassMat);
    sideGlass.position.set(-room.width / 2 + 0.15, 0.75, 0);
    group.add(sideGlass);
  }

  private buildDepartmentFurniture(group: THREE.Group, room: OfficeRoomConfig): void {
    const deskMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.4, metalness: 0.5 });
    const screenMat = new THREE.MeshBasicMaterial({ color: new THREE.Color(room.accentColor).multiplyScalar(1.2) });
    const chairMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.6 });

    switch (room.id) {
      case 'unit-exec': {
        // EXEC: Executive Oval Boardroom Table + Directive Presentation Screen
        const tableGeo = new THREE.CylinderGeometry(0.85, 0.95, 0.45, 24);
        const table = new THREE.Mesh(tableGeo, deskMat);
        table.position.set(0, 0.58, 0);
        table.castShadow = true;
        group.add(table);

        // Directive screen on back wall
        const screenGeo = new THREE.BoxGeometry(1.6, 0.6, 0.05);
        const screen = new THREE.Mesh(screenGeo, screenMat);
        screen.position.set(0, 1.25, -room.depth / 2 + 0.2);
        group.add(screen);

        // 2 Executive Chairs
        const chairGeo = new THREE.BoxGeometry(0.35, 0.45, 0.35);
        const chair1 = new THREE.Mesh(chairGeo, chairMat);
        chair1.position.set(-0.7, 0.55, 0);
        group.add(chair1);
        const chair2 = new THREE.Mesh(chairGeo, chairMat);
        chair2.position.set(0.7, 0.55, 0);
        group.add(chair2);
        break;
      }

      case 'unit-gov': {
        // GOV: Constitutional Rostrum Podium + Policy Desks
        const podiumGeo = new THREE.BoxGeometry(0.7, 0.85, 0.5);
        const podium = new THREE.Mesh(podiumGeo, deskMat);
        podium.position.set(0, 0.75, -0.6);
        podium.castShadow = true;
        group.add(podium);

        // Constitutional Ledger / Screen
        const ledgerGeo = new THREE.BoxGeometry(0.45, 0.08, 0.35);
        const ledger = new THREE.Mesh(ledgerGeo, screenMat);
        ledger.position.set(0, 1.2, -0.6);
        ledger.rotation.x = -0.3;
        group.add(ledger);

        // Lateral Deliberation Desk
        const deskGeo = new THREE.BoxGeometry(1.4, 0.45, 0.5);
        const desk = new THREE.Mesh(deskGeo, deskMat);
        desk.position.set(0, 0.58, 0.5);
        group.add(desk);
        break;
      }

      case 'unit-audit': {
        // AUDIT: Forensic Analysis Desk + Dual Security Scanners
        const deskGeo = new THREE.BoxGeometry(1.8, 0.45, 0.6);
        const desk = new THREE.Mesh(deskGeo, deskMat);
        desk.position.set(0, 0.58, 0);
        desk.castShadow = true;
        group.add(desk);

        // Security Scanner Screens (Teal Glow)
        const sGeo = new THREE.BoxGeometry(0.55, 0.35, 0.05);
        const sc1 = new THREE.Mesh(sGeo, screenMat);
        sc1.position.set(-0.45, 0.95, 0.05);
        sc1.rotation.y = 0.2;
        group.add(sc1);
        const sc2 = new THREE.Mesh(sGeo, screenMat);
        sc2.position.set(0.45, 0.95, 0.05);
        sc2.rotation.y = -0.2;
        group.add(sc2);
        break;
      }

      case 'unit-arch': {
        // ARCH: Blueprint Drafting Table with Holographic Grid
        const tableGeo = new THREE.BoxGeometry(1.6, 0.5, 1.0);
        const table = new THREE.Mesh(tableGeo, deskMat);
        table.position.set(0, 0.6, 0);
        table.castShadow = true;
        group.add(table);

        // Holographic Blueprint Plane
        const bpGeo = new THREE.PlaneGeometry(1.3, 0.75);
        bpGeo.rotateX(-Math.PI / 2);
        const bpMat = new THREE.MeshBasicMaterial({
          color: 0xf59e0b,
          wireframe: true,
        });
        const bp = new THREE.Mesh(bpGeo, bpMat);
        bp.position.set(0, 0.86, 0);
        group.add(bp);
        break;
      }

      case 'unit-eng': {
        // ENG: Developer Workstations in Battery + Dual Code Monitors
        const deskGeo = new THREE.BoxGeometry(1.8, 0.45, 0.6);
        const desk = new THREE.Mesh(deskGeo, deskMat);
        desk.position.set(0, 0.58, -0.2);
        desk.castShadow = true;
        group.add(desk);

        // Developer Dual Monitors
        const monGeo = new THREE.BoxGeometry(0.5, 0.3, 0.04);
        const mon1 = new THREE.Mesh(monGeo, screenMat);
        mon1.position.set(-0.4, 0.92, -0.2);
        group.add(mon1);
        const mon2 = new THREE.Mesh(monGeo, screenMat);
        mon2.position.set(0.4, 0.92, -0.2);
        group.add(mon2);
        break;
      }

      case 'unit-ops': {
        // OPS: Curved Mission Control Console + Large Telemetry Video Wall
        const consoleGeo = new THREE.CylinderGeometry(1.0, 1.1, 0.45, 16, 1, false, 0, Math.PI);
        const consoleMesh = new THREE.Mesh(consoleGeo, deskMat);
        consoleMesh.position.set(0, 0.58, 0.2);
        consoleMesh.rotation.y = Math.PI;
        group.add(consoleMesh);

        // Large Telemetry Video Wall
        const wallGeo = new THREE.BoxGeometry(2.0, 0.8, 0.08);
        const wallScreen = new THREE.Mesh(wallGeo, screenMat);
        wallScreen.position.set(0, 1.25, room.depth / 2 - 0.2);
        group.add(wallScreen);

        // Server Node Towers
        const towerGeo = new THREE.BoxGeometry(0.35, 1.1, 0.35);
        const towerMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.3 });
        const tower1 = new THREE.Mesh(towerGeo, towerMat);
        tower1.position.set(-1.4, 0.9, 0.8);
        group.add(tower1);
        break;
      }

      default: {
        const dGeo = new THREE.CylinderGeometry(0.8, 0.9, 0.45, 16);
        const d = new THREE.Mesh(dGeo, deskMat);
        d.position.set(0, 0.58, 0);
        group.add(d);
      }
    }
  }

  private createDepartmentLabelSprite(code: string, name: string, accentColor: string): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 96;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      // Rounded background badge
      ctx.fillStyle = 'rgba(10, 22, 40, 0.9)';
      ctx.strokeStyle = accentColor;
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.roundRect(6, 6, 244, 84, 16);
      ctx.fill();
      ctx.stroke();

      // Department Code
      ctx.textAlign = 'center';
      ctx.font = 'bold 34px sans-serif';
      ctx.fillStyle = accentColor;
      ctx.fillText(code, 128, 44);

      // Department Short Name
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

  public updateAgents(agents: AgentIdentity[]): void {
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

    // Group agents by room
    const byRoom: Map<string, AgentIdentity[]> = new Map();
    agents.forEach((agent) => {
      const list = byRoom.get(agent.unitId) || [];
      list.push(agent);
      byRoom.set(agent.unitId, list);
    });

    // Populate each room
    this.rooms.forEach((room) => {
      const roomAgents = byRoom.get(room.id) || [];
      const count = roomAgents.length;
      if (count === 0) return;

      // Smart placement supporting up to 100 agents gracefully
      roomAgents.forEach((agent, index) => {
        let localX = 0;
        let localZ = 0;

        if (count === 1) {
          localX = 0;
          localZ = 0.9;
        } else if (count <= 4) {
          // Quadrant workstation placement
          const offsets = [
            [-0.9, 0.8],
            [0.9, 0.8],
            [-0.9, -0.8],
            [0.9, -0.8],
          ];
          localX = offsets[index][0];
          localZ = offsets[index][1];
        } else {
          // Concentric circular distribution
          const ring = Math.floor(index / 8);
          const ringRadius = 0.85 + ring * 0.55;
          const indexInRing = index % 8;
          const ringCount = Math.min(8, count - ring * 8);
          const angle = (indexInRing / ringCount) * Math.PI * 2;
          localX = Math.cos(angle) * ringRadius;
          localZ = Math.sin(angle) * ringRadius;
        }

        const posX = room.x + localX;
        const posZ = room.z + localZ;

        const agentGroup = this.buildAgentAvatar(agent);
        agentGroup.position.set(posX, 0.35, posZ);
        agentGroup.userData = {
          type: 'agent',
          id: agent.id,
          unitId: agent.unitId,
          name: agent.name,
          agentType: agent.type,
        };

        this.agentsGroup.add(agentGroup);
        this.agentMeshes.set(agent.id, agentGroup);

        // Add root parts to interactive raycast meshes
        agentGroup.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.userData = agentGroup.userData;
            this.interactiveMeshes.push(child);
          }
        });
      });
    });

    // Populate unassigned / unknown agents in central atrium plaza
    const unassignedAgents = agents.filter(
      (a) =>
        a.unitId === 'unit-unassigned' ||
        a.unitId === 'unit-unknown' ||
        !this.rooms.some((r) => r.id === a.unitId)
    );
    if (unassignedAgents.length > 0) {
      unassignedAgents.forEach((agent, index) => {
        const ring = Math.floor(index / 8);
        const ringRadius = 1.0 + ring * 0.6;
        const indexInRing = index % 8;
        const ringCount = Math.min(8, unassignedAgents.length - ring * 8);
        const angle = (indexInRing / ringCount) * Math.PI * 2;
        const posX = Math.cos(angle) * ringRadius;
        const posZ = Math.sin(angle) * ringRadius;

        const agentGroup = this.buildAgentAvatar(agent);
        agentGroup.position.set(posX, 0.35, posZ);
        agentGroup.userData = {
          type: 'agent',
          id: agent.id,
          unitId: agent.unitId,
          name: agent.name,
          agentType: agent.type,
        };

        this.agentsGroup.add(agentGroup);
        this.agentMeshes.set(agent.id, agentGroup);

        agentGroup.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.userData = agentGroup.userData;
            this.interactiveMeshes.push(child);
          }
        });
      });
    }

    // Update selection ring if active agent exists
    if (this.activeAgentId) {
      this.selectAgent(this.activeAgentId);
    }
  }

  public getInteractiveMeshesCount(): number {
    return this.interactiveMeshes.length;
  }

  public getAgentMeshGroup(agentId: string): THREE.Group | undefined {
    return this.agentMeshes.get(agentId);
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

  private buildAgentAvatar(agent: AgentIdentity): THREE.Group {
    const group = new THREE.Group();

    // Color based on agent type and telemetry
    const isStanding = agent.type === 'STANDING';
    const isEphemeral = agent.type === 'EPHEMERAL';
    const bodyColor = isStanding ? 0x2563eb : isEphemeral ? 0x0891b2 : 0x64748b;

    // Telemetry aura color
    let haloColor = 0x64748b; // UNKNOWN
    if (agent.heartbeatStatus === 'HEALTHY') haloColor = 0x22c55e;
    else if (agent.heartbeatStatus === 'STALE') haloColor = 0xeab308;
    else if (agent.heartbeatStatus === 'UNAVAILABLE') haloColor = 0xef4444;

    // 1. Base Telemetry Halo Ring
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

    if (isStanding) {
      // Standing Agent Avatar: Sturdy geometric humanoid torso + head + desk pedestal
      // Pedestal
      const pedGeo = new THREE.CylinderGeometry(0.22, 0.26, 0.12, 16);
      const pedMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5 });
      const ped = new THREE.Mesh(pedGeo, pedMat);
      ped.position.y = 0.06;
      group.add(ped);

      // Torso / Body
      const bodyGeo = new THREE.CylinderGeometry(0.18, 0.22, 0.65, 16);
      const bodyMat = new THREE.MeshStandardMaterial({
        color: bodyColor,
        roughness: 0.4,
        metalness: 0.3,
      });
      const body = new THREE.Mesh(bodyGeo, bodyMat);
      body.position.y = 0.44;
      body.castShadow = true;
      group.add(body);

      // Head Sphere
      const headGeo = new THREE.SphereGeometry(0.16, 16, 16);
      const headMat = new THREE.MeshStandardMaterial({
        color: 0xf1f5f9,
        roughness: 0.2,
        metalness: 0.5,
      });
      const head = new THREE.Mesh(headGeo, headMat);
      head.position.y = 0.86;
      head.castShadow = true;
      group.add(head);
    } else if (isEphemeral) {
      // Ephemeral Agent Avatar: Floating Crystal / Octahedron with ethereal transparency
      const crystalGeo = new THREE.OctahedronGeometry(0.28, 0);
      const crystalMat = new THREE.MeshStandardMaterial({
        color: bodyColor,
        roughness: 0.1,
        metalness: 0.8,
        transparent: true,
        opacity: 0.88,
      });
      const crystal = new THREE.Mesh(crystalGeo, crystalMat);
      crystal.position.y = 0.58;
      crystal.castShadow = true;
      group.add(crystal);

      // Floating Crown Ring
      const crownGeo = new THREE.RingGeometry(0.18, 0.24, 16);
      crownGeo.rotateX(-Math.PI / 2);
      const crownMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide });
      const crown = new THREE.Mesh(crownGeo, crownMat);
      crown.position.y = 0.95;
      group.add(crown);
    } else {
      // Unknown Agent Type: Neutral geometric prism (no synthetic pedestal, no crystal)
      const unknownGeo = new THREE.BoxGeometry(0.32, 0.55, 0.32);
      const unknownMat = new THREE.MeshStandardMaterial({
        color: 0x64748b,
        roughness: 0.5,
        metalness: 0.2,
      });
      const unknownMesh = new THREE.Mesh(unknownGeo, unknownMat);
      unknownMesh.position.y = 0.38;
      unknownMesh.castShadow = true;
      group.add(unknownMesh);

      const markerGeo = new THREE.SphereGeometry(0.12, 12, 12);
      const markerMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8 });
      const marker = new THREE.Mesh(markerGeo, markerMat);
      marker.position.y = 0.75;
      group.add(marker);
    }

    // Mini Name Label Sprite with high contrast
    const label = this.createAgentNameSprite(agent.name.split(' ')[0], haloColor);
    label.position.set(0, 1.25, 0);
    group.add(label);

    return group;
  }

  private createAgentNameSprite(shortName: string, borderColor: number): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 160;
    canvas.height = 48;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      const hex = '#' + borderColor.toString(16).padStart(6, '0');
      ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
      ctx.strokeStyle = hex;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.roundRect(4, 4, 152, 40, 10);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = 'center';
      ctx.font = 'bold 20px sans-serif';
      ctx.fillStyle = '#ffffff';
      ctx.fillText(shortName.slice(0, 10), 80, 29);
    }

    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(1.4, 0.42, 1);
    return sprite;
  }

  public selectRoom(roomId: string, animate = true): void {
    this.activeRoomId = roomId;
    const roomConfig = this.rooms.find((r) => r.id === roomId);
    if (!roomConfig) return;

    // Move spotlight to active room
    if (this.roomSpotlight) {
      this.roomSpotlight.position.set(roomConfig.x, 12, roomConfig.z);
      this.roomSpotlight.target.position.set(roomConfig.x, 0, roomConfig.z);
      this.scene.add(this.roomSpotlight.target);
    }

    // Adjust platform colors
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

    // Smart Zoom: smoothly focus camera onto selected department
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

      // Ensure room of agent is focused
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

  private updateCameraPosition(): void {
    const radY = THREE.MathUtils.degToRad(this.cameraAngle);
    const radX = THREE.MathUtils.degToRad(this.cameraElevation);

    const x = this.cameraTarget.x + this.cameraDistance * Math.sin(radY) * Math.cos(radX);
    const y = this.cameraTarget.y + this.cameraDistance * Math.sin(radX);
    const z = this.cameraTarget.z + this.cameraDistance * Math.cos(radY) * Math.cos(radX);

    this.camera.position.set(x, y, z);
    this.camera.lookAt(this.cameraTarget);
  }

  private bindEvents(): void {
    const dom = this.renderer.domElement;

    dom.addEventListener('pointerdown', this.handlePointerDown);
    dom.addEventListener('pointermove', this.handlePointerMove);
    dom.addEventListener('pointerup', this.handlePointerUp);
    dom.addEventListener('wheel', this.handleWheel, { passive: false });
  }

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

    // Raycast hover detection when not dragging
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
    if (this.isDisposed) return;

    // Smooth camera panning and smart zooming
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

    // Subtle idle animation strictly for EPHEMERAL crystal agents
    if (!this.options.reducedMotion) {
      const t = time * 0.002;
      this.agentMeshes.forEach((group) => {
        // Enforce limitation: ONLY EPHEMERAL crystal agents animate, NEVER STANDING agents
        if (group.userData?.agentType === 'EPHEMERAL') {
          if (group.children.length > 1 && group.children[1] instanceof THREE.Mesh) {
            // Subtle hover bob and crystal rotation
            group.children[1].position.y = 0.58 + Math.sin(t + group.position.x) * 0.04;
            group.children[1].rotation.y = t * 0.5;
          }
        }
      });

      // Pulse active selection ring
      if (this.selectionRing && this.selectionRing.visible) {
        const s = 1.0 + Math.sin(time * 0.006) * 0.08;
        this.selectionRing.scale.set(s, s, s);
      }
    }
  }

  private animate(time: number): void {
    if (this.isDisposed) return;

    this.stepAnimation(time);

    this.renderer.render(this.scene, this.camera);
    this.animFrameId = requestAnimationFrame(this.animate);
  }

  private disposeHierarchy(obj: THREE.Object3D): void {
    obj.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        if (child.geometry) child.geometry.dispose();
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => m.dispose());
        } else if (child.material) {
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
    }

    this.disposeHierarchy(this.scene);
    if (this.renderer && typeof this.renderer.dispose === 'function') {
      this.renderer.dispose();
    }
    if (dom && typeof dom.remove === 'function') {
      dom.remove();
    }
  }
}
