/* The password gate: every page, file and function of the site but the
   sign-in page and its function needs the cookie api/login.js issues. Pages
   without it go to the sign-in page; functions answer 401. */
import { next } from '@vercel/functions';
import { COOKIE, cookieOf, valid } from './lib/gate.js';

export const config = {
  matcher: ['/((?!login\\.html|api/login|favicon\\.ico).*)'],
};

export default async function middleware(request) {
  if (await valid(process.env.SITE_SECRET, cookieOf(request.headers.get('cookie'), COOKIE))) return next();
  const url = new URL(request.url);
  if (url.pathname.startsWith('/api/')) {
    return new Response(JSON.stringify({ ok: false, error: 'Sign in first.' }),
      { status: 401, headers: { 'content-type': 'application/json; charset=utf-8' } });
  }
  const to = new URL('/login.html', url);
  to.searchParams.set('next', url.pathname + url.search);
  return Response.redirect(to, 302);
}
