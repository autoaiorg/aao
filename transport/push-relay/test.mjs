import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker, {sign} from './worker.mjs';
const github = 'g'.repeat(32), pull = 'p'.repeat(32);
const id = '11111111-1111-4111-8111-111111111111';
const bytes = value => new TextEncoder().encode(value);
function setup() {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('./schema.sql', import.meta.url), 'utf8'));
  const env = {GITHUB_SECRET: github, PULL_SECRET: pull, REPOSITORIES_JSON: '["o/r"]',
    DB: {prepare(sql) { let values=[]; return {bind(...args){values=args.map(x => x instanceof ArrayBuffer ? new Uint8Array(x) : x);return this;},
      async run(){return db.prepare(sql).run(...values);},
      async first(){return db.prepare(sql).get(...values);},
      async all(){return {results: db.prepare(sql).all(...values)};}};}}};
  return {db,env};
}
const payload = () => JSON.stringify({repository:{full_name:'o/r'}, sender:{login:'app[bot]'}, ref:'refs/heads/x', before:'0'.repeat(40), after:'a'.repeat(40)});
async function push(env, body=payload(), signature=null) {
  return worker.fetch(new Request('https://relay/github/push', {method:'POST',body,
    headers:{'X-GitHub-Delivery':id,'X-GitHub-Event':'push','X-Hub-Signature-256':signature || `sha256=${await sign(github,bytes(body))}`}}),env);
}
async function call(env, path='/receipts', method='GET', timestamp=String(Math.floor(Date.now()/1000))) {
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes(''))), x=>x.toString(16).padStart(2,'0')).join('');
  const signature = await sign(pull,bytes(`${method}\n${path}\n${timestamp}\n${digest}`));
  return worker.fetch(new Request(`https://relay${path}`,{method, headers:{'X-AAO-Timestamp':timestamp,'X-AAO-Signature':signature}}),env);
}
test('original bytes survive durable SQL/pull; ack retains tombstone and stops delivery',async()=>{
  const {env,db}=setup(); const body=payload()+'\n  ';
  assert.equal((await push(env,body)).status,202);
  assert.equal((await push(env,body)).status,202);
  const rows=await (await call(env)).json();
  assert.equal(atob(rows[0].body_base64),body);
  assert.equal(rows[0].signature,`sha256=${await sign(github,bytes(body))}`);
  assert.equal((await call(env,`/receipts/${id}/ack`,'POST')).status,204);
  assert.deepEqual(await (await call(env)).json(),[]);
  assert.equal(db.prepare('SELECT count(*) AS n FROM receipts').get().n,1);
  assert.equal((await push(env,body)).status,202);
});
test('conflict, invalid HMAC, repo and size rejected; no replacement',async()=>{
  const {env}=setup(); assert.equal((await push(env)).status,202);
  assert.equal((await push(env,payload()+' ')).status,409);
  assert.equal((await push(env,payload(),'sha256='+'0'.repeat(64))).status,401);
  assert.equal((await push(env,payload().replace('o/r','o/other'))).status,400);
  assert.equal((await push(env,'x'.repeat(1024*1024+1))).status,413);
});
test('private pull/ack require valid fresh HMAC',async()=>{
  const {env}=setup();
  assert.equal((await worker.fetch(new Request('https://relay/receipts'),env)).status,401);
  assert.equal((await worker.fetch(new Request(`https://relay/receipts/${id}/ack`,{method:'POST'}),env)).status,401);
  assert.equal((await call(env,'/receipts','GET','1000000000')).status,401);
});
test('unacknowledged data does not expire; capacity fails closed',async()=>{
  const {env,db}=setup(); await push(env);
  db.prepare("UPDATE receipts SET received_at='2000-01-01'").run();
  assert.equal((await (await call(env)).json()).length,1);
  db.exec("CREATE TRIGGER full BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT,'full'); END");
  assert.equal((await push(env)).status,503);
  assert.equal(db.prepare('SELECT count(*) AS n FROM receipts').get().n,1);
});

test('real schema capacity prevents new IDs but preserves idempotent retry',async()=>{
  const {env,db}=setup(); await push(env);
  const insert=db.prepare("INSERT INTO receipts(delivery_id,digest,body,signature,repository) VALUES(?,'x',x'01','x','o/r')");
  db.exec('BEGIN');
  for (let i=0;i<9999;i++) insert.run(`test-${i}`);
  db.exec('COMMIT');
  assert.equal((await push(env)).status,202);
  assert.throws(()=>insert.run('overflow'),/capacity exceeded/);
  assert.equal(db.prepare('SELECT count(*) AS n FROM receipts').get().n,10000);
});
