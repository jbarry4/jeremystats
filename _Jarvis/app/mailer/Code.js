/**
 * Jarvis Mailer: sends Jarvis's "Last 7 days' work" printout from the lab's
 * Google account (barrylabuvm@gmail.com).
 *
 * Jarvis (backend/weekly.py, tools/weekly_email.py) posts the printout here
 * as JSON and this sends it. Two locks, both in this file, so neither rests
 * on Jarvis's word:
 *
 *   - The secret. Only its SHA-256 is written here. Jarvis keeps the secret
 *     on the computer that sends (%LOCALAPPDATA%\Jarvis\weekly\mail.json).
 *   - The recipients. Only an address whose SHA-256 (lower case) is in
 *     ALLOWED can be mailed, so a leaked secret still cannot mail anyone
 *     else. The addresses are not written out because this file is in a
 *     public repository.
 *
 * Once, signed in as barrylabuvm@gmail.com: open this project, choose
 * `authorize` in the toolbar, Run, and Allow. That grants "send email as
 * you"; nothing can send until it is done.
 *
 * To change who may receive it: add the address's hash to ALLOWED
 *   python -c "import hashlib;print(hashlib.sha256('a@uvm.edu'.lower().encode()).hexdigest())"
 * then `clasp push` and `clasp deploy -i <deployment id>` from this folder,
 * and add the address to the lists in mail.json.
 */
const SECRET_SHA256 = '1d48f495211dc2b57979a3ed3e1013345075eff80436a22595374c0fa0a9cbf0';
const ALLOWED = [
  '76e36d7575322f2b36dcd0ceba0939cdb4beeb78cda5befa68a108052f5177c9',
  'b0b76e5ab6920b0b1b02112d39a2b033c2bee32ebc4c78a61378c2210e063552',
  '57f68ebdbee480883402ae3439a665cb58975c0903f97631079a8290246cde96',
  '2cbb3e5862cdcc05a59042819100f18f32a9aa9d5c76be717734b5200fe91196',
];
const MAX_BODY = 400000;
const SENDER = 'Jarvis (Barry Lab)';

function doPost(e) {
  try {
    const body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (body.kind !== 'weekly_email') throw new Error('this web app only sends the weekly email');
    if (!body.secret || sha256_(String(body.secret)) !== SECRET_SHA256) throw new Error('the secret is wrong');
    const to = (body.to || []).map(function (a) { return String(a).trim(); }).filter(Boolean);
    if (!to.length) throw new Error('nobody to send it to');
    const refused = to.filter(function (a) { return ALLOWED.indexOf(sha256_(a.toLowerCase())) < 0; });
    if (refused.length) throw new Error(refused.length + ' address(es) are not on the list this mailer may send to');
    const subject = String(body.subject || '').slice(0, 250);
    const text = String(body.text || '');
    const html = String(body.html || '');
    if (!subject || !text) throw new Error('a subject and a text body are needed');
    if (text.length > MAX_BODY || html.length > MAX_BODY) throw new Error('the email is too long');
    const msg = { to: to.join(','), subject: subject, body: text, name: SENDER };
    if (html) msg.htmlBody = html;
    MailApp.sendEmail(msg);
    return json_({ ok: true, kind: 'weekly_email', sent: to.length,
                   quota: MailApp.getRemainingDailyQuota() });
  } catch (err) {
    return json_({ ok: false, kind: 'weekly_email', error: String(err && err.message || err) });
  }
}

/* Is it up, and allowed to send? Jarvis asks before it relies on it. */
function doGet() {
  return json_({ ok: true, kind: 'weekly_email', quota: MailApp.getRemainingDailyQuota() });
}

/* Run once from the editor, as barrylabuvm@gmail.com, to allow sending. */
function authorize() {
  Logger.log('Jarvis Mailer may send %s more emails today.', MailApp.getRemainingDailyQuota());
}

function sha256_(s) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, s, Utilities.Charset.UTF_8)
    .map(function (b) { return ('0' + ((b + 256) % 256).toString(16)).slice(-2); })
    .join('');
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
