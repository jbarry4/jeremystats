/* Sign out: the cookie is cleared, and the page goes back to sign-in. */
import { COOKIE } from '../lib/gate.js';

export default function handler(req, res) {
  res.setHeader('Set-Cookie', COOKIE + '=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax');
  res.status(200).json({ ok: true });
}
