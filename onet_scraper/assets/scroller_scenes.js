/* ============================================================
   SCENES — one builder per chapter. Each returns tick(p, idx, local).
   D is the data payload written in by scroller.py.
   ============================================================ */
const D = window.__STORY__;
const W = 1600, H = 900;

/* An inked dot. A two-point Stroke renders as a sliver, not a mark, so a dot is
   a small closed polygon run through the same marker geometry as every other
   stroke - it picks up the same wobble, bleed and grain. */
function Dot(parent, cx, cy, r, cls, seed){
  const pts = [];
  for(let i=0;i<8;i++){
    const a = i/8*Math.PI*2;
    pts.push([cx + Math.cos(a)*r, cy + Math.sin(a)*r]);
  }
  return Stroke(parent, pts, {cls:cls, amp:r*0.22, seed:seed, closed:true, w:r*0.9});
}

/* ---------- 01 INVERSION: the same jobs, two measures, no agreement -------- */
BUILD.inversion = function(ctx){
  const g = S('g', null, ctx.svg);
  const L = 430, R = 1170, TOP = 170, BOT = 790;
  const y = r => TOP + r * (BOT - TOP);
  const rows = D.inversion;

  Txt(g, L, TOP - 46, 'P(COMPUTERISATION), 2013', {cls:'sm', anchor:'middle', op:0});
  Txt(g, R, TOP - 46, 'LLM SUSCEPTIBILITY, 2026', {cls:'sm', anchor:'middle', op:0});
  const heads = [g.lastChild.previousSibling, g.lastChild];
  const axisL = Stroke(g, [[L, TOP-22],[L, BOT+22]], {cls:'ink w1 soft', amp:1.6});
  const axisR = Stroke(g, [[R, TOP-22],[R, BOT+22]], {cls:'ink w1 soft', amp:1.6});
  Txt(g, L - 26, TOP - 6, 'HIGH', {cls:'sm dim', anchor:'end', op:0});
  Txt(g, L - 26, BOT + 16, 'LOW', {cls:'sm dim', anchor:'end', op:0});
  const sideLabels = [g.childNodes[g.childNodes.length-2], g.lastChild];

  const placed = [];
  const links = rows.map(function(d, i){
    const hl = d.hl;
    const pts = [[L, y(d.fo)], [L+150, y(d.fo)], [R-150, y(d.ours)], [R, y(d.ours)]];
    const s = Stroke(g, pts, {cls: hl ? 'ink coral w3' : 'ink w1 ghost', amp: hl ? 2.0 : 1.4,
                              seed: 200+i*13});
    const dotL = Dot(g, L, y(d.fo), hl?7:4, hl?'ink coral':'ink soft', 400+i);
    const dotR = Dot(g, R, y(d.ours), hl?7:4, hl?'ink coral':'ink soft', 600+i);
    let ly = y(d.ours) + 5;
    if(d.t){
      while(placed.some(function(v){ return Math.abs(v-ly) < 26; })) ly += 26;
      placed.push(ly);
    }
    const lab = Txt(g, R + 26, ly, d.t, {cls: hl ? 'sm' : 'sm dim', op:0});
    return {s:s, dotL:dotL, dotR:dotR, lab:lab, hl:hl, d:d};
  });

  const note = Txt(g, 800, 862, 'r = 0.006  —  ACROSS 150 OCCUPATIONS WITH BOTH SCORES',
                   {cls:'sm', anchor:'middle', op:0});

  return function(p, idx, local){
    axisL.draw(clamp(p*7,0,1)); axisR.draw(clamp(p*7-.4,0,1));
    heads.forEach(function(h,i){ h.style.opacity = eo(clamp(p*8-i*.3,0,1)); });
    sideLabels.forEach(function(h){ h.style.opacity = eo(clamp(p*6-.5,0,1))*.7; });

    links.forEach(function(k, i){
      const hl = k.hl;
      /* beat 1: the 2013 column only. beat 2: the highlighted job crosses.
         beat 3: every other line follows. */
      const dotIn = eo(clamp(p*6 - i*0.012, 0, 1));
      k.dotL.draw(dotIn);
      const start = hl ? 0.30 : 0.56 + (i % 9) * 0.012;
      const t = eo(clamp((p - start) / 0.20, 0, 1));
      k.s.draw(t);
      k.dotR.draw(t);
      k.s.opacity(hl ? 1 : 0.55);
      k.lab.style.opacity = hl ? eo(clamp((p-start-.05)/.12,0,1))
                               : eo(clamp((p-start-.05)/.12,0,1)) * 0.45;
    });
    note.style.opacity = eo(clamp((p-0.80)/0.12,0,1));

    if(idx === 0) ctx.readout('Mathematicians, 2013', '4.7% chance');
    else if(idx === 1) ctx.readout('Mathematicians, 2026', 'most exposed in STEM');
    else ctx.readout('Agreement between the two', 'r = 0.006');
  };
};

