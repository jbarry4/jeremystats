/* POST {password}: the site's one password (SITE_PASSWORD), answered with
   the gate's cookie for 30 days. A wrong one waits a moment first. */
import { COOKIE, DAYS, samePassword, sign } from '../lib/gate.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ ok: false, error: 'POST the password.' });
    return;
  }
  const secret = process.env.SITE_SECRET, want = process.env.SITE_PASSWORD;
  if (!secret || !want) {
    res.status(500).json({ ok: false, error: 'This site has no password set yet (SITE_PASSWORD and SITE_SECRET).' });
    return;
  }
  const given = String(((req.body && typeof req.body === 'object') ? req.body.password : '') || '');
  if (!(await samePassword(secret, given, want))) {
    await new Promise((r) => setTimeout(r, 600));
    res.status(401).json({ ok: false, error: 'That is not the password.' });
    return;
  }
  const until = Date.now() + DAYS * 864e5;
  res.setHeader('Set-Cookie', COOKIE + '=' + (await sign(secret, until)) + '; Path=/; Max-Age=' + DAYS * 86400
    + '; HttpOnly; Secure; SameSite=Lax');
  res.status(200).json({ ok: true });
}
