/* atlas.app.js — the pool page (hockey atlas, 2026-09-29).
 *
 * Every Czech player with a season in a covered league in the window, one row
 * each: games by season coloured by the rung of the league (a sparkline), and
 * his seasons in a table that opens under the row. Above the list, the pool
 * season by season by rung. Data: atlas/pool.json (src/web/charts.py, from
 * outputs/pool.json). The list is plain HTML; the overview chart needs D3.
 */
(function () {
  const root = document.querySelector('[data-atlas-app]');
  if (!root) return;
  const CSS = getComputedStyle(document.documentElement);
  const ACID = CSS.getPropertyValue('--acid').trim() || '#1F5FD6';
  // the rung palette (spec §5): rung 1 the held colour, rung 2 ink, other grey, home the pale base
  const RUNG = {
    '1': { col: ACID, label: 'NHL (rung 1)', short: 'NHL', rank: 0 },
    '2': { col: '#111111', label: 'SHL, Liiga, NL, DEL (rung 2)', short: 'rung 2', rank: 1 },
    other: { col: '#8a8a8a', label: 'other covered league', short: 'other', rank: 2 },
    home: { col: '#c9c9c4', label: 'Extraliga (home)', short: 'home', rank: 3 },
  };
  const NONE = { col: '#e6e6e3', label: 'no season in a covered league' };
  const ORDER = ['1', '2', 'other', 'home'];
  const PAGE = 50;
  const POS = { F: 'forward', D: 'defenceman', G: 'goalkeeper' };
  const BASIS = { citizenship: 'citizenship (league record)', national_team: 'national-team roster', eligibility: 'eligibility only (Extraliga foreigner flag or licence)' };
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fold = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const short = (s) => `${s.slice(2, 4)}/${s.slice(5, 7)}`;
  const mmss = (sec) => (sec == null ? '–' : `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, '0')}`);
  const ui = {
    q: root.querySelector('[data-ax-search]'), pos: root.querySelector('[data-ax-pos]'), rung: root.querySelector('[data-ax-rung]'),
    sort: root.querySelector('[data-ax-sort]'), list: root.querySelector('[data-ax-list]'), head: root.querySelector('[data-ax-head]'),
    count: root.querySelector('[data-ax-count]'), more: root.querySelector('[data-ax-more]'), empty: root.querySelector('[data-ax-empty]'),
    overview: root.querySelector('[data-ax-overview]'), rungs: root.querySelector('[data-ax-rungs]'),
  };
  let DATA = null, SEASONS = [], LATEST = '', limit = PAGE;
  const open = new Set();

  function derive(p) {
    const by = new Map();
    for (const r of p.s) {
      const [season, , rung, , games] = r;
      const cur = by.get(season) || { games: 0, rung, rows: [] };
      cur.games += games; cur.rows.push(r);
      if (RUNG[rung].rank < RUNG[cur.rung].rank) cur.rung = rung;
      by.set(season, cur);
    }
    const now = by.get(LATEST);
    p.d = {
      by, now,
      age: p.b ? +LATEST.slice(0, 4) - p.b : null,
      gNow: now ? now.games : 0,
      rungNow: now ? now.rung : null,
      team: p.l ? p.l.team : '',
      league: p.l ? p.l.league : '',
      peak: Math.max(...[...by.values()].map((v) => v.games), 1),
      search: fold([p.n, ...p.s.map((r) => r[3]), ...p.s.map((r) => r[1])].join(' ')),
    };
    return p;
  }

  const SORTS = {
    games: (a, b) => b.d.gNow - a.d.gNow || b.g - a.g || a.n.localeCompare(b.n),
    total: (a, b) => b.g - a.g || a.n.localeCompare(b.n),
    rung: (a, b) => RUNG[a.r].rank - RUNG[b.r].rank || b.g - a.g,
    age: (a, b) => (a.d.age == null) - (b.d.age == null) || a.d.age - b.d.age || b.d.gNow - a.d.gNow,
    name: (a, b) => a.n.localeCompare(b.n, 'cs'),
  };
  function filtered() {
    const q = fold(ui.q.value.trim()), pos = ui.pos.value, rung = ui.rung.value;
    const rows = DATA.players.filter((p) =>
      (!q || p.d.search.includes(q)) && (!pos || p.p === pos) &&
      (!rung || (rung === 'none' ? !p.d.now : p.d.rungNow === rung)));
    return rows.sort(SORTS[ui.sort.value] || SORTS.games);
  }

  function spark(p) {
    return `<span class="ax-sp" style="--n:${SEASONS.length}" aria-hidden="true">` + SEASONS.map((s) => {
      const v = p.d.by.get(s);
      if (!v) return `<span class="ax-sp-c" title="${short(s)}: ${NONE.label}"><i style="height:2px;background:${NONE.col}"></i></span>`;
      const h = Math.max(10, Math.round((v.games / Math.max(p.d.peak, 60)) * 100));
      return `<span class="ax-sp-c" title="${short(s)}: ${v.games} games, ${RUNG[v.rung].short}"><i style="height:${h}%;background:${RUNG[v.rung].col}"></i></span>`;
    }).join('') + '</span>';
  }
  function rowHtml(p) {
    const isOpen = open.has(p.id);
    return `<tr class="ax-row${isOpen ? ' is-open' : ''}" data-id="${esc(p.id)}">` +
      `<td class="ax-c-name"><button type="button" class="ax-row-btn" aria-expanded="${isOpen}"><span class="ax-row-name">${esc(p.n)}</span>${p.r === '1' ? ' <span class="ax-nt" title="an NHL season in the window">NHL</span>' : ''}</button></td>` +
      `<td class="ax-c-age num">${p.d.age != null ? p.d.age : '–'}</td>` +
      `<td class="ax-c-pos">${p.p || '–'}</td>` +
      `<td class="ax-c-club">${esc(p.d.team || '–')}${p.d.league ? ` <span class="ax-lg">${esc(p.d.league)}</span>` : ''}</td>` +
      `<td class="ax-c-spark">${spark(p)}</td>` +
      `<td class="ax-c-min num">${p.d.now ? p.d.gNow : '–'}</td></tr>` +
      (isOpen ? `<tr class="ax-detail-row"><td colspan="6">${panel(p)}</td></tr>` : '');
  }
  function panel(p) {
    const goalie = p.p === 'G';
    const head = goalie
      ? '<th scope="col">season</th><th scope="col">league</th><th scope="col">team</th><th scope="col" class="num">GP</th><th scope="col" class="num">SV%</th><th scope="col" class="num">GA</th><th scope="col" class="num">TOI/GP</th>'
      : '<th scope="col">season</th><th scope="col">league</th><th scope="col">team</th><th scope="col" class="num">GP</th><th scope="col" class="num">G</th><th scope="col" class="num">A</th><th scope="col" class="num">P</th><th scope="col" class="num">TOI/GP</th>';
    const rows = p.s.slice().sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : RUNG[a[2]].rank - RUNG[b[2]].rank)).map((r) => {
      const [season, league, rung, team, gp, a5, a6, pts, toi, q] = r;
      const lead = `<td class="mono">${season}</td><td><span class="ax-dot" style="background:${RUNG[rung].col}"></span>${esc(league)}</td><td>${esc(team)}</td><td class="num">${gp}</td>`;
      const rest = goalie
        ? `<td class="num">${a5 == null ? '–' : a5.toFixed(3).replace(/^0/, '')}</td><td class="num">${a6}</td><td class="num">${mmss(toi)}</td>`
        : `<td class="num">${a5}</td><td class="num">${a6}</td><td class="num">${pts}</td><td class="num">${mmss(toi)}</td>`;
      return `<tr class="${q ? '' : 'ax-under'}">${lead}${rest}</tr>`;
    }).join('');
    const meta = [POS[p.p] || 'position unknown', p.bd ? `born ${p.bd}` : (p.b ? `born ${p.b}` : 'birth date not published'), `Czech by ${BASIS[p.nb] || p.nb}`];
    return `<div class="ax-panel ax-panel-hk"><div class="ax-panel-head"><div class="ax-panel-id"><p class="ax-panel-name">${esc(p.n)}</p>` +
      `<p class="ax-panel-meta">${meta.map(esc).join(' · ')}</p><p class="ax-panel-rank">${p.g} games in covered leagues, ${esc(DATA.seasons[0])}–${esc(LATEST)}</p></div></div>` +
      `<div class="ax-table-wrap"><table class="ax-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>` +
      `<p class="ax-note">Regular season only. Grey rows are below the games threshold for that league-season. TOI/GP is minutes:seconds where the league publishes it.</p></div>`;
  }

  function render() {
    const rows = filtered();
    const total = DATA.players.length;
    const shown = rows.slice(0, limit);
    ui.count.textContent = `${rows.length === total ? total : `${rows.length} of ${total}`} players · showing ${Math.min(limit, rows.length)}`;
    ui.empty.hidden = rows.length > 0;
    ui.more.hidden = rows.length <= limit;
    ui.list.innerHTML = shown.map(rowHtml).join('');
  }

  function headSpark() {
    const th = ui.head.querySelector('.ax-col-spark');
    if (th) th.innerHTML = `<span class="ax-sp ax-sp-head" style="--n:${SEASONS.length}">${SEASONS.map((s) => `<span class="ax-sp-c">${short(s)}</span>`).join('')}</span>`;
  }
  function rungLegend() {
    const used = new Set(DATA.players.flatMap((p) => p.s.map((r) => r[2])));
    ui.rungs.innerHTML = ORDER.filter((k) => used.has(k)).map((k) => `<span><i style="background:${RUNG[k].col}"></i>${RUNG[k].label}</span>`).join('') +
      `<span><i class="ax-legend-none" style="background:${NONE.col}"></i>${NONE.label}</span>`;
  }

  // the pool, season by season: players by the highest rung they played in that season
  function overview() {
    if (typeof d3 === 'undefined' || !ui.overview) return;
    const box = ui.overview.querySelector('[data-ax-overview-chart]');
    const draw = () => {
      box.innerHTML = '';
      const data = SEASONS.map((s) => ({ s, ...DATA.by_season_rung[s] }));
      const keys = ORDER.filter((k) => data.some((d) => d[k]));
      const w = Math.max(300, box.clientWidth || 900), H = w < 560 ? 220 : 260, M = { t: 14, r: 12, b: 28, l: 40 };
      const svg = d3.select(box).append('svg').attr('viewBox', `0 0 ${w} ${H}`).attr('width', '100%').attr('height', H).attr('role', 'img')
        .attr('aria-label', 'Czech players in the covered leagues by season and by rung');
      const x = d3.scaleBand().domain(SEASONS).range([M.l, w - M.r]).padding(0.22);
      const tot = (d) => keys.reduce((a, k) => a + (d[k] || 0), 0);
      const y = d3.scaleLinear().domain([0, d3.max(data, tot)]).nice().range([H - M.b, M.t]);
      const st = (g) => { g.selectAll('path, line').attr('stroke', '#d9d9d5'); g.selectAll('text').attr('fill', '#666').attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 10); };
      svg.append('g').attr('transform', `translate(0,${H - M.b})`).call(d3.axisBottom(x)).call(st);
      svg.append('g').attr('transform', `translate(${M.l},0)`).call(d3.axisLeft(y).ticks(5)).call(st);
      const tip = document.querySelector('.chart-tip') || Object.assign(document.body.appendChild(document.createElement('div')), { className: 'chart-tip', hidden: true });
      data.forEach((d) => {
        let acc = 0;
        keys.forEach((k) => {
          const v = d[k] || 0; if (!v) return;
          svg.append('rect').attr('x', x(d.s)).attr('width', x.bandwidth()).attr('y', y(acc + v)).attr('height', Math.max(0, y(acc) - y(acc + v) - 1)).attr('fill', RUNG[k].col)
            .on('mousemove', (ev) => {
              tip.innerHTML = `<b>${d.s}</b>${keys.map((kk) => `<span>${RUNG[kk].label}: ${d[kk] || 0}</span>`).join('')}<span class="mono">${tot(d)} players</span>`;
              tip.hidden = false; const r = tip.getBoundingClientRect();
              tip.style.left = Math.max(8, Math.min(ev.clientX + 14, innerWidth - r.width - 12)) + 'px'; tip.style.top = (ev.clientY - r.height - 12) + 'px';
            }).on('mouseleave', () => { tip.hidden = true; });
          acc += v;
        });
        svg.append('text').attr('x', x(d.s) + x.bandwidth() / 2).attr('y', y(tot(d)) - 4).attr('text-anchor', 'middle').attr('font-family', 'JetBrains Mono, monospace').attr('font-size', 10).attr('fill', '#111').text(tot(d));
      });
    };
    draw();
    let lw = innerWidth; addEventListener('resize', () => { if (Math.abs(innerWidth - lw) > 8) { lw = innerWidth; draw(); } });
  }

  function bind() {
    const reset = () => { limit = PAGE; render(); };
    ui.q.addEventListener('input', reset);
    [ui.pos, ui.rung, ui.sort].forEach((el) => el.addEventListener('change', reset));
    ui.more.addEventListener('click', () => { limit += PAGE; render(); });
    ui.list.addEventListener('click', (ev) => {
      const tr = ev.target.closest('.ax-row'); if (!tr) return;
      if (ev.target.closest('.ax-detail-row')) return;
      const id = tr.dataset.id;
      if (open.has(id)) open.delete(id); else open.add(id);
      render();
      const again = ui.list.querySelector(`.ax-row[data-id="${window.CSS && window.CSS.escape ? window.CSS.escape(id) : id}"] .ax-row-btn`);
      if (again) again.focus({ preventScroll: true });
    });
  }

  fetch('pool.json').then((r) => (r.ok ? r.json() : Promise.reject(r.status))).then((data) => {
    DATA = data; SEASONS = data.seasons; LATEST = data.latest;
    DATA.players.forEach(derive);
    headSpark(); rungLegend(); bind(); render(); overview();
  }).catch((e) => {
    console.warn('pool failed', e);
    ui.empty.hidden = false; ui.empty.textContent = 'the pool list could not be loaded';
  });
})();
