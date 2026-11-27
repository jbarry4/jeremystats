"""Render "Watching a seizure spread", the standalone video of Seahorse's
seizure story (KCNT1 mouse 459) for an outside audience, from the app itself.

    python tools/seahorse/film/render_film.py --out film.mp4      the whole film, with its music and sounds
    python tools/seahorse/film/render_film.py --stills 3,40,90    pictures at these film seconds
    python tools/seahorse/film/render_film.py --scene spread --stills 120,130
    python tools/seahorse/film/render_film.py --out part.mp4 --from 60 --to 90 --silent
    python tools/seahorse/film/soundtrack.py CUES.json --mux PICTURE.mp4 film.mp4    new sound, same picture

How: a private Jarvis server and a headless Chromium on the GPU (ANGLE/D3D11)
open Seahorse at 1280x720 CSS px at 1.5x device pixels (1920x1080 frames,
text sized for a screen across a room). vt.js stops the page's clocks, and
film.js (the director: scenes, words, the drawings over the stage) moves the
film on one frame at a time, so every frame is drawn at exactly its moment
however long the laptop takes; each frame is captured as a PNG and piped into
ffmpeg (H.264, yuv420p BT.709). film.js also lists its sound cues (where the
picture changes angle, the music's moods); soundtrack.py writes the music and
the effects from them, and the two are put together at the end. The picture
alone is kept beside the film (NAME.picture.mp4) with the cues (NAME.cues.json),
so the sound can be redone in a minute. The 3:13 first cut took 23 to 33 minutes
on the lab laptop (2026-11-26); the 4:42 second cut 25 (2026-11-27). --script
writes every word on screen with its time (the cards too), for proofreading.

The words are in film.js (scene(...) cap: [from, to, main, sub]). The images
are in assets/: the lab's logo and the 2026 KCNT1 conference artwork from
kcnt1epilepsy.org. Preferences writes are answered here and never reach the
server; the theme is set to UVM Dark for the film without being saved."""
import argparse, base64, json, logging, os, subprocess, sys, tempfile, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "tools"))
import ui_shots  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SH = "BARRY.views.seahorse"
ST = SH + "._state"
W, H, DPR = 1280, 720, 1.5
FULL_CSS = r"""
#view-seahorse .sh-stage { position: fixed !important; left: 0 !important; top: 0 !important;
  width: 100vw !important; height: 100vh !important; z-index: 2147480000 !important; }
#view-seahorse .sh-dock, #view-seahorse .sh-nav, #view-seahorse .sh-tools, #view-seahorse .sh-minicap,
#view-seahorse .sh-miniframe, #view-seahorse .sh-tip, #view-seahorse .sh-inset { display: none !important; }
*, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; }
"""


def data_url(path):
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


def start_server():
    port = ui_shots.free_port()
    threading.Thread(target=ui_shots.serve, args=(port,), daemon=True).start()
    while not ui_shots.port_open(port):
        time.sleep(0.25)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    return port


def open_seahorse(pw, port, headless=True):
    br = pw.chromium.launch(headless=headless, args=["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
                                                     "--force-color-profile=srgb", "--hide-scrollbars"])
    ctx = br.new_context(viewport={"width": W, "height": H}, device_scale_factor=DPR, color_scheme="dark")
    ctx.add_init_script(open(os.path.join(HERE, "vt.js"), encoding="utf-8").read())
    page = ctx.new_page()
    page.route("**/api/prefs*", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok": true}')
               if r.request.method == "POST" else r.continue_())
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)[:400]))
    page.goto("http://127.0.0.1:%d/?menu=0" % port)
    page.wait_for_function("!document.getElementById('boot') || document.getElementById('boot').classList.contains('gone') || "
                           "getComputedStyle(document.getElementById('boot')).display === 'none'", timeout=120000)
    page.evaluate("setView('seahorse')")
    page.wait_for_function("BARRY.views.seahorse && BARRY.views.seahorse._state.stage && BARRY.views.seahorse._state.volumesUp === true",
                           timeout=300000)
    page.add_style_tag(content=FULL_CSS)
    return br, ctx, page, errs