/* ---------- 02 VOCABULARY: 5,717 tasks stand on 963 subtasks -------------- */
BUILD.vocabulary = function(ctx){
  const g = S('g', null, ctx.svg);
  const cols = [
    {n:'287',   k:'STEM OCCUPATIONS', x:300,  count:26},
    {n:'5,717', k:'TASKS',            x:800,  count:64},
    {n:'963',   k:'DISTINCT SUBTASKS',x:1300, count:18},
  ];
  const marks = [], heads = [];
  cols.forEach(function(c, ci){
    const per = Math.ceil(Math.sqrt(c.count)), gap = 26;
    for(let i=0;i<c.count;i++){
      const cx = c.x - (per*gap)/2 + (i%per)*gap + gap/2;
      const cy = 340 + Math.floor(i/per)*gap;
      marks.push({s: Dot(g, cx, cy, 6, ci===2 ? 'ink coral' : 'ink soft', 900+ci*97+i),
                  ci:ci, i:i, n:c.count});
    }
    const big = Txt(g, c.x, 250, c.n, {cls:'big', anchor:'middle', op:0});
    const lab = Txt(g, c.x, 286, c.k, {cls:'sm dim', anchor:'middle', op:0});
    heads.push([big, lab]);
  });
  const a1 = Stroke(g, [[470,300],[630,300]], {cls:'ink w1 soft', amp:1.4});
  const a2 = Stroke(g, [[970,300],[1130,300]], {cls:'ink w1 soft', amp:1.4});
  const back = Stroke(g, [[1300,640],[1300,700],[800,700],[800,640]],
                      {cls:'ink coral w1', amp:1.6});
  const backLab = Txt(g, 1050, 736, 'SCORE 963 ONCE → EVERY TASK AND JOB INHERITS IT',
                      {cls:'sm', anchor:'middle', op:0});

  return function(p, idx){
    marks.forEach(function(m){
      const start = m.ci * 0.22 + (m.i / m.n) * 0.16;
      m.s.draw(eo(clamp((p - start) / 0.10, 0, 1)));
    });
    heads.forEach(function(h, i){
      const o = eo(clamp((p - i*0.22 - 0.05)/0.08, 0, 1));
      h[0].style.opacity = o; h[1].style.opacity = o * 0.7;
    });
    a1.draw(eo(clamp((p-0.20)/0.08,0,1)));
    a2.draw(eo(clamp((p-0.42)/0.08,0,1)));
    back.draw(eo(clamp((p-0.72)/0.16,0,1)));
    backLab.style.opacity = eo(clamp((p-0.84)/0.10,0,1));
    ctx.readout(['Occupations','Tasks','Distinct subtasks','Scored once'][Math.min(idx,3)],
                ['287','5,717','963','6× less work'][Math.min(idx,3)]);
  };
};

