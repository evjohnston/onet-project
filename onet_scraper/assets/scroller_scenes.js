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
  let curveLit = false;
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
    const cd = eo(clamp((p-0.38)/0.18,0,1));
    curve.draw(cd);
    /* Once the frontier is drawn, ink keeps travelling along it. The curve is
       the claim this chapter is making, and a still line does not read as a
       moving boundary. */
    if(cd > 0.98 && !curveLit){ curveLit = true; curve.flow(true, {dur: 6.4, len: 70, gap: 300}); }
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
  /* Both hero curves keep ink running along them once they are drawn - this is
     the first thing on the page and it was completely still. The flat line
     moves slowly, the rising one faster, so the pair reads as two rates rather
     than two lines. */
  /* The hero is driven by scroll, so at scroll 0 - which is what everyone sees
     first - both curves were undrawn and the page opened completely still.
     They now ink themselves on arrival and then keep ink running along them, so
     there is motion before the reader has done anything. Scroll still drives
     the draw once it starts; the entrance only ever sets a floor. */
  let intro = 0, lit = false;
  const t0 = performance.now();
  function entrance(now){
    intro = eo(clamp((now - t0 - 260) / 1500, 0, 1));
    render(0);
    if(intro < 1) requestAnimationFrame(entrance);
  }
  function render(t){
    const u = Math.max(t, intro);
    a.draw(clamp(u*2.2,0,1));
    b.draw(clamp(u*1.7-0.12,0,1));
    if(!lit && u > 0.42){
      lit = true;
      a.flow(true, {dur: 9.5, len: 30, gap: 300, w: 2.4});
      b.flow(true, {dur: 5.6, len: 60, gap: 260, w: 3.4});
    }
  }
  if(AMBIENT) requestAnimationFrame(entrance); else { intro = 1; render(0); }
  return render;
}

function buildCoda(){
  const svg = document.getElementById('codaCanvas');
  if(!svg) return function(){};
  const g = S('g', null, svg);
  const s = Stroke(g, [[80,150],[420,150],[760,150],[1100,150]], {cls:'ink acid w1', amp:2.2});
  let lit = false;
  return function(t){
    s.draw(clamp(t,0,1));
    if(!lit && t > 0.8){ lit = true; s.flow(true, {dur: 7.4, len: 42, gap: 380}); }
  };
}

/* ---------- 02b COMPOSITION: a job is a bundle of tasks ------------------- */
BUILD.composition = function(ctx){
  const g = S('g', null, ctx.svg);
  const byCode = {}; D.comp.forEach(function(c){ byCode[c.c] = c; });
  const picks = [byCode[D.exemplars.all], byCode[D.exemplars.split], byCode[D.exemplars.none]]
                  .filter(Boolean);
  const CX = [330, 800, 1270], TOP = 250, COLW = 330;
  const cols = picks.map(function(c, ci){
    const x0 = CX[ci] - COLW/2;
    const n = c.scores.length;
    const rowH = Math.min(22, 430 / n);
    const bars = c.scores.map(function(sc, i){
      const y = TOP + i*rowH;
      const w = Math.max(6, (sc/100) * COLW);
      return {s: Stroke(g, [[x0, y],[x0 + w, y]],
                {cls: sc>=70 ? 'ink coral w3' : (sc<50 ? 'ink blue w3' : 'ink w3 soft'),
                 amp:1.0, seed:7000+ci*211+i}), i:i, n:n};
    });
    const name = Txt(g, CX[ci], 186, c.t.length>26 ? c.t.slice(0,25)+'…' : c.t,
                     {cls:'sm', anchor:'middle', op:0});
    const stat = Txt(g, CX[ci], 216, Math.round(c.hi*100) + '% OF ' + n + ' TASKS EXPOSED',
                     {cls:'sm dim', anchor:'middle', op:0});
    return {bars:bars, name:name, stat:stat, ci:ci};
  });

  /* beat 4: how the whole field distributes */
  const HX0 = 360, HX1 = 1240, HY = 700, HH = 330;
  const bins = [0,0,0,0,0];
  D.comp.forEach(function(c){ bins[Math.min(4, Math.floor(c.hi*5))]++; });
  const hmax = Math.max.apply(null, bins);
  const hist = bins.map(function(v, i){
    const bw = (HX1-HX0)/5, cx = HX0 + i*bw + bw/2;
    const h = (v/hmax)*HH;
    /* a thick vertical stroke, not a closed rectangle - four corner points run
       through Catmull-Rom come out as a lozenge */
    return {s: Stroke(g, [[cx, HY],[cx, HY-h]],
              {cls: i>=3 ? 'ink coral' : 'ink soft', amp:1.2, seed:7600+i, w:bw*0.52}),
            lab: Txt(g, cx, HY+26, (i*20)+'–'+((i+1)*20)+'%',
                     {cls:'sm dim', anchor:'middle', op:0}),
            val: Txt(g, cx, HY-h-16, String(v), {cls:'sm', anchor:'middle', op:0}), i:i};
  });
  const histLab = Txt(g, 800, 862, 'SHARE OF A JOB’S TASKS THAT ARE HIGHLY EXPOSED',
                      {cls:'sm', anchor:'middle', op:0});

  return function(p, idx){
    cols.forEach(function(col){
      const t0 = col.ci * 0.20;
      col.name.style.opacity = eo(clamp((p-t0)/0.06,0,1));
      col.stat.style.opacity = eo(clamp((p-t0-0.03)/0.06,0,1))*.75;
      col.bars.forEach(function(b){
        b.s.draw(eo(clamp((p - t0 - 0.02 - (b.i/b.n)*0.10)/0.08, 0, 1)));
      });
    });
    const fade = 1 - eo(clamp((p-0.62)/0.08,0,1));
    cols.forEach(function(col){
      col.bars.forEach(function(b){ b.s.opacity(fade); });
      col.name.style.opacity = Math.min(col.name.style.opacity || 1, fade);
      col.stat.style.opacity = Math.min(col.stat.style.opacity || 1, fade);
    });
    hist.forEach(function(h){
      h.s.draw(eo(clamp((p-0.66-h.i*0.03)/0.08,0,1)));
      h.lab.style.opacity = eo(clamp((p-0.70-h.i*0.03)/0.06,0,1))*.7;
      h.val.style.opacity = eo(clamp((p-0.74-h.i*0.03)/0.06,0,1));
    });
    histLab.style.opacity = eo(clamp((p-0.88)/0.08,0,1));
    ctx.readout(['A whole job','A job that splits','A job that holds','Across 268 jobs'][Math.min(idx,3)],
                [picks[0] ? Math.round(picks[0].hi*100)+'% of tasks' : '—',
                 picks[1] ? 'spread ±'+picks[1].spread : '—',
                 picks[2] ? Math.round(picks[2].hi*100)+'% of tasks' : '—',
                 bins[0]+' jobs under 20%'][Math.min(idx,3)]);
  };
};

