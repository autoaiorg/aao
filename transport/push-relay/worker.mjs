// Opt-in transport. No network/service is provisioned by importing this module.
const encoder = new TextEncoder();
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_BODY = 1024 * 1024;
const hex = bytes => [...new Uint8Array(bytes)].map(x => x.toString(16).padStart(2, '0')).join('');
async function key(secret) {
  return crypto.subtle.importKey('raw', encoder.encode(secret), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign', 'verify']);
}
export async function sign(secret, bytes) {
  return hex(await crypto.subtle.sign('HMAC', await key(secret), bytes));
}
async function verify(secret, bytes, signature) {
  if (!/^[0-9a-f]{64}$/.test(signature || '')) return false;
  return crypto.subtle.verify('HMAC', await key(secret), Uint8Array.from(signature.match(/../g), x => parseInt(x, 16)), bytes);
}
async function readBounded(request) {
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const parts = [];
  let size = 0;
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    size += value.length;
    if (size > MAX_BODY) { await reader.cancel(); throw new Error('size'); }
    parts.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) { body.set(part, offset); offset += part.length; }
  return body;
}
const reply = (status, value = '') => new Response(status === 204 ? null : value, {status, headers: {'Cache-Control': 'no-store'}});
export default {
  async fetch(request, env) {
    if (!env.DB || !env.GITHUB_SECRET || !env.PULL_SECRET ||
        encoder.encode(env.GITHUB_SECRET).length < 32 || encoder.encode(env.PULL_SECRET).length < 32 ||
        env.GITHUB_SECRET === env.PULL_SECRET) return reply(503);
    const url = new URL(request.url);
    if (url.protocol !== 'https:' || url.search) return reply(404);
    const ingest = request.method === 'POST' && url.pathname === '/github/push';
    const pull = request.method === 'GET' && url.pathname === '/receipts';
    const ack = request.method === 'POST' && /^\/receipts\/[0-9a-f-]+\/ack$/.test(url.pathname);
    if (!ingest && !pull && !ack) return reply(404);
    let body;
    try { body = await readBounded(request); } catch { return reply(413); }
    if (!ingest) {
      const timestamp = request.headers.get('X-AAO-Timestamp') || '';
      if (!/^\d{10}$/.test(timestamp) || Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) return reply(401);
      const digest = hex(await crypto.subtle.digest('SHA-256', body));
      const message = encoder.encode(`${request.method}\n${url.pathname}\n${timestamp}\n${digest}`);
      if (!await verify(env.PULL_SECRET, message, request.headers.get('X-AAO-Signature'))) return reply(401);
    }
    try {
      if (pull) {
        const result = await env.DB.prepare('SELECT delivery_id, body, signature FROM receipts WHERE acknowledged = 0 ORDER BY received_at, delivery_id LIMIT 1').all();
        return reply(200, JSON.stringify(result.results.map(row => ({delivery_id: row.delivery_id,
          ...encodeRow(row)}))));
      }
      if (ack) {
        const id = url.pathname.split('/')[2];
        if (!UUID.test(id) || body.length) return reply(400);
        await env.DB.prepare('UPDATE receipts SET acknowledged = 1 WHERE delivery_id = ?').bind(id).run();
        return reply(204);
      }
      const id = (request.headers.get('X-GitHub-Delivery') || '').toLowerCase();
      const signature = request.headers.get('X-Hub-Signature-256') || '';
      if (!UUID.test(id) || request.headers.get('X-GitHub-Event') !== 'push' ||
          !signature.startsWith('sha256=') || !await verify(env.GITHUB_SECRET, body, signature.slice(7))) return reply(401);
      const payload = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(body));
      const repository = payload.repository?.full_name;
      const allowed = JSON.parse(env.REPOSITORIES_JSON || '[]');
      if (!Array.isArray(allowed) || !allowed.includes(repository) || !payload.sender?.login || payload.deleted === true ||
          !/^refs\/heads\/.+/.test(payload.ref || '') || !/^[0-9a-f]{40}$/.test(payload.before || '') ||
          !/^[0-9a-f]{40}$/.test(payload.after || '')) return reply(400);
      const digest = hex(await crypto.subtle.digest('SHA-256', body));
      await env.DB.prepare('INSERT INTO receipts(delivery_id,digest,body,signature,repository) VALUES(?,?,?,?,?) ON CONFLICT(delivery_id) DO NOTHING')
        .bind(id, digest, body.buffer, signature, repository).run();
      const stored = await env.DB.prepare('SELECT digest FROM receipts WHERE delivery_id = ?').bind(id).first();
      return reply(stored?.digest === digest ? 202 : 409);
    } catch { return reply(503); } // Never log payloads, credentials, or exception details.
  }
};
function encodeRow(row) {
  const bytes = new Uint8Array(row.body);
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 8192)
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  return {body_base64: btoa(binary), signature: row.signature};
}
