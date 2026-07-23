/* Loss Radar board. Static JSON in, triage list out. */

const FRESH_WINDOW_HOURS = 24;   // the drain bar empties over this span

const state = {
  leads: [],
  generatedAt: null,
  show: { priority: true, watch: true, logged: false },
};

const board = document.getElementById('board');
const stamp = document.getElementById('stamp');

/* ---------- formatting ---------- */

function ageParts(iso) {
  const mins = Math.max(0, (Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 60) return { n: Math.round(mins), unit: 'min' };
  if (mins < 60 * 48) return { n: Math.round(mins / 60), unit: 'hr' };
  return { n: Math.round(mins / 1440), unit: 'day' };
}

function ago(iso) {
  const { n, unit } = ageParts(iso);
  return `${n} ${unit}${n === 1 ? '' : 's'} ago`;
}

function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/* Signals arrive as "alarm_level:second alarm" or "-single_family:mobile home".
   Render them as readable chips, negatives struck through. */
function chip(signal) {
  const negative = signal.startsWith('-');
  const raw = negative ? signal.slice(1) : signal;
  const [rule, hit] = raw.split(':');
  const label = hit ? hit.replace(/_/g, ' ') : rule.replace(/_/g, ' ');
  const key = !negative && (rule === 'alarm_level' || rule === 'electronics_exposure');
  return `<span class="chip" data-neg="${negative ? 1 : 0}" data-key="${key ? 1 : 0}"
    title="${escapeHtml(rule.replace(/_/g, ' '))}">${escapeHtml(label)}</span>`;
}

function verdict(llm) {
  if (!llm) return '';
  const type = (llm.property_type || 'unclear').replace(/_/g, ' ');
  const sev = llm.severity ? `severity ${llm.severity}/5` : '';
  const elec = llm.electronics_likely ? 'electronics likely' : '';
  const line = [type, sev, elec].filter(Boolean).join(' · ');
  const why = llm.rationale ? ` — ${escapeHtml(llm.rationale)}` : '';
  return `<p class="verdict"><b>${escapeHtml(line)}</b>${why}</p>`;
}

/* ---------- render ---------- */

function card(lead) {
  const { n, unit } = ageParts(lead.published);
  const hours = (Date.now() - new Date(lead.published).getTime()) / 3600000;
  const remaining = Math.max(0, Math.min(100, (1 - hours / FRESH_WINDOW_HOURS) * 100));

  const where = [lead.place, lead.county && `${lead.county} Co.`]
    .filter(Boolean).join(' · ') || 'Location unconfirmed';

  const coverage = lead.cluster_size > 1
    ? `<span>${lead.cluster_size} outlets</span>` : '';

  return `
  <article class="lead" data-tier="${escapeHtml(lead.tier)}">
    <div class="strip" aria-hidden="true"></div>
    <div class="clock">
      <div class="age" data-published="${escapeHtml(lead.published)}">
        ${n}<small>${unit}</small>
      </div>
      <div class="drain" aria-hidden="true"><i style="width:${remaining.toFixed(0)}%"></i></div>
    </div>
    <div class="body">
      <div class="meta">
        <span class="cat" data-c="${escapeHtml(lead.category)}">${escapeHtml(lead.category)}</span>
        <span>${escapeHtml(where)}</span>
        <span>${escapeHtml(lead.source)}</span>
        ${coverage}
        <span class="score">${Math.round(lead.score)}</span>
      </div>
      <h2 class="headline">
        <a href="${escapeHtml(lead.url)}" target="_blank" rel="noopener noreferrer">
          ${escapeHtml(lead.title)}
        </a>
      </h2>
      <div class="chips">${(lead.signals || []).slice(0, 7).map(chip).join('')}</div>
      ${verdict(lead.llm)}
    </div>
  </article>`;
}

function render() {
  const visible = state.leads.filter(l => state.show[l.tier]);

  if (!visible.length) {
    board.innerHTML = `
      <div class="empty">
        <h2>Nothing on the board</h2>
        <p>No leads match the selected tiers. Turn on Logged to see everything
        the collector found.</p>
      </div>`;
    return;
  }

  board.innerHTML = visible.map(card).join('');
}

function updateCounts() {
  for (const tier of ['priority', 'watch', 'logged']) {
    const el = document.getElementById(`n-${tier}`);
    if (el) el.textContent = state.leads.filter(l => l.tier === tier).length;
  }
}

/* Tick the clocks so a tab left open doesn't quietly lie about freshness. */
function tick() {
  document.querySelectorAll('.age[data-published]').forEach(el => {
    const { n, unit } = ageParts(el.dataset.published);
    el.innerHTML = `${n}<small>${unit}</small>`;
  });
  if (state.generatedAt) {
    stamp.innerHTML =
      `last run <b>${ago(state.generatedAt)}</b><br>${state.leads.length} events tracked`;
  }
}

/* ---------- boot ---------- */

document.getElementById('filters').addEventListener('click', e => {
  const btn = e.target.closest('button[data-tier]');
  if (!btn) return;
  const tier = btn.dataset.tier;
  state.show[tier] = !state.show[tier];
  btn.setAttribute('aria-pressed', String(state.show[tier]));
  render();
});

fetch(`data/leads.json?t=${Date.now()}`)
  .then(r => {
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  })
  .then(data => {
    state.leads = data.leads || [];
    state.generatedAt = data.generated_at;
    updateCounts();
    render();
    tick();
    setInterval(tick, 30000);
  })
  .catch(err => {
    stamp.textContent = 'no data';
    board.innerHTML = `
      <div class="error">
        <h2>Can't load leads.json</h2>
        <p>${escapeHtml(err.message)}</p>
        <p>If the collector hasn't run yet, trigger it from the Actions tab —
        the workflow is "Collect leads".</p>
      </div>`;
  });
