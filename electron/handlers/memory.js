const fs = require('fs').promises;
const path = require('path');
const { app } = require('electron');

function dataPath() {
  const dir = app ? app.getPath('userData') : path.join(process.cwd(), 'data');
  return path.join(dir, 'jarvis-memory.json');
}

async function readAll() {
  try {
    const raw = await fs.readFile(dataPath(), 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    if (err.code === 'ENOENT') return {};
    throw err;
  }
}

async function writeAll(state) {
  const file = dataPath();
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, JSON.stringify(state, null, 2), 'utf8');
}

async function get(key) {
  const state = await readAll();
  return state[key];
}

async function set(key, value) {
  const state = await readAll();
  state[key] = value;
  await writeAll(state);
  return { ok: true };
}

async function learnPreference(pref) {
  const state = await readAll();
  state.preferences = { ...(state.preferences || {}), ...pref };
  await writeAll(state);
  return state.preferences;
}

async function learnAlias(spoken, intent) {
  const state = await readAll();
  state.aliases = state.aliases || {};
  state.aliases[spoken.toLowerCase().trim()] = intent;
  await writeAll(state);
  return { ok: true, count: Object.keys(state.aliases).length };
}

async function resolveAlias(spoken) {
  const state = await readAll();
  const aliases = state.aliases || {};
  return aliases[spoken.toLowerCase().trim()] || null;
}

async function exportAll() {
  return readAll();
}

module.exports = { get, set, learnPreference, learnAlias, resolveAlias, exportAll };
