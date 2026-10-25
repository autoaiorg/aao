import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DataState, OrganizationStructure, AgentIdentity } from '../../domain/models';

/** F4 interactive spatial viewer. No operational commands, no inferred live presence. */
export interface VirtualOfficeViewProps {
  organization: DataState<OrganizationStructure>;
  onNavigate?: (target: 'organization' | 'kanban' | 'projects') => void;
}

type Vec3 = { x: number; y: number; z: number };
type Room = { id: string; name: string; code: string; x: number; z: number; color: string };
const ROOMS: Room[] = [
  { id: 'unit-exec', name: 'Dirección', code: 'EXEC', x: -5, z: -3.1, color: '#5985c8' },
  { id: 'unit-gov', name: 'Gobernanza', code: 'GOV', x: 0, z: -3.1, color: '#9d7bd0' },
  { id: 'unit-audit', name: 'Auditoría', code: 'AUDIT', x: 5, z: -3.1, color: '#36a997' },
  { id: 'unit-arch', name: 'Arquitectura', code: 'ARCH', x: -5, z: 3.1, color: '#dd9b4c' },
  { id: 'unit-eng', name: 'Ingeniería', code: 'ENG', x: 0, z: 3.1, color: '#3c9ec8' },
  { id: 'unit-ops', name: 'Operaciones', code: 'OPS', x: 5, z: 3.1, color: '#a98766' },
];
const styles = `
.aao-f4{color:var(--text-primary,#e6edf8);display:grid;gap:16px} .aao-f4 button{cursor:pointer}
.aao-f4 button:focus-visible{outline:3px solid #71bbff;outline-offset:3px}
.aao-f4 .toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.aao-f4 .action{border:1px solid #405473;border-radius:9px;padding:9px 12px;background:#1f314b;color:#f1f6ff;font:inherit;font-size:13px}
.aao-f4 .action[aria-pressed=true]{background:#3a75ad;border-color:#78bdfb}
.aao-f4 .layout{display:grid;grid-template-columns:minmax(0,1fr) 315px;gap:16px;align-items:start}
.aao-f4 .viewport{width:100%;position:relative;min-height:530px;background:#0a172a;border:1px solid #304767;border-radius:16px;overflow:hidden}
.aao-f4 canvas{width:100%;height:530px;display:block;touch-action:none;cursor:grab}
.aao-f4 canvas:active{cursor:grabbing}
.aao-f4 .hint{position:absolute;left:12px;bottom:12px;background:#071629de;color:#d8e7f9;border:1px solid #435c7b;border-radius:9px;padding:8px 10px;font-size:12px;pointer-events:none}
.aao-f4 .panel{background:var(--bg-surface,#17253a);border:1px solid var(--border-subtle,#435570);padding:18px;border-radius:14px;min-height:320px}
.aao-f4 .muted{color:var(--text-secondary,#a8bbd5);font-size:12px;line-height:1.55}
.aao-f4 .grid2d{background:#0c1b30;padding:16px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;min-height:530px;align-content:center}
.aao-f4 .tile{color:#f0f5ff;text-align:left;background:#233956;border:2px solid #4c6585;border-radius:12px;padding:20px 10px;min-height:128px;font:inherit}
.aao-f4 .tile[aria-pressed=true]{border-color:#78bdfb;background:#315984}
.aao-f4 .agent{width:100%;text-align:left;border:1px solid #435570;border-radius:8px;background:transparent;color:inherit;padding:10px;margin:5px 0}
.aao-f4 .agent[aria-pressed=true]{background:#2c527d}
.aao-f4 .status{border:1px solid #597fa9;border-radius:9px;background:#1c344f;color:#e5f1ff;padding:10px;font-size:12px;font-weight:600}
.aao-f4 .group{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}
.aao-f4 .group button{flex:1;min-width:75px}
@media(max-width:930px){.aao-f4 .layout{grid-template-columns:1fr}.aao-f4 .viewport,.aao-f4 .grid2d{min-height:410px}.aao-f4 canvas{height:410px}}
@media(max-width:520px){.aao-f4 .grid2d{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){.aao-f4 *{animation:none!important;transition:none!important}}
`;

