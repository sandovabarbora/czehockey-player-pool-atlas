/* charts.js — the report's interactive figures (hockey atlas, 2026-09-29).
 *
 * Each <figure data-chart="..."> carries a plain table with the same numbers
 * (print, no scripts). When this runs, the table is hidden and a live chart is
 * drawn from charts/report.json (written by src/web/charts.py from outputs/)
 * in the page's register: ink on white paper, mono capitals for labels, the
 * held jersey blue for Czechia and nothing else.
 *
 * Charts: q1-bars / q7-bars (per million, one season), q1-series / q7-series
 * (the season series), q2-break (the break model), q3-cohorts, q4-youth,
 * q5-abroad, q6-roster. D3 v7 from cdnjs; if it fails to load, the tables stay.
 */
(function () {
  if (typeof d3 === 'undefined') return;
  // the site root, from this script's own address: the question pages sit two levels down
  const SELF = document.currentScript && document.currentScript.src;
  const BASE = SELF ? new URL('.', SELF).href : '';
  const CSS = getComputedStyle(document.documentElement);
  const tok = (n, d) => CSS.getPropertyValue(n).trim() || d;
  const C = {
    acid: tok('--acid', '#1F5FD6'), ink: tok('--ink', '#111111'), muted: tok('--muted', '#666666'),
    rule: tok('--rule', '#d9d9d5'), page: tok('--page-bg', '#ffffff'), grey: '#8a8a8a', pale: '#c9c9c4', none: '#e6e6e3',
  };
  // the rung palette (spec §5): rung 1 the held colour, rung 2 ink, other grey, home the pale base
  const RUNG = { '1': C.acid, '2': C.ink, other: C.grey, home: C.pale, khl: 'url(#hatch)', unknown: C.none };
  const RUNG_SWATCH = { '1': C.acid, '2': C.ink, other: C.grey, home: C.pale, khl: 'repeating-linear-gradient(45deg,#111 0 1.5px,#fff 1.5px 4px)', unknown: C.none };
  const CAT_LABEL = { '1': 'NHL', '2': 'rung 2', home: 'Extraliga', khl: 'KHL', other: 'other league', unknown: 'not placed' };
  const fmt2 = (v) => d3.format('.2f')(v).replace('-', '\u2212'), pct = (v) => d3.format('.1f')(v * 100).replace('-', '\u2212') + '\u00a0%', pct0 = (v) => d3.format('.0f')(v * 100) + '\u00a0%';
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const short = (s) => `${s.slice(2, 4)}/${s.slice(5, 7)}`;

  // ------------------------------------------------------------ helpers
  const tip = document.createElement('div');
  tip.className = 'chart-tip'; tip.hidden = true; document.body.appendChild(tip);
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    const px = Math.max(8, Math.min(x + 14, window.innerWidth - r.width - 12));
    const py = y - r.height - 12 < 60 ? y + 18 : y - r.height - 12;
    tip.style.left = px + 'px'; tip.style.top = py + 'px';
  }
  const hideTip = () => { tip.hidden = true; };
  function mount(fig) {
    fig.querySelectorAll('.fig-table').forEach((t) => t.classList.add('chart-fallback'));
    const box = document.createElement('div'); box.className = 'chart';
    const ctl = document.createElement('div'); ctl.className = 'chart-controls';
    const plot = document.createElement('div'); plot.className = 'chart-plot';
    box.append(ctl, plot);
    fig.insertBefore(box, fig.querySelector('figcaption') || null);
    return { box, ctl, plot };
  }
  function row(parent) { const r = document.createElement('div'); r.className = 'chart-row'; parent.appendChild(r); return r; }
  // a group of chips where one is pressed at a time
  function radio(parent, options, value, cb) {
    const r = row(parent);
    const btns = options.map(([v, label]) => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'chart-chip'; b.textContent = label;
      b.setAttribute('aria-pressed', String(v === value));
      b.addEventListener('click', () => { btns.forEach((x) => x.setAttribute('aria-pressed', String(x === b))); cb(v); });
      r.appendChild(b); return b;
    });
    return r;
  }
  function legend(parent, items) {
    const p = document.createElement('p'); p.className = 'ax-legend chart-legend';
    p.innerHTML = items.map(([label, col, kind]) => `<span><i class="${kind === 'line' ? 'lg-line' : kind === 'hollow' ? 'lg-hollow' : ''}" style="${kind === 'line' ? `border-top-color:${col}` : kind === 'hollow' ? '' : `background:${col}`}"></i>${esc(label)}</span>`).join('');
    parent.appendChild(p); return p;
  }
  function svgIn(plot, h) {
    plot.innerHTML = '';
    const w = Math.max(280, plot.clientWidth || 900);
    const svg = d3.select(plot).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('width', '100%').attr('height', h).attr('role', 'img');
    const defs = svg.append('defs');
    const pat = defs.append('pattern').attr('id', 'hatch').attr('width', 5).attr('height', 5).attr('patternUnits', 'userSpaceOnUse').attr('patternTransform', 'rotate(45)');
    pat.append('rect').attr('width', 5).attr('height', 5).attr('fill', '#ffffff');
    pat.append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 5).attr('stroke', C.ink).attr('stroke-width', 1.6);
    return { svg, w, h, narrow: w < 560 };
  }
  const axisStyle = (g) => {
    g.selectAll('path, line').attr('stroke', C.rule);
    g.selectAll('text').attr('fill', C.muted).attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 10).attr('letter-spacing', '0.06em');
  };
  const label = (svg, x, y, text, anchor = 'start', fill = C.muted) => svg.append('text').attr('class', 'chart-axis-label').attr('x', x).attr('y', y).attr('text-anchor', anchor).attr('fill', fill).text(text);
  const redraws = [];
  let lastW = window.innerWidth;
  window.addEventListener('resize', () => {
    if (Math.abs(window.innerWidth - lastW) < 8) return; lastW = window.innerWidth;
    clearTimeout(window.__chartsT); window.__chartsT = setTimeout(() => redraws.forEach((f) => f()), 120);
  });

  // ------------------------------------------------------------ per million, one season: sorted bars, the peer median as a rule
  function bars(fig, block, opts) {
    const { ctl, plot } = mount(fig);
    const state = { metric: 'nhl' };
    radio(ctl, [['nhl', 'NHL'], ['top5', 'NHL + rung 2']], 'nhl', (v) => { state.metric = v; draw(); });
    function draw() {
      const key = state.metric + '_pm';
      const rows = block.bars.slice().sort((a, b) => b[key] - a[key]);
      const med = block.peer_median[state.metric + '_per_million'];
      const rowH = 30, M = { t: 22, r: 64, b: 28, l: 108 };
      const { svg, w } = svgIn(plot, M.t + M.b + rowH * rows.length);
      const x = d3.scaleLinear().domain([0, d3.max(rows, (d) => d[key]) * 1.05 || 1]).range([M.l, w - M.r]);
      const y = (i) => M.t + i * rowH;
      svg.append('g').attr('transform', `translate(0,${M.t + rowH * rows.length})`).call(d3.axisBottom(x).ticks(w < 560 ? 4 : 8)).call(axisStyle);
      const g = svg.append('g').selectAll('g').data(rows).join('g').attr('transform', (d, i) => `translate(0,${y(i)})`);
      g.append('rect').attr('x', M.l).attr('y', 8).attr('height', rowH - 16).attr('width', (d) => Math.max(1, x(d[key]) - M.l))
        .attr('fill', (d) => (d.iso3 === opts.home ? C.acid : C.ink));
      g.append('text').attr('x', M.l - 10).attr('y', rowH / 2 + 4).attr('text-anchor', 'end').attr('font-size', 13)
        .attr('fill', (d) => (d.iso3 === opts.home ? C.acid : C.ink)).attr('font-weight', (d) => (d.iso3 === opts.home ? 500 : 400)).text((d) => d.name);
      g.append('text').attr('x', (d) => x(d[key]) + 6).attr('y', rowH / 2 + 4).attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 11)
        .attr('fill', (d) => (d.iso3 === opts.home ? C.acid : C.ink)).text((d) => fmt2(d[key]));
      g.append('rect').attr('x', 0).attr('width', w).attr('height', rowH).attr('fill', 'transparent')
        .on('mousemove', (ev, d) => showTip(`<b>${esc(d.name)}</b><span>${d[state.metric]} ${opts.noun} · ${fmt2(d[key])} per million</span>`, ev.clientX, ev.clientY))
        .on('mouseleave', hideTip);
      svg.append('line').attr('x1', x(med)).attr('x2', x(med)).attr('y1', M.t - 6).attr('y2', M.t + rowH * rows.length).attr('stroke', C.muted).attr('stroke-dasharray', '3 3');
      label(svg, x(med) + 4, M.t - 8, `peer median ${fmt2(med)}`);
    }
    redraws.push(draw); draw();
  }

  // ------------------------------------------------------------ season series: every nation, Czechia held, two peers in ink and grey
  function series(fig, blocks, opts) {
    const { ctl, plot } = mount(fig);
    const views = Object.keys(blocks);
    const state = { view: views[0], metric: 'pm', focus: opts.focus.slice() };
    if (views.length > 1) radio(ctl, views.map((v) => [v, blocks[v].label]), state.view, (v) => { state.view = v; draw(); });
    radio(ctl, [['pm', 'per million'], ['n', 'players']], 'pm', (v) => { state.metric = v; draw(); });
    const pick = row(ctl);
    const codes = opts.nations.map((n) => n.iso3).filter((c) => c !== opts.home);
    const name = Object.fromEntries(opts.nations.map((n) => [n.iso3, n.name]));
    const chips = codes.map((c) => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'chart-chip'; b.textContent = name[c];
      b.addEventListener('click', () => {
        const i = state.focus.indexOf(c);
        if (i >= 0) state.focus.splice(i, 1); else { state.focus.push(c); if (state.focus.length > 2) state.focus.shift(); }
        draw();
      });
      pick.appendChild(b); return [c, b];
    });
    const lg = document.createElement('p'); lg.className = 'ax-legend chart-legend'; ctl.appendChild(lg);
    const colour = (c) => (c === opts.home ? C.acid : c === state.focus[0] ? C.ink : c === state.focus[1] ? C.grey : C.rule);
    function draw() {
      chips.forEach(([c, b]) => b.setAttribute('aria-pressed', String(state.focus.includes(c))));
      lg.innerHTML = [opts.home, ...state.focus].map((c) => `<span><i class="lg-line" style="border-top-color:${colour(c)}"></i>${esc(name[c])}</span>`).join('') + '<span><i class="lg-line" style="border-top-color:' + C.rule + '"></i>the other peers</span>';
      const b = blocks[state.view];
      const seasons = b.seasons;
      const H = opts.height || 380, M = { t: 16, r: 56, b: 34, l: 40 };
      const { svg, w, narrow } = svgIn(plot, H);
      const x = d3.scalePoint().domain(seasons).range([M.l, w - M.r]).padding(0.4);
      const val = (c, i) => b.nations[c][state.metric][i];
      const maxV = d3.max(Object.keys(b.nations).flatMap((c) => b.nations[c][state.metric])) || 1;
      const y = d3.scaleLinear().domain([0, maxV * 1.06]).nice().range([H - M.b, M.t]);
      const every = narrow ? 6 : 3;
      svg.append('g').attr('transform', `translate(0,${H - M.b})`).call(d3.axisBottom(x).tickValues(seasons.filter((s, i) => i % every === 0)).tickFormat(short)).call(axisStyle);
      svg.append('g').attr('transform', `translate(${M.l},0)`).call(d3.axisLeft(y).ticks(5)).call(axisStyle);
      // seasons that are a lower bound (rung 2 nationality incomplete): a pale band
      if (b.complete) {
        const first = b.complete.indexOf(true);
        if (first > 0) {
          const x1 = x(seasons[first]) - x.step() / 2;
          svg.append('rect').attr('x', M.l).attr('y', M.t).attr('width', Math.max(0, x1 - M.l)).attr('height', H - M.b - M.t).attr('fill', '#f6f6f4');
          label(svg, M.l + 6, M.t + 12, narrow ? 'lower bound' : 'lower bound: rung 2 nationality incomplete');
        }
      }
      const line = d3.line().defined((d) => d != null).x((d, i) => x(seasons[i])).y((d) => y(d));
      const order = Object.keys(b.nations).sort((a, c) => (colour(a) === C.rule ? 0 : a === opts.home ? 2 : 1) - (colour(c) === C.rule ? 0 : c === opts.home ? 2 : 1));
      svg.append('g').selectAll('path').data(order).join('path').attr('fill', 'none')
        .attr('stroke', colour).attr('stroke-width', (c) => (c === opts.home ? 2.6 : colour(c) === C.rule ? 1 : 1.6))
        .attr('d', (c) => line(seasons.map((s, i) => val(c, i))));
      const ends = order.filter((c) => colour(c) !== C.rule).map((c) => {
        let i = seasons.length - 1; while (i > 0 && val(c, i) == null) i--; return { c, v: val(c, i), i };
      }).sort((a, c) => y(a.v) - y(c.v));
      let lastY = -Infinity;
      ends.forEach((e) => { e.y = Math.max(y(e.v) + 4, lastY + 12); lastY = e.y; });
      svg.append('g').selectAll('text').data(ends).join('text').attr('class', 'chart-axis-label').attr('x', w - M.r + 6).attr('y', (e) => e.y).attr('fill', (e) => colour(e.c)).text((e) => e.c);
      if (opts.missing) opts.missing.forEach((s) => { if (seasons.includes(s)) label(svg, x(s), H - M.b - 6, 'lockout', 'middle'); });
      const hover = svg.append('line').attr('y1', M.t).attr('y2', H - M.b).attr('stroke', C.muted).attr('stroke-dasharray', '2 3').style('display', 'none');
      svg.on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev, svg.node());
        const i = Math.round((mx - M.l) / x.step()); if (i < 0 || i >= seasons.length) { hideTip(); hover.style('display', 'none'); return; }
        hover.style('display', null).attr('x1', x(seasons[i])).attr('x2', x(seasons[i]));
        const rows = Object.keys(b.nations).map((c) => [c, val(c, i)]).filter(([, v]) => v != null).sort((a, c) => c[1] - a[1])
          .map(([c, v]) => `<span${c === opts.home ? ' style="text-decoration:underline"' : ''}>${esc(name[c])}: ${state.metric === 'pm' ? fmt2(v) : v}</span>`).join('');
        const lb = b.complete && !b.complete[i] ? '<span class="mono">lower bound</span>' : '';
        showTip(`<b>${seasons[i]}</b>${rows || '<span>no season (lockout)</span>'}${lb}`, ev.clientX, ev.clientY);
      }).on('mouseleave', () => { hideTip(); hover.style('display', 'none'); });
    }
    redraws.push(draw); draw();
  }

  // ------------------------------------------------------------ q2: the break model, one nation at a time
  function breakModel(fig, q2, home) {
    const { ctl, plot } = mount(fig);
    const codes = Object.keys(q2.nations);
    const state = { c: home };
    radio(ctl, codes.map((c) => [c, q2.nations[c].name]), home, (v) => { state.c = v; draw(); });
    const lg = document.createElement('p'); lg.className = 'ax-legend chart-legend'; ctl.appendChild(lg);
    function draw() {
      const d = q2.nations[state.c], seasons = q2.seasons;
      const held = state.c === home ? C.acid : C.ink;
      lg.innerHTML = `<span><i style="background:${held};border-radius:50%"></i>players (20+ games)</span><span><i class="lg-line" style="border-top-color:${held}"></i>fitted level</span><span><i style="background:#e9eefb"></i>90\u00a0% HDI</span><span><i style="background:${C.ink}"></i>step with median factor below 1</span><span><i style="background:${C.pale}"></i>step with median factor above 1</span>`;
      const H = 440, top = 300, M = { t: 16, r: 20, b: 34, l: 40 };
      const { svg, w, narrow } = svgIn(plot, H);
      const x = d3.scalePoint().domain(seasons).range([M.l, w - M.r]).padding(0.5);
      const y = d3.scaleLinear().domain([0, d3.max([...d.hi, ...d.n.filter((v) => v != null)]) * 1.05]).nice().range([top, M.t]);
      const yb = d3.scaleLinear().domain([0, Math.max(0.1, d3.max(d.steps.flatMap((s) => s.marginal)))]).range([H - M.b, top + 36]);
      svg.append('g').attr('transform', `translate(${M.l},0)`).call(d3.axisLeft(y).ticks(5)).call(axisStyle);
      svg.append('g').attr('transform', `translate(0,${H - M.b})`).call(d3.axisBottom(x).tickValues(seasons.filter((s, i) => i % (narrow ? 6 : 3) === 0)).tickFormat(short)).call(axisStyle);
      const band = d3.area().x((v, i) => x(seasons[i])).y0((v, i) => y(d.lo[i])).y1((v, i) => y(d.hi[i]));
      svg.append('path').attr('d', band(d.median)).attr('fill', state.c === home ? '#e9eefb' : '#ececea');
      svg.append('path').attr('d', d3.line().x((v, i) => x(seasons[i])).y((v) => y(v))(d.median)).attr('fill', 'none').attr('stroke', held).attr('stroke-width', 2);
      svg.append('g').selectAll('circle').data(d.n.map((v, i) => [v, i]).filter(([v]) => v != null)).join('circle')
        .attr('cx', ([, i]) => x(seasons[i])).attr('cy', ([v]) => y(v)).attr('r', 3.2).attr('fill', held);
      label(svg, M.l + 4, M.t + 8, 'players');
      // the break seasons' probabilities under the series: a fall in ink, a rise in the pale base
      const bw = Math.max(2, x.step() * 0.36);
      d.steps.forEach((s, k) => {
        svg.append('g').selectAll('rect').data(s.marginal.map((p, i) => [p, i]).filter(([p]) => p > 0)).join('rect')
          .attr('x', ([, i]) => x(seasons[i]) - bw + k * bw).attr('width', bw).attr('y', ([p]) => yb(p)).attr('height', ([p]) => yb(0) - yb(p))
          .attr('fill', s.direction === 'down' ? C.ink : C.pale);
      });
      label(svg, M.l + 4, top + 26, narrow ? 'probability of a step, by season' : 'probability that a step falls in this season');
      svg.append('line').attr('x1', M.l).attr('x2', w - M.r).attr('y1', yb(0)).attr('y2', yb(0)).attr('stroke', C.rule);
      svg.on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev, svg.node());
        const i = Math.floor((mx - M.l) / x.step()); if (i < 0 || i >= seasons.length) return hideTip();
        const steps = d.steps.map((s) => `<span>step ${s.order}: ${pct(s.marginal[i])}</span>`).join('');
        showTip(`<b>${seasons[i]}</b><span>${d.n[i] == null ? 'no season (lockout)' : d.n[i] + ' players'}</span><span>fitted ${d.median[i].toFixed(1)} (${d.lo[i].toFixed(1)}–${d.hi[i].toFixed(1)})</span>${steps}`, ev.clientX, ev.clientY);
      }).on('mouseleave', hideTip);
    }
    redraws.push(draw); draw();
  }

  // ------------------------------------------------------------ q3: cohorts, Czechia against each peer and the peer median
  function cohorts(fig, q3, nations, home) {
    const { ctl, plot } = mount(fig);
    const name = Object.fromEntries(nations.map((n) => [n.iso3, n.name]));
    const state = { pos: 'all' };
    radio(ctl, [['all', 'all'], ['F', 'forwards'], ['D', 'defencemen'], ['G', 'goalkeepers']], 'all', (v) => { state.pos = v; draw(); });
    legend(ctl, [['Czechia', C.acid], ['peer median', C.ink], ['a peer', C.grey], ['peer left out of the median', '', 'hollow']]);
    const POS = { F: 'forwards', D: 'defencemen', G: 'goalkeepers' };
    function draw() {
      const rows = q3.rows.filter((r) => state.pos === 'all' || r.position === state.pos);
      const rowH = 34, M = { t: 10, r: 24, b: 30, l: 150 };
      const { svg, w } = svgIn(plot, M.t + M.b + rowH * rows.length);
      const maxV = d3.max(rows.flatMap((r) => Object.values(r.pm))) || 1;
      const x = d3.scaleSymlog().constant(0.5).domain([0, maxV * 1.1]).range([M.l, w - M.r]);
      const ticks = [0, 0.5, 1, 2, 5, 10, 20, 50].filter((t) => t <= maxV * 1.1);
      svg.append('g').attr('transform', `translate(0,${M.t + rowH * rows.length})`).call(d3.axisBottom(x).tickValues(ticks).tickFormat(d3.format('~g'))).call(axisStyle);
      rows.forEach((r, i) => {
        const cy = M.t + i * rowH + rowH / 2;
        const g = svg.append('g');
        g.append('line').attr('x1', M.l).attr('x2', w - M.r).attr('y1', cy).attr('y2', cy).attr('stroke', '#ececea');
        g.append('text').attr('x', M.l - 10).attr('y', cy + 4).attr('text-anchor', 'end').attr('font-size', 12).attr('fill', C.ink).text(`${POS[r.position]}, ${r.band}`);
        Object.entries(r.pm).filter(([c]) => c !== home).forEach(([c, v]) => {
          const inMed = r.in_median.includes(c);
          g.append('circle').attr('cx', x(v)).attr('cy', cy).attr('r', 4).attr('fill', inMed ? C.grey : '#ffffff').attr('stroke', C.grey)
            .on('mousemove', (ev) => showTip(`<b>${esc(name[c])}</b><span>${r.counts[c]} players · ${fmt2(v)} per million</span>${inMed ? '' : '<span class="mono">left out of the median: ages or positions unknown</span>'}`, ev.clientX, ev.clientY))
            .on('mouseleave', hideTip);
        });
        g.append('line').attr('x1', x(r.median)).attr('x2', x(r.median)).attr('y1', cy - 9).attr('y2', cy + 9).attr('stroke', C.ink).attr('stroke-width', 2);
        g.append('circle').attr('cx', x(r.pm[home])).attr('cy', cy).attr('r', 6).attr('fill', C.acid)
          .on('mousemove', (ev) => showTip(`<b>Czechia · ${POS[r.position]}, ${r.band}</b><span>${r.counts[home]} players · ${fmt2(r.pm[home])} per million</span><span>peer median ${fmt2(r.median)}</span><span>${r.shortfall > 0 ? `${r.shortfall.toFixed(1)} players below the peer median` : 'at or above the peer median'}</span>`, ev.clientX, ev.clientY))
          .on('mouseleave', hideTip);
      });
      label(svg, w - M.r, M.t + rowH * rows.length + 26, 'players per million (log scale)', 'end');
    }
    redraws.push(draw); draw();
  }

  // ------------------------------------------------------------ q4: under-21 share of games / ice time by league
  function youth(fig, q4) {
    const { ctl, plot } = mount(fig);
    const state = { m: 'games' };
    radio(ctl, [['games', 'share of games'], ['toi', 'share of ice time']], 'games', (v) => { state.m = v; draw(); });
    const STY = { Extraliga: [C.acid, 2.6, null], Liiga: [C.ink, 1.6, null], SHL: [C.grey, 1.6, null], NL: [C.pale, 1.4, '4 3'], DEL: [C.pale, 1.4, '1 3'] };
    const lg = document.createElement('p'); lg.className = 'ax-legend chart-legend'; ctl.appendChild(lg);
    function draw() {
      const seasons = q4.seasons;
      const leagues = Object.keys(q4.leagues).filter((l) => q4.leagues[l][state.m].some((v) => v != null));
      lg.innerHTML = leagues.map((l) => `<span><i class="lg-line" style="border-top-color:${STY[l][0]};border-top-style:${STY[l][2] ? 'dashed' : 'solid'}"></i>${l}${q4.leagues[l].measured.some(Boolean) ? '' : ' (not measured)'}</span>`).join('');
      const H = 360, M = { t: 16, r: 84, b: 34, l: 44 };
      const { svg, w, narrow } = svgIn(plot, H);
      const x = d3.scalePoint().domain(seasons).range([M.l, w - M.r]).padding(0.4);
      const maxV = d3.max(leagues.flatMap((l) => q4.leagues[l][state.m])) || 0.1;
      const y = d3.scaleLinear().domain([0, maxV * 1.1]).nice().range([H - M.b, M.t]);
      svg.append('g').attr('transform', `translate(0,${H - M.b})`).call(d3.axisBottom(x).tickValues(seasons.filter((s, i) => i % (narrow ? 3 : 1) === 0)).tickFormat(short)).call(axisStyle);
      svg.append('g').attr('transform', `translate(${M.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(pct0)).call(axisStyle);
      const line = d3.line().defined((v) => v != null).x((v, i) => x(seasons[i])).y((v) => y(v));
      leagues.slice().reverse().forEach((l) => {
        const [col, sw, dash] = STY[l];
        svg.append('path').attr('d', line(q4.leagues[l][state.m])).attr('fill', 'none').attr('stroke', col).attr('stroke-width', sw).attr('stroke-dasharray', dash);
      });
      const ends = leagues.map((l) => ({ l, v: q4.leagues[l][state.m].at(-1) })).filter((e) => e.v != null).sort((a, b) => y(a.v) - y(b.v));
      let lastY = -Infinity; ends.forEach((e) => { e.y = Math.max(y(e.v) + 4, lastY + 12); lastY = e.y; });
      ends.forEach((e) => label(svg, w - M.r + 6, e.y, e.l, 'start', STY[e.l][0] === C.pale ? C.muted : STY[e.l][0]));
      const hover = svg.append('line').attr('y1', M.t).attr('y2', H - M.b).attr('stroke', C.muted).attr('stroke-dasharray', '2 3').style('display', 'none');
      svg.on('mousemove', (ev) => {
        const [mx] = d3.pointer(ev, svg.node());
        const i = Math.round((mx - M.l) / x.step()); if (i < 0 || i >= seasons.length) return hideTip();
        hover.style('display', null).attr('x1', x(seasons[i])).attr('x2', x(seasons[i]));
        const rows = leagues.map((l) => { const L = q4.leagues[l]; const v = L[state.m][i]; return v == null ? '' : `<span>${l}: ${pct(v)}${L.measured[i] ? '' : ` <em class="tag">ages known for ${pct0(L.known[i])} of games</em>`}</span>`; }).join('');
        showTip(`<b>${seasons[i]}</b>${rows}`, ev.clientX, ev.clientY);
      }).on('mouseleave', () => { hideTip(); hover.style('display', 'none'); });
    }
    redraws.push(draw); draw();
  }

  // ------------------------------------------------------------ q5: how each nation's players fare against the league median
  function abroad(fig, q5, nations, home) {
    const { ctl, plot } = mount(fig);
    const name = Object.fromEntries(nations.map((n) => [n.iso3, n.name]));
    const state = { m: 'toi' };
    radio(ctl, [['toi', 'ice time per game'], ['ppg', 'points per game']], 'toi', (v) => { state.m = v; draw(); });
    legend(ctl, [['Czechia', C.acid], ['a peer (10+ player-seasons)', C.ink], ['a peer, fewer', '', 'hollow']]);
    function draw() {
      const leagues = Object.keys(q5.leagues);
      const rowH = 64, M = { t: 18, r: 24, b: 34, l: 80 };
      const { svg, w } = svgIn(plot, M.t + M.b + rowH * leagues.length);
      const all = leagues.flatMap((l) => Object.values(q5.leagues[l]).map((v) => v[state.m])).filter((v) => v != null);
      const x = d3.scaleLog().domain([Math.min(0.9, d3.min(all) * 0.94), Math.max(1.1, d3.max(all) * 1.06)]).range([M.l, w - M.r]);
      const tv = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5].filter((t) => t >= x.domain()[0] && t <= x.domain()[1]);
      svg.append('g').attr('transform', `translate(0,${M.t + rowH * leagues.length})`).call(d3.axisBottom(x).tickValues(w < 560 ? tv.filter((t, i) => i % 2 === 0 || t === 1) : tv).tickFormat((t) => `×${t}`)).call(axisStyle);
      svg.append('line').attr('x1', x(1)).attr('x2', x(1)).attr('y1', M.t - 8).attr('y2', M.t + rowH * leagues.length).attr('stroke', C.ink);
      label(svg, x(1) + 4, M.t - 6, 'league median');
      leagues.forEach((l, i) => {
        const cy = M.t + i * rowH + rowH / 2;
        svg.append('line').attr('x1', M.l).attr('x2', w - M.r).attr('y1', cy).attr('y2', cy).attr('stroke', '#ececea');
        svg.append('text').attr('x', M.l - 12).attr('y', cy + 4).attr('text-anchor', 'end').attr('font-size', 13).attr('fill', C.ink).text(l);
        const pts = Object.entries(q5.leagues[l]).filter(([, v]) => v[state.m] != null).sort(([a], [b]) => (a === home) - (b === home));
        pts.forEach(([c, v]) => {
          const isHome = c === home, big = v.n >= 10;
          const dot = svg.append('circle').attr('cx', x(v[state.m])).attr('cy', cy).attr('r', isHome ? 7 : 4.5)
            .attr('fill', isHome ? C.acid : big ? C.ink : '#ffffff').attr('stroke', isHome ? C.acid : C.ink);
          if (isHome) svg.append('text').attr('x', x(v[state.m])).attr('y', cy - 12).attr('text-anchor', 'middle').attr('class', 'chart-axis-label').attr('fill', C.acid).text(`CZE ×${fmt2(v[state.m])}`);
          dot.on('mousemove', (ev) => showTip(`<b>${esc(name[c])} in the ${l}</b><span>ice time ×${fmt2(v.toi)} · points ×${fmt2(v.ppg)} the median</span><span class="mono">${v.players} players · ${v.n} player-seasons</span>`, ev.clientX, ev.clientY)).on('mouseleave', hideTip);
        });
      });
      label(svg, w - M.r, M.t + rowH * leagues.length + 30, w < 560 ? 'ratio to the median (log)' : 'median player to league-season-position median (log scale)', 'end');
    }
    redraws.push(draw); draw();
  }

  // ------------------------------------------------------------ q6: where the national team's players played
  function roster(fig, q6, nations, home) {
    const { ctl, plot } = mount(fig);
    const name = Object.fromEntries(nations.map((n) => [n.iso3, n.name]));
    const state = { v: 'nations' };
    radio(ctl, [['nations', 'every nation, mean since 2010'], ['home', 'Czechia, tournament by tournament']], 'nations', (v) => { state.v = v; draw(); });
    legend(ctl, q6.categories.map((k) => [CAT_LABEL[k], RUNG_SWATCH[k]]));
    function draw() {
      const cats = q6.categories;
      if (state.v === 'nations') {
        const rows = Object.entries(q6.mean_shares).sort((a, b) => (b[1]['1'] + b[1]['2']) - (a[1]['1'] + a[1]['2']));
        const rowH = 30, M = { t: 8, r: 16, b: 28, l: 108 };
        const { svg, w } = svgIn(plot, M.t + M.b + rowH * rows.length);
        const x = d3.scaleLinear().domain([0, 1]).range([M.l, w - M.r]);
        svg.append('g').attr('transform', `translate(0,${M.t + rowH * rows.length})`).call(d3.axisBottom(x).ticks(5).tickFormat(pct0)).call(axisStyle);
        rows.forEach(([c, sh], i) => {
          const y0 = M.t + i * rowH;
          svg.append('text').attr('x', M.l - 10).attr('y', y0 + rowH / 2 + 4).attr('text-anchor', 'end').attr('font-size', 13).attr('fill', c === home ? C.acid : C.ink).attr('font-weight', c === home ? 500 : 400).text(name[c]);
          let acc = 0;
          cats.forEach((k) => {
            const v = sh[k] || 0; if (!v) return;
            svg.append('rect').attr('x', x(acc)).attr('y', y0 + 6).attr('height', rowH - 12).attr('width', Math.max(0, x(acc + v) - x(acc) - 1)).attr('fill', RUNG[k])
              .on('mousemove', (ev) => showTip(`<b>${esc(name[c])}</b><span>${CAT_LABEL[k]}: ${pct(v)} of roster spots</span>`, ev.clientX, ev.clientY)).on('mouseleave', hideTip);
            acc += v;
          });
          if (c === home) svg.append('rect').attr('x', M.l - 4).attr('y', y0 + 4).attr('width', 2).attr('height', rowH - 8).attr('fill', C.acid);
        });
      } else {
        const ev = q6.home_by_event;
        const H = 340, M = { t: 12, r: 12, b: 44, l: 36 };
        const { svg, w, narrow } = svgIn(plot, H);
        const x = d3.scaleBand().domain(ev.map((e) => `${e.event} ${e.year}`)).range([M.l, w - M.r]).padding(0.18);
        const y = d3.scaleLinear().domain([0, d3.max(ev, (e) => e.players)]).nice().range([H - M.b, M.t]);
        svg.append('g').attr('transform', `translate(${M.l},0)`).call(d3.axisLeft(y).ticks(5)).call(axisStyle);
        const ax = svg.append('g').attr('transform', `translate(0,${H - M.b})`).call(d3.axisBottom(x).tickFormat((d) => (narrow ? `'${d.slice(-2)}` : d.replace(' ', ' ')))).call(axisStyle);
        ax.selectAll('text').attr('transform', narrow ? null : 'rotate(-40)').attr('text-anchor', narrow ? 'middle' : 'end').attr('dx', narrow ? 0 : '-0.4em').attr('dy', narrow ? '0.9em' : '0.5em');
        ev.forEach((e) => {
          let acc = 0; const k0 = `${e.event} ${e.year}`;
          cats.forEach((k) => {
            const v = e[k] || 0; if (!v) return;
            svg.append('rect').attr('x', x(k0)).attr('width', x.bandwidth()).attr('y', y(acc + v)).attr('height', y(acc) - y(acc + v) - 1).attr('fill', RUNG[k])
              .on('mousemove', (m) => showTip(`<b>${e.event === 'OG' ? 'Olympics' : 'World Championship'} ${e.year}</b><span>${CAT_LABEL[k]}: ${v} of ${e.players} players</span>`, m.clientX, m.clientY)).on('mouseleave', hideTip);
            acc += v;
          });
        });
        label(svg, M.l + 4, M.t + 8, 'players on the roster');
      }
    }
    redraws.push(draw); draw();
  }

  // ------------------------------------------------------------ run
  fetch(BASE + 'charts/report.json').then((r) => (r.ok ? r.json() : null)).then((D) => {
    if (!D) return;
    const home = D.home;
    const run = {
      'q1-bars': (f) => bars(f, D.q1, { home, noun: 'players' }),
      'q1-series': (f) => series(f, {
        nhl: { label: 'NHL, from 1995/96', ...D.q1.nhl_series },
        top5: { label: 'NHL + rung 2, from 2008/09', ...D.q1.top5_series },
      }, { home, nations: D.nations, focus: ['FIN', 'SWE'], missing: ['2004/05'] }),
      'q2-break': (f) => breakModel(f, D.q2, home),
      'q3-cohorts': (f) => cohorts(f, D.q3, D.nations, home),
      'q4-youth': (f) => youth(f, D.q4),
      'q5-abroad': (f) => abroad(f, D.q5, D.nations, home),
      'q6-roster': (f) => roster(f, D.q6, D.nations, home),
      'q7-bars': (f) => bars(f, D.q7, { home, noun: 'goalkeepers' }),
      'q7-series': (f) => series(f, { nhl: { label: 'NHL goalkeepers', ...D.q7.nhl_series } }, { home, nations: D.nations, focus: ['FIN', 'SWE'], missing: ['2004/05'], height: 300 }),
    };
    document.querySelectorAll('figure[data-chart]').forEach((fig) => {
      const fn = run[fig.dataset.chart];
      if (!fn) return;
      try { fn(fig); } catch (e) { console.warn('chart failed', fig.dataset.chart, e); fig.querySelectorAll('.fig-table').forEach((t) => t.classList.remove('chart-fallback')); }
    });
  }).catch((e) => console.warn('chart data failed', e));
})();
