// Footer year
document.getElementById('year').textContent = new Date().getFullYear();

// ---------------------------------------------------------------
// Live deals, pulled from coupons.json (generated daily by
// .github/workflows/update-coupons.yml via the Involve Asia API).
// No hardcoded links here anymore — everything comes from the data.
// ---------------------------------------------------------------

function cleanOfferName(name) {
  if (!name) return 'Deal';
  return name
    .replace(/\s*-\s*(CPS|CPA|CPA_BOTH|CPC|CPM)\s*$/i, '')
    .replace(/\s*\((Deeplinkable|Non-deeplinkable|ClickID)\)\s*/gi, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function formatUpdatedAt(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('en-MY', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

function dealCardHTML(deal) {
  const name = cleanOfferName(deal.name);
  // Show a voucher code if one exists (future-proofed for when campaigns
  // start carrying real codes); otherwise show the cashback rate.
  const headline = deal.voucher_code
    ? `Code: ${deal.voucher_code}`
    : (deal.commission ? `${deal.commission} cashback` : 'Official partner link');
  const meta = [deal.country, deal.category].filter(Boolean).join(' · ');
  const ctaText = deal.voucher_code ? 'Get this deal →' : 'Shop via official link →';

  return `
    <article class="deal-card">
      <p class="deal-platform">${name}</p>
      <p class="deal-title">${headline}</p>
      <p class="deal-code">${meta}</p>
      <a href="${deal.url}" class="deal-link" target="_blank" rel="noopener sponsored">${ctaText}</a>
    </article>
  `;
}

function renderTicker(deals) {
  const track = document.querySelector('.ticker-track');
  if (!track || deals.length === 0) return;
  const items = deals.slice(0, 8).map(d => {
    const name = cleanOfferName(d.name);
    const label = d.voucher_code ? `Code ${d.voucher_code}` : (d.commission ? `${d.commission} cashback` : 'Live offer');
    return `<span>${name} — ${label}</span>`;
  });
  // duplicate the list so the existing CSS scroll loop (translateX -50%) stays seamless
  track.innerHTML = items.concat(items).join('');
}

function renderDeals(deals) {
  const grid = document.getElementById('deal-grid');
  if (!grid) return;
  if (!deals || deals.length === 0) {
    grid.innerHTML = `<p class="deal-empty">No live deals right now — check back soon or join the Telegram channel for alerts.</p>`;
    return;
  }
  grid.innerHTML = deals.map(dealCardHTML).join('');
}

fetch('./coupons.json')
  .then(res => {
    if (!res.ok) throw new Error(`coupons.json ${res.status}`);
    return res.json();
  })
  .then(data => {
    const deals = data.deals || [];
    renderDeals(deals);
    renderTicker(deals);
    const updatedEl = document.getElementById('deals-updated');
    if (updatedEl) {
      updatedEl.textContent = `Updated ${formatUpdatedAt(data.updated_at)} · ${deals.length} live offers`;
    }
  })
  .catch(err => {
    console.error('Failed to load deals:', err);
    const grid = document.getElementById('deal-grid');
    if (grid) {
      grid.innerHTML = `<p class="deal-empty">Couldn't load today's deals. Please refresh, or check back shortly.</p>`;
    }
  });