/* ---------- 03 AXES: capability and permission are different questions ---- */
BUILD.axes = function(ctx){
  const g = S('g', null, ctx.svg);
  const X0=320, X1=1330, Y0=180, Y1=790;
  const xs = v => X0 + (v-10)/80*(X1-X0);
  const ys = v => Y1 - (v-10)/70*(Y1-Y0);
  const ax = Stroke(g, [[X0,Y1],[X1,Y1]], {cls:'ink w1', amp:1.6});
  const ay = Stroke(g, [[X0,Y1],[X0,Y0]], {cls:'ink w1', amp:1.6});
  Txt(g, (X0+X1)/2, Y1+52, 'EXPOSURE — CAN A MACHINE DO IT', {cls:'sm', anchor:'middle', op:0});
  const xlab = g.lastChild;
  Txt(g, X0-40, (Y0+Y1)/2, 'ANCHORING — MUST A HUMAN', {cls:'sm', anchor:'middle', op:0, rot:-90});
  const ylab = g.lastChild;

  const vsplit = Stroke(g, [[xs(D.splits.x),Y0],[xs(D.splits.x),Y1]], {cls:'ink w1 ghost', amp:1.2});
  const hsplit = Stroke(g, [[X0,ys(D.splits.y)],[X1,ys(D.splits.y)]], {cls:'ink w1 ghost', amp:1.2});
  const dots = D.axes.map(function(d,i){
    return {s: Dot(g, xs(d.e), ys(d.a), 6,
              d.s>=62 ? 'ink coral' : (d.s<=45 ? 'ink blue' : 'ink soft'), 1500+i*7),
            d:d, i:i};
  });
  const qs = [
    Txt(g, xs(80), ys(18), 'DISPLACEABLE', {cls:'sm', anchor:'end', op:0}),
    Txt(g, xs(16), ys(74), 'HUMAN-ANCHORED', {cls:'sm', anchor:'start', op:0}),
  ];
  const counts = [
    Txt(g, xs(80), ys(18)+30, D.quad.disp + ' OCCUPATIONS', {cls:'sm dim', anchor:'end', op:0}),
    Txt(g, xs(16), ys(74)+30, D.quad.anch + ' OCCUPATIONS', {cls:'sm dim', anchor:'start', op:0}),
  ];

  return function(p, idx){
    ax.draw(clamp(p*6,0,1)); ay.draw(clamp(p*6-.2,0,1));
    xlab.style.opacity = eo(clamp(p*6-.3,0,1))*.8;
    ylab.style.opacity = eo(clamp(p*6-.6,0,1))*.8;
    dots.forEach(function(k){
      /* beat 1 draws everything faintly; colour arrives with beat 3 */
      k.s.draw(eo(clamp((p - 0.10 - (k.i%40)*0.004)/0.10, 0, 1)));
      k.s.opacity(p < 0.52 ? 0.34 : 1);
    });
    vsplit.draw(eo(clamp((p-0.52)/0.10,0,1)));
    hsplit.draw(eo(clamp((p-0.58)/0.10,0,1)));
    qs.forEach(function(q,i){ q.style.opacity = eo(clamp((p-0.68-i*.04)/0.08,0,1)); });
    counts.forEach(function(q,i){ q.style.opacity = eo(clamp((p-0.78-i*.04)/0.08,0,1))*.7; });
    ctx.readout(['Exposure','Anchoring','Correlation between them','Split'][Math.min(idx,3)],
                ['can a machine do it','must a human own it','−0.03 — independent',
                 D.quad.disp+' vs '+D.quad.anch][Math.min(idx,3)]);
  };
};

