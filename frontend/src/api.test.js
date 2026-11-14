import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { api, resetCsrf } from './api.js';
const originalFetch=globalThis.fetch;
const reply=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
beforeEach(()=>resetCsrf());
afterEach(()=>{globalThis.fetch=originalFetch});
test('expired CSRF is refreshed once before repeating a rejected write',async()=>{
 const requests=[];let tokens=0,writes=0;
 globalThis.fetch=async(path,opts)=>{
  requests.push([path,opts]);
  if(path==='/api/csrf')return reply({token:++tokens===1?'old':'new'});
  return ++writes===1?reply({code:'csrf_failed'},400):reply({id:17});
 };
 assert.deepEqual(await api('/teams/1/tasks','POST',{title:'Готово'}),{id:17});
 assert.equal(tokens,2);assert.equal(writes,2);
 assert.equal(requests.at(-1)[1].headers['X-CSRFToken'],'new');
});
test('ordinary write failures are not repeated',async()=>{
 let writes=0;
 globalThis.fetch=async path=>path==='/api/csrf'?reply({token:'ok'}):(writes++,reply({error:'Дедлайн завершён'},409));
 await assert.rejects(()=>api('/teams/1/submit','POST',{}),/Дедлайн завершён/);
 assert.equal(writes,1);
});
test('server down and non-JSON proxy responses explain what to do',async()=>{
 globalThis.fetch=async()=>{throw new TypeError('Failed to fetch')};
 await assert.rejects(()=>api('/me'),/Flask запущен/);
 globalThis.fetch=async()=>new Response('<html>Bad Gateway</html>',{status:502});
 await assert.rejects(()=>api('/me'),/терминал Flask/);
});