def setup(page):
    """Everything that takes real time happens here, before the clocks stop: the
    theme, the story's data, the crowd of cells, the 3D programs."""
    page.evaluate("applyTheme('dark', false)")
    time.sleep(0.5)
    page.evaluate(ST + ".labels = false")
    page.evaluate(SH + "._do.startStory('m459')")
    page.wait_for_function("(() => { const P = %s.play; return P && P.kind === 'story' && P.stop && !P.moving; })()" % ST, timeout=180000)
    page.evaluate(ST + ".stage.holdFull(true)")
    page.add_script_tag(content=open(os.path.join(HERE, "film.js"), encoding="utf-8").read())
    assets = {"lab": data_url(os.path.join(HERE, "assets", "lab_logo.png")),
              "art": data_url(os.path.join(HERE, "assets", "kcnt1_2026_rising_higher_together.png"))}
    info = page.evaluate("(a) => FILM.init(a)", assets)
    # visit what the film will show, so the crowd is built and the programs compiled
    for key, secs in [("film_hpf", 2.5), ("film_probe", 1.5), ("loop", 2.5), ("global", 2.0), ("film_dentate", 1.0), ("film_brain", 1.5)]:
        page.evaluate("(() => { const st = BARRY.shStory.stories()[0].stops; %s.slice.pos = -999; %s._do.storyGo(st.findIndex((s) => s.key === '%s')); })()" % (ST, SH, key))
        time.sleep(secs)
        if key == "film_hpf":
            page.wait_for_function("!!%s.crowdN" % ST, timeout=120000)
    page.wait_for_function("(() => { const P = %s.play; return P && !P.moving; })()" % ST, timeout=120000)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="the MP4 to write")
    ap.add_argument("--stills", default="", help="film seconds to save as PNGs")
    ap.add_argument("--every", type=float, default=0, help="a PNG every this many seconds")
    ap.add_argument("--scene", default="", help="start at this scene")
    ap.add_argument("--from", dest="t_from", type=float, default=0)
    ap.add_argument("--to", dest="t_to", type=float, default=0)
    ap.add_argument("--stills-dir", default=os.path.join(tempfile.gettempdir(), "seahorse-film-stills"))
    ap.add_argument("--script", default="", help="write the film's words, with their times, to this text file")
    ap.add_argument("--cues", default="", help="write the sound cues (JSON) here (with --out: beside it)")
    ap.add_argument("--silent", action="store_true", help="no music or effects: a silent audio track")
    ap.add_argument("--crf", default="15")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    port = start_server()
    os.makedirs(a.stills_dir, exist_ok=True)
    with sync_playwright() as pw:
        br, ctx, page, errs = open_seahorse(pw, port, headless=not a.headed)
        cdp = ctx.new_cdp_session(page)
        t0 = time.time()
        info = setup(page)
        print("film: %.1f s, %d frames; setup %.0f s" % (info["total"], info["frames"], time.time() - t0), flush=True)
        stem = os.path.splitext(a.out)[0] if a.out else ""
        cues_path = a.cues or (stem + ".cues.json" if a.out else "")
        if cues_path:
            json.dump(page.evaluate("FILM.cues()"), open(cues_path, "w", encoding="utf-8"), indent=1)
            print("wrote", cues_path)
        if a.script:
            mmss = lambda s: "%d:%04.1f" % (s // 60, s % 60)  # noqa: E731
            lines, chap = [], None
            for c in page.evaluate("FILM.script()"):
                head = c["chapter"] or {"title": "Title", "end": "End"}.get(c["scene"], "")
                if head != chap:
                    chap = head
                    lines.append("\n" + head.upper())
                if c.get("card"):
                    # a card: its kind, then each of its lines
                    lines.append("%s-%s  [%s]" % (mmss(c["from"]), mmss(c["to"]), c["card"][0]) + "".join("\n             " + s for s in c["card"][1:]))
                else:
                    lines.append("%s-%s  %s" % (mmss(c["from"]), mmss(c["to"]), c["main"]) + ("\n             (%s)" % c["sub"] if c["sub"] else ""))
            open(a.script, "w", encoding="utf-8").write("Watching a seizure spread: the words on screen\n" + "\n".join(lines).lstrip("\n") + "\n")
            print("wrote", a.script)
        if not (a.out or a.stills or a.every):
            br.close()
            return
        if a.scene:
            page.evaluate("FILM.seekScene(%s)" % json.dumps(a.scene))
        elif a.t_from:
            page.evaluate("FILM.frame = %d" % round(a.t_from * 30))
        start = page.evaluate("FILM.frame")
        end = round((a.t_to or info["total"]) * 30)
        want = set()
        if a.stills:
            want = {round(float(x) * 30) for x in a.stills.split(",") if x.strip()}
            if not a.out:
                end = max(want) + 1
        elif a.every:
            want = set(range(start, end, max(1, round(a.every * 30))))
        page.evaluate("__vt.start()")
        enc, picture = None, ""
        if a.out:
            picture = stem + ".picture.mp4"
            vf = "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", "30", "-c:v", "png", "-i", "-"]
            if a.silent:
                cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-map", "0:v", "-map", "1:a", "-shortest", "-c:a", "aac", "-b:a", "96k"]
            cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", a.crf, "-profile:v", "high", "-tune", "film",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                    "-movflags", "+faststart", a.out if a.silent else picture]
            enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        tl, n = time.time(), 0
        for f in range(start, end):
            r = page.evaluate("FILM.step()")
            if enc or f in want:
                data = base64.b64decode(cdp.send("Page.captureScreenshot", {"format": "png", "fromSurface": True, "optimizeForSpeed": True,
                                                                            "clip": {"x": 0, "y": 0, "width": W, "height": H, "scale": DPR}})["data"])
                if enc:
                    enc.stdin.write(data)
                if f in want:
                    open(os.path.join(a.stills_dir, "t%06.2f_%s.png" % (f / 30, r["scene"])), "wb").write(data)
            n += 1
            if n % 300 == 0:
                el = time.time() - tl
                print("frame %d/%d  t=%.1f s  %s  %.2f s/frame, %.0f min left" % (f, end, r["t"], r["scene"], el / n, el / n * (end - f) / 60), flush=True)
        if enc:
            enc.stdin.close()
            enc.wait()
        vt_err = page.evaluate("__vt.errors.slice(0, 5)")
        print("errors in the page:", (errs + vt_err)[:5] or "none")
        br.close()
    if a.out and not a.silent:
        # the music and the effects, from the cues, laid under the picture (from --from, if the picture starts late)
        subprocess.check_call([sys.executable, os.path.join(HERE, "soundtrack.py"), cues_path, "--mux", picture, a.out,
                               "--start", str(start / 30)])
    print("done in %.0f min" % ((time.time() - t0) / 60))


if __name__ == "__main__":
    main()