/* ---------- 04 FRONTIER: Watson's two axes and the crossing line ---------- */
BUILD.frontier = function(ctx){
  const g = S('g', null, ctx.svg);
  const X0=330, X1=1330, Y0=170, Y1=780;
  const xs = v => X0 + (v-24)/58*(X1-X0);
  const ys = v => Y1 - (v-26)/60*(Y1-Y0);
  const ax = Stroke(g, [[X0,Y1],[X1,Y1]], {cls:'ink w1', amp:1.6});
  const ay = Stroke(g, [[X0,Y1],[X0,Y0]], {cls:'ink w1', amp:1.6});
  Txt(g, (X0+X1)/2, Y1+52, 'TRACTABILITY — CAN AI LEAD IT', {cls:'sm', anchor:'middle', op:0});
  const xlab = g.lastChild;
  Txt(g, X0-40, (Y0+Y1)/2, 'RESISTANCE — WILL IT BE PERMITTED', {cls:'sm', anchor:'middle', op:0, rot:-90});
  const ylab = g.lastChild;

  const curvePts = [];
  for(let T=28; T<=80; T+=2){ const R = Math.min(96,(53*53)/T); if(R>=26&&R<=86) curvePts.push([xs(T),ys(R)]); }
  const curve = Stroke(g, curvePts, {cls:'ink coral w3', amp:2.0});
  const curveLab = Txt(g, xs(40)+14, ys(Math.min(96,2809/40))-18, 'THE FRONTIER TODAY',
                       {cls:'sm', op:0});

  const CLS = {'Watch point':'ink coral', 'Crossing now':'ink blue',
               'Handed off':'ink', 'Human held':'ink ghost'};
  const dots = D.frontier.map(function(d,i){
    return {s: Dot(g, xs(d.T), ys(d.R), d.cls === 'Watch point' ? 8 : 6,
              CLS[d.cls]||'ink soft', 2200+i*11), d:d, i:i};
  });
  const wpUsed = [];
  const wpLabels = D.watch.slice(0,4).map(function(d,i){
    let ly = ys(d.R) + 4;
    while(wpUsed.some(function(v){ return Math.abs(v-ly) < 30; })) ly -= 30;
    wpUsed.push(ly);
    return Txt(g, xs(d.T)+20, ly, d.t.toUpperCase(), {cls:'sm', op:0});
  });
  const wpCount = Txt(g, 800, 860, D.counts.watch + ' WATCH POINTS — CAPABILITY PRESENT, ACCOUNTABILITY HOLDING THE LINE',
                      {cls:'sm', anchor:'middle', op:0});

  return function(p, idx){
    ax.draw(clamp(p*6,0,1)); ay.draw(clamp(p*6-.2,0,1));
    xlab.style.opacity = eo(clamp(p*6-.3,0,1))*.8;
    ylab.style.opacity = eo(clamp(p*6-.6,0,1))*.8;
    dots.forEach(function(k){
      k.s.draw(eo(clamp((p - 0.08 - (k.i%40)*0.004)/0.10, 0, 1)));
      /* the classes only mean anything once the frontier is on screen */
      k.s.opacity(p < 0.40 ? 0.3 : (k.d.cls === 'Watch point' && p > 0.62 ? 1 : 0.72));
    });
    curve.draw(eo(clamp((p-0.38)/0.18,0,1)));
    curveLab.style.opacity = eo(clamp((p-0.50)/0.10,0,1));
    wpLabels.forEach(function(l,i){ l.style.opacity = eo(clamp((p-0.66-i*.035)/0.08,0,1)); });
    wpCount.style.opacity = eo(clamp((p-0.84)/0.10,0,1));
    ctx.readout(['Tractability','Resistance','The frontier','Watch points'][Math.min(idx,3)],
                ['can AI lead it','will it be permitted','where work crosses',
                 D.counts.watch + ' occupations'][Math.min(idx,3)]);
  };
};

/* ---------- 05 LADDER: six stages, and the distance still to travel ------- */
BUILD.ladder = function(ctx){
  const g = S('g', null, ctx.svg);
  const X0 = 620, X1 = 1330, TOP = 210, GAP = 104;
  const max = Math.max.apply(null, D.ladder.now.concat(D.ladder.reach), 1);
  const xs = v => X0 + v/max*(X1-X0);
  const rows = D.ladder.labels.map(function(name, i){
    const y = TOP + i*GAP;
    const lab = Txt(g, X0-32, y+6, (i+'. '+name).toUpperCase(), {cls:'sm', anchor:'end', op:0});
    const bar = Stroke(g, [[xs(0),y],[xs(Math.max(D.ladder.now[i], D.ladder.reach[i])),y]],
                       {cls:'ink w1 soft', amp:1.2, seed:3100+i*9});
    const dNow = Dot(g, xs(D.ladder.now[i]), y, 9, 'ink soft', 3200+i);
    const dRe  = Dot(g, xs(D.ladder.reach[i]), y, 9, 'ink coral', 3300+i);
    const num  = Txt(g, xs(Math.max(D.ladder.now[i], D.ladder.reach[i]))+26, y+6,
                     D.ladder.now[i] + ' → ' + D.ladder.reach[i], {cls:'sm', op:0});
    return {lab:lab, bar:bar, dNow:dNow, dRe:dRe, num:num, i:i};
  });
  const cross = Txt(g, X0-32, TOP+3*GAP+34, 'HANDOFF BY EROSION — NO EVENT TO OBSERVE',
                    {cls:'sm', anchor:'end', op:0});

  return function(p, idx){
    rows.forEach(function(r){
      const t0 = 0.06 + r.i*0.055;
      r.lab.style.opacity = eo(clamp((p-t0)/0.06,0,1));
      r.bar.draw(eo(clamp((p-t0-0.02)/0.08,0,1)));
      r.dNow.draw(eo(clamp((p-t0-0.04)/0.06,0,1)));
      r.dRe.draw(eo(clamp((p-0.52-r.i*0.04)/0.08,0,1)));
      r.num.style.opacity = eo(clamp((p-0.60-r.i*0.03)/0.08,0,1));
    });
    cross.style.opacity = eo(clamp((p-0.86)/0.10,0,1));
    ctx.readout(['Six stages','Today','Reachable now','Erosion'][Math.min(idx,3)],
                ['of cognitive leadership', D.ladder.now[3]+' at AI-executed',
                 D.ladder.reach[3]+' at AI-executed', 'the quiet crossing'][Math.min(idx,3)]);
  };
};

