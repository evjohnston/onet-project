
(function(){
"use strict";

/* ============================================================
   0. MATH + UTILITY
   ============================================================ */
const NS = 'http://www.w3.org/2000/svg';
let DEFS = null;   /* one shared defs node for every reveal clip */
const clamp = (v,a,b)=> v<a?a:(v>b?b:v);
const lerp  = (a,b,t)=> a+(b-a)*t;
const eo    = t=> 1-Math.pow(1-clamp(t,0,1),3);            // easeOutCubic
const eio   = t=> (t=clamp(t,0,1))<.5 ? 4*t*t*t : 1-Math.pow(-2*t+2,3)/2;
const logis = (t,mid,k)=> 1/(1+Math.exp(-k*(t-mid)));
const f2    = n=> Math.round(n*100)/100;
const pad   = n=> String(n).padStart(2,'0');
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------- drawing helpers (design system from sample_scroller) ---------- */
function prng(seed){
  let a = seed>>>0;
  return function(){
    a += 0x6D2B79F5; let t = a;
    t = Math.imul(t ^ t>>>15, t|1);
    t ^= t + Math.imul(t ^ t>>>7, t|61);
    return ((t ^ t>>>14)>>>0) / 4294967296;
  };
}

function S(tag, attrs, parent){
  const n = document.createElementNS(NS, tag);
  if(attrs) for(const k in attrs) n.setAttribute(k, attrs[k]);
  if(parent) parent.appendChild(n);
  return n;
}

/* Catmull-Rom through points -> cubic bezier path, for a fluid hand-drawn line */
function smoothD(p, closed){
  const n = p.length;
  if(n < 2) return '';
  if(n === 2) return 'M'+f2(p[0][0])+' '+f2(p[0][1])+'L'+f2(p[1][0])+' '+f2(p[1][1]);
  const get = i => closed ? p[(i+n)%n] : p[clamp(i,0,n-1)];
  let d = 'M'+f2(p[0][0])+' '+f2(p[0][1]);
  const last = closed ? n : n-1;
  for(let i=0;i<last;i++){
    const p0=get(i-1), p1=get(i), p2=get(i+1), p3=get(i+2);
    d += 'C'+f2(p1[0]+(p2[0]-p0[0])/6)+' '+f2(p1[1]+(p2[1]-p0[1])/6)
        +' '+f2(p2[0]-(p3[0]-p1[0])/6)+' '+f2(p2[1]-(p3[1]-p1[1])/6)
        +' '+f2(p2[0])+' '+f2(p2[1]);
  }
  return d + (closed ? 'Z' : '');
}

/* Jitter the points so the stroke reads as inked by hand, not plotted */
function roughPts(pts, amp, seed){
  const r = prng(seed || 7);
  const a = amp == null ? 2.2 : amp;
  return pts.map(function(pt,i){
    const k = (i===0 || i===pts.length-1) ? a*0.45 : a;
    return [pt[0]+(r()-.5)*k, pt[1]+(r()-.5)*k];
  });
}
function roughD(pts, amp, seed, closed){ return smoothD(roughPts(pts, amp, seed), closed); }

/* Sample n points from a parametric function */
function samp(n, fn){ const o=[]; for(let i=0;i<=n;i++) o.push(fn(i/n)); return o; }

/* ---- marker geometry -----------------------------------------------------
   Every mark is a FILLED OUTLINE, not a stroked line: trace the centreline
   out to half-width on each side, wobble both edges, taper toward the ends,
   close the path and fill it.  Stack two translucent offset copies so ink
   reads as having built up where marks cross.  This is what separates a
   drawn mark from a plotted one.
   ------------------------------------------------------------------------ */
const WMUL = matchMedia('(max-width:1000px)').matches ? 1.4 : 1;
const WIDTH = {w1:1.9, w3:5.0, w4:7.2, base:3.2};

function polyLen(p){
  let L=0; for(let i=1;i<p.length;i++) L += Math.hypot(p[i][0]-p[i-1][0], p[i][1]-p[i-1][1]);
  return L;
}
function resample(p, n){
  if(p.length < 2) return p.slice();
  const segs=[]; let acc=0;
  for(let i=1;i<p.length;i++){
    const d = Math.hypot(p[i][0]-p[i-1][0], p[i][1]-p[i-1][1]);
    if(d > 1e-6){ segs.push([acc, acc+d, p[i-1], p[i]]); acc += d; }
  }
  if(!segs.length) return p.slice();
  const out=[];
  for(let k=0;k<n;k++){
    const d = (k/(n-1))*acc;
    let sg = segs[segs.length-1];
    for(let i=0;i<segs.length;i++) if(d <= segs[i][1]){ sg = segs[i]; break; }
    const u = (d - sg[0]) / Math.max(1e-6, sg[1]-sg[0]);
    out.push([lerp(sg[2][0],sg[3][0],u), lerp(sg[2][1],sg[3][1],u)]);
  }
  return out;
}
/* centreline -> filled marker outline */
function markerD(pts, w, seed, closed){
  const n = clamp(Math.round(polyLen(pts)/7), 10, 96);
  const P = closed ? pts.slice() : resample(pts, n);
  const m = P.length;
  if(m < 2) return '';
  const r = prng(seed||3);
  const L=[], R=[];
  for(let i=0;i<m;i++){
    const t = m>1 ? i/(m-1) : 0;
    const a = P[closed ? (i-1+m)%m : Math.max(0,i-1)];
    const b = P[closed ? (i+1)%m   : Math.min(m-1,i+1)];
    let tx = b[0]-a[0], ty = b[1]-a[1];
    const mag = Math.hypot(tx,ty) || 1; tx/=mag; ty/=mag;
    const nx = -ty, ny = tx;
    /* thin at the ends, with a slow swell along the length */
    const taper = closed ? 1 : Math.max(0.2, Math.pow(Math.sin(Math.PI*clamp(t,0,1)), 0.32));
    const wob = 1 + 0.2*Math.sin(t*10 + (seed||0)) + 0.16*(r()-0.5);
    const hw = (w/2) * taper * wob;
    L.push([P[i][0]+nx*hw + (r()-.5)*0.45, P[i][1]+ny*hw + (r()-.5)*0.45]);
    R.push([P[i][0]-nx*hw + (r()-.5)*0.45, P[i][1]-ny*hw + (r()-.5)*0.45]);
  }
  R.reverse();
  if(closed) return smoothD(L,true) + smoothD(R,true);           /* ring, even-odd */
  return smoothD(L,false) + smoothD(R,false).replace('M','L') + 'Z';
}

/* ---- Stroke: a revealable marker mark ---------------------------------- */
let SID = 0, CID = 0;
function Stroke(parent, pts, opt){
  const o = Object.assign({amp:2.2, seed:(SID+=17), cls:'ink', w:null, closed:false, double:true}, opt||{});
  const cl = String(o.cls);
  const wKey = /\bw1\b/.test(cl) ? 'w1' : /\bw3\b/.test(cl) ? 'w3' : /\bw4\b/.test(cl) ? 'w4' : 'base';
  const w = (o.w != null ? o.w : WIDTH[wKey]) * WMUL;
  const tone = (cl.match(/\b(coral|acid|blue|soft|ghost)\b/) || [,''])[1];
  const extra = /\bopt\b/.test(cl) ? ' opt' : '';   /* survives into the mark's class */
  const base = roughPts(pts, o.amp, o.seed);

  const g = S('g',{filter:'url(#grain)'}, parent);
  const shapes = [];
  /* bleed first, so the solid mark sits on top of it */
  if(o.double){
    for(let k=0;k<2;k++){
      const b = S('path',{d: markerD(base, w*(1.35+k*0.3), o.seed+71+k*29, o.closed),
                          class:'mk bleed'+(tone?' '+tone:'')+extra}, g);
      if(o.closed) b.setAttribute('fill-rule','evenodd');
      shapes.push(b);
    }
  }
  const core = S('path',{d: markerD(base, w, o.seed, o.closed),
                         class:'mk'+(tone?' '+tone:'')+extra}, g);
  if(o.closed) core.setAttribute('fill-rule','evenodd');
  shapes.push(core);

  /* reveal along the mark's own direction, lazily — a clip is only built if
     something actually animates this mark */
  let clipRect = null, drawn = -1;
  const first = base[0], last = base[base.length-1];
  function buildClip(){
    let dx = last[0]-first[0], dy = last[1]-first[1];
    if(o.closed || Math.hypot(dx,dy) < 1){ dx = 1; dy = 0; }
    const mg = Math.hypot(dx,dy); dx/=mg; dy/=mg;
    let s0=Infinity, s1=-Infinity, q0=Infinity, q1=-Infinity;
    for(let i=0;i<base.length;i++){
      const vx = base[i][0]-first[0], vy = base[i][1]-first[1];
      const sp = vx*dx + vy*dy, qp = -vx*dy + vy*dx;
      if(sp<s0) s0=sp; if(sp>s1) s1=sp; if(qp<q0) q0=qp; if(qp>q1) q1=qp;
    }
    const pad = w*2 + 6;
    const id = 'mkc'+(++CID);
    const cp = S('clipPath',{id:id}, DEFS);
    clipRect = S('rect',{x:f2(s0-pad), y:f2(q0-pad), width:0, height:f2(q1-q0+pad*2),
      transform:'translate('+f2(first[0])+' '+f2(first[1])+') rotate('+f2(Math.atan2(dy,dx)*180/Math.PI)+')'}, cp);
    clipRect._span = (s1-s0) + pad*2;
    g.setAttribute('clip-path','url(#'+id+')');
  }
  return {
    g: g,
    draw: function(t){
      const k = clamp(t,0,1);
      if(Math.abs(k-drawn) < 0.002) return;
      drawn = k;
      if(k >= 0.999){ if(clipRect) clipRect.setAttribute('width', f2(clipRect._span)); return; }
      if(!clipRect) buildClip();
      clipRect.setAttribute('width', f2(clipRect._span * k));
    },
    full: function(){ this.draw(1); },
    opacity: function(v){ g.style.opacity = v; }
  };
}

function Txt(parent, x, y, str, opt){
  opt = opt || {};
  const t = S('text', {x:x, y:y, class:'lbl '+(opt.cls||''), 'text-anchor':opt.anchor||'start'}, parent);
  t.textContent = str;
  if(opt.rot) t.setAttribute('transform','rotate('+opt.rot+' '+x+' '+y+')');
  t.style.opacity = opt.op != null ? opt.op : 0;
  return t;
}

/* Fade registry: [node, from, to] windows against scene progress */
function Fades(){
  const list = [];
  return {
    add: function(node, from, to){ list.push([node, from, to]); return node; },
    apply: function(p){
      for(let i=0;i<list.length;i++){
        const it = list[i];
        it[0].style.opacity = eo(clamp((p-it[1])/Math.max(0.0001,it[2]-it[1]),0,1));
      }
    }
  };
}

/* ============================================================
   1. SCENE BUILDERS
   Each returns tick(p, idx, local) and may set ctx.readout()
   ============================================================ */
const BUILD = {};


(function(){
  const sv = S('svg',{width:0, height:0, 'aria-hidden':'true',
                      style:'position:absolute'}, document.body);
  DEFS = S('defs', null, sv);
  /* Stipple. Noise luminance is subtracted from each mark's alpha, so a fill
     breaks up the way pigment does on paper instead of sitting flat. Applied
     to the mark group, which never changes once built — the reveal animates a
     clip above it — so the browser caches the filtered result. */
  const f = S('filter',{id:'grain', x:'-6%', y:'-6%', width:'112%', height:'112%',
                        'color-interpolation-filters':'sRGB'}, DEFS);
  S('feTurbulence',{type:'fractalNoise', baseFrequency:'0.62', numOctaves:'2', seed:'7', result:'n'}, f);
  S('feColorMatrix',{in:'n', type:'luminanceToAlpha', result:'a'}, f);
  S('feComposite',{in:'SourceGraphic', in2:'a', operator:'arithmetic',
                   k1:'0', k2:'1', k3:'-0.34', k4:'0'}, f);
})();

/* Graph-paper ruling, drawn into the figure's own SVG so it shares the figure's
   coordinates and its squares stay square at any viewport. Ruled by hand, not
   by a repeating background: the lines wander and a few bear down harder. */

function paperGrid(svg, W, H){
  const g = S('g',{'aria-hidden':'true'}, null);
  svg.insertBefore(g, svg.firstChild);
  const r = prng(31);
  const line = (x1,y1,x2,y2,op) => {
    const n = S('line',{x1:f2(x1), y1:f2(y1), x2:f2(x2), y2:f2(y2), class:'gridline'}, g);
    n.style.opacity = f2(op);
    return n;
  };
  const STEP = 42;
  for(let x=0; x<=W; x+=STEP)  line(x+(r()-.5)*2, 0, x+(r()-.5)*2, H, 0.05+r()*0.028);
  for(let y=0; y<=H; y+=STEP)  line(0, y+(r()-.5)*2, W, y+(r()-.5)*2, 0.05+r()*0.028);
  for(let x=0; x<=W; x+=STEP*5) line(x+(r()-.5)*2, 0, x+(r()-.5)*2, H, 0.085+r()*0.03);
  for(let y=0; y<=H; y+=STEP*5) line(0, y+(r()-.5)*2, W, y+(r()-.5)*2, 0.085+r()*0.03);
  /* the few rulings that got pressed harder */
  for(let i=0;i<8;i++){
    const x = Math.round(r()*(W/STEP))*STEP;
    line(x+(r()-.5)*2.5, r()*H*0.2, x+(r()-.5)*2.5, H-r()*H*0.2, 0.1+r()*0.07);
  }
  return g;
}


/* __SCENES__ */

/* ---------- scroll driver ---------- */
const reg = [];
document.querySelectorAll('[data-scene]').forEach(function(root){
  const build = BUILD[root.dataset.scene];
  if(!build) return;
  const ctx = {
    root: root,
    svg: root.querySelector('.plot'),
    frame: root.querySelector('.stage-frame'),
    beatsEl: root.querySelector('.beats'),
    beats: [].slice.call(root.querySelectorAll('[data-beat]')),
    hud: root.querySelector('[data-hud-i]'),
    rk: root.querySelector('[data-readout-k]'),
    rv: root.querySelector('[data-readout-v]'),
    idx: -1, lastK:'', lastV:''
  };
  ctx.readout = function(k, v){
    if(k !== ctx.lastK){ ctx.lastK = k; if(ctx.rk) ctx.rk.textContent = k; }
    if(v !== ctx.lastV){ ctx.lastV = v; if(ctx.rv) ctx.rv.textContent = v; }
  };
  /* the ruling goes down before the figure does */
  if(ctx.svg){
    const vb = (ctx.svg.getAttribute('viewBox')||'0 0 1600 900').split(/\s+/).map(Number);
    paperGrid(ctx.svg, vb[2], vb[3]);
    ctx.svg.setAttribute('viewBox', vb.join(' '));
  }
  /* beat copy rides over the figure in a card, so wrap what the markup declared */
  ctx.beats.forEach(function(b){
    const card = document.createElement('div');
    card.className = 'beat-card';
    while(b.firstChild) card.appendChild(b.firstChild);
    b.appendChild(card);
  });
  ctx.tick = build(ctx) || function(){};
  reg.push(ctx);
});

const railLinks = [].slice.call(document.querySelectorAll('#rail a'));
const rail = document.getElementById('rail');
const bar = document.getElementById('progressBar');
const header = document.getElementById('siteHeader');
const heroTick = buildHero();
const codaTick = buildCoda();
const heroEl = document.getElementById('hero');
const codaEl = document.querySelector('.coda');
const darkZones = [].slice.call(document.querySelectorAll('.hero, .ending'));
/* On phones the figure pins to the top of the viewport and the beats scroll
   underneath it, so the reading line has to sit below the figure — not at the
   middle of the viewport, which is behind it. */
const narrow = matchMedia('(max-width:1000px)');

const headerNote = document.getElementById('headerNote');
let lastY = -1, lastVH = -1, force = true, lastNote = '';

function update(y, vh){
  /* ---- read phase ---- */
  let anchor = vh * 0.5;
  if(narrow.matches && reg.length && reg[0].frame){
    const fh = reg[0].frame.getBoundingClientRect().height;
    anchor = Math.min(fh + (vh - fh) * 0.5, vh * 0.86);
  }
  const reads = [];
  for(let s=0; s<reg.length; s++){
    const sc = reg[s];
    const r = sc.root.getBoundingClientRect();
    if(r.bottom < -160 || r.top > vh + 160){ reads.push(null); continue; }
    const cr = sc.beatsEl.getBoundingClientRect();
    const p = clamp((anchor - cr.top) / Math.max(1, cr.height), 0, 1);
    let idx = 0, best = Infinity;
    for(let i=0;i<sc.beats.length;i++){
      const br = sc.beats[i].getBoundingClientRect();
      const d = Math.abs(br.top + br.height/2 - anchor);
      if(d < best){ best = d; idx = i; }
    }
    const br = sc.beats[idx].getBoundingClientRect();
    const local = clamp((anchor - br.top) / Math.max(1, br.height), 0, 1);
    /* the last beat's centre sits at (n-0.5)/n of the way down the list */
    const span = (sc.beats.length - 0.5) / sc.beats.length;
    reads.push({p:clamp(p/span,0,1), idx:idx, local:local, top:r.top, bottom:r.bottom});
  }
  const heroR = heroEl ? heroEl.getBoundingClientRect() : null;
  const codaR = codaEl ? codaEl.getBoundingClientRect() : null;
  let onDark = false;
  for(let i=0;i<darkZones.length;i++){
    const r = darkZones[i].getBoundingClientRect();
    if(r.top <= 52 && r.bottom >= 52){ onDark = true; break; }
  }
  const docMax = document.documentElement.scrollHeight - vh;

  /* ---- write phase ---- */
  bar.style.width = (docMax > 0 ? clamp(y/docMax,0,1)*100 : 0) + '%';
  header.classList.toggle('is-light', !onDark);
  header.classList.toggle('is-away', heroR ? (y > vh*0.1 && heroR.bottom > 90) : false);
  rail.classList.toggle('on-dark', onDark);
  rail.classList.toggle('is-on', y > vh*0.9);

  if(heroR) heroTick(clamp(-heroR.top / Math.max(1, heroR.height*0.9), 0, 1));
  if(codaR) codaTick(clamp((vh*0.92 - codaR.top) / Math.max(1, vh*0.5), 0, 1));

  for(let s=0; s<reg.length; s++){
    const rd = reads[s]; if(!rd) continue;
    const sc = reg[s];
    if(rd.idx !== sc.idx){
      sc.idx = rd.idx;
      for(let i=0;i<sc.beats.length;i++) sc.beats[i].classList.toggle('is-active', i === rd.idx);
      if(sc.hud) sc.hud.textContent = pad(rd.idx+1);
    }
    sc.tick(rd.p, rd.idx, rd.local);
  }

  /* rail active state */
  let active = -1;
  for(let i=0;i<reg.length;i++){
    const rd = reads[i];
    if(rd && rd.top < vh*0.5 && rd.bottom > vh*0.5) active = i;
  }
  for(let i=0;i<railLinks.length;i++) railLinks[i].classList.toggle('is-on', i === active);
  const note = active >= 0
    ? railLinks[active].querySelector('.rail-label').textContent
    : (y > vh*0.5 ? 'A provisional framework' : 'Scroll to draw the story');
  if(note !== lastNote){ lastNote = note; headerNote.textContent = note; }
}

function loop(){
  const y = window.scrollY || window.pageYOffset || 0;
  const vh = window.innerHeight;
  if(force || y !== lastY || vh !== lastVH){
    lastY = y; lastVH = vh; force = false;
    update(y, vh);
  }
  requestAnimationFrame(loop);
}

addEventListener('resize', function(){ force = true; }, {passive:true});
addEventListener('load', function(){ force = true; }, {passive:true});
document.fonts && document.fonts.ready.then(function(){ force = true; });

requestAnimationFrame(loop);

/* Static-render hook. Headless Chrome screenshots before a scroll settles and
   does not advance rAF under a virtual clock, so there is no way to capture a
   scene mid-story from the CLI. This drives every scene to a given progress
   directly, which is also how the still figures are exported. */
window.__story = {
  scenes: reg.map(function(s){ return s.root.id; }),
  freeze: function(id, p){
    for(let i=0;i<reg.length;i++){
      const sc = reg[i];
      if(id && sc.root.id !== id) continue;
      const last = sc.beats.length - 1;
      const idx = Math.min(last, Math.floor(p * sc.beats.length));
      for(let b=0;b<sc.beats.length;b++)
        sc.beats[b].classList.toggle('is-active', b === idx);
      if(sc.hud) sc.hud.textContent = pad(idx+1);
      sc.tick(p, idx, 1);
    }
  },
  freezeAll: function(p){ this.freeze(null, p == null ? 1 : p); }
};
})();
