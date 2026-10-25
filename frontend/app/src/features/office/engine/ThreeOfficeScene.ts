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
}

export class ThreeOfficeScene {
  private container: HTMLElement;
  private options: ThreeSceneOptions;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer;
  private animFrameId: number | null = null;
  private isDisposed = false;

  // Interaction & Raycasting
  private raycaster = new THREE.Raycaster();
  private mouse = new THREE.Vector2();
  private pointerDownPos = new THREE.Vector2();
  private isDragging = false;

  // Camera Orbit parameters
  private cameraAngle = 35; // degrees around Y
  private cameraElevation = 45; // degrees tilt
  private cameraDistance = 28; // distance from target
  private cameraTarget = new THREE.Vector3(0, 0, 0);
  private desiredTarget = new THREE.Vector3(0, 0, 0);

  // Groups and Interactive Meshes
  private roomsGroup = new THREE.Group();
  private agentsGroup = new THREE.Group();
  private lightsGroup = new THREE.Group();
  private interactiveMeshes: THREE.Object3D[] = [];
  private roomPlatforms: Map<string, THREE.Mesh> = new Map();
  private agentMeshes: Map<string, THREE.Group> = new Map();
  private roomSpotlight: THREE.SpotLight | null = null;
  private activeRoomId: string = 'unit-exec';
  private activeAgentId: string | null = null;

  // Selected agent selection ring
  private selectionRing: THREE.Mesh | null = null;

  constructor(container: HTMLElement, options: ThreeSceneOptions) {
    this.container = container;
    this.options = options;

    // 1. Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a1628);
    this.scene.fog = new THREE.FogExp2(0x0a1628, 0.015);

    // 2. Camera
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;
    this.camera = new THREE.PerspectiveCamera(42, width / height, 0.5, 200);
    this.updateCameraPosition();

    // 3. Renderer
    this.renderer =
      options.renderer ||
      new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setSize(width, height);
    if (!options.renderer) {
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }
    if (!container.contains(this.renderer.domElement)) {
      container.appendChild(this.renderer.domElement);
    }

    // 4. Hierarchy Groups
    this.scene.add(this.roomsGroup);
    this.scene.add(this.agentsGroup);
    this.scene.add(this.lightsGroup);

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
    const ambient = new THREE.AmbientLight(0x2d3e58, 1.8);
    this.lightsGroup.add(ambient);

    // Main Key Sun Light
    const dirLight = new THREE.DirectionalLight(0xffffff, 2.2);
    dirLight.position.set(18, 30, 16);
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
    const fillLight = new THREE.DirectionalLight(0x38bdf8, 1.0);
    fillLight.position.set(-20, 15, -15);
    this.lightsGroup.add(fillLight);

    // Dynamic Spotlight focused on active department
    this.roomSpotlight = new THREE.SpotLight(0x60a5fa, 4, 30, Math.PI / 4, 0.35, 1);
    this.roomSpotlight.position.set(-6, 12, -4);
    this.roomSpotlight.castShadow = true;
    this.lightsGroup.add(this.roomSpotlight);
  }

