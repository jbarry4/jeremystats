/* The review site's functions and gate, run under Node with a stand-in for
   the one package they import (tools/check_review.py copies the site, the
   stand-in and this file into a temporary folder and runs it there).
   Prints "ok"/"FAIL" lines and a last line "N passed, M failed". */
import { COOKIE, cookieOf, safeNext, samePassword, sign, valid } from './lib/gate.js';
import middleware from './middleware.js';
import login from './api/login.js';
import questions from './api/questions.js';

let ok = 0, bad = 0;
const check = (name, cond, detail) => {
  if (cond) { ok++; console.log('  ok    ' + name); } else { bad++; console.log('  FAIL  ' + name + (detail === undefined ? '' : '   [' + JSON.stringify(detail) + ']')); }
};
function res() {
  const r = { code: 200, headers: {}, body: null };
  r.status = (c) => { r.code = c; return r; };
  r.json = (b) => { r.body = b; return r; };
  r.send = (b) => { r.body = b; return r; };
  r.setHeader = (k, v) => { r.headers[k.toLowerCase()] = v; };
  return r;
}

console.log('The gate');
const S = 'test-secret-' + 'x'.repeat(20);
const tok = await sign(S, Date.now() + 60000);
check('a cookie it signed is valid', await valid(S, tok));
check('an expired one is not', !(await valid(S, await sign(S, Date.now() - 1))));
check('a tampered one is not', !(await valid(S, tok.replace(/.$/, (c) => (c === '0' ? '1' : '0')))));
check('one signed with another secret is not', !(await valid(S, await sign('other-secret', Date.now() + 60000))));
check('nothing, or rubbish, is not', !(await valid(S, null)) && !(await valid(S, 'abc.def')) && !(await valid('', tok)));
check('the password: right, wrong, empty', (await samePassword(S, 'hunter2', 'hunter2')) && !(await samePassword(S, 'hunter3', 'hunter2'))
      && !(await samePassword(S, '', 'hunter2')));
check('the cookie is found among others', cookieOf('a=1; ' + COOKIE + '=' + tok + '; b=2') === tok && cookieOf('a=1') === null);
check('after signing in, only a path on this site', safeNext('/monolith.html#x') === '/monolith.html#x' && safeNext('//evil.com') === '/'
      && safeNext('https://evil.com') === '/' && safeNext('/\\evil.com') === '/');

console.log('The middleware');
process.env.SITE_SECRET = S;
const req = (path, cookie) => new Request('https://dewey-monolith.example' + path, { headers: cookie ? { cookie } : {} });
let r = await middleware(req('/monolith.html'));
check('no cookie: a page goes to sign-in, saying where it was going', r.status === 302
      && /\/login\.html\?next=%2Fmonolith\.html/.test(r.headers.get('location')), r.headers.get('location'));
r = await middleware(req('/api/questions'));
check('no cookie: a function answers 401', r.status === 401);
r = await middleware(req('/data/edges_raw.f32z'));
check('no cookie: the data is gated too', r.status === 302);
r = await middleware(req('/monolith.html', COOKIE + '=' + tok));
check('with the cookie: on through', r.headers.get('x-middleware-next') === '1');
r = await middleware(req('/monolith.html', COOKIE + '=' + tok.slice(0, -2) + 'ff'));
check('with a forged cookie: sign-in', r.status === 302);
const { config } = await import('./middleware.js');
const m = new RegExp('^' + config.matcher[0] + '$');
check('the sign-in page and its function are not gated, everything else is', !m.test('/login.html') && !m.test('/api/login')
      && m.test('/') && m.test('/monolith.html') && m.test('/api/questions') && m.test('/data/summary.json') && m.test('/api/logout'));

console.log('Signing in');
process.env.SITE_PASSWORD = 'hunter2';
let rr = res();
await login({ method: 'POST', body: { password: 'hunter2' } }, rr);
check('the right password: a cookie for 30 days, HttpOnly, Secure', rr.code === 200 && /^dm_gate=\d+\.[0-9a-f]{64}; Path=\/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax$/.test(rr.headers['set-cookie']),
      rr.headers['set-cookie']);
