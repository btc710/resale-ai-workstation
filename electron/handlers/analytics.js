const fs = require('fs').promises;
const path = require('path');
const { app } = require('electron');

function dataPath() {
  const dir = app ? app.getPath('userData') : path.join(process.cwd(), 'data');
  return path.join(dir, 'jarvis-analytics.json');
}

async function readEvents() {
  try {
    const raw = await fs.readFile(dataPath(), 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }
}

async function writeEvents(events) {
  const file = dataPath();
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, JSON.stringify(events, null, 2), 'utf8');
}

async function record(event) {
  const events = await readEvents();
  events.push({ ...event, ts: Date.now() });
  // Cap at 10k events
  if (events.length > 10000) events.splice(0, events.length - 10000);
  await writeEvents(events);
  return { ok: true };
}

async function summary() {
  const events = await readEvents();
  const last24h = events.filter((e) => Date.now() - e.ts < 24 * 3600 * 1000);

  const byKind = {};
  for (const e of events) {
    if (!byKind[e.kind]) byKind[e.kind] = { total: 0, ok: 0, failed: 0, totalMs: 0 };
    byKind[e.kind].total++;
    if (e.ok) byKind[e.kind].ok++;
    else byKind[e.kind].failed++;
    if (e.durationMs) byKind[e.kind].totalMs += e.durationMs;
  }

  for (const k of Object.keys(byKind)) {
    byKind[k].avgMs = byKind[k].total ? Math.round(byKind[k].totalMs / byKind[k].total) : 0;
    byKind[k].successRate = byKind[k].total ? byKind[k].ok / byKind[k].total : 1;
  }

  const recentCommands = events
    .filter((e) => e.kind === 'command' || e.kind === 'chat')
    .slice(-20)
    .reverse();

  return {
    totalEvents: events.length,
    last24h: last24h.length,
    byKind,
    recentCommands,
  };
}

module.exports = { record, summary };