  private buildWorld(): void {
    // 1. Central Plaza & Complex Ground Slab
    const groundGeo = new THREE.BoxGeometry(26, 0.4, 20);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x111e33,
      roughness: 0.85,
      metalness: 0.15,
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.position.y = -0.2;
    ground.receiveShadow = true;
    this.scene.add(ground);

    // Ground Grid overlay
    const grid = new THREE.GridHelper(26, 26, 0x38bdf8, 0x1e3a5f);
    grid.position.y = 0.01;
    this.scene.add(grid);

    // Central Connecting Atrium Walkway
    const atriumGeo = new THREE.CylinderGeometry(3.5, 3.5, 0.08, 32);
    const atriumMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.5,
      metalness: 0.4,
    });
    const atrium = new THREE.Mesh(atriumGeo, atriumMat);
    atrium.position.y = 0.04;
    atrium.receiveShadow = true;
    this.scene.add(atrium);

    // 2. Department Pavilions
    OFFICE_ROOMS.forEach((room) => {
      this.buildRoom(room);
    });

    // 3. Selection Ring (for active agent)
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
      wireframe: false,
    });
    const border = new THREE.Mesh(borderGeo, borderMat);
    border.position.y = 0.38;
    roomGroup.add(border);

    // Translucent Corner Glass Pillars
    const pillarGeo = new THREE.BoxGeometry(0.2, 1.6, 0.2);
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
      p.position.set(cx, 1.0, cz);
      p.castShadow = true;
      roomGroup.add(p);
    });

    // Central Desk/Console Unit (Furniture)
    const deskGeo = new THREE.CylinderGeometry(0.85, 0.95, 0.5, 16);
    const deskMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.4,
      metalness: 0.6,
    });
    const desk = new THREE.Mesh(deskGeo, deskMat);
    desk.position.set(0, 0.5, 0);
    desk.castShadow = true;
    desk.receiveShadow = true;
    roomGroup.add(desk);

    // Floating Department Label Sprite
    const labelSprite = this.createDepartmentLabelSprite(room.code, room.name, room.accentColor);
    labelSprite.position.set(0, 2.2, 0);
    roomGroup.add(labelSprite);

    this.roomsGroup.add(roomGroup);
  }

  private createDepartmentLabelSprite(code: string, name: string, accentColor: string): THREE.Sprite {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 96;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      // Rounded background badge
      ctx.fillStyle = 'rgba(10, 22, 40, 0.88)';
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
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(3.2, 1.2, 1);
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
    OFFICE_ROOMS.forEach((room) => {
      const roomAgents = byRoom.get(room.id) || [];
      const count = roomAgents.length;
      if (count === 0) return;

      const radius = count === 1 ? 0.0 : Math.min(1.6, 0.9 + count * 0.15);

      roomAgents.forEach((agent, index) => {
        const angle = count === 1 ? 0 : (index / count) * Math.PI * 2;
        const localX = count === 1 ? 0 : Math.cos(angle) * radius;
        const localZ = count === 1 ? 1.0 : Math.sin(angle) * radius;

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

  private buildAgentAvatar(agent: AgentIdentity): THREE.Group {
    const group = new THREE.Group();

    // Color based on agent type and telemetry
    const isStanding = agent.type === 'STANDING';
    const bodyColor = isStanding ? 0x2563eb : 0x0891b2;

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
      // Standing Agent Avatar: Sturdy geometric humanoid torso + head
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
    } else {
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
    }

    // Mini Name Label Sprite
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
      ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
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
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(1.4, 0.42, 1);
    return sprite;
  }

  public selectRoom(roomId: string, animate = true): void {
    this.activeRoomId = roomId;
    const roomConfig = OFFICE_ROOMS.find((r) => r.id === roomId);
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
      const conf = OFFICE_ROOMS.find((r) => r.id === id);
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

    // Set target for smooth camera pan
    this.desiredTarget.set(roomConfig.x, 0, roomConfig.z);

    if (!animate || this.options.reducedMotion) {
      this.cameraTarget.copy(this.desiredTarget);
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
    this.cameraDistance = Math.max(14, Math.min(45, this.cameraDistance * deltaFactor));
    this.updateCameraPosition();
  }

  public resetCamera(): void {
    this.cameraAngle = 35;
    this.cameraElevation = 45;
    this.cameraDistance = 28;
    this.desiredTarget.set(0, 0, 0);
    this.cameraTarget.set(0, 0, 0);
    this.updateCameraPosition();
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
    try {
      this.renderer.domElement.releasePointerCapture(e.pointerId);
    } catch {
      // Ignore if not captured
    }

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

    // Smooth camera panning toward desiredTarget
    if (!this.options.reducedMotion && this.cameraTarget.distanceTo(this.desiredTarget) > 0.05) {
      this.cameraTarget.lerp(this.desiredTarget, 0.08);
      this.updateCameraPosition();
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
    dom.removeEventListener('pointerdown', this.handlePointerDown);
    dom.removeEventListener('pointermove', this.handlePointerMove);
    dom.removeEventListener('pointerup', this.handlePointerUp);
    dom.removeEventListener('wheel', this.handleWheel);

    this.disposeHierarchy(this.scene);
    this.renderer.dispose();

    if (dom.parentElement === this.container) {
      this.container.removeChild(dom);
    }
  }
}