/* ---------- 06 PEOPLE: weight it by who actually does the work ------------ */
BUILD.people = function(ctx){
  const g = S('g', null, ctx.svg);
  const BX0 = 300, BX1 = 1330, BY = 300, BH = 92;
  let acc = 0;
  const segs = D.people.quadrants.map(function(q, i){
    const w = q.share * (BX1-BX0);
    const x0 = BX0 + acc; acc += w;
    const cls = ['ink coral w3','ink blue w3','ink w3','ink w3 ghost'][i] || 'ink w3 soft';
    const box = Stroke(g, [[x0,BY],[x0+w,BY],[x0+w,BY+BH],[x0,BY+BH]],
                       {cls:cls, amp:1.8, seed:4100+i*13, closed:true});
    const lab = Txt(g, x0+w/2, BY+BH+34, q.name.toUpperCase(), {cls:'sm', anchor:'middle', op:0});
    const pct = Txt(g, x0+w/2, BY-18, Math.round(q.share*100)+'%', {cls:'sm', anchor:'middle', op:0});
    return {box:box, lab:lab, pct:pct, i:i, w:w};
  });
  const total = Txt(g, 800, 200, D.people.total_m + ' MILLION WORKERS',
                    {cls:'big', anchor:'middle', op:0});

  const BY2 = 560;
  const bars = D.people.top.map(function(o, i){
    const y = BY2 + i*62;
    const w = (o.emp / D.people.top[0].emp) * 560;
    const bar = Stroke(g, [[720,y],[720+w,y]], {cls: o.s>=60?'ink coral w4':'ink blue w4',
                                                amp:1.4, seed:4400+i*7});
    const lab = Txt(g, 700, y+6, o.t.toUpperCase(), {cls:'sm', anchor:'end', op:0});
    const val = Txt(g, 720+w+22, y+6, (o.emp/1e6).toFixed(2)+'M · SUSC ' + Math.round(o.s),
                    {cls:'sm dim', op:0});
    return {bar:bar, lab:lab, val:val, i:i};
  });
  const shift = Txt(g, 800, 862, 'WEIGHTING BY HEADCOUNT MOVES THE MEAN BY ' + D.people.shift,
                    {cls:'sm', anchor:'middle', op:0});

  return function(p, idx){
    total.style.opacity = eo(clamp(p*6,0,1));
    segs.forEach(function(s){
      s.box.draw(eo(clamp((p-0.10-s.i*0.05)/0.10,0,1)));
      s.lab.style.opacity = eo(clamp((p-0.16-s.i*0.05)/0.08,0,1));
      s.pct.style.opacity = eo(clamp((p-0.18-s.i*0.05)/0.08,0,1));
    });
    bars.forEach(function(b){
      b.bar.draw(eo(clamp((p-0.52-b.i*0.05)/0.10,0,1)));
      b.lab.style.opacity = eo(clamp((p-0.52-b.i*0.05)/0.08,0,1));
      b.val.style.opacity = eo(clamp((p-0.58-b.i*0.05)/0.08,0,1))*.75;
    });
    shift.style.opacity = eo(clamp((p-0.86)/0.10,0,1));
    ctx.readout(['Workers covered','Displaceable','The two biggest jobs','Net effect'][Math.min(idx,3)],
                [D.people.total_m+' million', Math.round(D.people.quadrants[0].share*100)+'%',
                 'pull opposite ways', D.people.shift][Math.min(idx,3)]);
  };
};

