// HubSpot -> Outreach pipeline with BlueSend (calling) and thanks.io (direct mail).
// This is a stub — wire your real API calls in the marked sections.
//
// Flow:
//   1. Pull contacts from HubSpot (filter: list, segment, recent-update, etc.)
//   2. Push each into Outreach as a prospect (idempotent on email)
//   3. Queue BlueSend call task
//   4. Queue thanks.io postcard

async function fetchHubSpotContacts({ listId, limit = 25 }) {
  const apiKey = process.env.HUBSPOT_API_KEY;
  if (!apiKey) {
    return { ok: false, error: 'HUBSPOT_API_KEY not set in .env' };
  }
  // TODO: Replace with real HubSpot API call:
  //   GET https://api.hubapi.com/crm/v3/lists/{listId}/memberships
  //   GET https://api.hubapi.com/crm/v3/objects/contacts/{id}
  return {
    ok: true,
    contacts: [
      { id: 'demo-1', email: 'demo@example.com', firstName: 'Demo', lastName: 'Contact', listId },
    ].slice(0, limit),
  };
}

async function pushToOutreach(contact) {
  const apiKey = process.env.OUTREACH_API_KEY;
  if (!apiKey) return { ok: false, error: 'OUTREACH_API_KEY not set' };
  // TODO: POST https://api.outreach.io/api/v2/prospects
  return { ok: true, prospectId: `outreach-${contact.id}`, email: contact.email };
}

async function queueBlueSendCall(contact) {
  const apiKey = process.env.BLUESEND_API_KEY;
  if (!apiKey) return { ok: false, error: 'BLUESEND_API_KEY not set' };
  // TODO: POST https://api.bluesend.example/calls
  return { ok: true, taskId: `bluesend-${contact.id}` };
}

async function queueThanksIoPostcard(contact) {
  const apiKey = process.env.THANKS_IO_API_KEY;
  if (!apiKey) return { ok: false, error: 'THANKS_IO_API_KEY not set' };
  // TODO: POST https://api.thanks.io/v2/orders
  return { ok: true, orderId: `thanksio-${contact.id}` };
}

async function hubspotToOutreach({ listId, limit = 25, withCall = true, withPostcard = true } = {}) {
  const contacts = await fetchHubSpotContacts({ listId, limit });
  if (!contacts.ok) return contacts;

  const results = [];
  for (const contact of contacts.contacts) {
    const outreach = await pushToOutreach(contact);
    const call = withCall ? await queueBlueSendCall(contact) : { ok: false, skipped: true };
    const postcard = withPostcard ? await queueThanksIoPostcard(contact) : { ok: false, skipped: true };
    results.push({ contact, outreach, call, postcard });
  }

  const succeeded = results.filter((r) => r.outreach.ok).length;
  return {
    ok: true,
    processed: results.length,
    succeeded,
    failed: results.length - succeeded,
    results,
  };
}

module.exports = { hubspotToOutreach };
