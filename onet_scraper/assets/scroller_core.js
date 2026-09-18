
(function(){
"use strict";

/* ============================================================
   0. MATH + UTILITY
   ============================================================ */
const NS = 'http://www.w3.org/2000/svg';
let DEFS = null;   /* one shared defs node for every reveal clip */
const clamp = (v,a,b)=> v<a?a:(v>b?b:v);
const lerp  = (a,b,t)=> a+(b-a)*t;
/* One place to ask whether motion is wanted at all. The CSS reduced-motion rule
   cannot switch off something it never knew was applied, so the script has to
   check too. */
const AMBIENT = !(window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches);
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

  /* Ambient motion goes on a WRAPPER, not on the mark's own group.

     drift animates transform and breathe animates opacity - which are exactly
     the two things scale() and opacity() write to. A CSS animation beats an
     inline style, so animating the same group the script controls would have
     let the ambience silently override a scene's own state. Today no drifting
     mark is also scaled (drift is ghost-only; the scaled squares are soft,
     violet, blue and acid) but that is a coincidence, not a design. Nesting
     makes the two transforms compose instead of compete. */
  const ambient = AMBIENT && /\bghost\b/.test(cl)
    && !/\bno-amb\b/.test(cl) && (o.seed % 3) === 0;
  const host = ambient ? S('g', {class:'drift breathe'}, parent) : parent;
  const g = S('g',{filter:'url(#grain)'}, host);
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

  /* Idle life. The drift/breathe keyframes were written for this and then never
     applied to anything, so every figure froze solid the moment scrolling
     stopped - which is most of what separates a live graphic from a diagram.
     Only the faintest marks breathe, and only their opacity: translating a
     data point would move it off its own value. Seeded from the mark's seed so
     the phase is scattered but the render stays deterministic. */
  /* Ghost marks only, and only a third of those. Every Stroke group carries the
     grain filter, and animating opacity on 1,400 filtered groups - which
     tagging every ghost and soft mark produced - is a lot of style recalculation
     for an effect that reads the same from a scattered subset. */
  if(ambient){
    const rr = prng(o.seed * 7 + 3);
    host.style.setProperty('--dur', f2(4.6 + rr() * 3.2) + 's');
    host.style.setProperty('--del', f2(rr() * 4.5) + 's');
    /* And a slow wander, which is the other half of a field that looks alive.
       Amplitude is in the drawing's own units - up to about 7 of 1600, so four
       or five screen pixels at a typical width. Enough to catch the eye at the
       edge of vision, not enough to read as a point relocating: these are the
       faintest background marks and they carry context, not a value anyone
       measures off the page. Composited transform, so it costs nothing per
       frame. */
    const ang = rr() * Math.PI * 2, mag = 3.4 + rr() * 3.6;
    host.style.setProperty('--dx', f2(Math.cos(ang) * mag) + 'px');
    host.style.setProperty('--dy', f2(Math.sin(ang) * mag) + 'px');
  }
  if(o.closed) core.setAttribute('fill-rule','evenodd');
  shapes.push(core);

  /* reveal along the mark's own direction, lazily — a clip is only built if
     something actually animates this mark */
  let clipRect = null, drawn = -1, flowPath = null;
  let first = base[0], last = base[base.length-1];
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
  /* Centroid of the base points, for scaling a mark about its own centre. */
  let cx0 = 0, cy0 = 0;
  for (let i=0;i<base.length;i++){ cx0 += base[i][0]; cy0 += base[i][1]; }
  cx0 /= base.length; cy0 /= base.length;
  let curPts = base, curTone = tone, curScale = 1;

  function repaint(){
    for (let i=0;i<shapes.length;i++){
      const bleed = /\bbleed\b/.test(shapes[i].getAttribute('class') || '');
      shapes[i].setAttribute('class',
        'mk' + (bleed ? ' bleed' : '') + (curTone ? ' ' + curTone : '') + extra);
    }
  }

  return {
    g: g,
    /* Swap the tone class without rebuilding geometry - the reveal clip and the
       cached filter both survive, so a colour change is cheap enough to do on
       every frame as the scenario toggle demands. */
    recolor: function(cls){
      const t = (String(cls).match(/\b(coral|acid|blue|violet|soft|ghost)\b/) || [,''])[1];
      if (t === curTone) return;
      curTone = t; repaint();
    },
    scale: function(k){
      if (Math.abs(k - curScale) < 0.001) return;
      curScale = k;
      g.setAttribute('transform', k === 1 ? '' :
        'translate(' + f2(cx0) + ' ' + f2(cy0) + ') scale(' + f2(k) +
        ') translate(' + f2(-cx0) + ' ' + f2(-cy0) + ')');
    },
    /* Re-run the marker geometry over new points. Used by marks whose extent is
       driven by live data rather than fixed at build time. */
    setPoints: function(pts){
      curPts = roughPts(pts, o.amp, o.seed);
      first = curPts[0]; last = curPts[curPts.length-1];
      cx0 = 0; cy0 = 0;
      for (let i=0;i<curPts.length;i++){ cx0 += curPts[i][0]; cy0 += curPts[i][1]; }
      cx0 /= curPts.length; cy0 /= curPts.length;
      let n = 0;
      if (o.double){
        for (let k=0;k<2;k++)
          shapes[n++].setAttribute('d',
            markerD(curPts, w*(1.35+k*0.3), o.seed+71+k*29, o.closed));
      }
      shapes[n].setAttribute('d', markerD(curPts, w, o.seed, o.closed));
      clipRect = null; drawn = -1;   // the reveal must be rebuilt for new extents
    },
    draw: function(t){
      const k = clamp(t,0,1);
      if(Math.abs(k-drawn) < 0.002) return;
      drawn = k;
      if(k >= 0.999){ if(clipRect) clipRect.setAttribute('width', f2(clipRect._span)); return; }
      if(!clipRect) buildClip();
      clipRect.setAttribute('width', f2(clipRect._span * k));
    },
    full: function(){ this.draw(1); },
    opacity: function(v){ g.style.opacity = v; },

    /* An ink highlight that travels along the mark, continuously.

       The marker geometry is a filled outline, not a strokable centreline, so a
       dashed overlay cannot reuse it - this lays a separate stroked path down
       the middle (the same Catmull-Rom curve the outline was built around) and
       animates its dash offset. Motion along a path, rather than motion OF the
       path: nothing moves off its own value, which is why this is safe to put
       on an axis or a fitted curve.

       Composited by the browser as a dash-offset animation, and it lives inside
       the same reveal clip, so it stays hidden until the mark has been drawn. */
    flow: function(on, opt){
      opt = opt || {};
      if(!on){ if(flowPath){ flowPath.remove(); flowPath = null; } return; }
      if(!AMBIENT) return;
      if(!flowPath){
        flowPath = S('path', {d: smoothD(curPts, o.closed), class: 'inkflow'
          + (curTone ? ' ' + curTone : '')}, g);
      } else {
        flowPath.setAttribute('d', smoothD(curPts, o.closed));
      }
      const len = opt.len != null ? opt.len : 46;
      const gap = opt.gap != null ? opt.gap : 320;
      flowPath.style.strokeWidth = f2((opt.w != null ? opt.w : w * 0.8));
      flowPath.style.strokeDasharray = f2(len) + ' ' + f2(gap);
      flowPath.style.setProperty('--flow-span', f2(len + gap));
      flowPath.style.setProperty('--flow-dur', f2(opt.dur != null ? opt.dur : 5.2) + 's');
      flowPath.style.setProperty('--flow-del', f2(opt.delay != null ? opt.delay : 0) + 's');
    }
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

/* The drawing's own coordinate space. Scenes place everything inside this and
   never need to know the viewport - what adapts is the WINDOW onto it, not the
   drawing.

   The stage used to carry a fixed viewBox of 0 0 1600 900 with
   preserveAspectRatio="meet", so at any other aspect ratio it letterboxed: 31%
   of the frame left empty on a 2560-wide monitor, 58% in portrait, with the
   figure stranded in a band across the middle while the HUD stayed pinned to
   the frame edge. Measured, not guessed.

   Extending the viewBox to the container's aspect ratio fixes that without
   touching a single scene coordinate. At 16:9 the box is exactly 1600x900, so
   the composition every scene was drawn against is preserved; anywhere else the
   surplus becomes more ruled paper around the same figure. */
const BASE_VB = {w: 1600, h: 900};

function fitViewBox(svg, host){
  const box = (host || svg.parentElement).getBoundingClientRect();
  if(!box.width || !box.height) return null;
  const ar = box.width / box.height;
  let w = BASE_VB.w, h = BASE_VB.h;
  if(BASE_VB.w / BASE_VB.h < ar) w = h * ar;   /* wider than 16:9: add paper at the sides */
  else h = w / ar;                             /* taller: add paper above and below */
  const vb = [(BASE_VB.w - w) / 2, (BASE_VB.h - h) / 2, w, h];
  svg.setAttribute('viewBox', vb.map(f2).join(' '));
  return vb;
}

/* Redrawable: the ruling has to be re-laid when the box changes, so it owns a
   node it can replace rather than appending another layer each time. */
function paperGrid(svg, vb){
  const prev = svg.querySelector('g[data-grid]');
  if(prev) prev.remove();
  const g = S('g',{'aria-hidden':'true','data-grid':'1'}, null);
  svg.insertBefore(g, svg.firstChild);
  const X0 = vb[0], Y0 = vb[1], W = vb[2], H = vb[3];
  const r = prng(31);
  const line = (x1,y1,x2,y2,op) => {
    const n = S('line',{x1:f2(x1), y1:f2(y1), x2:f2(x2), y2:f2(y2), class:'gridline'}, g);
    n.style.opacity = f2(op);
    return n;
  };
  const STEP = 42;
  /* Start the ruling on a multiple of STEP so the lines do not shift under the
     figure when the box grows - the paper should look like it was ruled once. */
  const sx = Math.floor(X0 / STEP) * STEP, sy = Math.floor(Y0 / STEP) * STEP;
  const ex = X0 + W, ey = Y0 + H;
  for(let x=sx; x<=ex; x+=STEP)  line(x+(r()-.5)*2, Y0, x+(r()-.5)*2, ey, 0.05+r()*0.028);
  for(let y=sy; y<=ey; y+=STEP)  line(X0, y+(r()-.5)*2, ex, y+(r()-.5)*2, 0.05+r()*0.028);
  for(let x=sx; x<=ex; x+=STEP*5) line(x+(r()-.5)*2, Y0, x+(r()-.5)*2, ey, 0.085+r()*0.03);
  for(let y=sy; y<=ey; y+=STEP*5) line(X0, y+(r()-.5)*2, ex, y+(r()-.5)*2, 0.085+r()*0.03);
  /* the few rulings that got pressed harder */
  for(let i=0;i<8;i++){
    const x = sx + Math.round(r()*(W/STEP))*STEP;
    line(x+(r()-.5)*2.5, Y0+r()*H*0.2, x+(r()-.5)*2.5, ey-r()*H*0.2, 0.1+r()*0.07);
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
    ctx.refit = function(){
      const vb = fitViewBox(ctx.svg, ctx.svg.parentElement);
      if(vb) paperGrid(ctx.svg, vb);
    };
    ctx.refit();
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

let PAUSED = false;
function loop(){
  if (PAUSED) { requestAnimationFrame(loop); return; }
  const y = window.scrollY || window.pageYOffset || 0;
  const vh = window.innerHeight;
  if(force || y !== lastY || vh !== lastVH){
    lastY = y; lastVH = vh; force = false;
    update(y, vh);
  }
  requestAnimationFrame(loop);
}

/* A resize changes the aspect ratio, so the window onto every drawing has to be
   refitted and the paper re-ruled - not just the progress recomputed. Debounced,
   because a drag-resize fires continuously and re-ruling is not free. */
let refitTimer = null;
addEventListener('resize', function(){
  force = true;
  clearTimeout(refitTimer);
  refitTimer = setTimeout(function(){
    for(let i=0;i<reg.length;i++) if(reg[i].refit) reg[i].refit();
    force = true;
  }, 120);
}, {passive:true});
addEventListener('load', function(){ force = true; }, {passive:true});
document.fonts && document.fonts.ready.then(function(){ force = true; });

requestAnimationFrame(loop);

/* Static-render hook. Headless Chrome screenshots before a scroll settles and
   does not advance rAF under a virtual clock, so there is no way to capture a
   scene mid-story from the CLI. This drives every scene to a given progress
   directly, which is also how the still figures are exported. */
/* Hand-inked rules under the headings.

   The story's whole visual argument is that it was drawn rather than rendered,
   and the chapter titles were the one place with nothing drawn anywhere near
   them - plain type, then a hard jump to an inked figure. Each heading now
   carries a rule in the same marker geometry as the figures, and it inks itself
   when the heading arrives rather than being there from the start.

   Built from the same roughPts/markerD pair the figures use, so it is the same
   pen, not a CSS border pretending to be one. */
function headingRules(){
  const heads = document.querySelectorAll('[data-rule]');
  if(!heads.length) return;
  const drawn = [];
  heads.forEach(function(h, i){
    /* Uniform scaling. preserveAspectRatio="none" stretched the box to the
       heading's width and flattened the marker geometry into a hairline - the
       pen has a width, and a non-uniform scale destroys it. A short box keeps
       the nib heavy relative to the stroke's length. */
    const svg = S('svg', {class:'headrule', viewBox:'0 0 240 16',
                          preserveAspectRatio:'xMinYMid meet', 'aria-hidden':'true'}, null);
    h.appendChild(svg);
    /* a rule that lifts slightly to the right, the way a hand does */
    const r = prng(9000 + i * 37);
    const pts = [];
    for(let k=0;k<=6;k++){
      const t = k/6;
      pts.push([t*234 + 3, 10 - t*2.0 + (r()-0.5)*2.0]);
    }
    const mk = Stroke(svg, pts, {cls:'ink w3', amp:1.4, seed:9100+i*13, double:false});
    mk.draw(0);
    drawn.push(mk);
  });

  if(!AMBIENT || !('IntersectionObserver' in window)){
    drawn.forEach(function(m){ m.full(); });
    return;
  }
  /* Ink over ~420ms once the heading is properly in view. rAF rather than a CSS
     transition because the reveal is a clip width, not an animatable property
     the compositor can interpolate for us. */
  const io = new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      if(!e.isIntersecting) return;
      const mk = drawn[+e.target.dataset.ruleIdx];
      io.unobserve(e.target);
      const t0 = performance.now();
      (function step(now){
        const t = clamp((now - t0) / 420, 0, 1);
        mk.draw(eo(t));
        if(t < 1) requestAnimationFrame(step);
      })(t0);
    });
  }, {threshold: 0.6});
  heads.forEach(function(h, i){ h.dataset.ruleIdx = i; io.observe(h); });
}
headingRules();

window.__story = {
  scenes: reg.map(function(s){ return s.root.id; }),
  /* Stop the scroll loop before freezing. Otherwise the next frame recomputes
     progress from the real scroll position and overwrites the frozen state -
     and with the beats hidden for a still, that position reads as zero. */
  pause: function(){ PAUSED = true; },
  resume: function(){ PAUSED = false; force = true; },
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