/** Software-projected 3D coordinates keep the viewer working without a GPU/WebGL. */
function project(p: Vec3, angle: number, tilt: number, zoom: number, width: number, height: number) {
  const a = angle * Math.PI / 180, t = tilt * Math.PI / 180;
  const xx = p.x * Math.cos(a) - p.z * Math.sin(a);
  const zz = p.x * Math.sin(a) + p.z * Math.cos(a);
  const yy = p.y * Math.cos(t) - zz * Math.sin(t);
  const depth = p.y * Math.sin(t) + zz * Math.cos(t);
  const scale = Math.min(width / 24, height / 15) * zoom * (1 + depth * 0.018);
  return { x: width / 2 + xx * scale, y: height * 0.53 - yy * scale, depth };
}
function drawPoly(ctx: CanvasRenderingContext2D, points: {x:number;y:number}[], fill: string, stroke = '#8193b8') {
  ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y)); ctx.closePath();
  ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = stroke; ctx.lineWidth = 1.2; ctx.stroke();
}

export const VirtualOfficeView: React.FC<VirtualOfficeViewProps> = ({ organization, onNavigate }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hits = useRef<{roomId:string;x:number;y:number;r:number}[]>([]);
  const drag = useRef<{x:number;angle:number;dragged:boolean}|null>(null);
  const [angle, setAngle] = useState(29);
  const [tilt, setTilt] = useState(43);
  const [zoom, setZoom] = useState(1);
  const [view2d, setView2d] = useState(false);
  const [selectedId, setSelectedId] = useState('unit-exec');
  const [selectedAgentId, setSelectedAgentId] = useState<string|null>(null);
  const data = organization.kind === 'ready' ? organization.data : null;
  const isDemo = organization.kind === 'ready' && organization.origin === 'demo';
  const selected = ROOMS.find(r => r.id === selectedId) || ROOMS[0];
  const unit = data?.units.find(u => u.id === selectedId);
  const agents = useMemo(() => (data?.agents || []).filter(a => a.unitId === selectedId), [data, selectedId]);
  const activeAgent: AgentIdentity | undefined = agents.find(a => a.id === selectedAgentId);
  const choose = useCallback((id: string) => { setSelectedId(id); setSelectedAgentId(null); }, []);
  const roomCount = useCallback((id:string) => (data?.agents || []).filter(a=>a.unitId===id).length, [data]);

  const paint = useCallback(() => {
    const canvas = canvasRef.current; if (!canvas) return;
    const ctx = canvas.getContext('2d'); if (!ctx) return;
    const rect = canvas.getBoundingClientRect(); if (!rect.width || !rect.height) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2), w = rect.width, h = rect.height;
    canvas.width = Math.floor(w*dpr); canvas.height = Math.floor(h*dpr);
    ctx.setTransform(dpr,0,0,dpr,0,0);
    const grad = ctx.createLinearGradient(0,0,0,h); grad.addColorStop(0,'#11294b'); grad.addColorStop(1,'#071323');
    ctx.fillStyle = grad; ctx.fillRect(0,0,w,h);
    for(let i=0;i<65;i++){const x=((i*147.73)%997)/997*w,y=((i*61.97)%773)/773*h;ctx.fillStyle='#a5d4ff26';ctx.fillRect(x,y,2,2)}
    const p = (x:number,y:number,z:number) => project({x,y,z},angle,tilt,zoom,w,h);
    drawPoly(ctx,[p(-8,0,-6.4),p(8,0,-6.4),p(8,0,6.4),p(-8,0,6.4)],'#1d3554','#6684ae');
    for(let x=-8;x<=8;x+=2){const a=p(x,0,-6.4),b=p(x,0,6.4);ctx.strokeStyle='#7ca4d422';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}
    for(let z=-6;z<=6;z+=2){const a=p(-8,0,z),b=p(8,0,z);ctx.strokeStyle='#7ca4d422';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}
    const nodes: {room:Room;center:{x:number;y:number;depth:number}}[] = ROOMS.map(room=>({room,center:p(room.x,0.1,room.z)}));
    nodes.sort((a,b)=>a.center.depth-b.center.depth);
    const nextHits: typeof hits.current = [];
    for(const {room,center} of nodes){
      const x=room.x,z=room.z, y=0.16, ht=1.35, dx=1.85,dz=2.18;
      const a=p(x-dx,y,z-dz),b=p(x+dx,y,z-dz),c=p(x+dx,y,z+dz),d=p(x-dx,y,z+dz);
      const aa=p(x-dx,y+ht,z-dz),bb=p(x+dx,y+ht,z-dz),cc=p(x+dx,y+ht,z+dz),dd=p(x-dx,y+ht,z+dz);
      const selectedRoom = selectedId===room.id;
      drawPoly(ctx,[a,b,bb,aa], selectedRoom?'#446e9c':'#284763',room.color);
      drawPoly(ctx,[b,c,cc,bb], selectedRoom?'#365e89':'#203b56',room.color);
      drawPoly(ctx,[d,c,cc,dd], selectedRoom?'#416a97':'#294766',room.color);
      drawPoly(ctx,[aa,bb,cc,dd],selectedRoom?'#c2e8ff':room.color,selectedRoom?'#ffffff':'#adc4e3');
      const text=p(x,ht+0.12,z);
      ctx.textAlign='center';ctx.font='bold 13px system-ui';ctx.fillStyle=selectedRoom?'#061b35':'#ffffff';
      ctx.fillText(room.code,text.x,text.y+4);
      const number=roomCount(room.id);
      if(number){ctx.font='11px system-ui';ctx.fillText(`${number} agentes · ${isDemo?'DEMO':'registrados'}`,text.x,text.y+19)}
      if(selectedRoom){ctx.strokeStyle='#b7ebff';ctx.lineWidth=2.5;ctx.beginPath();ctx.arc(text.x,text.y,Math.max(30,Math.min(w/13,54)),0,Math.PI*2);ctx.stroke()}
      nextHits.push({roomId:room.id,x:text.x,y:text.y,r:Math.max(31,Math.min(w/12,62))});
    }
    hits.current=nextHits.reverse();
    ctx.textAlign='left';ctx.fillStyle='#aec8e9';ctx.font='12px system-ui';ctx.fillText(`CÁMARA ${Math.round(angle)}°  ·  ZOOM ${Math.round(zoom*100)}%`,16,26);
  },[angle,tilt,zoom,selectedId,roomCount,isDemo]);
  useEffect(()=>{if(view2d)return;paint();const observer=new ResizeObserver(paint);if(canvasRef.current)observer.observe(canvasRef.current);return()=>observer.disconnect()},[paint,view2d]);
  const onPointerDown=(e:React.PointerEvent<HTMLCanvasElement>)=>{drag.current={x:e.clientX,angle,dragged:false};e.currentTarget.setPointerCapture(e.pointerId)};
  const onPointerMove=(e:React.PointerEvent<HTMLCanvasElement>)=>{if(!drag.current)return;const d=e.clientX-drag.current.x;if(Math.abs(d)>5)drag.current.dragged=true;setAngle(drag.current.angle+d*.28)};
  const onPointerUp=(e:React.PointerEvent<HTMLCanvasElement>)=>{const d=drag.current;drag.current=null;if(!d || d.dragged)return;const box=e.currentTarget.getBoundingClientRect();const x=e.clientX-box.left,y=e.clientY-box.top;const hit=hits.current.find(h=>Math.hypot(h.x-x,h.y-y)<h.r);if(hit)choose(hit.roomId)};
  return <section className="aao-f4" aria-label="Oficina virtual AAO">
    <style>{styles}</style>
    <header><h2 style={{margin:'0 0 4px'}}>Oficina virtual · F4</h2><p className="muted" style={{margin:0}}>Escena 3D interactiva de la organización. Los edificios indican departamentos, no la presencia de personas o agentes.</p></header>
    <div className="status" role="status">{isDemo?'DEMO · DATOS Y ASIGNACIONES SIMULADOS':data?'LIVE · ESTRUCTURA RECIBIDA · PRESENCIA NO ACREDITADA':'SIN DATOS LIVE · ESPACIOS ILUSTRATIVOS · NINGÚN AGENTE ACTIVO INFERIDO'}</div>
    <div className="toolbar" role="group" aria-label="Controles de oficina">
      <button className="action" aria-pressed={!view2d} onClick={()=>setView2d(false)}>Vista 3D</button>
      <button className="action" aria-pressed={view2d} onClick={()=>setView2d(true)}>Plano 2D</button>
      {!view2d && <><button className="action" onClick={()=>setAngle(a=>a-25)} aria-label="Rotar izquierda">↶ Rotar</button><button className="action" onClick={()=>setAngle(a=>a+25)} aria-label="Rotar derecha">Rotar ↷</button><button className="action" onClick={()=>setZoom(z=>Math.min(1.75,z+.15))} aria-label="Acercar cámara">+ Zoom</button><button className="action" onClick={()=>setZoom(z=>Math.max(.62,z-.15))} aria-label="Alejar cámara">− Zoom</button><button className="action" onClick={()=>{setAngle(29);setZoom(1);setTilt(43)}}>Restablecer</button></>}
    </div>
    <div className="layout"><div>
      {view2d?<div className="grid2d" aria-label="Plano accesible de departamentos">{ROOMS.map(room=><button className="tile" key={room.id} aria-pressed={selectedId===room.id} onClick={()=>choose(room.id)}><strong>{room.name}</strong><p className="muted">{roomCount(room.id)} agentes {isDemo?'simulados':'registrados'}</p></button>)}</div>:<div className="viewport"><canvas ref={canvasRef} tabIndex={0} role="img" aria-label="Escena tridimensional giratoria con seis departamentos. Usa los botones de departamento del panel para una navegación accesible." onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={()=>drag.current=null} onWheel={e=>{if(e.ctrlKey){e.preventDefault();setZoom(z=>Math.max(.62,Math.min(1.75,z-e.deltaY*.001)))}}}/><div className="hint">Arrastra para girar · Pulsa una sala para seleccionarla · El plano 2D ofrece los mismos datos</div></div>}
      <div className="group" role="group" aria-label="Seleccionar departamento">{ROOMS.map(room=><button className="action" key={room.id} aria-pressed={selectedId===room.id} onClick={()=>choose(room.id)}>{room.name}</button>)}</div>
    </div><aside className="panel" aria-live="polite" aria-label="Información del departamento">
      <p className="muted">DEPARTAMENTO SELECCIONADO</p><h3 style={{margin:'0 0 12px'}}>{unit?.name||selected.name}</h3>
      <p className="muted">{unit?.description||'Espacio conceptual; la API organizativa aún no ha aportado datos para este departamento.'}</p>
      <div className="group"><button className="action" disabled={!onNavigate} onClick={()=>onNavigate?.('organization')}>Organización</button><button className="action" disabled={!onNavigate} onClick={()=>onNavigate?.('kanban')}>Kanban</button><button className="action" disabled={!onNavigate} onClick={()=>onNavigate?.('projects')}>Proyectos</button></div>
      <h4>Agentes {data?`(${agents.length})`:'— sin datos'}</h4>
      {!data&&<p className="muted">No existe acceso a agentes LIVE. Ningún marcador debe interpretarse como presencia operativa.</p>}
      {data&&agents.length===0&&<p className="muted">No hay agentes registrados en esta unidad.</p>}
      {agents.map(agent=><button className="agent" key={agent.id} aria-pressed={agent.id===selectedAgentId} onClick={()=>setSelectedAgentId(agent.id)}><strong>{agent.name}</strong><span className="muted" style={{display:'block'}}>{agent.type==='STANDING'?'Plantilla':'Temporal'} · {isDemo?'Telemetría simulada':`Heartbeat declarado: ${agent.heartbeatStatus}`}</span></button>)}
      {activeAgent&&<div style={{padding:12,border:'1px solid #50739c',borderRadius:10}}><h4>{activeAgent.name}</h4><p className="muted">{activeAgent.roleTitle}</p><p className="muted">{activeAgent.authorityBoundary}</p><p className="muted">Capacidades: {activeAgent.capabilities.map(c=>c.name).join(', ')||'No registradas'}</p><button className="action" onClick={()=>setSelectedAgentId(null)}>Cerrar ficha</button></div>}
    </aside></div>
  </section>;
};
