/* Pneuservis Merklín · Roman Oberreiter
   Bez knihoven. Jedna smyčka requestAnimationFrame řídí kolo, pás, příběh, připnutou sekci, navigaci a mobilní lištu. */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const root = document.documentElement;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)').matches;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const easeOut = t => 1 - Math.pow(1 - t, 4);
  const plural = (n, one, few, many) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
  const cz = n => String(n).replace('.', ',');

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

  /* ---------- dělení nadpisů na slova ---------- */
  let wordIndex = 0;
  function wrapWord(content) {
    const w = document.createElement('span');
    w.className = 'w';
    const wi = document.createElement('span');
    wi.className = 'wi';
    wi.style.setProperty('--i', wordIndex++);
    if (typeof content === 'string') wi.textContent = content;
    else wi.appendChild(content);
    w.appendChild(wi);
    return w;
  }
  function splitNode(node) {
    Array.from(node.childNodes).forEach(child => {
      if (child.nodeType === 3) {
        const frag = document.createDocumentFragment();
        // dělí jen na běžných mezerách a koncích řádků, pevná mezera drží slova pohromadě
        child.textContent.split(/([ \t\n\r]+)/).forEach(part => {
          if (!part) return;
          frag.appendChild(/^[ \t\n\r]+$/.test(part) ? document.createTextNode(' ') : wrapWord(part));
        });
        node.replaceChild(frag, child);
      } else if (child.nodeType === 1) {
        if (child.hasAttribute('data-word')) {
          const holder = document.createElement('span');
          node.replaceChild(holder, child);
          holder.replaceWith(wrapWord(child));
        } else if (child.tagName !== 'BR') {
          splitNode(child);
        }
      }
    });
  }
  function splitHeadings() {
    $$('[data-split], [data-hero-title]').forEach(el => {
      wordIndex = 0;
      splitNode(el);
    });
  }

  /* ---------- odhalování při scrollu ---------- */
  function setupReveal() {
    // sourozenci se odhalují s malým zpožděním za sebou
    $$('.facts, .service-list, .tools-grid, .map-links, .benefits, .faq-list').forEach(group => {
      $$(':scope > [data-reveal]', group).forEach((el, i) => el.style.setProperty('--d', `${i * 0.09}s`));
    });
    if (!('IntersectionObserver' in window)) {
      $$('[data-reveal], [data-split]').forEach(el => el.classList.add('in'));
      return;
    }
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          io.unobserve(e.target);
        }
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.01 });
    $$('[data-reveal], [data-split]').forEach(el => io.observe(el));
  }

  /* ---------- sezóna ---------- */
  const swapBox = $('[data-swap]');
  const swapWord = $('[data-swap-word]');

  function animateSwap(next) {
    const w0 = swapBox.getBoundingClientRect().width;
    const out = swapWord.animate(
      [{ transform: 'none', opacity: 1, filter: 'blur(0)' }, { transform: 'translateY(-40%)', opacity: 0, filter: 'blur(8px)' }],
      { duration: 260, easing: 'cubic-bezier(.5,0,.9,.4)', fill: 'forwards' }
    );
    out.onfinish = () => {
      swapWord.textContent = next;
      swapBox.style.width = 'auto';
      const w1 = swapBox.getBoundingClientRect().width;
      swapBox.style.width = `${w0}px`;
      void swapBox.offsetWidth;
      swapBox.style.width = `${w1}px`;
      const inn = swapWord.animate(
        [{ transform: 'translateY(40%)', opacity: 0, filter: 'blur(8px)' }, { transform: 'none', opacity: 1, filter: 'blur(0)' }],
        { duration: 700, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'forwards' }
      );
      out.cancel();
      inn.onfinish = () => { inn.cancel(); swapBox.style.width = ''; };
    };
  }

  function setSeason(s, animate) {
    const changed = root.dataset.season !== s;
    root.dataset.season = s;
    try { localStorage.setItem('season', s); } catch (e) { /* soukromé okno */ }
    $$('[data-season-btn]').forEach(b => b.setAttribute('aria-checked', String(b.dataset.seasonBtn === s)));
    if (swapWord) {
      const next = swapWord.dataset[s];
      if (animate && !reduce && swapWord.textContent !== next) animateSwap(next);
      else swapWord.textContent = next;
    }
    if (animate && changed) {
      document.body.classList.remove('season-anim');
      void document.body.offsetWidth;
      document.body.classList.add('season-anim');
    }
    updateTread();
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

    if (m >= 11 || m <= 3) {
      const end = new Date(m >= 11 ? now.getFullYear() + 1 : now.getFullYear(), 2, 31);
      const d = dayDiff(end);
      if (todayEl) todayEl.textContent = 'Zimní období právě běží';
      if (label) label.textContent = 'Zimní období potrvá ještě';
      if (days) days.textContent = d;
      if (unit) unit.textContent = plural(d, 'den', 'dny', 'dní');
      if (note) note.textContent = 'Pořád jezdíte na letních? Zavolejte, přezujeme vás.';
    } else {
      const d = dayDiff(new Date(now.getFullYear(), 10, 1));
      if (todayEl) todayEl.textContent = m >= 9 ? `Zimní období za ${d} ${plural(d, 'den', 'dny', 'dní')}` : 'Sezóna letních pneu';
      if (days) days.textContent = d;
      if (unit) unit.textContent = plural(d, 'den', 'dny', 'dní');
    }
    const y = $('[data-year]');
    if (y) y.textContent = now.getFullYear();
  }

  /* ---------- běžící pás ---------- */
  const marquee = $('[data-marquee]');
  let marqueeX = 0;
  let setWidth = 0;
  function fillMarquee() {
    if (!marquee) return;
    const set = marquee.firstElementChild;
    setWidth = set.getBoundingClientRect().width;
    while (marquee.children.length < 2 || marquee.scrollWidth < innerWidth + setWidth) {
      marquee.appendChild(set.cloneNode(true));
    }
  }

  /* ---------- příběh: slova se rozsvěcují se scrollem ---------- */
  const stories = $$('[data-highlight]').map(el => ({ el, words: [], lit: -1 }));
  function setupManifest() {
    stories.forEach(st => {
      const frag = document.createDocumentFragment();
      st.el.textContent.trim().split(/([ \t\n\r]+)/).forEach(part => {
        if (/^[ \t\n\r]+$/.test(part)) frag.appendChild(document.createTextNode(' '));
        else {
          const w = document.createElement('span');
          w.className = 'mw';
          w.textContent = part;
          frag.appendChild(w);
        }
      });
      st.el.textContent = '';
      st.el.appendChild(frag);
      st.words = $$('.mw', st.el);
    });
  }
  function updateManifest(vh) {
    stories.forEach(st => {
      if (!st.el.offsetParent) return; // druhá sezóna je skrytá
      const r = st.el.getBoundingClientRect();
      if (r.bottom < -100 || r.top > vh + 100) return;
      const p = clamp((vh * 0.82 - r.top) / (r.height + vh * 0.32));
      const lit = Math.round(p * st.words.length);
      if (lit === st.lit) return;
      st.lit = lit;
      st.words.forEach((w, i) => w.classList.toggle('on', i < lit));
    });
  }

  /* ---------- navigace: zvýraznění sekce, ve které právě jste ---------- */
  const spyLinks = $$('[data-spy]');
  const spyMap = new Map(spyLinks.map(a => [a.dataset.spy, a]));
  const mainSections = $$('main > section');
  const navInd = $('[data-nav-ind]');
  let spyCurrent = null;
  function placeIndicator() {
    if (!navInd) return;
    const a = spyMap.get(spyCurrent);
    if (!a || !a.offsetParent) { navInd.classList.remove('on'); return; }
    navInd.style.width = `${a.offsetWidth}px`;
    navInd.style.transform = `translateX(${a.offsetLeft}px)`;
    navInd.classList.add('on');
  }
  function updateSpy(vh) {
    let cur = null;
    for (const sec of mainSections) {
      if (sec.getBoundingClientRect().top <= vh * 0.38) cur = spyMap.has(sec.id) ? sec.id : null;
      else break;
    }
    if (cur === spyCurrent) return;
    spyCurrent = cur;
    spyLinks.forEach(l => {
      const on = l.dataset.spy === cur;
      l.classList.toggle('is-current', on);
      if (on) l.setAttribute('aria-current', 'location'); else l.removeAttribute('aria-current');
    });
    placeIndicator();
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
    if (open) {
      setNavTheme('dark');
      setTimeout(() => { const first = $('a', menu); if (first && menuOpen) first.focus({ preventScroll: true }); }, 380);
    }
  }
  function setupMenu() {
    if (!menu || !burger) return;
    $$('.menu-links a', menu).forEach((a, i) => a.style.setProperty('--i', i));
    burger.addEventListener('click', () => setMenu(!menuOpen));
    // zámek scrollu se uvolní ještě před skokem na kotvu
    menu.addEventListener('click', e => { if (e.target.closest('a')) setMenu(false); });
    addEventListener('keydown', e => {
      if (e.key === 'Escape' && menuOpen) { setMenu(false); burger.focus(); }
    });
    matchMedia('(min-width: 1101px)').addEventListener('change', e => { if (e.matches && menuOpen) setMenu(false); });
  }

  /* ---------- časté otázky: plynulé rozbalení, otevřená je vždy jen jedna ---------- */
  function setupFaq() {
    const items = $$('.qa');
    const close = d => {
      const body = $('.qa-body', d);
      d.dataset.anim = '1';
      d.classList.add('closing');
      const a = body.animate([{ height: `${body.scrollHeight}px`, opacity: 1 }, { height: '0px', opacity: 0 }],
        { duration: 380, easing: 'cubic-bezier(.4,0,.2,1)' });
      a.onfinish = () => { d.open = false; d.classList.remove('closing'); delete d.dataset.anim; };
    };
    const open = d => {
      const body = $('.qa-body', d);
      d.open = true;
      d.dataset.anim = '1';
      const a = body.animate([{ height: '0px', opacity: 0 }, { height: `${body.scrollHeight}px`, opacity: 1 }],
        { duration: 560, easing: 'cubic-bezier(.22,1,.36,1)' });
      a.onfinish = () => { delete d.dataset.anim; };
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

  /* ---------- objednání služby přímo z ceníku ---------- */
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

  /* ---------- připnutá sekce "Jak to probíhá" ---------- */
  const proc = $('[data-process]');
  const P = proc && {
    steps: $$('[data-step]', proc),
    ring: $('[data-ring]', proc),
    bar: $('[data-process-bar]', proc),
    rot: $('[data-hub-rot]', proc),
    star: $('[data-star]', proc),
    count: $('[data-hub-count]', proc),
    nuts: $$('[data-nut]', proc),
    labels: $$('.nut-label', proc),
    order: [0, 2, 4, 1, 3],
    ringLen: 1709.03,
    starLen: 1426.6,
    p: 0,
    step: -1,
    lit: -1
  };
  function updateProcess(vh) {
    if (!P) return;
    const r = proc.getBoundingClientRect();
    if (r.bottom < 0 || r.top > vh) return;
    const raw = clamp(-r.top / (r.height - vh));
    P.p = reduce ? raw : lerp(P.p, raw, 0.16);
    if (Math.abs(P.p - raw) < 0.0005) P.p = raw;
    const p = P.p;

    const step = Math.min(3, Math.floor(raw * 4));
    if (step !== P.step) {
      P.step = step;
      P.steps.forEach((el, i) => el.classList.toggle('is-active', i === step));
      P.count.textContent = `0${step + 1}`;
    }
    P.ring.style.strokeDashoffset = (P.ringLen * (1 - p)).toFixed(1);
    P.bar.style.transform = `scaleX(${p.toFixed(4)})`;
    P.rot.setAttribute('transform', `rotate(${(-144 * (1 - clamp(p / 0.75))).toFixed(2)})`);

    // poslední krok: šrouby se dotahují do hvězdy 1, 3, 5, 2, 4
    const sub = clamp((p - 0.75) / 0.2);
    P.star.style.strokeDashoffset = (P.starLen * (1 - sub)).toFixed(1);
    const lit = sub <= 0 ? 0 : Math.min(5, Math.floor(sub * 5 + 0.0001) + 1);
    if (lit !== P.lit) {
      P.lit = lit;
      P.order.forEach((nutIdx, k) => {
        P.nuts[nutIdx].classList.toggle('on', k < lit);
        P.labels[k].classList.toggle('on', k < lit);
      });
    }
  }

  /* ---------- hlavní smyčka ---------- */
  const hero = $('[data-hero]');
  const heroInner = $('.hero-inner');
  const stage = $('[data-wheel-stage]');
  const wheelLayers = $$('[data-wheel-rot]');
  const nav = $('[data-nav]');
  const lightSections = $$('main > .light');
  let navTheme = 'dark';
  function setNavTheme(t) { if (nav && t !== navTheme) { navTheme = t; nav.dataset.theme = t; } }
  const mbar = $('[data-mbar]');
  const contactSec = $('#kontakt');
  let mbarOn = false;
  const ctaRing = $('[data-cta-ring]');
  let scrollY = window.scrollY;
  let smooth = scrollY;
  let last = smooth;
  let vel = 0;
  let heroOn = true;
  let introStart = Infinity;
  const INTRO_MS = 2000;
  let tiltX = 0, tiltY = 0, tX = 0, tY = 0;
  let prevTime = performance.now();
  let radiusPx = 1;
  const measure = () => { if (stage) radiusPx = stage.offsetWidth * 0.484 || 1; };

  addEventListener('scroll', () => { scrollY = window.scrollY; }, { passive: true });

  if (hero && 'IntersectionObserver' in window) {
    new IntersectionObserver(([e]) => { heroOn = e.isIntersecting; }).observe(hero);
  }
  if (hero && finePointer && !reduce) {
    hero.addEventListener('pointermove', e => {
      tX = (e.clientY / innerHeight - 0.5) * -5;
      tY = (e.clientX / innerWidth - 0.5) * 7;
    });
    hero.addEventListener('pointerleave', () => { tX = 0; tY = 0; });
  }

  function frame(now) {
    const dt = Math.min(64, now - prevTime);
    prevTime = now;
    const vh = innerHeight;

    smooth = reduce ? scrollY : lerp(smooth, scrollY, 0.13);
    if (Math.abs(smooth - scrollY) < 0.05) smooth = scrollY;
    vel = lerp(vel, smooth - last, 0.2);
    last = smooth;

    if (heroOn && stage) {
      // kolo se při vstupu přivalí zprava a otočí se přesně o ujetou dráhu
      const t = reduce ? 1 : clamp((now - introStart) / INTRO_MS);
      const e = easeOut(t);
      const rollPx = (1 - e) * innerWidth * 0.42;
      const rot = (rollPx / radiusPx) * 57.2958 + smooth * 0.2;
      const rotCss = `rotate(${rot.toFixed(2)}deg)`;
      for (let i = 0; i < wheelLayers.length; i++) wheelLayers[i].style.transform = rotCss;

      tiltX = lerp(tiltX, tX, 0.06);
      tiltY = lerp(tiltY, tY, 0.06);
      stage.style.transform = `perspective(1600px) translate3d(${rollPx.toFixed(1)}px, ${(smooth * 0.16).toFixed(1)}px, 0) rotateX(${tiltX.toFixed(2)}deg) rotateY(${tiltY.toFixed(2)}deg)`;
      if (heroInner) {
        const k = clamp(smooth / (vh * 0.9));
        heroInner.style.transform = `translate3d(0, ${(smooth * -0.08).toFixed(1)}px, 0)`;
        heroInner.style.opacity = (1 - k * 0.55).toFixed(3);
      }
    }

    if (marquee && setWidth) {
      const speed = reduce ? 0 : 0.045 + Math.min(1.6, Math.abs(vel) * 0.06);
      marqueeX -= speed * dt;
      if (-marqueeX >= setWidth) marqueeX += setWidth;
      marquee.style.transform = `translate3d(${marqueeX.toFixed(2)}px, 0, 0)`;
    }

    updateManifest(vh);
    updateProcess(vh);

    updateSpy(vh);

    if (nav && !menuOpen) {
      const mid = 42;
      setNavTheme(lightSections.some(sec => { const r = sec.getBoundingClientRect(); return r.top <= mid && r.bottom >= mid; }) ? 'light' : 'dark');
    }

    // mobilní lišta: ukáže se po úvodu, schová se u kontaktu
    if (mbar && contactSec) {
      const show = scrollY > vh * 0.75 && contactSec.getBoundingClientRect().top > vh * 0.9;
      if (show !== mbarOn) { mbarOn = show; mbar.classList.toggle('show', show); }
    }

    if (ctaRing && !reduce) {
      const r = ctaRing.parentElement.getBoundingClientRect();
      if (r.bottom > 0 && r.top < vh) ctaRing.style.transform = `rotate(${(smooth * 0.06).toFixed(2)}deg)`;
    }
    requestAnimationFrame(frame);
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
    if (!depth) return;
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
  splitHeadings();
  setupSeason();
  setupDates();
  setupManifest();
  fillMarquee();
  measure();
  setupDecoder();
  setupTread();
  updateTread();
  setupSms();
  setupMenu();
  setupFaq();
  setupPick();
  setupReveal();
  requestAnimationFrame(frame);

  let started = false;
  const start = () => {
    if (started) return;
    started = true;
    fitFooter();
    fillMarquee();
    measure();
    placeIndicator();
    root.classList.add('is-loaded');
    $('[data-hero-title]').classList.add('in');
    introStart = performance.now() + 120;
  };
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(start);
  setTimeout(start, 1500);
  addEventListener('resize', () => { fitFooter(); fillMarquee(); measure(); placeIndicator(); });
})();
