/* Pneuservis Merklín · Roman Oberreiter
   Animace: GSAP (ScrollTrigger, SplitText, DrawSVG). Plynulé kolečko myši: Lenis, dotyk zůstává nativní.
   Světlo pod kurzorem na kartách je port komponenty SpotlightCard z React Bits do čistého JS.
   Když se knihovny nenačtou nebo má návštěvník vypnuté animace, web funguje dál, jen bez pohybu. */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const root = document.documentElement;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)').matches;
  const G = window.gsap;
  const ST = window.ScrollTrigger;
  const SplitText = window.SplitText;
  const hasSplit = !!(G && SplitText);
  const hasDraw = !!(G && window.DrawSVGPlugin);
  const motion = !!(G && ST) && !reduce;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const plural = (n, one, few, many) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
  const cz = n => String(n).replace('.', ',');

  if (G && ST) G.registerPlugin(...[ST, SplitText, window.DrawSVGPlugin].filter(Boolean));
  if (!motion) root.classList.add('no-motion');

  // písmena se "vylijí": spadnou shora protažená jako kapka a dosednou s pružným dojezdem
  const POUR = { yPercent: -140, scaleY: 2.1, opacity: 0, transformOrigin: '50% 0%' };
  const pourIn = (chars, opts = {}) => G.from(chars, { ...POUR, duration: 1.25, ease: 'elastic.out(1, 0.6)', stagger: 0.034, ...opts });
  const DRAWABLE = 'path, circle, rect, polyline, polygon, line';

  /* ---------- geometrie kola a náboje ---------- */
  function buildGeometry() {
    const tread = $('[data-tread]');
    if (tread) {
      let s = '';
      for (let i = 0; i < 90; i++) s += `<rect x="-11" y="-485" width="22" height="22" rx="3" transform="rotate(${i * 4})"/>`;
      tread.innerHTML = s;
    }
    const holes = $('[data-disc-holes]');
    if (holes) {
      let s = '';
      for (let i = 0; i < 36; i++) s += `<circle cx="0" cy="${i % 2 ? -207 : -184}" r="5.5" transform="rotate(${i * 10})"/>`;
      holes.innerHTML = s;
    }
    const ticks = $('[data-hub-ticks]');
    if (ticks) {
      let s = '';
      for (let i = 0; i < 72; i++) s += `<line x1="0" y1="-287" x2="0" y2="${i % 6 ? -293 : -300}" transform="rotate(${i * 5})"/>`;
      ticks.innerHTML = s;
    }
  }

  /* ---------- Lenis: plynulé kolečko myši ---------- */
  let lenis = null;
  if (motion && window.Lenis) {
    lenis = new window.Lenis({ lerp: 0.1, smoothWheel: true, syncTouch: false });
    lenis.on('scroll', ST.update);
    G.ticker.add(time => lenis.raf(time * 1000));
    G.ticker.lagSmoothing(0);
  }
  const scrollY = () => (lenis ? lenis.scroll : window.scrollY);

  // kotvy v menu a tlačítkách jedou plynule i přes Lenis
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href^="#"]');
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey) return;
    const hash = a.getAttribute('href');
    const target = hash.length > 1 ? document.getElementById(hash.slice(1)) : null;
    if (!target) return;
    e.preventDefault();
    if (menuOpen) setMenu(false);
    if (lenis) lenis.scrollTo(target, { offset: hash === '#top' ? 0 : -84, duration: 1.3 });
    else target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  });

  /* ---------- sezóna ---------- */
  const swapBox = $('[data-swap]');
  const swapWord = $('[data-swap-word]');
  let swapSplit = null;
  let swapBusy = false;
  let swapQueued = null;

  function swapTo(next) {
    if (!swapWord) return;
    if (!motion || !swapSplit) { swapWord.textContent = next; return; }
    if (swapBusy) { swapQueued = next; return; }
    if (swapWord.textContent === next) return;
    swapBusy = true;
    const w0 = swapBox.offsetWidth;
    // staré slovo vyteče dolů, nové se vylije shora
    G.to(swapSplit.chars, {
      yPercent: 110, scaleY: 1.5, opacity: 0, transformOrigin: '50% 100%', duration: 0.32, ease: 'power2.in', stagger: 0.025,
      onComplete() {
        swapSplit.revert();
        swapWord.textContent = next;
        const w1 = swapBox.offsetWidth;
        G.fromTo(swapBox, { width: w0 }, { width: w1, duration: 0.8, ease: 'expo.out', clearProps: 'width' });
        swapSplit = SplitText.create(swapWord, { type: 'chars', charsClass: 'ch' });
        pourIn(swapSplit.chars, {
          duration: 1.1, stagger: 0.045,
          onComplete() {
            swapBusy = false;
            const q = swapQueued;
            swapQueued = null;
            if (q && q !== swapWord.textContent) swapTo(q);
          }
        });
      }
    });
  }

  function setSeason(s, animate) {
    const changed = root.dataset.season !== s;
    root.dataset.season = s;
    try { localStorage.setItem('season', s); } catch (e) { /* soukromé okno */ }
    $$('[data-season-btn]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.seasonBtn === s)));
    if (swapWord) {
      const next = swapWord.dataset[s];
      if (animate) swapTo(next);
      else if (!swapSplit) swapWord.textContent = next;
    }
    updateTread();
    if (animate && changed) {
      document.body.classList.remove('season-anim');
      void document.body.offsetWidth;
      document.body.classList.add('season-anim');
      // texty obou sezón mají jinou délku, pozice animací se musí přepočítat
      if (ST) requestAnimationFrame(() => ST.refresh());
    }
  }

  function setupSeason() {
    $$('[data-season-btn]').forEach(b => b.addEventListener('click', () => setSeason(b.dataset.seasonBtn, true)));
    const sw = $('.season-switch');
    if (sw) sw.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const next = root.dataset.season === 'winter' ? 'summer' : 'winter';
        setSeason(next, true);
        $(`[data-season-btn="${next}"]`).focus();
        e.preventDefault();
      }
    });
    setSeason(root.dataset.season === 'summer' ? 'summer' : 'winter', false);
  }

  /* ---------- dnešní datum a odpočet ---------- */
  function setupDates() {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const m = now.getMonth() + 1;
    const dayDiff = target => Math.round((target - today) / 864e5);
    const todayEl = $('[data-today]');
    const label = $('[data-cd-label]');
    const days = $('[data-cd-days]');
    const unit = $('[data-cd-unit]');
    const note = $('[data-cd-note]');
    let d;
    if (m >= 11 || m <= 3) {
      d = dayDiff(new Date(m >= 11 ? now.getFullYear() + 1 : now.getFullYear(), 2, 31));
      if (todayEl) todayEl.textContent = 'Zimní období právě běží';
      if (label) label.textContent = 'Zimní období potrvá ještě';
      if (note) note.textContent = 'Pořád jezdíte na letních? Zavolejte, přezujeme vás.';
    } else {
      d = dayDiff(new Date(now.getFullYear(), 10, 1));
      if (todayEl) todayEl.textContent = m >= 9 ? `Zimní období za ${d} ${plural(d, 'den', 'dny', 'dní')}` : 'Sezóna letních pneu';
    }
    if (days) days.textContent = d;
    if (unit) unit.textContent = plural(d, 'den', 'dny', 'dní');
    const y = $('[data-year]');
    if (y) y.textContent = now.getFullYear();

    // počet dní naskočí od nuly, když se karta objeví
    if (motion && days) {
      const c = { v: 0 };
      days.textContent = '0';
      G.to(c, {
        v: d, duration: 1.6, ease: 'power3.out',
        scrollTrigger: { trigger: days, start: 'top 90%', once: true },
        onUpdate: () => { days.textContent = Math.round(c.v); }
      });
    }
  }

  /* ---------- úvod: nadpis se vylije písmeno po písmenu, kolo se přivalí ---------- */
  const hero = $('[data-hero]');
  const stage = $('[data-wheel-stage]');
  const wheelLayers = $$('[data-wheel-rot]');
  const wheel = { roll: motion ? 1 : 0, tx: 0, ty: 0, tiltX: 0, tiltY: 0, radius: 1 };
  let heroOn = true;

  function heroIntro() {
    const title = $('[data-hero-title]');
    const hidden = [title, $('.hero-eyebrow'), $('.hero-bottom'), $('.hero-meta'), stage, nav].filter(Boolean);
    if (!motion) { window.__heroReady = true; return; }

    let chars = [];
    if (hasSplit) {
      const parts = $$('.split', title).map(el => SplitText.create(el, { type: 'words,chars', wordsClass: 'hw', charsClass: 'ch' }));
      swapSplit = SplitText.create(swapWord, { type: 'chars', charsClass: 'ch' });
      chars = [...parts[0].chars, ...swapSplit.chars, ...(parts[1] ? parts[1].chars : [])];
    }
    G.set(hidden, { visibility: 'visible' });
    window.__heroReady = true;

    const tl = G.timeline({ delay: 0.1 });
    if (chars.length) tl.add(pourIn(chars, { duration: 1.35, stagger: 0.032 }), 0);
    else tl.from(title, { y: 40, opacity: 0, duration: 1.1, ease: 'expo.out' }, 0);
    tl.from('.hero-eyebrow', { y: 16, opacity: 0, duration: 0.9, ease: 'expo.out' }, 0.05)
      .from(stage, { opacity: 0, duration: 1.4, ease: 'power2.out' }, 0.1)
      .fromTo(wheel, { roll: 1 }, { roll: 0, duration: 2.2, ease: 'power3.out' }, 0.1)
      .from(nav, { y: -24, opacity: 0, duration: 1.1, ease: 'expo.out' }, 0.35)
      .from($$('.hero-bottom > *'), { y: 28, opacity: 0, duration: 1.1, ease: 'expo.out', stagger: 0.08 }, 0.6)
      .from($$('.hero-meta > *'), { y: 20, opacity: 0, duration: 1, ease: 'expo.out', stagger: 0.06 }, 0.85);

    // text v úvodu se při odjezdu jemně zvedne a ztlumí
    G.to('.hero-inner', { yPercent: -6, opacity: 0.45, ease: 'none', scrollTrigger: { trigger: hero, start: 'top top', end: 'bottom top', scrub: true } });
  }

  function setupWheel() {
    if (!stage) return;
    const measure = () => { wheel.radius = stage.offsetWidth * 0.484 || 1; };
    measure();
    addEventListener('resize', measure);
    if (hero && 'IntersectionObserver' in window) new IntersectionObserver(([e]) => { heroOn = e.isIntersecting; }).observe(hero);
    if (hero && finePointer && motion) {
      hero.addEventListener('pointermove', e => {
        wheel.tx = (e.clientY / innerHeight - 0.5) * -5;
        wheel.ty = (e.clientX / innerWidth - 0.5) * 7;
      });
      hero.addEventListener('pointerleave', () => { wheel.tx = 0; wheel.ty = 0; });
    }
    const render = () => {
      if (!heroOn) return;
      const y = reduce ? 0 : scrollY();
      // kolo se otočí přesně o dráhu, kterou při vjezdu ujede
      const rollPx = wheel.roll * innerWidth * 0.42;
      const rot = (rollPx / wheel.radius) * 57.2958 + y * 0.2;
      const rotCss = `rotate(${rot.toFixed(2)}deg)`;
      for (let i = 0; i < wheelLayers.length; i++) wheelLayers[i].style.transform = rotCss;
      wheel.tiltX += (wheel.tx - wheel.tiltX) * 0.06;
      wheel.tiltY += (wheel.ty - wheel.tiltY) * 0.06;
      stage.style.transform = `perspective(1600px) translate3d(${rollPx.toFixed(1)}px, ${(y * 0.16).toFixed(1)}px, 0) rotateX(${wheel.tiltX.toFixed(2)}deg) rotateY(${wheel.tiltY.toFixed(2)}deg)`;
    };
    if (G) G.ticker.add(render);
    else { const loop = () => { render(); requestAnimationFrame(loop); }; loop(); }
  }

  /* ---------- nadpisy sekcí vyjíždějí slovo po slovu ---------- */
  function setupHeadings() {
    $$('[data-split]').forEach(el => {
      if (!hasSplit) {
        G.from(el, { y: 40, opacity: 0, duration: 1.1, ease: 'expo.out', scrollTrigger: { trigger: el, start: 'top 88%', once: true } });
        return;
      }
      const split = SplitText.create(el, { type: 'words', mask: 'words', wordsClass: 'wd' });
      G.from(split.words, {
        yPercent: 118, rotate: 6, transformOrigin: '0% 100%', duration: 1.15, ease: 'expo.out', stagger: 0.07,
        scrollTrigger: { trigger: el, start: 'top 88%', once: true }
      });
    });
    // výzva a patička: písmena se vylijí, když na ně dojedete
    $$('[data-pour]').forEach(el => {
      if (!hasSplit) return;
      const split = SplitText.create(el, { type: 'words,chars', wordsClass: 'pw', charsClass: 'ch' });
      pourIn(split.chars, { stagger: 0.03, scrollTrigger: { trigger: el, start: 'top 86%', once: true } });
    });
  }

  /* ---------- ostatní obsah vyjíždí zespodu ---------- */
  function setupReveals() {
    const els = $$('[data-reveal]');
    G.set(els, { opacity: 0, y: 34 });
    ST.batch(els, {
      start: 'top 92%',
      once: true,
      onEnter: batch => G.to(batch, { opacity: 1, y: 0, duration: 1.1, ease: 'expo.out', stagger: 0.08, overwrite: true })
    });
  }

  /* ---------- příběh: slova se rozsvěcují se scrollem ---------- */
  function setupStory() {
    $$('[data-highlight]').forEach(el => {
      const words = hasSplit ? SplitText.create(el, { type: 'words', wordsClass: 'mw' }).words : [el];
      G.fromTo(words, { opacity: 0.14 }, {
        opacity: 1, ease: 'none', stagger: 0.1,
        scrollTrigger: { trigger: el, start: 'top 80%', end: 'bottom 48%', scrub: 0.4 }
      });
    });
  }

  /* ---------- běžící pás reaguje na rychlost scrollu ---------- */
  function setupMarquee() {
    const track = $('[data-marquee]');
    if (!track) return;
    let setWidth = 0;
    const fill = () => {
      const set = track.firstElementChild;
      setWidth = set.getBoundingClientRect().width;
      while (track.children.length < 2 || track.scrollWidth < innerWidth + setWidth) track.appendChild(set.cloneNode(true));
    };
    fill();
    addEventListener('resize', fill);
    if (!motion) return;
    let x = 0;
    let vel = 0;
    ST.create({ start: 0, end: 'max', onUpdate: self => { vel = self.getVelocity(); } });
    G.ticker.add((time, dt) => {
      vel *= 0.92;
      x -= (0.045 + Math.min(0.9, Math.abs(vel) / 9000)) * dt;
      if (setWidth && -x >= setWidth) x += setWidth;
      track.style.transform = `translate3d(${x.toFixed(2)}px, 0, 0)`;
    });
  }

  /* ---------- služby: vějíř karet se rozevře ---------- */
  function setupFan() {
    const fan = $('[data-fan]');
    if (!fan) return;
    const cards = $$('.fan-card', fan);
    const n = cards.length;
    const mid = (n - 1) / 2;
    const iconParts = card => $$(DRAWABLE, $('.fc-ic', card));
    const mm = G.matchMedia();

    mm.add('(min-width: 1101px)', () => {
      fan.classList.add('fan-on');
      const cardW = () => Math.round(Math.min(264, Math.max(220, innerWidth * 0.19)));
      const setW = () => fan.style.setProperty('--card-w', `${cardW()}px`);
      const step = () => Math.min(250, (fan.clientWidth - cardW()) / (n - 1));
      setW();
      // prostřední karta leží nahoře, krajní pod ní
      cards.forEach((c, i) => { c.style.zIndex = String(10 - Math.round(Math.abs(i - mid) * 2)); });
      const tl = G.timeline({
        scrollTrigger: { trigger: fan, start: 'top 82%', end: 'top 26%', scrub: 0.8, invalidateOnRefresh: true, onRefreshInit: setW }
      });
      cards.forEach((c, i) => {
        const k = i - mid;
        tl.fromTo(c,
          { x: () => k * 14, y: () => 70 + Math.abs(k) * 4, rotation: k * 2.5 },
          { x: () => k * step(), y: () => k * k * 9, rotation: k * 5.5, ease: 'power2.out', duration: 1 }, 0);
      });
      // ikony se kreslí linkou, zatímco se vějíř otevírá
      if (hasDraw) tl.from(cards.flatMap(iconParts), { drawSVG: 0, ease: 'none', duration: 0.6, stagger: 0.012 }, 0.35);
      return () => {
        fan.classList.remove('fan-on');
        fan.style.removeProperty('--card-w');
        cards.forEach(c => { c.style.zIndex = ''; });
      };
    });

    mm.add('(max-width: 1100px)', () => {
      // na menší obrazovce se karty "rozdají" jedna po druhé
      cards.forEach((c, i) => {
        G.from(c, { y: 80, rotation: i % 2 ? 5 : -5, opacity: 0, duration: 1.1, ease: 'expo.out', scrollTrigger: { trigger: c, start: 'top 92%', once: true } });
        if (hasDraw) G.from(iconParts(c), { drawSVG: 0, duration: 1, ease: 'power2.out', stagger: 0.06, delay: 0.25, scrollTrigger: { trigger: c, start: 'top 92%', once: true } });
      });
    });
  }

  /* ---------- z dílny: na počítači se galerie posouvá do strany, kresby se kreslí linkou ---------- */
  function setupGallery() {
    const sec = $('[data-gallery]');
    if (!sec) return;
    const track = $('[data-gal-track]', sec);
    const viewport = $('[data-gal-viewport]', sec);
    const bar = $('[data-gal-bar]', sec);
    const cards = $$('.gal-card', track);
    const artOf = card => $$(DRAWABLE.split(', ').map(t => `.draw ${t}`).join(', '), card);
    const setBar = p => { if (bar) bar.style.transform = `scaleX(${p.toFixed(4)})`; };
    const onNativeScroll = () => setBar(viewport.scrollLeft / Math.max(1, viewport.scrollWidth - viewport.clientWidth));

    if (!motion) {
      viewport.addEventListener('scroll', onNativeScroll, { passive: true });
      return;
    }
    const mm = G.matchMedia();

    mm.add('(min-width: 1024px)', () => {
      sec.classList.add('gal-pinned');
      const dist = () => Math.max(0, track.scrollWidth - innerWidth);
      const tween = G.to(track, {
        x: () => -dist(),
        ease: 'none',
        scrollTrigger: {
          trigger: sec, start: 'top top', end: () => `+=${dist()}`, pin: true, scrub: 0.8, anticipatePin: 1, invalidateOnRefresh: true,
          onUpdate: self => setBar(self.progress)
        }
      });
      if (hasDraw) cards.forEach(card => {
        const art = artOf(card);
        if (art.length) G.from(art, {
          drawSVG: 0, duration: 1.5, ease: 'power2.inOut', stagger: 0.025,
          scrollTrigger: { trigger: card, containerAnimation: tween, start: 'left 90%', toggleActions: 'play none none reverse' }
        });
      });
      return () => sec.classList.remove('gal-pinned');
    });

    mm.add('(max-width: 1023px)', () => {
      viewport.addEventListener('scroll', onNativeScroll, { passive: true });
      if (!hasDraw) return () => viewport.removeEventListener('scroll', onNativeScroll);
      // na dotyku se karta nakreslí, když ji prstem posunete do záběru
      const drawn = cards.filter(card => artOf(card).length);
      drawn.forEach(card => G.set(artOf(card), { drawSVG: 0 }));
      let io = null;
      const st = ST.create({
        trigger: sec, start: 'top 70%', once: true,
        onEnter: () => {
          io = new IntersectionObserver(entries => entries.forEach(e => {
            if (!e.isIntersecting) return;
            G.to(artOf(e.target), { drawSVG: '100%', duration: 1.4, ease: 'power2.inOut', stagger: 0.025 });
            io.unobserve(e.target);
          }), { root: viewport, threshold: 0.45 });
          drawn.forEach(c => io.observe(c));
        }
      });
      return () => {
        viewport.removeEventListener('scroll', onNativeScroll);
        st.kill();
        if (io) io.disconnect();
      };
    });
  }

  /* ---------- připnutá sekce "Jak to probíhá" ---------- */
  function setupProcess() {
    const proc = $('[data-process]');
    if (!proc) return;
    const P = {
      steps: $$('[data-step]', proc),
      ring: $('[data-ring]', proc),
      bar: $('[data-process-bar]', proc),
      rot: $('[data-hub-rot]', proc),
      star: $('[data-star]', proc),
      count: $('[data-hub-count]', proc),
      nuts: $$('[data-nut]', proc),
      labels: $$('.nut-label', proc),
      order: [0, 2, 4, 1, 3],
      step: -1,
      lit: -1
    };
    const render = p => {
      const step = Math.min(3, Math.floor(p * 4));
      if (step !== P.step) {
        P.step = step;
        P.steps.forEach((el, i) => el.classList.toggle('is-active', i === step));
        P.count.textContent = `0${step + 1}`;
      }
      P.ring.style.strokeDashoffset = (1709.03 * (1 - p)).toFixed(1);
      P.bar.style.transform = `scaleX(${p.toFixed(4)})`;
      P.rot.setAttribute('transform', `rotate(${(-144 * (1 - clamp(p / 0.75))).toFixed(2)})`);
      // poslední krok: šrouby se dotahují do hvězdy 1, 3, 5, 2, 4
      const sub = clamp((p - 0.75) / 0.2);
      P.star.style.strokeDashoffset = (1426.6 * (1 - sub)).toFixed(1);
      const lit = sub <= 0 ? 0 : Math.min(5, Math.floor(sub * 5 + 0.0001) + 1);
      if (lit !== P.lit) {
        P.lit = lit;
        P.order.forEach((nutIdx, k) => {
          P.nuts[nutIdx].classList.toggle('on', k < lit);
          P.labels[k].classList.toggle('on', k < lit);
        });
      }
    };
    render(0);
    if (ST) {
      const state = { p: 0 };
      G.to(state, {
        p: 1, ease: 'none', onUpdate: () => render(state.p),
        scrollTrigger: { trigger: proc, start: 'top top', end: 'bottom bottom', scrub: reduce ? true : 0.6 }
      });
    } else {
      addEventListener('scroll', () => {
        const r = proc.getBoundingClientRect();
        render(clamp(-r.top / (r.height - innerHeight)));
      }, { passive: true });
    }
  }

  /* ---------- navigace: barva podle sekce, zvýraznění sekce, mobilní lišta ---------- */
  const nav = $('[data-nav]');
  let navTheme = 'dark';
  const setNavTheme = t => { if (nav && t !== navTheme) { navTheme = t; nav.dataset.theme = t; } };
  // sekce se zjistí hned, dokud je připnutá galerie ještě přímým potomkem <main>
  const mainSections = $$('main > section');
  const lightSections = mainSections.filter(sec => sec.classList.contains('light'));
  const spyLinks = $$('[data-spy]');
  const spyMap = new Map(spyLinks.map(a => [a.dataset.spy, a]));
  const navInd = $('[data-nav-ind]');
  let spyCurrent;

  function placeIndicator() {
    if (!navInd) return;
    const a = spyMap.get(spyCurrent);
    if (!a || !a.offsetParent) { navInd.classList.remove('on'); return; }
    navInd.style.width = `${a.offsetWidth}px`;
    navInd.style.transform = `translateX(${a.offsetLeft}px)`;
    navInd.classList.add('on');
  }
  function setSpy(id) {
    if (id === spyCurrent) return;
    spyCurrent = id;
    spyLinks.forEach(l => {
      const on = l.dataset.spy === id;
      l.classList.toggle('is-current', on);
      if (on) l.setAttribute('aria-current', 'location'); else l.removeAttribute('aria-current');
    });
    placeIndicator();
  }

  function setupNavState() {
    const mbar = $('[data-mbar]');
    const contact = $('#kontakt');
    const lights = lightSections;
    const sections = mainSections;
    if (ST) {
      const active = new Set();
      lights.forEach(sec => ST.create({
        trigger: sec, start: 'top 42px', end: 'bottom 42px',
        onToggle: self => {
          if (self.isActive) active.add(sec); else active.delete(sec);
          if (!menuOpen) setNavTheme(active.size ? 'light' : 'dark');
        }
      }));
      sections.forEach(sec => ST.create({
        trigger: sec, start: 'top 40%', end: 'bottom 40%',
        onToggle: self => { if (self.isActive) setSpy(spyMap.has(sec.id) ? sec.id : null); }
      }));
      if (mbar && hero && contact) ST.create({
        trigger: hero, start: 'bottom 25%', endTrigger: contact, end: 'top 90%',
        onToggle: self => mbar.classList.toggle('show', self.isActive)
      });
      return;
    }
    const update = () => {
      const vh = innerHeight;
      if (!menuOpen) setNavTheme(lights.some(s => { const r = s.getBoundingClientRect(); return r.top <= 42 && r.bottom >= 42; }) ? 'light' : 'dark');
      let cur = null;
      for (const s of sections) {
        if (s.getBoundingClientRect().top <= vh * 0.4) cur = spyMap.has(s.id) ? s.id : null;
        else break;
      }
      setSpy(cur);
      if (mbar && contact) mbar.classList.toggle('show', window.scrollY > vh * 0.75 && contact.getBoundingClientRect().top > vh * 0.9);
    };
    addEventListener('scroll', update, { passive: true });
    update();
  }

  /* ---------- menu pro mobil a tablet ---------- */
  const burger = $('[data-burger]');
  const menu = $('[data-menu]');
  let menuOpen = false;
  function setMenu(open) {
    if (!menu || !burger) return;
    menuOpen = open;
    menu.classList.toggle('open', open);
    if (open) menu.removeAttribute('inert'); else menu.setAttribute('inert', '');
    burger.setAttribute('aria-expanded', String(open));
    burger.setAttribute('aria-label', open ? 'Zavřít menu' : 'Otevřít menu');
    root.classList.toggle('menu-open', open);
    if (lenis) { if (open) lenis.stop(); else lenis.start(); }
    if (open) {
      setNavTheme('dark');
      setTimeout(() => { const first = $('a', menu); if (first && menuOpen) first.focus({ preventScroll: true }); }, 380);
    }
  }
  function setupMenu() {
    if (!menu || !burger) return;
    $$('.menu-links a', menu).forEach((a, i) => a.style.setProperty('--i', i));
    burger.addEventListener('click', () => setMenu(!menuOpen));
    addEventListener('keydown', e => {
      if (e.key === 'Escape' && menuOpen) { setMenu(false); burger.focus(); }
    });
    matchMedia('(min-width: 1101px)').addEventListener('change', e => { if (e.matches && menuOpen) setMenu(false); });
  }

  /* ---------- světlo pod kurzorem: port SpotlightCard z React Bits ---------- */
  function setupSpotlight() {
    if (!finePointer) return;
    $$('[data-spotlight]').forEach(card => {
      card.addEventListener('pointermove', e => {
        const r = card.getBoundingClientRect();
        card.style.setProperty('--sx', `${Math.round(e.clientX - r.left)}px`);
        card.style.setProperty('--sy', `${Math.round(e.clientY - r.top)}px`);
      });
      card.addEventListener('pointerenter', () => card.classList.add('lit'));
      card.addEventListener('pointerleave', () => card.classList.remove('lit'));
    });
  }

  /* ---------- výzva: kruh se točí se scrollem ---------- */
  function setupCta() {
    const ring = $('[data-cta-ring]');
    if (!ring) return;
    G.to(ring, { rotation: 140, ease: 'none', scrollTrigger: { trigger: ring.parentElement, start: 'top bottom', end: 'bottom top', scrub: true } });
  }

  /* ---------- časté otázky: plynulé rozbalení, otevřená je vždy jen jedna ---------- */
  function setupFaq() {
    const items = $$('.qa');
    const done = () => { if (ST) ST.refresh(); };
    const close = d => {
      const body = $('.qa-body', d);
      d.dataset.anim = '1';
      d.classList.add('closing');
      const a = body.animate([{ height: `${body.scrollHeight}px`, opacity: 1 }, { height: '0px', opacity: 0 }], { duration: 380, easing: 'cubic-bezier(.4,0,.2,1)' });
      a.onfinish = () => { d.open = false; d.classList.remove('closing'); delete d.dataset.anim; done(); };
    };
    const open = d => {
      const body = $('.qa-body', d);
      d.open = true;
      d.dataset.anim = '1';
      const a = body.animate([{ height: '0px', opacity: 0 }, { height: `${body.scrollHeight}px`, opacity: 1 }], { duration: 560, easing: 'cubic-bezier(.22,1,.36,1)' });
      a.onfinish = () => { delete d.dataset.anim; done(); };
    };
    items.forEach(d => {
      $('summary', d).addEventListener('click', e => {
        if (reduce) return;
        e.preventDefault();
        if (d.dataset.anim) return;
        if (d.open) { close(d); return; }
        items.forEach(o => { if (o !== d && o.open && !o.dataset.anim) close(o); });
        open(d);
      });
    });
  }

  /* ---------- objednání služby přímo z karty ---------- */
  function setupPick() {
    const sel = $('#f-service');
    if (!sel) return;
    $$('[data-pick]').forEach(a => a.addEventListener('click', () => {
      sel.value = a.dataset.pick;
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      const wrap = sel.parentElement;
      wrap.classList.remove('picked');
      void wrap.offsetWidth;
      wrap.classList.add('picked');
      setTimeout(() => wrap.classList.remove('picked'), 2200);
    }));
  }

  /* ---------- poradna: nápis na boku ---------- */
  const DEC = {
    w: ['205', 'Šířka pneumatiky', 'Šířka v milimetrech, od boku k boku. Tady 205 mm.'],
    p: ['55', 'Profil', 'Výška boku v procentech šířky. Tady 55 % z 205 mm, tedy zhruba 113 mm.'],
    r: ['R', 'Radiální konstrukce', 'Vlákna kostry vedou od středu kola ven, kolmo k běhounu. Dnes to platí skoro pro každou osobní pneumatiku.'],
    d: ['16', 'Průměr disku', 'Na jak velký disk pneumatika patří, v palcích. 16 palců je asi 40,6 cm.'],
    l: ['91', 'Index nosnosti', 'Kolik unese jedna pneumatika. Index 91 znamená 615 kg na kolo.'],
    s: ['V', 'Rychlostní index', 'Nejvyšší rychlost, pro kterou je pneumatika stavěná. V znamená až 240 km/h.'],
    t: ['4223', 'Datum výroby', 'Týden a rok výroby: 42. týden roku 2023. Guma stárne, i když auto stojí, takže starší pneumatiky je dobré nechat zkontrolovat.']
  };
  function setupDecoder() {
    const segs = $$('[data-seg]');
    const key = $('[data-dec-key]');
    const title = $('[data-dec-title]');
    const body = $('[data-dec-body]');
    const box = key && key.parentElement;
    const dims = $$('[data-dim]');
    if (!segs.length || !key) return;
    const select = id => {
      segs.forEach(b => {
        const on = b.dataset.seg === id;
        b.classList.toggle('is-on', on);
        b.setAttribute('aria-pressed', String(on));
      });
      dims.forEach(d => d.classList.toggle('on', d.dataset.dim === id));
      [key.textContent, title.textContent, body.textContent] = DEC[id];
      box.classList.remove('flash');
      void box.offsetWidth;
      box.classList.add('flash');
    };
    segs.forEach(b => {
      b.addEventListener('click', () => select(b.dataset.seg));
      if (finePointer) b.addEventListener('mouseenter', () => select(b.dataset.seg));
    });
    select('w');
  }

  /* ---------- poradna: hloubka dezénu ---------- */
  const K = 14;           // px na milimetr
  const BASE = 160;       // horní hrana kostry
  const SINK = 12;        // bloky zasahují do kostry, aby spodní zaoblení nebylo vidět
  const depth = $('[data-depth]');
  function setupTread() {
    const ruler = $('[data-ruler]');
    const blocks = $('[data-blocks]');
    if (!ruler || !blocks) return;
    let r = '';
    for (let mm = 0; mm <= 9; mm++) {
      const y = BASE - mm * K;
      r += `<g class="rl"><line x1="24" x2="32" y1="${y}" y2="${y}"/><text x="19" y="${y + 3.5}">${mm}</text></g>`;
    }
    ruler.innerHTML = r;
    let b = '';
    const bw = 30, gap = 9.6, x0 = 37;
    for (let i = 0; i < 6; i++) {
      const x = x0 + i * (bw + gap);
      b += `<rect class="tb" x="${x}" y="${BASE - 9 * K}" width="${bw}" height="${9 * K + SINK}" rx="4"/>`;
      if (i === 1 || i === 3) b += `<rect class="twi" x="${x + bw + 1.5}" y="${BASE - 1.6 * K}" width="${gap - 3}" height="${1.6 * K + 1}" rx="1.5"/>`;
    }
    blocks.innerHTML = b;
    const law = $('[data-lim="law"]');
    const lawT = $('[data-lim-t="law"]');
    const yLaw = BASE - 1.6 * K;
    law.setAttribute('y1', yLaw); law.setAttribute('y2', yLaw);
    lawT.setAttribute('y', yLaw + 16);
    $$('tspan', lawT)[0].setAttribute('y', yLaw + 16);
    depth.addEventListener('input', updateTread);
  }

  function verdict(v, season) {
    if (v < 1.6) return ['bad', 'Pod zákonným minimem. S tímhle už nejezděte, tyhle gumy je potřeba vyměnit.'];
    if (season === 'winter') {
      if (v < 4) return ['bad', 'Na zimu to nestačí. Zimní pneu musí mít aspoň 4 mm, jinak se za zimní nepočítá.'];
      if (v < 5) return ['warn', 'Na zimu ještě projde, ale nejspíš naposledy. Počítejte s novými.'];
      return ['ok', 'Dobrý stav. Stačí přezout a jet.'];
    }
    if (v < 3) return ['warn', 'Legální, ale na mokru už slabé. Nové gumy se vyplatí.'];
    if (v < 4) return ['ok', 'V pořádku, jen to hlídejte.'];
    return ['ok', 'Dobrý stav. Stačí přezout a jet.'];
  }

  function updateTread() {
    if (!depth || !$('.tb')) return;
    const v = parseFloat(depth.value);
    const season = root.dataset.season;
    const tool = depth.closest('.tool');
    const sy = (v * K + SINK) / (9 * K + SINK);
    $$('.tb').forEach(b => { b.style.transform = `scaleY(${sy.toFixed(4)})`; });
    depth.style.setProperty('--val', `${(v / 9) * 100}%`);
    $('[data-depth-out]').textContent = `${cz(v.toFixed(1))} mm`;
    const [level, text] = verdict(v, season);
    const out = $('[data-verdict]');
    out.dataset.level = level;
    out.textContent = text;
    tool.dataset.level = level;

    const lim = season === 'winter' ? 4 : 3;
    const y = BASE - lim * K;
    const line = $('[data-lim="season"]');
    const t = $('[data-lim-t="season"]');
    if (line && t) {
      line.setAttribute('y1', y); line.setAttribute('y2', y);
      t.setAttribute('y', y - 17);
      $('[data-lim-v]', t).setAttribute('y', y - 17);
      $('[data-lim-v]', t).textContent = `${lim} mm`;
      $('[data-lim-s]', t).textContent = season === 'winter' ? 'zima' : 'doporučeno';
    }
  }

  /* ---------- SMS ---------- */
  function setupSms() {
    const form = $('[data-sms]');
    if (!form) return;
    const preview = $('[data-sms-preview]');
    const note = $('[data-sms-note]');
    const tel = $('a[href^="tel:"]');
    const phone = tel ? tel.getAttribute('href').slice(4) : '';
    const val = n => (form.elements[n] ? form.elements[n].value.trim() : '');
    const compose = () => {
      const svc = val('service');
      const lines = [svc ? `Dobrý den, prosím o termín: ${svc.toLowerCase()}.` : 'Dobrý den, potřebuji poradit s pneumatikami.'];
      if (val('car')) lines.push(`Auto: ${val('car')}`);
      if (val('size')) lines.push(`Rozměr: ${val('size')}`);
      if (!svc || svc.startsWith('Přezutí')) lines.push(`Gumy na discích: ${val('rims') || 'nevím'}`);
      if (val('when')) lines.push(`Hodí se mi: ${val('when')}`);
      lines.push(val('name') ? `Děkuji, ${val('name')}` : 'Děkuji');
      return lines.join('\n');
    };
    const rimsField = $('[data-rims-field]', form);
    const render = () => {
      // otázka na disky dává smysl jen u přezutí
      if (rimsField) { const svc = val('service'); rimsField.hidden = !!svc && !svc.startsWith('Přezutí'); }
      preview.textContent = compose();
    };
    form.addEventListener('input', render);
    form.addEventListener('change', render);
    form.addEventListener('submit', e => {
      e.preventDefault();
      if (!phone || /x/i.test(phone)) {
        note.hidden = false;
        note.textContent = 'Telefonní číslo ještě není na webu doplněné. Zatím prosím zavolejte.';
        return;
      }
      window.location.href = `sms:${phone}?&body=${encodeURIComponent(compose())}`;
    });
    render();
  }

  /* ---------- patička: nápis přes celou šířku ---------- */
  function fitFooter() {
    const el = $('.footer-word');
    if (!el) return;
    el.style.fontSize = '100px';
    el.style.display = 'inline-block';
    const w = el.getBoundingClientRect().width;
    el.style.display = '';
    const target = el.parentElement.clientWidth * 0.94;
    if (w) el.style.fontSize = `${(100 * target) / w}px`;
  }

  /* ---------- start ---------- */
  buildGeometry();
  setupSeason();
  setupDecoder();
  setupTread();
  updateTread();
  setupSms();
  setupMenu();
  setupFaq();
  setupPick();
  setupSpotlight();
  fitFooter();

  let started = false;
  const start = () => {
    if (started) return;
    started = true;
    fitFooter();
    if (motion) {
      // připnutá galerie se zakládá první, aby pozice všeho pod ní počítaly s jejím místem
      setupGallery();
      heroIntro();
      setupHeadings();
      setupReveals();
      setupStory();
      setupFan();
      setupCta();
    } else {
      heroIntro();
      setupGallery();
    }
    setupDates();
    setupMarquee();
    setupWheel();
    setupProcess();
    setupNavState();
    placeIndicator();
    if (ST) { ST.sort(); ST.refresh(); }
  };
  // úvod startuje až s načteným písmem, aby se písmena nepřeskládala uprostřed animace
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(start);
  setTimeout(start, 1200);
  addEventListener('resize', () => { fitFooter(); placeIndicator(); });
})();
