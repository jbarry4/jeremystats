/* The password gate's arithmetic, shared by the middleware (which checks
   every request) and api/login.js (which issues the cookie). Web Crypto
   only, so the same file runs at the edge and in a Node function.

   The cookie is `<until>.<hex HMAC-SHA256(SITE_SECRET, "dewey-monolith:" +
   until)>`: it says when it ends and proves the site issued it, and it
   holds nothing else -- no name, no password. Changing SITE_SECRET signs
   everybody out. */
const enc = new TextEncoder();
export const COOKIE = 'dm_gate';
export const DAYS = 30;

async function key(secret) {
  return crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);
}
const hex = (buf) => Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');

export async function sign(secret, until) {
  const k = await key(secret);
  return until + '.' + hex(await crypto.subtle.sign('HMAC', k, enc.encode('dewey-monolith:' + until)));
}

export async function valid(secret, token, now = Date.now()) {
  if (!secret || !token) return false;
  const [until, mac] = String(token).split('.');
  if (!/^\d{1,16}$/.test(until || '') || !/^[0-9a-f]{64}$/.test(mac || '') || Number(until) < now) return false;
  const k = await key(secret);
  const bytes = new Uint8Array(mac.match(/../g).map((h) => parseInt(h, 16)));
  return crypto.subtle.verify('HMAC', k, bytes, enc.encode('dewey-monolith:' + until));
}

/* The password, compared in constant time: the expected one's MAC verified
   against the given one. */
export async function samePassword(secret, given, want) {
  if (!secret || !want || typeof given !== 'string') return false;
  const k = await key(secret);
  const mac = await crypto.subtle.sign('HMAC', k, enc.encode(want));
  return crypto.subtle.verify('HMAC', k, mac, enc.encode(given));
}

export function cookieOf(header, name = COOKIE) {
  for (const part of String(header || '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

/* Where to go after signing in: a path on this site, never another host. */
export function safeNext(next) {
  const s = String(next || '/');
  return s.startsWith('/') && !s.startsWith('//') && !s.startsWith('/\\') ? s : '/';
}