/* ---------- EXPLORER: work through any job yourself ----------------------- */
(function explorer(){
  const sel = document.getElementById('x-occ');
  if(!sel || !D.comp) return;
  const thr = document.getElementById('x-thr');
  const thrOut = document.getElementById('x-thr-out');
  const nEl = document.getElementById('x-n');
  const kEl = document.getElementById('x-k');
  const subEl = document.getElementById('x-sub');
  const listEl = document.getElementById('x-list');
  const strip = document.getElementById('x-strip');
  const byCode = {}; D.comp.forEach(function(c){ byCode[c.c] = c; });

  sel.innerHTML = D.comp.slice().sort(function(a,b){ return a.t.localeCompare(b.t); })
    .map(function(c){ return '<option value="'+c.c+'">'+c.t+'</option>'; }).join('');
  sel.value = D.exemplars.split;

  /* The comparison strip: every occupation as a pip, the current one marked.
     A percentage means little until you can see the distribution behind it. */
  function drawStrip(share){
    const pips = D.comp.map(function(c){
      return '<i class="pip" style="left:'+(c.hi*100).toFixed(1)+'%"></i>';
    }).join('');
    strip.innerHTML = '<div class="track"></div>' + pips +
      '<div class="me" style="left:'+(share*100).toFixed(1)+'%"></div>' +
      '<div class="cap" style="left:0">0% of tasks</div>' +
      '<div class="cap" style="right:0;left:auto">100%</div>';
  }

  function render(){
    const c = byCode[sel.value]; if(!c) return;
    const t = +thr.value;
    thrOut.textContent = t;
    const rows = (D.tasks[c.c] || []);
    const over = rows.filter(function(r){ return r.s >= t; });
    const share = rows.length ? over.length / rows.length : 0;

    nEl.textContent = Math.round(share*100) + '%';
    kEl.textContent = over.length + ' of ' + rows.length + ' tasks at or above ' + t;
    const rank = D.comp.filter(function(o){ return o.hi > c.hi; }).length + 1;
    subEl.innerHTML = 'Ranked <b>' + rank + '</b> of ' + D.comp.length +
      ' STEM occupations by share of tasks highly exposed. Internal spread ±' +
      c.spread + ' — ' + (c.spread > 15
        ? 'this job pulls hard in both directions.'
        : 'its tasks score fairly close together.');

    listEl.innerHTML = rows.map(function(r){
      return '<div class="xtask' + (r.s >= t ? ' over' : '') + '">' +
        '<div class="sc">' + r.s + '</div>' +
        '<div class="tx">' + r.t.replace(/[&<>]/g, function(ch){
          return {'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]; }) + '</div>' +
        '<div class="bar"><i style="width:' + r.s + '%"></i></div>' +
      '</div>';
    }).join('');
    drawStrip(share);
  }

  sel.addEventListener('change', render);
  thr.addEventListener('input', render);
  document.querySelectorAll('[data-xpick]').forEach(function(b){
    b.addEventListener('click', function(){
      sel.value = D.exemplars[b.dataset.xpick] || sel.value; render();
    });
  });
  render();
})();

/* ---------- 03b LEVERAGE: a few activities run through everything --------- */
BUILD.leverage = function(ctx){
  const g = S('g', null, ctx.svg);
  const X0=340, X1=1290, Y0=180, Y1=700;
  const maxN = Math.max.apply(null, D.lev.map(function(r){ return r.n; }));
  /* reach is heavily long-tailed - 27% of subtasks touch one job - so the
     axis is square-root scaled or the whole field stacks on the left edge */
  const xs = v => X0 + Math.sqrt(v/maxN)*(X1-X0);
  const ys = v => Y1 - (v-10)/85*(Y1-Y0);
  const ax = Stroke(g, [[X0,Y1],[X1,Y1]], {cls:'ink w1', amp:1.6});
  const ay = Stroke(g, [[X0,Y1],[X0,Y0]], {cls:'ink w1', amp:1.6});
  Txt(g, (X0+X1)/2, Y1+50, 'JOBS THAT USE THIS ACTIVITY →', {cls:'sm', anchor:'middle', op:0});
  const xlab = g.lastChild;
  Txt(g, X0-42, (Y0+Y1)/2, 'SUSCEPTIBILITY →', {cls:'sm', anchor:'middle', op:0, rot:-90});
  const ylab = g.lastChild;
  [1,5,10,20,40].forEach(function(v){
    if(v>maxN) return;
    const t=Txt(g, xs(v), Y1+24, String(v), {cls:'sm dim', anchor:'middle', op:0});
    t.dataset.tick='1';
  });
  [25,50,75].forEach(function(v){
    const t=Txt(g, X0-14, ys(v)+4, String(v), {cls:'sm dim', anchor:'end', op:0});
    t.dataset.tick='1';
  });
  const ticks = [].slice.call(g.querySelectorAll('[data-tick]'));

  const dots = D.lev.map(function(r,i){
    const lever = r.n >= 12 && r.s >= 65;
    return {s: Dot(g, xs(r.n), ys(r.s), lever?8:5,
             lever ? 'ink coral' : (r.n===1 ? 'ink ghost' : 'ink soft'), 8200+i*5),
            r:r, i:i, lever:lever};
  });
  /* The high-leverage dots sit in one dense cluster, so labelling them in place
     overprints both the cluster and each other. They go in the empty lower-left
     as a ranked callout instead - the chart carries the pattern, the list
     carries the names. */
  const top = D.lev.filter(function(r){ return r.n>=12 && r.s>=65; })
                   .sort(function(a,b){ return b.n*b.s - a.n*a.s; }).slice(0,5);
  const LX = X0 + 24, LY = Y1 - 210;
  const listHead = Txt(g, LX, LY - 26, 'HIGHEST LEVERAGE \u2014 REACH \u00d7 EXPOSURE',
                       {cls:'sm', op:0});
  const labels = top.map(function(r, i){
    const txt = r.n + ' JOBS \u00b7 ' + r.s + ' \u00b7 ' +
                (r.t.length > 42 ? r.t.slice(0,41) + '\u2026' : r.t).toUpperCase();
    return Txt(g, LX, LY + i*30, txt, {cls: i===0 ? 'sm' : 'sm dim', op:0});
  });

  /* beat 4 replaces the scatter rather than sharing the panel with it */
  const CX0=420, CX1=1240, CY0=250, CY1=700;
  const cpts = [[CX0, CY1]].concat(D.cum.map(function(c){
    return [CX0 + Math.sqrt(c.k/D.levStats.total)*(CX1-CX0), CY1 - c.share*(CY1-CY0)];
  }));
  const curve = Stroke(g, cpts, {cls:'ink coral w3', amp:1.6});
  const cAxX = Stroke(g, [[CX0,CY1],[CX1,CY1]], {cls:'ink w1 soft', amp:1.4});
  const cAxY = Stroke(g, [[CX0,CY1],[CX0,CY0]], {cls:'ink w1 soft', amp:1.4});
  const cMark = Dot(g, CX0 + Math.sqrt(100/D.levStats.total)*(CX1-CX0),
                    CY1 - D.levStats.top100*(CY1-CY0), 9, 'ink coral', 8800);
  const cNote = Txt(g, CX0 + Math.sqrt(100/D.levStats.total)*(CX1-CX0) + 18,
                    CY1 - D.levStats.top100*(CY1-CY0) - 8,
                    '100 ACTIVITIES \u2192 ' + Math.round(D.levStats.top100*100) + '%',
                    {cls:'sm', op:0});
  const cX = Txt(g, (CX0+CX1)/2, CY1+44, 'ACTIVITIES, MOST WIDELY USED FIRST \u2192',
                 {cls:'sm', anchor:'middle', op:0});
  const cY = Txt(g, CX0-40, (CY0+CY1)/2, 'SHARE OF ALL LINKS \u2192',
                 {cls:'sm', anchor:'middle', op:0, rot:-90});
  const clab = Txt(g, 800, 862,
    'THE 100 MOST WIDELY USED ACTIVITIES CARRY ' +
    Math.round(D.levStats.top100*100) + '% OF EVERY JOB\u2013ACTIVITY LINK',
    {cls:'sm', anchor:'middle', op:0});

  return function(p, idx){
    ax.draw(clamp(p*6,0,1)); ay.draw(clamp(p*6-.2,0,1));
    xlab.style.opacity = eo(clamp(p*6-.3,0,1))*.8;
    ylab.style.opacity = eo(clamp(p*6-.6,0,1))*.8;
    ticks.forEach(function(t,i){ t.style.opacity = eo(clamp(p*6-.4-i*.05,0,1))*.6; });
    dots.forEach(function(k){
      k.s.draw(eo(clamp((p - 0.06 - (k.i%50)*0.003)/0.10, 0, 1)));
      /* beat 1 is about the singletons; the levers only light up at beat 3 */
      k.s._o = p < 0.30 ? (k.r.n === 1 ? 1 : 0.22) : (p < 0.58 ? 0.62 : (k.lever ? 1 : 0.34));
      k.s.opacity(k.s._o);
    });
    const outro = eo(clamp((p-0.74)/0.08,0,1));      // scatter steps aside
    const fade = 1 - outro;
    listHead.style.opacity = eo(clamp((p-0.58)/0.06,0,1)) * fade;
    labels.forEach(function(l,i){
      l.style.opacity = eo(clamp((p-0.60-i*.035)/0.08,0,1)) * fade;
    });
    dots.forEach(function(k){ if(outro > 0) k.s.opacity(k.s._o * fade); });
    [ax, ay].forEach(function(a){ a.opacity(fade); });
    ticks.forEach(function(t){ t.style.opacity = (t.style.opacity||0) * (fade||0.001); });
    xlab.style.opacity *= fade; ylab.style.opacity *= fade;

    cAxX.draw(outro); cAxY.draw(outro);
    curve.draw(eo(clamp((p-0.78)/0.14,0,1)));
    cMark.draw(eo(clamp((p-0.88)/0.06,0,1)));
    cNote.style.opacity = eo(clamp((p-0.90)/0.06,0,1));
    cX.style.opacity = outro*.8; cY.style.opacity = outro*.8;
    clab.style.opacity = eo(clamp((p-0.92)/0.06,0,1));
    ctx.readout(['Used by one job only','The widest reach','High leverage','Concentration'][Math.min(idx,3)],
                [D.levStats.unique + ' of ' + D.levStats.total,
                 (D.levStats.widest ? D.levStats.widest.n + ' jobs' : '—'),
                 'reach × exposure',
                 Math.round(D.levStats.top100*100) + '% from 100'][Math.min(idx,3)]);
  };
};

/* ---------- COMPARE: two jobs, what they share ---------------------------- */
(function compare(){
  const aSel = document.getElementById('c-a'), bSel = document.getElementById('c-b');
  if(!aSel || !D.occDwa) return;
  const out = document.getElementById('c-out');
  const sum = document.getElementById('c-sum');
  const opts = D.comp.slice().sort(function(a,b){ return a.t.localeCompare(b.t); })
    .map(function(c){ return '<option value="'+c.c+'">'+c.t+'</option>'; }).join('');
  aSel.innerHTML = opts; bSel.innerHTML = opts;
  aSel.value = D.exemplars.pairA || D.exemplars.all;
  bSel.value = D.exemplars.pairB || D.exemplars.none;

  function esc2(x){ return String(x).replace(/[&<>]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }

  function col(title, ids, cls){
    return '<div class="ccol"><h4>' + esc2(title) + '</h4>' +
      (ids.length ? ids.map(function(d){
        const s = D.dwaSusc[d] || 0;
        return '<div class="crow ' + cls + (s>=70?' hot':'') + '">' +
          '<span class="cs">' + s + '</span>' +
          '<span class="ct">' + esc2(D.dwaTitle[d] || d) + '</span></div>';
      }).join('') : '<p class="cnone">None.</p>') + '</div>';
  }

  function render(){
    const A = D.occDwa[aSel.value] || [], B = D.occDwa[bSel.value] || [];
    const setB = new Set(B);
    const shared = A.filter(function(d){ return setB.has(d); });
    const onlyA = A.filter(function(d){ return !setB.has(d); });
    const onlyB = B.filter(function(d){ return A.indexOf(d) < 0; });
    const union = new Set(A.concat(B)).size || 1;
    const bySusc = function(a,b){ return (D.dwaSusc[b]||0) - (D.dwaSusc[a]||0); };
    shared.sort(bySusc); onlyA.sort(bySusc); onlyB.sort(bySusc);

    const aName = aSel.options[aSel.selectedIndex].text;
    const bName = bSel.options[bSel.selectedIndex].text;
    const hotShared = shared.filter(function(d){ return (D.dwaSusc[d]||0) >= 70; }).length;
    sum.innerHTML =
      '<div class="cstat"><div class="n">' + Math.round(shared.length/union*100) + '%</div>' +
      '<div class="k">of their combined activities are shared</div></div>' +
      '<p class="sub"><b>' + shared.length + '</b> activities in common, <b>' +
      onlyA.length + '</b> unique to ' + esc2(aName) + ', <b>' + onlyB.length +
      '</b> unique to ' + esc2(bName) + '. ' +
      (hotShared
        ? '<b>' + hotShared + '</b> of the shared ones score 70 or above — automating those touches both jobs at once.'
        : 'None of the shared activities are highly exposed.') + '</p>';

    out.innerHTML = col('Shared — ' + shared.length, shared, 'sh') +
                    col('Only ' + aName, onlyA, 'oa') +
                    col('Only ' + bName, onlyB, 'ob');
  }
  aSel.addEventListener('change', render);
  bSel.addEventListener('change', render);
  document.querySelectorAll('[data-cpick]').forEach(function(btn){
    btn.addEventListener('click', function(){
      const pair = btn.dataset.cpick.split(',');
      aSel.value = D.exemplars[pair[0]] || aSel.value;
      bSel.value = D.exemplars[pair[1]] || bSel.value;
      render();
    });
  });
  render();
})();

/* ---------- 08 WAGES: what is doing the protecting ----------------------- */
BUILD.wages = function(ctx){
  const g = S('g', null, ctx.svg);
  const dec = (D.wage && D.wage.deciles) || [];
  if(!dec.length) return function(){};
  const X0=340, X1=1300, Y0=210, Y1=640;
  /* domain from the data - anchoring runs well below any sensible fixed floor */
  const all = dec.reduce(function(a,d){
    return a.concat([+d.exposure, +d.anchoring, +d.susceptibility]); }, []);
  const lo = Math.floor(Math.min.apply(null, all)/5)*5 - 2;
  const hi = Math.ceil(Math.max.apply(null, all)/5)*5 + 2;
  const xs = i => X0 + (i/(dec.length-1))*(X1-X0);
  const ys = v => Y1 - (v-lo)/((hi-lo)||1)*(Y1-Y0);
  const ax = Stroke(g, [[X0,Y1],[X1,Y1]], {cls:'ink w1', amp:1.6});
  const ay = Stroke(g, [[X0,Y1],[X0,Y0]], {cls:'ink w1', amp:1.6});
  Txt(g, (X0+X1)/2, Y1+52, 'WAGE DECILE, EQUAL NUMBERS OF WORKERS →',
      {cls:'sm', anchor:'middle', op:0});
  const xlab = g.lastChild;
  for(let v=Math.ceil(lo/10)*10; v<=hi; v+=10){
    const t=Txt(g, X0-14, ys(v)+4, String(v), {cls:'sm dim', anchor:'end', op:0});
    t.dataset.wt='1';
  }
  const yt = [].slice.call(g.querySelectorAll('[data-wt]'));

  const lineE = Stroke(g, dec.map(function(d,i){ return [xs(i), ys(+d.exposure)]; }),
                       {cls:'ink coral w3', amp:1.6});
  const lineA = Stroke(g, dec.map(function(d,i){ return [xs(i), ys(+d.anchoring)]; }),
                       {cls:'ink blue w3', amp:1.6});
  const lineS = Stroke(g, dec.map(function(d,i){ return [xs(i), ys(+d.susceptibility)]; }),
                       {cls:'ink w3 soft', amp:1.6});
  const labE = Txt(g, X1+14, ys(+dec[dec.length-1].exposure)+4, 'EXPOSURE', {cls:'sm', op:0});
  const labA = Txt(g, X1+14, ys(+dec[dec.length-1].anchoring)+4, 'ANCHORING', {cls:'sm', op:0});
  const labS = Txt(g, X1+14, ys(+dec[dec.length-1].susceptibility)+4, 'NET', {cls:'sm dim', op:0});

  const rs = Txt(g, X0+26, Y0+16,
    'WAGE vs EXPOSURE r=' + D.wage.rExposure +
    '   ·   vs ANCHORING r=' + D.wage.rAnchoring, {cls:'sm', op:0});
  const prot = Object.keys(D.wage.protection || {})
    .map(function(k){ return [k, D.wage.protection[k]]; })
    .sort(function(a,b){ return b[1].workers - a[1].workers; });
  const protLabs = prot.map(function(kv, i){
    return Txt(g, X0+26, 742 + i*30,
      Math.round(kv[1].share_of_workers*100) + '%  ·  ' + kv[0].toUpperCase(),
      {cls: i===2 ? 'sm' : 'sm dim', op:0});
  });

  return function(p, idx){
    ax.draw(clamp(p*6,0,1)); ay.draw(clamp(p*6-.2,0,1));
    xlab.style.opacity = eo(clamp(p*6-.3,0,1))*.8;
    yt.forEach(function(t){ t.style.opacity = eo(clamp(p*6-.4,0,1))*.6; });
    lineE.draw(eo(clamp((p-0.08)/0.16,0,1)));
    labE.style.opacity = eo(clamp((p-0.18)/0.08,0,1));
    lineA.draw(eo(clamp((p-0.30)/0.16,0,1)));
    labA.style.opacity = eo(clamp((p-0.40)/0.08,0,1));
    rs.style.opacity = eo(clamp((p-0.46)/0.08,0,1));
    lineS.draw(eo(clamp((p-0.56)/0.16,0,1)));
    labS.style.opacity = eo(clamp((p-0.66)/0.08,0,1))*.7;
    protLabs.forEach(function(l,i){ l.style.opacity = eo(clamp((p-0.76-i*.04)/0.08,0,1)); });
    ctx.readout(['Wage vs exposure','Wage vs anchoring','Net effect','Who is protected'][Math.min(idx,3)],
                ['r = ' + D.wage.rExposure, 'r = ' + D.wage.rAnchoring,
                 'r = ' + D.wage.rSusc,
                 (prot[2] ? Math.round(prot[2][1].share_of_workers*100)+'% by accountability' : '—')
                ][Math.min(idx,3)]);
  };
};

/* ---------- 09 NOWHERE TO GO: exposure is clustered ---------------------- */
BUILD.pathways = function(ctx){
  const g = S('g', null, ctx.svg);
  const T = D.trans || {};
  const moves = T.moves || [];
  const L = 480, R = 1120, TOP = 250, ROW = 62;
  const rows = moves.map(function(m, i){
    const y = TOP + i*ROW;
    const arrow = Stroke(g, [[L, y],[R, y]],
      {cls: m.v === 'Real move' ? 'ink blue w1' : 'ink coral w1', amp:1.4, seed:9100+i});
    const a = Dot(g, L, y, 7, 'ink coral', 9200+i);
    const b = Dot(g, R, y, 7, m.v === 'Real move' ? 'ink blue' : 'ink coral', 9300+i);
    const la = Txt(g, L-20, y+5, m.t.toUpperCase() + '  ' + Math.round(m.s),
                   {cls:'sm', anchor:'end', op:0});
    const lb = Txt(g, R+20, y+5, m.d.toUpperCase() + '  ' + Math.round(m.ds),
                   {cls:'sm dim', op:0});
    return {arrow:arrow, a:a, b:b, la:la, lb:lb, i:i};
  });
  const head = Txt(g, 800, 196, 'THE MOVES THAT EXIST', {cls:'sm', anchor:'middle', op:0});
  const big = Txt(g, 800, 690, String(T.stranded || 0), {cls:'big', anchor:'middle', op:0});
  const bigLab = Txt(g, 800, 726,
    'OF ' + ((T.stranded||0)+(T.withDest||0)) + ' OCCUPATIONS HAVE NO CLOSE, LESS-EXPOSED NEIGHBOUR',
    {cls:'sm', anchor:'middle', op:0});
  const sens = Txt(g, 800, 772,
    'SENSITIVITY — ' +
    (T.sensitivity && T.sensitivity.length
      ? Math.min.apply(null, T.sensitivity.map(function(s){return s.stranded;})) + '–' +
        Math.max.apply(null, T.sensitivity.map(function(s){return s.stranded;})) +
        ' ACROSS THE THRESHOLD SWEEP'
      : 'NOT RUN'),
    {cls:'sm dim', anchor:'middle', op:0});

  return function(p, idx){
    head.style.opacity = eo(clamp(p*6,0,1));
    rows.forEach(function(r){
      const t0 = 0.08 + r.i*0.06;
      r.la.style.opacity = eo(clamp((p-t0)/0.06,0,1));
      r.a.draw(eo(clamp((p-t0)/0.05,0,1)));
      r.arrow.draw(eo(clamp((p-t0-0.02)/0.08,0,1)));
      r.b.draw(eo(clamp((p-t0-0.05)/0.05,0,1)));
      r.lb.style.opacity = eo(clamp((p-t0-0.06)/0.06,0,1))*.8;
    });
    big.style.opacity = eo(clamp((p-0.62)/0.10,0,1));
    bigLab.style.opacity = eo(clamp((p-0.70)/0.08,0,1));
    sens.style.opacity = eo(clamp((p-0.84)/0.08,0,1))*.8;
    ctx.readout(['Moves that exist','Where they lead','Stranded','How firm is that'][Math.min(idx,3)],
                [(T.withDest||0) + ' of ' + ((T.stranded||0)+(T.withDest||0)),
                 (T.realMoves||0) + ' real, ' + (T.carries||0) + ' carry exposure',
                 (T.stranded||0) + ' occupations',
                 'sweep ' + (T.sensitivity && T.sensitivity.length
                   ? Math.min.apply(null,T.sensitivity.map(function(s){return s.stranded;}))+'–'+
                     Math.max.apply(null,T.sensitivity.map(function(s){return s.stranded;}))
                   : '—')][Math.min(idx,3)]);
  };
};

/* ---------- 10 CHURN: has the work already moved? ------------------------ */
BUILD.churn = function(ctx){
  const g = S('g', null, ctx.svg);
  const C = D.churn || {};
  const steps = C.steps || [];
  if(!steps.length) return function(){};

  /* top: turnover per release step */
  const X0=380, X1=1280, Y0=230, Y1=520;
  const maxT = Math.max.apply(null, steps.map(function(s){ return +s.turnover_rate; }));
  const xs = i => X0 + (i/(steps.length-1))*(X1-X0);
  const ys = v => Y1 - (v/(maxT||1))*(Y1-Y0);
  const ax = Stroke(g, [[X0,Y1],[X1,Y1]], {cls:'ink w1', amp:1.4});
  const line = Stroke(g, steps.map(function(s,i){ return [xs(i), ys(+s.turnover_rate)]; }),
                      {cls:'ink w3 soft', amp:1.6});
  const pts = steps.map(function(s,i){
    return {d: Dot(g, xs(i), ys(+s.turnover_rate), 7,
              (+s.year) >= 2023 ? 'ink coral' : 'ink soft', 9500+i),
            lab: Txt(g, xs(i), Y1+26, String(s.year), {cls:'sm dim', anchor:'middle', op:0}),
            i:i};
  });
  const gptMark = Stroke(g, [[xs(3.1), Y0-16],[xs(3.1), Y1]],
                         {cls:'ink coral w1 ghost', amp:1.2});
  const gptLab = Txt(g, xs(3.1)+12, Y0-4, 'CHATGPT', {cls:'sm', op:0});
  const head = Txt(g, X0, Y0-40, 'TASK TURNOVER PER RELEASE — IT DID NOT ACCELERATE',
                   {cls:'sm', op:0});

  /* bottom: the split that matters */
  const f = C.refreshed_only || {}, st = C.stale_only || {};
  const BY = 640, BW = 420;
  const bars = [
    {t:'RE-SURVEYED SINCE 2022', n:C.reviewed_since_cutoff, v:(f.turnover_rate||0), cls:'ink coral'},
    {t:'NEVER RE-SURVEYED', n:C.not_reviewed_since_cutoff, v:(st.turnover_rate||0), cls:'ink soft'},
  ].map(function(b, i){
    const y = BY + i*66;
    const w = (b.v/0.12)*BW;
    return {s: Stroke(g, [[620,y],[620+Math.max(6,w),y]], {cls:b.cls+' w4', amp:1.4, seed:9700+i}),
            lab: Txt(g, 600, y+5, b.t, {cls:'sm', anchor:'end', op:0}),
            val: Txt(g, 620+Math.max(6,w)+18, y+5,
                     (b.v*100).toFixed(1)+'%  ·  '+b.n+' OCCUPATIONS', {cls:'sm dim', op:0}),
            i:i};
  });
  const splitHead = Txt(g, 600, BY-38,
    'BUT THE OVERALL FIGURE IS DILUTED BY OCCUPATIONS NOBODY CHECKED',
    {cls:'sm', anchor:'end', op:0});

  const ex = (C.byExposure || []).map(function(b, i){
    const y = BY + 150 + i*40;
    const w = (b.turnover/0.16)*BW;
    return {s: Stroke(g, [[620,y],[620+Math.max(6,w),y]],
              {cls: i===0 ? 'ink coral w3' : 'ink blue w3', amp:1.3, seed:9800+i}),
            lab: Txt(g, 600, y+5, b.label.toUpperCase(), {cls:'sm', anchor:'end', op:0}),
            val: Txt(g, 620+Math.max(6,w)+18, y+5,
                     (b.turnover*100).toFixed(1)+'%  ·  n='+b.n, {cls:'sm dim', op:0}),
            i:i};
  });
  const exHead = Txt(g, 600, BY+118,
    'AMONG THOSE, THE EXPOSED JOBS MOVED FASTEST', {cls:'sm', anchor:'end', op:0});

  return function(p, idx){
    ax.draw(clamp(p*5,0,1));
    head.style.opacity = eo(clamp(p*6,0,1));
    line.draw(eo(clamp((p-0.05)/0.18,0,1)));
    pts.forEach(function(k){
      k.d.draw(eo(clamp((p-0.06-k.i*0.02)/0.06,0,1)));
      k.lab.style.opacity = eo(clamp((p-0.08-k.i*0.02)/0.06,0,1))*.7;
    });
    gptMark.draw(eo(clamp((p-0.22)/0.08,0,1)));
    gptLab.style.opacity = eo(clamp((p-0.26)/0.06,0,1));

    splitHead.style.opacity = eo(clamp((p-0.40)/0.06,0,1));
    bars.forEach(function(b){
      b.s.draw(eo(clamp((p-0.44-b.i*0.06)/0.10,0,1)));
      b.lab.style.opacity = eo(clamp((p-0.44-b.i*0.06)/0.06,0,1));
      b.val.style.opacity = eo(clamp((p-0.48-b.i*0.06)/0.06,0,1))*.8;
    });
    exHead.style.opacity = eo(clamp((p-0.70)/0.06,0,1));
    ex.forEach(function(b){
      b.s.draw(eo(clamp((p-0.74-b.i*0.05)/0.09,0,1)));
      b.lab.style.opacity = eo(clamp((p-0.74-b.i*0.05)/0.06,0,1));
      b.val.style.opacity = eo(clamp((p-0.78-b.i*0.05)/0.06,0,1))*.8;
    });
    ctx.readout(['Turnover since 2015','After ChatGPT','Who was actually checked','Exposed jobs'][Math.min(idx,3)],
                [((C.turnover_rate||0)*100).toFixed(1)+'% overall',
                 'no acceleration',
                 ((f.turnover_rate||0)*100).toFixed(1)+'% vs '+((st.turnover_rate||0)*100).toFixed(1)+'%',
                 (C.byExposure && C.byExposure[0]
                   ? (C.byExposure[0].turnover*100).toFixed(1)+'% turnover' : '—')
                ][Math.min(idx,3)]);
  };
};

/* ---------- scenario state, shared by every scene that reads it ----------- */
let SCEN = (D.scen && D.scen.gridDefault) ? 'substantial' : 'substantial';
const FATE_CLS = {unchanged:'ink soft', augmented:'ink violet',
                  automated:'ink blue', new:'ink acid'};
const FATE_LABEL = {unchanged:'Unchanged by AI', augmented:'Augmented',
                    automated:'Automated', new:'New tasks'};

/* A grain-textured solid block. This does NOT go through the marker outline
   geometry the line marks use: that traces a centreline out to half-width on
   each side and fills with evenodd, which on a short closed path inverts into a
   donut - at rectangular proportions it renders as an outlined blob. A filled
   block needs a solid path, so this builds its own wobbly quadrilateral and
   fills it, keeping the grain filter and the draw/recolor/scale surface. */
function Block(parent, x, y, w, h, cls, seed){
  const g = S('g', {filter:'url(#grain)'}, parent);
  const tone = t => (String(t).match(/\b(coral|acid|blue|violet|soft|ghost)\b/) || [,''])[1];
  const path = S('path', {class: 'mk ' + tone(cls)}, g);
  let cur = tone(cls), drawn = -1, sc = 1, cx = x + w/2, cy = y + h/2;

  function shape(x, y, w, h){
    const r = prng(seed || 5);
    const j = Math.max(1.2, Math.min(3.2, Math.min(w, h) * 0.06));
    const p = (px, py) => [px + (r()-.5)*j, py + (r()-.5)*j];
    /* Subdivide each edge every ~40 units. Eight corner points run through
       Catmull-Rom bow the long sides of a tall bar into a barrel; enough
       intermediate points keep the edge straight while still reading as inked. */
    const step = 40;
    const edge = (x0, y0, x1, y1) => {
      const n = Math.max(1, Math.round(Math.hypot(x1-x0, y1-y0) / step));
      const out = [];
      for (let i = 0; i < n; i++)
        out.push(p(x0 + (x1-x0)*i/n, y0 + (y1-y0)*i/n));
      return out;
    };
    return smoothD([].concat(
      edge(x, y, x+w, y), edge(x+w, y, x+w, y+h),
      edge(x+w, y+h, x, y+h), edge(x, y+h, x, y)), true);
  }
  path.setAttribute('d', shape(x, y, w, h));

  return {
    g: g,
    setRect: function(nx, ny, nw, nh){
      cx = nx + nw/2; cy = ny + nh/2;
      path.setAttribute('d', shape(nx, ny, Math.max(2, nw), Math.max(2, nh)));
    },
    draw: function(t){
      const k = clamp(t, 0, 1);
      if (Math.abs(k - drawn) < 0.01) return;
      drawn = k; g.style.opacity = k;
    },
    full: function(){ this.draw(1); },
    opacity: function(v){ g.style.opacity = v; },
    recolor: function(c){
      const t = tone(c);
      if (t === cur) return;
      cur = t; path.setAttribute('class', 'mk ' + t);
    },
    scale: function(k){
      if (Math.abs(k - sc) < 0.005) return;
      sc = k;
      g.setAttribute('transform', k === 1 ? '' :
        'translate(' + f2(cx) + ' ' + f2(cy) + ') scale(' + f2(k) +
        ') translate(' + f2(-cx) + ' ' + f2(-cy) + ')');
    },
  };
}

function Square(parent, cx, cy, size, cls, seed){
  return Block(parent, cx - size/2, cy - size/2, size, size, cls, seed);
}

/* Task statements are sentences, and a grid column is ~246 units wide. One line
   of them collides with its neighbours, so captions wrap to two lines and
   ellipsise whatever is left. */
function Caption(parent, cx, cy, text, chars, lines){
  chars = chars || 17; lines = lines || 2;
  const words = String(text).split(/\s+/);
  const rows = [];
  let cur = '';
  for (const w of words){
    if (!cur.length) { cur = w; }
    else if ((cur + ' ' + w).length <= chars) { cur += ' ' + w; }
    else { rows.push(cur); cur = w; if (rows.length === lines) break; }
  }
  if (rows.length < lines && cur.length) rows.push(cur);
  if (words.join(' ').length > rows.join(' ').length && rows.length)
    rows[rows.length-1] = rows[rows.length-1].slice(0, chars-1) + '\u2026';
  return rows.map(function(r, i){
    return Txt(parent, cx, cy + i*18, r, {cls:'sm dim', anchor:'middle', op:0});
  });
}

function fateOf(task, scenario){
  const t = D.scen.thresholds[scenario];
  if(!t) return 'unchanged';
  if(task.e >= t.auto_exposure && task.a < t.auto_anchoring_max) return 'automated';
  if(task.e >= t.augment_exposure) return 'augmented';
  return 'unchanged';
}

function scenarioBar(host, onChange){
  if(!host || !D.scen) return;
  host.innerHTML = '<span class="lbl">Scenario</span>' +
    D.scen.order.map(function(k){
      return '<button data-s="'+k+'"'+(k===SCEN?' class="on"':'')+'>'+
             D.scen.meta[k].label+'</button>';
    }).join('');
  host.querySelectorAll('button').forEach(function(b){
    b.onclick = function(){
      SCEN = b.dataset.s;
      document.querySelectorAll('.scenbar').forEach(function(bar){
        bar.querySelectorAll('button').forEach(function(x){
          x.classList.toggle('on', x.dataset.s === SCEN); });
      });
      document.querySelectorAll('[data-scenblurb]').forEach(function(el){
        el.textContent = D.scen.meta[SCEN].blurb; });
      if(onChange) onChange();
    };
  });
}

/* ---------- 11 TASK GRID: what happens to each task in one job ----------- */
BUILD.taskgrid = function(ctx){
  let g = S('g', null, ctx.svg);
  let built = null, cells = [], newCells = [], title = null;
  const pick = document.getElementById('tg-occ');
  if(pick){
    pick.innerHTML = D.comp.slice().sort(function(a,b){ return a.t.localeCompare(b.t); })
      .filter(function(c){ return (D.tasks[c.c]||[]).length <= 26; })
      .map(function(c){ return '<option value="'+c.c+'">'+c.t+'</option>'; }).join('');
    pick.value = D.scen.gridDefault;
    pick.onchange = function(){ built = null; };
  }
  scenarioBar(document.getElementById('tg-scen'));

  function build(code){
    while(g.firstChild) g.removeChild(g.firstChild);
    cells = []; newCells = [];
    const tasks = (D.tasks[code] || []).slice(0, 24);   // 4 rows of six
    const news = (D.newTasks[code] || []);
    const per = 6, SZ = 40, GX = 246, GY = 172, ROW = 146;
    const occ = D.comp.find(function(c){ return c.c === code; });
    title = Txt(g, 800, 96, (occ ? occ.t : code).toUpperCase() + '’S TASKS',
                {cls:'sm', anchor:'middle', op:0});
    tasks.forEach(function(t, i){
      const cx = 800 - (per-1)*GX/2 + (i % per)*GX;
      const cy = GY + Math.floor(i/per)*ROW;
      const sq = Square(g, cx, cy, SZ, 'ink soft', 11000+i*7);
      const lab = Caption(g, cx, cy + SZ/2 + 22, t.t);
      cells.push({sq:sq, lab:lab, t:t, i:i, cx:cx, cy:cy});
    });
    news.slice(0, 4).forEach(function(txt, j){
      const row = Math.ceil(tasks.length/per);
      const cx = 800 - (per-1)*GX/2 + (j % per)*GX;
      const cy = GY + row*ROW;
      const sq = Square(g, cx, cy, SZ, 'ink acid', 12000+j*7);
      const lab = Caption(g, cx, cy + SZ/2 + 22, txt);
      newCells.push({sq:sq, lab:lab, j:j});
    });
    built = code;
  }

  return function(p, idx){
    const code = pick ? pick.value : D.scen.gridDefault;
    if(built !== code) build(code);
    title.style.opacity = eo(clamp(p*6,0,1));

    /* beat 1 lays the bundle down grey; 2 keeps the unchanged grey; 3 lights the
       augmented; 4 the automated; 5 brings new work in; 6 grows what AI touched */
    const show = {unchanged: p >= 0.00, augmented: p >= 0.36, automated: p >= 0.54};
    cells.forEach(function(c){
      c.sq.draw(eo(clamp((p - 0.02 - (c.i/Math.max(cells.length,1))*0.14)/0.10, 0, 1)));
      const lo = eo(clamp((p - 0.04 - (c.i/Math.max(cells.length,1))*0.14)/0.10, 0, 1))*.85;
      c.lab.forEach(function(n){ n.style.opacity = lo; });
      const f = fateOf(c.t, SCEN);
      const lit = f === 'unchanged' ? true : show[f];
      const cls = lit ? FATE_CLS[f] : FATE_CLS.unchanged;
      if(c.cls !== cls){ c.cls = cls; c.sq.recolor(cls); }
      const grown = p >= 0.86 && f !== 'unchanged';
      c.sq.scale(grown ? 1.45 : 1);
    });
    newCells.forEach(function(n){
      const t = eo(clamp((p - 0.70 - n.j*0.03)/0.08, 0, 1));
      n.sq.draw(t);
      n.lab.forEach(function(x){ x.style.opacity = t*.85; });
    });
    ctx.readout(
      ['A bundle of tasks','What AI cannot do','Augmented','Automated','New work','More gets done'][Math.min(idx,5)],
      [cells.length + ' tasks',
       cells.filter(function(c){ return fateOf(c.t,SCEN)==='unchanged'; }).length + ' unchanged',
       cells.filter(function(c){ return fateOf(c.t,SCEN)==='augmented'; }).length + ' augmented',
       cells.filter(function(c){ return fateOf(c.t,SCEN)==='automated'; }).length + ' automated',
       newCells.length + ' observed new tasks',
       D.scen.meta[SCEN].label + ' scenario'][Math.min(idx,5)]);
  };
};

/* ---------- 12 FLOWS: where the workers end up under each scenario ------- */
BUILD.flows = function(ctx){
  const g = S('g', null, ctx.svg);
  scenarioBar(document.getElementById('fl-scen'));
  const LX = 330, RX = 1010, W = 210, TOP = 190, H = 470;

  const whole = Block(g, LX, TOP, W, H, 'ink soft', 13001);
  const wholeN = Txt(g, LX - 24, TOP + H/2 - 4, '', {cls:'big', anchor:'end', op:0});
  const wholeK = Txt(g, LX - 24, TOP + H/2 + 26, 'ALL STEM WORKERS',
                     {cls:'sm dim', anchor:'end', op:0});

  const segs = [
    {key:'kept',  cls:'ink soft',   label:'LITTLE CHANGE'},
    {key:'moved', cls:'ink violet', label:'COULD MOVE TO SAFER WORK'},
    {key:'stuck', cls:'ink coral',  label:'NOWHERE ADJACENT TO GO'},
  ].map(function(d, i){
    return {
      key: d.key, label: d.label,
      box: Block(g, RX, TOP, W, 10, d.cls, 13100 + i*37),
      /* a thin band from the left column to this segment, so the split reads as
         one population dividing rather than three unrelated bars */
      link: Block(g, LX + W, TOP, RX - LX - W, 6, d.cls, 13200 + i*37),
      n: Txt(g, RX + W + 22, TOP, '', {cls:'big', op:0}),
      k: Txt(g, RX + W + 22, TOP, d.label, {cls:'sm dim', op:0}),
      i: i,
    };
  });

  const head = Txt(g, RX + W/2, TOP - 34, 'UNDER THIS SCENARIO',
                   {cls:'sm', anchor:'middle', op:0});
  const note = Txt(g, 800, 730, '', {cls:'sm', anchor:'middle', op:0});
  const caveat = Txt(g, 800, 766,
    'SCENARIOS ARE ASSUMPTION SETS ABOUT HANDING OVER ACCOUNTABILITY \u2014 NOT FORECASTS, AND UNDATED',
    {cls:'sm dim', anchor:'middle', op:0});

  return function(p, idx){
    const fl = (D.scen.flows || {})[SCEN] || {};
    const share = {
      kept: 1 - (fl.share_reshaped || 0),
      moved: fl.share_with_destination || 0,
      stuck: fl.share_stranded || 0,
    };
    const pct = v => (v*100).toFixed(1) + '%';
    wholeN.textContent = ((fl.workers || 0)/1e6).toFixed(1) + 'M';

    let y = TOP;
    segs.forEach(function(sg){
      const h = Math.max(7, H * share[sg.key]);
      sg.box.setRect(RX, y, W, h);
      sg.link.setRect(LX + W, y + h/2 - 3, RX - LX - W, 6);
      sg.n.setAttribute('y', y + h/2 + 2);
      sg.n.textContent = pct(share[sg.key]);
      sg.k.setAttribute('y', y + h/2 + 28);
      y += h + 10;
    });

    whole.draw(eo(clamp((p-0.02)/0.10,0,1)));
    wholeN.style.opacity = eo(clamp((p-0.06)/0.08,0,1));
    wholeK.style.opacity = eo(clamp((p-0.08)/0.08,0,1))*.75;
    head.style.opacity = eo(clamp((p-0.20)/0.08,0,1));
    segs.forEach(function(sg){
      const t = eo(clamp((p - 0.24 - sg.i*0.17)/0.12, 0, 1));
      sg.link.draw(t*0.5); sg.box.draw(t);
      sg.n.style.opacity = t; sg.k.style.opacity = t*.75;
    });
    note.textContent = D.scen.meta[SCEN].label.toUpperCase() + ' \u2014 ' +
      (fl.occupations_reshaped||0) + ' OF 195 OCCUPATIONS RESHAPED, ' +
      Math.round((fl.mean_task_share_automated||0)*100) +
      '% OF THE AVERAGE TASK LIST AUTOMATED';
    note.style.opacity = eo(clamp((p-0.76)/0.08,0,1));
    caveat.style.opacity = eo(clamp((p-0.86)/0.08,0,1))*.7;
    ctx.readout(['All STEM workers','Little change','Could move','Stranded'][Math.min(idx,3)],
                [((fl.workers||0)/1e6).toFixed(1)+'M', pct(share.kept),
                 pct(share.moved), pct(share.stuck)][Math.min(idx,3)]);
  };
};
