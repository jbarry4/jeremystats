/* ==========================================================================
   radio.js -- something to work to.

   Curating six hundred candidates is a couple of hours of pressing a key and
   looking at a trace. People put music on for it, and switching windows to
   do that loses the keyboard focus the mode depends on -- so the player is
   in here, minimised to a pill, out of the way.

   The one thing in BARRY that reaches the internet
   ------------------------------------------------
   Everything else is local: the server binds to 127.0.0.1 and the README
   says nothing leaves the machine. A YouTube embed breaks that, so:

     it is off until somebody turns it on,
     it says what it is about to do before it does it, the first time, and
     nothing loads until then -- the iframe is not in the page while the
     radio is off, so a closed radio is not a connection.

   No API key and no oEmbed lookup: the embed is a plain iframe, which means
   the only thing sent is the request for the player itself. A station is a
   video id and a name, in a list anybody can add to.
   ========================================================================== */
'use strict';

BARRY.radio = (function () {
  /* Stations. A video id, because that is all an embed needs -- no key, no
     lookup, no account. Live streams rather than playlists: they do not end
     halfway through an afternoon. */
  const STATIONS = [
    { id: 'rFZHOHl-L8A', name: 'Lofi',
      what: 'lofi hip hop radio — beats to relax/study to (Lofi Girl)' },
    { id: '4xDzrJKXOOY', name: 'Synthwave',
      what: 'synthwave radio — beats to chill/game to (Lofi Girl)' },
    /* Not music, and not pretending to be: ten hours of a mouse eating
       M&Ms. Named for what it is, like the others -- and in a program
       whose every other window is a mouse, it earns its place. */
    { id: 'DA7wDV4MbNo', name: 'Mouse',
      what: 'Mouse Eating M&M’s, ten hours (10HoursMovies)' },
  ];

  const PREF = 'radio';

  let on = false;          // is the player in the page at all
  let small = true;        // minimised to a pill
  let station = STATIONS[0].id;
  let volume = 55;
  let agreed = false;      // has somebody said yes to the outbound request

  function store() {
    return (BARRY.prefs && BARRY.prefs.get) ? BARRY.prefs : null;
  }

  function remember() {
    /* Through the ordinary preferences, whose writes are coalesced -- and
       which are per machine, which is the point for the consent: agreeing
       on the desktop must not silently open a connection from the rig. */
    const p = store();
    if (!p) return;
    p.set(PREF, { small, station, volume, agreed });
  }

  async function load() {
    const st = store();
    if (st && st.load) { try { await st.load(); } catch (e) { /* defaults */ } }
    const p = (st && st.get(PREF, {})) || {};
    if (typeof p.small === 'boolean') small = p.small;
    if (typeof p.station === 'string') station = p.station;
    if (typeof p.volume === 'number') volume = p.volume;
    agreed = !!p.agreed;
    // Deliberately not restoring `on`: a reload should not start playing
    // audio at somebody who did not ask for it this time.
    on = false;
    paintChip();
  }

  function paintChip() {
    const chip = document.getElementById('radioBtn');
    if (!chip) return;
    chip.classList.toggle('on', on);
    const s = STATIONS.find((x) => x.id === station) || STATIONS[0];
    chip.title = on
      ? 'Radio on — ' + s.name + '. Click to turn it off.'
      : 'A radio to work to. Streams from YouTube, which is the only thing '
        + 'in BARRY that leaves this machine.';
    const label = chip.querySelector('span');
    if (label) label.textContent = on ? s.name : 'Radio';
  }

  /* The embed URL.

     `autoplay` because somebody just asked for it, and `playsinline` so a
     click does not go full screen.

     No `origin`. That parameter is for the IFrame Player API, which needs to
     postMessage back to a known origin -- this uses a plain iframe and talks
     to it not at all, and passing a loopback origin YouTube cannot resolve
     is one of the ways an embed comes back as "player configuration
     error". */
  function src() {
    const p = new URLSearchParams({
      autoplay: '1',
      playsinline: '1',
      rel: '0',
      modestbranding: '1',
    });
    return 'https://www.youtube.com/embed/' + encodeURIComponent(station)
         + '?' + p.toString();
  }

  function watchUrl() {
    return 'https://www.youtube.com/watch?v=' + encodeURIComponent(station);
  }

  async function turnOn() {
    if (!agreed) {
      const ok = await BARRY.confirm(
        'Play a radio stream from YouTube?',
        'This is the only part of BARRY that reaches the internet. '
        + 'Everything else runs against 127.0.0.1 and nothing leaves this '
        + 'machine — turning the radio on loads a player from '
        + 'youtube.com, which will see this machine’s address the way '
        + 'any web page would. No recording data, no logs and no filenames '
        + 'are sent: the only request is for the player itself.\n\n'
        + 'Asked once per machine. The radio stays off until you say so.',
        'Turn the radio on');
      if (!ok) return;
      agreed = true;
    }
    on = true;
    remember();
    render();
    paintChip();
    BARRY.activity.log('radio.on', { station: station });
  }

  function turnOff() {
    on = false;
    remember();
    render();
    paintChip();
    BARRY.activity.log('radio.off', {});
  }

  function toggle() { if (on) turnOff(); else turnOn(); }

  function pick(id) {
    if (station === id) return;
    station = id;
    remember();
    // The iframe is rebuilt, which is what changes the stream: there is no
    // API to talk to without loading YouTube's script, and loading a script
    // from them is a bigger promise than an iframe.
    render();
    paintChip();
    BARRY.activity.log('radio.station', { station: id });
  }

  /* How tall the body is when it is open, measured rather than declared.

     A height in the stylesheet cannot be right: the body is a player plus a
     station row plus a notice, and the number changes when the notice does.
     `1fr` -> `0fr` on a grid row cannot be right either -- a grid item will
     not shrink past its own content, and it stopped 15px short. And
     `display: none` after the movement, which is how the rail solves this,
     would risk detaching a playing iframe -- and keeping the audio going is
     the entire purpose of minimising.

     So: ask the element. Once, after a frame, when it has been laid out. */
  function measure() {
    const dock = document.getElementById('radioDock');
    const body = dock && dock.querySelector('.radio-body');
    if (!body) return;
    requestAnimationFrame(() => {
      // Read it open, whatever state it ends up in.
      const wasMini = dock.classList.contains('mini');
      if (wasMini) dock.classList.remove('mini');
      body.style.height = 'auto';
      const h = body.scrollHeight;
      body.style.height = h > 0 ? h + 'px' : '';
      if (wasMini) dock.classList.add('mini');
    });
  }

  /* Minimising must not rebuild the dock.

     `render()` empties it, which destroys the iframe -- and destroying the
     iframe stops the audio, which is the one thing minimising is for. So
     this toggles the class and relabels the button in place, and the player
     keeps playing behind a collapsed bar. */
  function setSmall(v) {
    small = !!v;
    remember();
    const dock = document.getElementById('radioDock');
    if (dock) dock.classList.toggle('mini', small);
    const btn = dock && dock.querySelector('.radio-x');
    if (btn) {
      btn.textContent = small ? '▴' : '▾';
      btn.title = small ? 'Show the player' : 'Minimise to the bar';
    }
  }

  function render() {
    const dock = document.getElementById('radioDock');
    if (!dock) return;
    dock.innerHTML = '';
    dock.classList.toggle('hidden', !on);
    dock.classList.toggle('mini', small);
    if (!on) return;

    const s = STATIONS.find((x) => x.id === station) || STATIONS[0];

    dock.appendChild(el('div', { class: 'radio-head' }, [
      el('span', { class: 'radio-dot' }),
      el('span', { class: 'radio-name', text: s.name,
                   title: s.what + ' — streamed from YouTube' }),
      el('div', { style: 'flex:1' }),
      el('button', {
        class: 'radio-x', text: small ? '▴' : '▾',
        title: small ? 'Show the player' : 'Minimise to the bar',
        onclick: () => setSmall(!small),
      }),
      el('button', {
        class: 'radio-x', text: '×', title: 'Turn the radio off',
        onclick: turnOff,
      }),
    ]));

    /* The stations, and the player. Both hidden by CSS when minimised
       rather than removed, because removing the iframe would stop the
       audio -- which is the one thing minimising must not do. */
    dock.appendChild(el('div', { class: 'radio-body' }, [
      el('div', { class: 'radio-stations' }, STATIONS.map((x) => el('button', {
        class: 'radio-pick' + (x.id === station ? ' on' : ''),
        text: x.name, title: x.what,
        onclick: () => pick(x.id),
      }))),
      /* Deliberately plain.

         This carried `referrerpolicy="no-referrer"` and a `sandbox`, added
         as privacy hardening, and the player answered with "Error 153 --
         video player configuration error". YouTube's embed validates the
         page it is embedded in from the Referer header, so suppressing the
         referrer suppresses the thing it checks; and sandboxing the frame
         interferes with the player's own configuration fetch.

         Neither bought anything real. A cross-origin iframe already cannot
         touch this page -- the browser guarantees that, not the sandbox
         attribute -- and the referrer it now sends is `127.0.0.1`, which
         says nothing about the recordings, the lab, or the machine. */
      el('iframe', {
        class: 'radio-frame', id: 'radioFrame',
        src: src(), title: s.name + ' — ' + s.what,
        allow: 'autoplay; encrypted-media; picture-in-picture',
        allowfullscreen: 'true',
      }),
      el('p', { class: 'radio-note' }, [
        el('span', { text: 'Streaming from youtube.com. Volume and playback '
                         + 'are in the player; BARRY only decides whether it '
                         + 'is here at all. If it refuses to play, the '
                         + 'stream itself has usually ended — ' }),
        /* A way out of an error only YouTube can explain. Their embed
           failures are a number and nothing else, and "153" is not
           something anybody should have to look up. */
        el('a', { class: 'radio-link', href: watchUrl(), target: '_blank',
                  rel: 'noopener noreferrer',
                  text: 'open it on YouTube' }),
        el('span', { text: ' to check.' }),
      ]),
    ]));

    // The height the collapse animates from, off the dock just built.
    measure();
  }

  function wire() {
    const chip = document.getElementById('radioBtn');
    if (chip) chip.addEventListener('click', toggle);
    load();
  }

  return {
    wire, load, render, toggle,
    /* For web/_dev/radio.html: it drives the real thing rather than a copy,
       and needs to get past the one-time question without a human. */
    stations: () => STATIONS.slice(),
    state: () => ({ on, small, station, volume, agreed }),
    _agree: (v) => { agreed = !!v; },
    turnOn, turnOff, pick, setSmall,
  };
})();
