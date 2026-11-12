/* The open questions: one list anyone with the password can add to,
   answer and close. Kept in the lab's Supabase, table review_questions
   (BARRY GUI/supabase/22_review_questions.sql), through PostgREST with a
   server-side key that lives only in this project's environment
   (SUPABASE_URL, SUPABASE_SERVICE_KEY) and never reaches a browser.

     GET                                   every question, oldest first
     POST  {text, asked_by, about?}        a new one
     PATCH {id, status?, answer?, answered_by?}   answered, closed, reopened */
const TABLE = 'review_questions';
const STATUS = ['open', 'answered', 'closed'];
const COLS = 'id,text,asked_by,about,status,answer,answered_by,created_at,updated_at';

function db(path, init) {
  const url = process.env.SUPABASE_URL, key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new Error('The questions list is not connected yet (SUPABASE_URL and SUPABASE_SERVICE_KEY).');
  return fetch(url.replace(/\/$/, '') + '/rest/v1/' + path, Object.assign({}, init, {
    headers: Object.assign({ apikey: key, Authorization: 'Bearer ' + key, 'Content-Type': 'application/json',
                             Prefer: 'return=representation' }, (init && init.headers) || {}),
  }));
}
const str = (v, max) => (typeof v === 'string' ? v.trim().slice(0, max) : '');

export default async function handler(req, res) {
  try {
    let r;
    if (req.method === 'GET') {
      r = await db(TABLE + '?select=' + COLS + '&order=created_at.asc', { method: 'GET' });
    } else if (req.method === 'POST') {
      const b = req.body || {};
      const text = str(b.text, 2000), by = str(b.asked_by, 80), about = str(b.about, 300);
      if (!text) { res.status(400).json({ ok: false, error: 'Write the question first.' }); return; }
      if (!by) { res.status(400).json({ ok: false, error: 'Say who is asking.' }); return; }
      r = await db(TABLE + '?select=' + COLS, { method: 'POST', body: JSON.stringify({ text, asked_by: by, about: about || null }) });
    } else if (req.method === 'PATCH') {
      const b = req.body || {};
      const id = Number(b.id);
      if (!Number.isInteger(id) || id < 1) { res.status(400).json({ ok: false, error: 'Which question?' }); return; }
      const patch = { updated_at: new Date().toISOString() };
      if (b.status != null) {
        if (!STATUS.includes(b.status)) { res.status(400).json({ ok: false, error: 'A question is open, answered or closed.' }); return; }
        patch.status = b.status;
      }
      if (b.answer != null) patch.answer = str(b.answer, 4000) || null;
      if (b.answered_by != null) patch.answered_by = str(b.answered_by, 80) || null;
      r = await db(TABLE + '?id=eq.' + id + '&select=' + COLS, { method: 'PATCH', body: JSON.stringify(patch) });
    } else {
      res.status(405).json({ ok: false, error: 'GET, POST or PATCH.' });
      return;
    }
    const body = await r.json().catch(() => null);
    if (!r.ok) {
      res.status(502).json({ ok: false, error: 'The lab database said: ' + ((body && (body.message || body.hint)) || ('HTTP ' + r.status)) });
      return;
    }
    res.status(200).json({ ok: true, questions: Array.isArray(body) ? body : [] });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
}
