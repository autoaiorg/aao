/**
 * Tests for PR C: OfficeFurnitureSystem, Procedural Textures, Biophilia & Lighting Polish.
 *
 * Verifies:
 * 1. SharedFurniturePool geometry and material pooling, ownership checks, and clean disposal.
 * 2. Procedural IDE code editor canvas texture generation.
 * 3. Architectural lighting setup with soft contact shadow bias and hemisphere skylight fill.
 * 4. Biophilic office plants construction and placement in atrium and canonical departments.
 * 5. Modern ergonomic workstation configurations (ultrawide curved monitors, cable grommets).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as THREE from 'three';
import {
  ThreeOfficeScene,
  SharedFurniturePool,
  createProceduralIdeTexture,
  type ThreeSceneCallbacks,
} from '../features/office/engine/ThreeOfficeScene';
import { DEMO_AGENTS } from '../data/adapters/demo/fixtures';
import { OFFICE_ROOMS } from '../features/office/types';

describe('PR C: Office Furniture, Procedural IDE Textures, Biophilia & Lighting', () => {
  describe('SharedFurniturePool & Procedural Textures', () => {
    it('creates procedural IDE code editor texture with correct dimensions and mipmaps', () => {
      const texture = createProceduralIdeTexture();
      expect(texture).toBeInstanceOf(THREE.CanvasTexture);
      expect(texture.image).toBeDefined();
      expect(texture.image.width).toBe(256);
      expect(texture.image.height).toBe(128);
      expect(texture.generateMipmaps).toBe(true);
      texture.dispose();
    });

    it('manages pooled geometries and materials with strict ownership and disposal', () => {
      const pool = new SharedFurniturePool();

      // Check geometry counts and instances
      expect(pool.getGeometriesCount()).toBe(17);
      expect(pool.ownsGeometry(pool.ultrawideMonitorGeo)).toBe(true);
      expect(pool.ownsGeometry(pool.deskGrommetGeo)).toBe(true);
      expect(pool.ownsGeometry(pool.planterPotGeo)).toBe(true);
      expect(pool.ownsGeometry(pool.plantFoliageGeo)).toBe(true);

      const foreignGeo = new THREE.BoxGeometry(1, 1, 1);
      expect(pool.ownsGeometry(foreignGeo)).toBe(false);

      // Check materials and instances
      expect(pool.getMaterialsCount()).toBe(10);
      expect(pool.ownsMaterial(pool.monitorIdeMat)).toBe(true);
      expect(pool.ownsMaterial(pool.plantPotMat)).toBe(true);
      expect(pool.ownsMaterial(pool.plantLeafMat)).toBe(true);
      expect(pool.ownsMaterial(pool.deskTrimMat)).toBe(true);

      const foreignMat = new THREE.MeshBasicMaterial();
      expect(pool.ownsMaterial(foreignMat)).toBe(false);

      // Disposal
      const geoDisposeSpies = [
        vi.spyOn(pool.ultrawideMonitorGeo, 'dispose'),
        vi.spyOn(pool.deskGrommetGeo, 'dispose'),
        vi.spyOn(pool.planterPotGeo, 'dispose'),
        vi.spyOn(pool.plantFoliageGeo, 'dispose'),
      ];
      const matDisposeSpies = [
        vi.spyOn(pool.monitorIdeMat, 'dispose'),
        vi.spyOn(pool.plantPotMat, 'dispose'),
        vi.spyOn(pool.plantLeafMat, 'dispose'),
        vi.spyOn(pool.deskTrimMat, 'dispose'),
      ];
      const texDisposeSpy = vi.spyOn(pool.ideTexture, 'dispose');

      pool.dispose();

      for (const spy of geoDisposeSpies) {
        expect(spy).toHaveBeenCalled();
      }
      for (const spy of matDisposeSpies) {
        expect(spy).toHaveBeenCalled();
      }
      expect(texDisposeSpy).toHaveBeenCalled();
      foreignGeo.dispose();
      foreignMat.dispose();
    });
  });

  describe('Architectural Lighting and Biophilic Elements in ThreeOfficeScene', () => {
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

    it('configures architectural directional contact shadow bias and hemisphere ambient skylight', () => {
      const lightsGroup = (scene as unknown as { lightsGroup: THREE.Group }).lightsGroup;
      expect(lightsGroup).toBeDefined();

      // Find main directional light
      const dirLight = lightsGroup.children.find(
        (child) => child instanceof THREE.DirectionalLight && child.castShadow
      ) as THREE.DirectionalLight;
      expect(dirLight).toBeDefined();
      expect(dirLight.shadow.bias).toBeCloseTo(-0.0004, 5);

      // Find hemisphere light
      const hemiLight = lightsGroup.children.find(
        (child) => child instanceof THREE.HemisphereLight
      ) as THREE.HemisphereLight;
      expect(hemiLight).toBeDefined();
      expect(hemiLight.color.getHex()).toBe(0xfff7e8);
      expect(hemiLight.groundColor.getHex()).toBe(0x5b554c);
      expect(hemiLight.intensity).toBeCloseTo(0.9, 2);
    });

    it('keeps circulation geometry flush with the shared floor instead of drawing raised floor pads', () => {
      const groundGroup = (scene as unknown as { groundGroup: THREE.Group }).groundGroup;
      const walkwaysGroup = (scene as unknown as { walkwaysGroup: THREE.Group }).walkwaysGroup;
      const slab = groundGroup.children.find((child) => child.name === 'campus-continuous-floor') as THREE.Mesh;

      expect(slab).toBeDefined();
      const slabTop = slab.position.y + (slab.geometry as THREE.BoxGeometry).parameters.height / 2;
      expect(walkwaysGroup.children.length).toBeGreaterThan(0);

      for (const segment of walkwaysGroup.children as THREE.Mesh[]) {
        const geometry = segment.geometry as THREE.BoxGeometry;
        const bottom = segment.position.y - geometry.parameters.height / 2;
        expect(bottom).toBeCloseTo(slabTop, 3);
      }
    });

    it('uses a shared floor datum, invisible room hit targets, and source-neutral reception architecture', () => {
      const root = (scene as unknown as { scene: THREE.Scene }).scene;
      const reception = root.getObjectByName('architectural-reception') as THREE.Group;
      expect(reception).toBeDefined();
      expect(reception.userData).toMatchObject({ role: 'architectural-common-space', zone: 'reception', sourceNeutral: true });
      expect(reception.position.z).toBeGreaterThan(6);
      expect(reception.position.x).toBeCloseTo(-2.1);
      expect(reception.getObjectByName('reception-welcome-backdrop')).toBeDefined();
      const visitorLounge = reception.getObjectByName('reception-visitor-lounge') as THREE.Group;
      expect(visitorLounge).toBeDefined();
      expect(visitorLounge.children).toHaveLength(4);
      const centralLounge = root.getObjectByName('architectural-central-lounge') as THREE.Group;
      expect(centralLounge).toBeDefined();
      expect(centralLounge.userData).toMatchObject({ role: 'architectural-common-space', sourceNeutral: true });
      expect(centralLounge.getObjectByName('central-lounge-sofa-west')).toBeDefined();
      expect(centralLounge.getObjectByName('central-lounge-sofa-east')).toBeDefined();
      expect(centralLounge.getObjectByName('central-lounge-coffee-table')).toBeDefined();

      const roomGroups = (scene as unknown as { roomsGroup: THREE.Group }).roomsGroup;
      const room = roomGroups.children.find((child) => child.name === 'room-unit-eng');
      expect(room).toBeDefined();
      expect(room!.position.y).toBeCloseTo(-0.35, 3);
      const selectableFloor = (room as THREE.Group).children.find(
        (child) => child instanceof THREE.Mesh && child.userData.type === 'room'
      ) as THREE.Mesh;
      expect(selectableFloor).toBeDefined();
      expect(selectableFloor.geometry).toBeInstanceOf(THREE.PlaneGeometry);
      expect(selectableFloor.rotation.x).toBeCloseTo(-Math.PI / 2);
      expect(selectableFloor.position.y + room!.position.y).toBeCloseTo(0.02);
      const hitMaterial = selectableFloor.material as THREE.MeshBasicMaterial;
      expect(hitMaterial.opacity).toBe(0);
      expect(hitMaterial.colorWrite).toBe(false);
      expect(hitMaterial.depthWrite).toBe(false);

      expect(room!.getObjectByName('department-finish-acoustic-carpet')).toBeUndefined();

      const backPartition = room!.getObjectByName('department-back-partition') as THREE.Mesh<THREE.BoxGeometry>;
      const sideGlass = room!.getObjectByName('department-side-glass-left') as THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial>;
      const frontGlass = room!.getObjectByName('department-front-glass-left') as THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial>;
      expect(backPartition.geometry.parameters.height).toBeLessThan(0.65);
      expect(sideGlass.geometry.parameters.height).toBeLessThan(0.65);
      expect(frontGlass.geometry.parameters.height).toBeLessThan(0.65);
      const roomConfig = (room as THREE.Group).userData.room as (typeof OFFICE_ROOMS)[number];
      expect(backPartition.geometry.parameters.width).toBeLessThan(roomConfig.width * 0.5);
      expect(sideGlass.geometry.parameters.depth).toBeLessThan(roomConfig.depth * 0.3);
      expect(frontGlass.geometry.parameters.width).toBeLessThan(0.5);
      expect(sideGlass.material.opacity).toBeLessThan(0.15);
      expect(room!.getObjectByName('department-wall-sign')).toBeDefined();
    });

    it('keeps an accessible opening in the continuous curtain facade', () => {
      const root = (scene as unknown as { scene: THREE.Scene }).scene;
      const facade = root.getObjectByName('architectural-curtain-facade') as THREE.Group;
      const entrance = root.getObjectByName('architectural-main-entrance') as THREE.Group;
      expect(facade).toBeDefined();
      expect(entrance).toBeDefined();
      expect(entrance.userData.accessible).toBe(true);
      expect(entrance.children).toHaveLength(4);

      const frontGlassWidth = facade.children
        .filter((child) => child instanceof THREE.Mesh && child.rotation.y === 0 && child.position.z > 0)
        .filter((child) => (child as THREE.Mesh).geometry instanceof THREE.BoxGeometry)
        .map((child) => (child as THREE.Mesh<THREE.BoxGeometry>).geometry.parameters)
        .filter((geometry) => geometry.height === 2.65)
        .reduce((sum, geometry) => sum + geometry.width, 0);
      expect(facade.userData.facadeWidth - frontGlassWidth).toBeCloseTo(
        facade.userData.entranceWidth,
        5,
      );
    });

    it('uses a locally generated stone finish and disposes its texture with the scene', () => {
      const groundGroup = (scene as unknown as { groundGroup: THREE.Group }).groundGroup;
      const slab = groundGroup.children.find(
        (child) => child instanceof THREE.Mesh && child.geometry instanceof THREE.BoxGeometry
      ) as THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial>;
      expect(slab).toBeDefined();
      expect(slab.material.map).toBeInstanceOf(THREE.CanvasTexture);
      const textureDispose = vi.spyOn(slab.material.map!, 'dispose');

      scene.dispose();

      expect(textureDispose).toHaveBeenCalledOnce();
    });

    it('reports renderer counters and transparent CPU-side geometry/texture memory estimates', () => {
      const metrics = scene.getPerformanceMetrics();
      expect(metrics.sceneBuildDurationMs).toBeGreaterThanOrEqual(0);
      expect(metrics.geometryBytesApprox).toBeGreaterThan(0);
      expect(metrics.textureBytesApprox).toBeGreaterThan(0);
      expect(metrics.drawCalls).toBe(0); // The injected test renderer does not implement WebGLInfo.
    });

    it('builds biophilic office plants with ceramic pot and botanical foliage', () => {
      const plant = scene.buildBiophilicOfficePlant(2.5, -1.8);
      expect(plant).toBeInstanceOf(THREE.Group);
      expect(plant.position.x).toBeCloseTo(2.5, 3);
      expect(plant.position.y).toBeCloseTo(0.04, 3);
      expect(plant.position.z).toBeCloseTo(-1.8, 3);

      // Verify child meshes
      expect(plant.children.length).toBe(2);
      const [potMesh, foliageMesh] = plant.children as THREE.Mesh[];

      expect(potMesh).toBeInstanceOf(THREE.Mesh);
      expect(potMesh.geometry).toBe(scene.getFurniturePool().planterPotGeo);
      expect(potMesh.material).toBe(scene.getFurniturePool().plantPotMat);
      expect(potMesh.castShadow).toBe(true);

      expect(foliageMesh).toBeInstanceOf(THREE.Mesh);
      expect(foliageMesh.geometry).toBe(scene.getFurniturePool().plantFoliageGeo);
      expect(foliageMesh.material).toBe(scene.getFurniturePool().plantLeafMat);
      expect(foliageMesh.castShadow).toBe(true);
    });

    it('places biophilic plants around central atrium perimeter and in canonical department rooms', () => {
      const groundGroup = (scene as unknown as { groundGroup: THREE.Group }).groundGroup;
      expect(groundGroup).toBeDefined();

      // Atrium plants at ±3.4, ±3.4
      const atriumPlantCorners: [number, number][] = [
        [-3.4, -3.4],
        [3.4, -3.4],
        [3.4, 3.4],
        [-3.4, 3.4],
      ];

      for (const [px, pz] of atriumPlantCorners) {
        const found = groundGroup.children.some((child) => {
          if (child instanceof THREE.Group && child.children.length === 2) {
            return (
              Math.abs(child.position.x - px) < 0.01 &&
              Math.abs(child.position.z - pz) < 0.01
            );
          }
          return false;
        });
        expect(found).toBe(true);
      }

      // Check canonical department rooms have biophilic plants
      const roomsGroup = (scene as unknown as { roomsGroup: THREE.Group }).roomsGroup;
      expect(roomsGroup).toBeDefined();

      const engRoom = roomsGroup.children.find((group) => {
        return group.name.includes('room-unit-eng') || group.userData?.room?.code === 'ENG';
      });
      expect(engRoom).toBeDefined();

      // Eng room must contain a biophilic plant group
      const hasPlant = engRoom!.children.some((child) => {
        return (
          child instanceof THREE.Group &&
          child.children.length === 2 &&
          (child.children[0] as THREE.Mesh).geometry === scene.getFurniturePool().planterPotGeo
        );
      });
      expect(hasPlant).toBe(true);
    });

    it('populates ergonomic workstations with ultrawide monitors and cable grommets in canonical rooms', () => {
      const roomsGroup = (scene as unknown as { roomsGroup: THREE.Group }).roomsGroup;
      const engRoom = roomsGroup.children.find((group) => group.userData?.room?.code === 'ENG')!;
      expect(engRoom).toBeDefined();

      // Find desk group
      let deskFound = false;
      let hasUltrawide = false;
      let hasGrommet = false;
      let hasIdeTexture = false;

      engRoom.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          if (obj.geometry === scene.getFurniturePool().ultrawideMonitorGeo) {
            hasUltrawide = true;
            if (obj.material === scene.getFurniturePool().monitorIdeMat) {
              hasIdeTexture = true;
            }
          }
          if (obj.geometry === scene.getFurniturePool().deskGrommetGeo) {
            hasGrommet = true;
          }
          if (obj.geometry === scene.getFurniturePool().deskTopGeo) {
            deskFound = true;
          }
        }
      });

      expect(deskFound).toBe(true);
      expect(hasUltrawide).toBe(true);
      expect(hasIdeTexture).toBe(true);
      expect(hasGrommet).toBe(true);
    });
  });
});