check('and the cookie it gives passes the gate', await valid(S, rr.headers['set-cookie'].split(';')[0].split('=')[1]));
rr = res();
await login({ method: 'POST', body: { password: 'nope' } }, rr);
check('a wrong one: 401, no cookie', rr.code === 401 && !rr.headers['set-cookie']);
rr = res();
await login({ method: 'GET' }, rr);
check('anything but POST: 405', rr.code === 405);
delete process.env.SITE_PASSWORD;
rr = res();
await login({ method: 'POST', body: { password: 'hunter2' } }, rr);
check('no password set on the site: said, never open', rr.code === 500 && /no password set/.test(rr.body.error));

console.log('The open questions');
const calls = [];
globalThis.fetch = async (url, init) => {
  calls.push({ url, init });
  const body = init.method === 'GET' ? [{ id: 1, text: 'q', status: 'open' }] : [Object.assign({ id: 2 }, JSON.parse(init.body))];
  return new Response(JSON.stringify(body), { status: 200 });
};
rr = res();
await questions({ method: 'GET' }, rr);
check('not connected yet: said', rr.code === 500 && /not connected/.test(rr.body.error), rr.body);
process.env.SUPABASE_URL = 'https://lab.supabase.co/';
process.env.SUPABASE_SERVICE_KEY = 'service-key';
rr = res();
await questions({ method: 'GET' }, rr);
check('the list, oldest first, from the table with the service key', rr.code === 200 && rr.body.questions.length === 1
      && /^https:\/\/lab\.supabase\.co\/rest\/v1\/review_questions\?select=.*&order=created_at\.asc$/.test(calls[0].url)
      && calls[0].init.headers.apikey === 'service-key', calls[0] && calls[0].url);
rr = res();
await questions({ method: 'POST', body: { text: '  Why 4 rats?  ', asked_by: 'Travis', about: 'Histology v2', status: 'closed', id: 99 } }, rr);
const posted = JSON.parse(calls[1].init.body);
check('a new one: only its words, who and what about (trimmed); never its id or status', rr.code === 200
      && JSON.stringify(posted) === JSON.stringify({ text: 'Why 4 rats?', asked_by: 'Travis', about: 'Histology v2' }), posted);
rr = res();
await questions({ method: 'POST', body: { text: '   ', asked_by: 'Travis' } }, rr);
check('an empty question is refused', rr.code === 400 && calls.length === 2);
rr = res();
await questions({ method: 'POST', body: { text: 'x'.repeat(5000), asked_by: 'y'.repeat(500) } }, rr);
const long = JSON.parse(calls[2].init.body);
check('a long one is cut to the table’s limits', long.text.length === 2000 && long.asked_by.length === 80);
rr = res();
await questions({ method: 'PATCH', body: { id: 7, status: 'answered', answer: 'Because.', answered_by: 'Travis', text: 'rewritten' } }, rr);
const patched = JSON.parse(calls[3].init.body);
check('answered: by id, its status, answer and who; the question itself is not rewritten', /review_questions\?id=eq\.7&/.test(calls[3].url)
      && patched.status === 'answered' && patched.answer === 'Because.' && patched.answered_by === 'Travis' && !('text' in patched) && patched.updated_at, patched);
rr = res();
await questions({ method: 'PATCH', body: { id: 7, status: 'deleted' } }, rr);
check('a status that is not one is refused', rr.code === 400 && calls.length === 4);
rr = res();
await questions({ method: 'PATCH', body: { id: '7; drop table' } }, rr);
check('an id that is not one is refused', rr.code === 400 && calls.length === 4);
rr = res();
await questions({ method: 'DELETE' }, rr);
check('nothing is deleted', rr.code === 405);

console.log(ok + ' passed, ' + bad + ' failed');
