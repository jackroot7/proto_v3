/* Proto v3 — Global JavaScript
   POS-specific logic lives in templates/pos/index.html
   This file handles: modals, sync status, alerts, shared utils */

// ── Day open/close modals ──────────────────────────────────────
function showOpenDayModal() {
  document.getElementById('openDayModal').style.display = 'flex';
}

function showCloseDayModal() {
  document.getElementById('closeDayModal').style.display = 'flex';

  const el = document.getElementById('day-summary-data');
  el.innerHTML = '<p style="color:#6b6b80;font-size:13px">Loading summary...</p>';

  fetch('/day/summary/')
    .then(r => r.json())
    .then(d => {
      const fmt = n => Math.round(parseFloat(n)).toLocaleString();
      const profit = parseFloat(d.profit);
      el.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px">
          <div style="background:#f0edfb;border-radius:8px;padding:12px">
            <div style="font-size:10px;color:#7060a8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Total Revenue</div>
            <div style="font-size:18px;font-weight:700;color:#3d2a8f">TSh ${fmt(d.total)}</div>
            <div style="font-size:11px;color:#7060a8;margin-top:2px">${d.txns} transaction${d.txns !== 1 ? 's' : ''}</div>
          </div>
          <div style="background:${profit >= 0 ? '#e8f5ee' : '#fdeaea'};border-radius:8px;padding:12px">
            <div style="font-size:10px;color:${profit >= 0 ? '#0a3d1f' : '#7a1f1f'};text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Gross Profit</div>
            <div style="font-size:18px;font-weight:700;color:${profit >= 0 ? '#0D512B' : '#9b2626'}">TSh ${fmt(d.profit)}</div>
            <div style="font-size:11px;color:${profit >= 0 ? '#1a6b3a' : '#a03030'};margin-top:2px">After cost of goods</div>
          </div>
        </div>
        <table style="width:100%;font-size:12px;border-collapse:collapse;margin-bottom:10px">
          <tr style="border-bottom:1px solid #f0f0f2">
            <td style="padding:6px 0;color:#6b6b80">Cash sales</td>
            <td style="padding:6px 0;text-align:right;font-weight:500">TSh ${fmt(d.cash)}</td>
          </tr>
          <tr style="border-bottom:1px solid #f0f0f2">
            <td style="padding:6px 0;color:#6b6b80">M-Pesa sales</td>
            <td style="padding:6px 0;text-align:right;font-weight:500">TSh ${fmt(d.mpesa)}</td>
          </tr>
          <tr style="border-bottom:1px solid #f0f0f2">
            <td style="padding:6px 0;color:#6b6b80">Credit sales</td>
            <td style="padding:6px 0;text-align:right;font-weight:500">TSh ${fmt(d.credit)}</td>
          </tr>
          <tr style="border-bottom:1px solid #f0f0f2">
            <td style="padding:6px 0;color:#6b6b80">Tax collected</td>
            <td style="padding:6px 0;text-align:right;font-weight:500">TSh ${fmt(d.tax)}</td>
          </tr>
          <tr style="border-bottom:1px solid #f0f0f2">
            <td style="padding:6px 0;color:#6b6b80">Expenses today</td>
            <td style="padding:6px 0;text-align:right;font-weight:500;color:#9b2626">TSh ${fmt(d.expenses)}</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:#6b6b80">Opening cash</td>
            <td style="padding:6px 0;text-align:right;font-weight:500">TSh ${fmt(d.opening_cash)}</td>
          </tr>
        </table>`;
    })
    .catch(() => {
      document.getElementById('day-summary-data').innerHTML =
        '<p style="color:#9b2626;font-size:13px">Could not load summary. You can still close the day.</p>';
    });
}

function hideModal(id) {
  document.getElementById(id).style.display = 'none';
}

document.addEventListener('click', function(e) {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.style.display = 'none';
  }
});

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay').forEach(m => m.style.display = 'none');
  }
});

// ── Sync status ────────────────────────────────────────────────
function checkSync() {
  fetch('/sync/status/')
    .then(r => r.json())
    .then(data => {
      const badge = document.getElementById('sync-indicator');
      if (!badge) return;
      if (data.online) {
        badge.textContent = data.pending > 0 ? '\u29F3 Syncing (' + data.pending + ')' : '\u25CF Online';
        badge.style.background = data.pending > 0 ? '#fef3dc' : '#e8f5ee';
        badge.style.color = data.pending > 0 ? '#7a5010' : '#0a3d1f';
      } else {
        badge.textContent = '\u25CC Offline';
        badge.style.background = '#f0edfb';
        badge.style.color = '#3d2a8f';
      }
    }).catch(() => {
      const badge = document.getElementById('sync-indicator');
      if (badge) {
        badge.textContent = '\u25CC Offline';
        badge.style.background = '#fdeaea';
        badge.style.color = '#7a1f1f';
      }
    });
}

const syncBadge = document.getElementById('sync-indicator');
if (syncBadge) {
  syncBadge.addEventListener('click', function() {
    doSync();
  });
}

function doSync() {
  fetch('/sync/trigger/', {
    method: 'POST',
    headers: { 'X-CSRFToken': getCookie('csrftoken') },
  }).then(r => r.json()).then(d => {
    checkSync();
    if (d.synced > 0) showToast('Synced ' + d.synced + ' record(s).', 'success');
    if (d.failed > 0) showToast(d.failed + ' record(s) failed to sync.', 'warning');
    if (d.error) showToast(d.error, 'warning');
  }).catch(() => {});
}

// Auto-sync every 30s if there are pending items
function autoSync() {
  fetch('/sync/status/')
    .then(r => r.json())
    .then(d => {
      checkSync();
      if (d.configured && d.pending > 0 && d.online) {
        doSync();
      }
    }).catch(() => {});
}

if (document.getElementById('sync-indicator')) {
  setInterval(autoSync, 30000);
  checkSync();
}

// ── Shared utilities ───────────────────────────────────────────
function getCookie(name) {
  let value = null;
  document.cookie.split(';').forEach(c => {
    const [k, v] = c.trim().split('=');
    if (k === name) value = decodeURIComponent(v);
  });
  return value;
}

function showToast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = 'alert alert-' + type;
  t.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:2000;min-width:220px;font-size:13px;';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// Auto-dismiss alerts after 5s
document.querySelectorAll('.alert').forEach(a => {
  setTimeout(() => { a.style.opacity = '0'; a.style.transition = 'opacity .5s'; }, 4500);
  setTimeout(() => a.remove(), 5000);
});