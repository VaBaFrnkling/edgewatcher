const assert = require('node:assert/strict');
const api = process.env.API_URL || 'http://localhost:8000';
const red = process.env.NODERED_URL || 'http://localhost:1880';
async function json(url) { const r = await fetch(url, {signal: AbortSignal.timeout(15000)}); assert(r.ok, url + ': ' + r.status); return r.json(); }
async function main() {
 const devices = await json(api + '/devices'); assert(Array.isArray(devices) && devices.length, 'No known devices');
 for (const d of devices) {
  const root = api + '/devices/' + encodeURIComponent(d.hostname);
  const history = await json(root + '/history'); assert(Array.isArray(history));
  for (let i = 1; i < history.length; i++) assert(Date.parse(history[i].ts) >= Date.parse(history[i-1].ts), 'History is not chronological');
  const processes = await json(root + '/processes'); assert(Array.isArray(processes.top_cpu) && Array.isArray(processes.top_ram));
  assert(processes.top_cpu.length <= 15 && processes.top_ram.length <= 15);
  const rules = await json(root + '/rules'); assert(Number.isInteger(rules.version) && Array.isArray(rules.rules));
  console.log('PASS backend contracts: ' + d.hostname);
 }
 for (const page of ['fleet','alerts','device','rules']) { const r = await fetch(red + '/dashboard/' + page, {signal: AbortSignal.timeout(15000)}); assert(r.ok); assert((await r.text()).includes('<html')); console.log('PASS dashboard route: ' + page); }
 const flows = await json(red + '/flows'); assert(Array.isArray(flows)); const ids = new Set(flows.map(n => n.id)); assert.equal(ids.size, flows.length);
 for (const n of flows) for (const wire of n.wires || []) for (const id of wire) assert(ids.has(id), 'Broken wire: ' + id);
 const broker = flows.find(n => n.type === 'mqtt-broker' && n.clientid === 'nodered-dashboard'); assert(broker && broker.cleansession === false && broker.autoUnsubscribe === false);
 assert(flows.some(n => n.type === 'mqtt in' && n.topic === 'dashboard/alerts' && String(n.qos) === '1'));
 console.log('PASS flow wiring and persistent MQTT settings');
 const unknown = await fetch(api + '/devices/__qa_unknown_device__/history'); assert.equal(unknown.status, 404);
 console.log('PASS unknown-device response. Read-only smoke checks complete.');
}
main().catch(e => {console.error(e);process.exit(1);});
