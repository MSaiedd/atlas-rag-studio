const $ = (id) => document.getElementById(id);
async function request(path, method = 'GET', body) {
  const response = await fetch(path, {method, headers: {'Authorization': `Bearer ${$('token').value}`, 'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
  const data = await response.json(); if (!response.ok) throw new Error(JSON.stringify(data.detail)); return data;
}
$('ticket').addEventListener('submit', async (event) => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  $('ticket-result').textContent = 'Processing…';
  try {
    const result = await request('/tickets', 'POST', {message: $('message').value, order_id: $('order').value || null});
    $('ticket-result').replaceChildren();
    const answer = document.createElement('p'); answer.textContent = result.response;
    const status = document.createElement('p'); status.className = 'muted'; status.textContent = `Ticket ${result.status} · ${result.refunds.length} refund request(s)`;
    const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Inspect tool trace';
    const trace = document.createElement('pre'); trace.textContent = JSON.stringify(result.trace, null, 2); details.append(summary, trace);
    $('ticket-result').append(answer, status, details);
  }
  catch (error) { $('ticket-result').textContent = error.message; } finally { button.disabled = false; }
});
async function refresh() {
  try {
    const items = await request('/refunds'); $('pending').replaceChildren();
    if (!items.length) $('pending').textContent = 'No pending requests.';
    for (const item of items) {
      const row = document.createElement('section'); const text = document.createElement('p');
      text.textContent = `${item.order_id} · ${(item.amount_cents / 100).toFixed(2)} USD · ${item.user}`; row.append(text);
      for (const [label, approve] of [['Approve sandbox refund', true], ['Reject', false]]) {
        const button = document.createElement('button'); button.textContent = label;
        button.addEventListener('click', async () => { button.disabled = true; try { await request(`/refunds/${item.id}/decision`, 'POST', {approve}); await refresh(); } catch (error) { text.textContent = error.message; button.disabled = false; } }); row.append(button);
      }
      $('pending').append(row);
    }
  } catch (error) { $('pending').textContent = error.message; }
}
$('refresh').addEventListener('click', refresh);
$('audit-button').addEventListener('click', async () => { try { $('audit').textContent = (await request('/audit')).map(event => `${event.timestamp} · ${event.actor}\n${event.kind}`).join('\n\n'); } catch (error) { $('audit').textContent = error.message; } });