/* ---------- 07 VALIDATION: does anyone else agree ------------------------- */
BUILD.validation = function(ctx){
  const g = S('g', null, ctx.svg);
  const X0=360, X1=1280, Y0=180, Y1=770;
  const xs = v => X0 + (v-15)/70*(X1-X0);
  const ys = v => Y1 - v*(Y1-Y0);
  const ax = Stroke(g, [[X0,Y1],[X1,Y1]], {cls:'ink w1', amp:1.6});
  const ay = Stroke(g, [[X0,Y1],[X0,Y0]], {cls:'ink w1', amp:1.6});
  Txt(g, (X0+X1)/2, Y1+52, 'OUR SUSCEPTIBILITY INDEX', {cls:'sm', anchor:'middle', op:0});
  const xlab = g.lastChild;
  Txt(g, X0-40, (Y0+Y1)/2, 'HUMAN EXPERT RATING', {cls:'sm', anchor:'middle', op:0, rot:-90});
  const ylab = g.lastChild;
  const dots = D.validation.map(function(d,i){
    return {s: Dot(g, xs(d.x), ys(d.y), 6, 'ink blue', 5200+i*7), i:i};
  });
  const fit = Stroke(g, [[xs(20),ys(D.fit.a+D.fit.b*20)],[xs(82),ys(D.fit.a+D.fit.b*82)]],
                     {cls:'ink coral w3', amp:1.8});
  const rlab = Txt(g, X0+40, Y0+40, 'r = 0.85', {cls:'big', op:0});
  const sub = Txt(g, X0+40, Y0+76, 'AGAINST INDEPENDENT HUMAN ANNOTATORS', {cls:'sm dim', op:0});

  return function(p, idx){
    ax.draw(clamp(p*6,0,1)); ay.draw(clamp(p*6-.2,0,1));
    xlab.style.opacity = eo(clamp(p*6-.3,0,1))*.8;
    ylab.style.opacity = eo(clamp(p*6-.6,0,1))*.8;
    dots.forEach(function(k){
      k.s.draw(eo(clamp((p - 0.12 - (k.i%40)*0.005)/0.10, 0, 1)));
    });
    fit.draw(eo(clamp((p-0.50)/0.16,0,1)));
    rlab.style.opacity = eo(clamp((p-0.62)/0.10,0,1));
    sub.style.opacity = eo(clamp((p-0.68)/0.10,0,1))*.7;
    ctx.readout(['A model rating work','Published human ratings','Agreement'][Math.min(idx,2)],
                ['is an assertion','268 of 268 matched','r = 0.85'][Math.min(idx,2)]);
  };
};

/* ---------- hero + coda ---------------------------------------------------- */
function buildHero(){
  const svg = document.getElementById('heroCanvas');
  if(!svg) return function(){};
  const g = S('g', null, svg);
  const pts = [];
  for(let i=0;i<=60;i++){ const t=i/60; pts.push([120+t*960, 640 - Math.pow(t,2.6)*470]); }
  const flat = [];
  for(let i=0;i<=60;i++){ const t=i/60; flat.push([120+t*960, 640 - t*90]); }
  const a = Stroke(g, flat, {cls:'ink w1 soft', amp:2.4, seed:11});
  const b = Stroke(g, pts, {cls:'ink acid w3', amp:2.6, seed:23});
  return function(t){ a.draw(clamp(t*2.2,0,1)); b.draw(clamp(t*1.7-0.12,0,1)); };
}

function buildCoda(){
  const svg = document.getElementById('codaCanvas');
  if(!svg) return function(){};
  const g = S('g', null, svg);
  const s = Stroke(g, [[80,150],[420,150],[760,150],[1100,150]], {cls:'ink acid w1', amp:2.2});
  return function(t){ s.draw(clamp(t,0,1)); };
}
