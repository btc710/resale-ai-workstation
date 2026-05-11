const fs = require('fs').promises;
const path = require('path');
const { app } = require('electron');

const REPO_ROOT = path.join(__dirname, '..', '..');
const EDITABLE_ROOTS = ['electron', 'renderer'];

function isInsideEditableRoot(filePath) {
  const abs = path.resolve(REPO_ROOT, filePath);
  return EDITABLE_ROOTS.some((root) => abs.startsWith(path.resolve(REPO_ROOT, root)));
}

function historyPath() {
  const dir = app ? app.getPath('userData') : path.join(process.cwd(), 'data');
  return path.join(dir, 'jarvis-self-edit-history.json');
}

async function readHistory() {
  try {
    const raw = await fs.readFile(historyPath(), 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }
}

async function writeHistory(entries) {
  const file = historyPath();
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, JSON.stringify(entries, null, 2), 'utf8');
}

// Load a curated set of source files Claude can consider editing.
async function gatherEditableSnapshot() {
  const files = [
    'electron/handlers/claude.js',
    'electron/handlers/memory.js',
    'electron/handlers/analytics.js',
    'electron/handlers/system.js',
    'electron/handlers/workflow.js',
    'renderer/lib/commands.ts',
    'renderer/lib/jarvis.ts',
  ];
  const snapshot = {};
  for (const rel of files) {
    try {
      snapshot[rel] = await fs.readFile(path.join(REPO_ROOT, rel), 'utf8');
    } catch {
      // skip missing files
    }
  }
  return snapshot;
}

async function propose({ request, generate }) {
  const currentFiles = await gatherEditableSnapshot();
  const proposal = await generate({ request, currentFiles });
  return {
    ok: true,
    proposal: {
      ...proposal,
      id: `edit-${Date.now()}`,
      request,
      proposedAt: new Date().toISOString(),
    },
  };
}

async function apply(proposal) {
  if (!proposal || !Array.isArray(proposal.changes)) {
    return { ok: false, error: 'Invalid proposal' };
  }

  const applied = [];
  for (const change of proposal.changes) {
    if (!isInsideEditableRoot(change.path)) {
      return { ok: false, error: `Refusing to write outside editable roots: ${change.path}` };
    }
    const abs = path.join(REPO_ROOT, change.path);
    const previous = await fs.readFile(abs, 'utf8').catch(() => null);
    await fs.mkdir(path.dirname(abs), { recursive: true });
    await fs.writeFile(abs, change.newContent, 'utf8');
    applied.push({ path: change.path, previous });
  }

  const history = await readHistory();
  history.push({
    id: proposal.id,
    request: proposal.request,
    summary: proposal.summary,
    appliedAt: new Date().toISOString(),
    applied,
  });
  await writeHistory(history);

  return { ok: true, count: applied.length };
}

async function history() {
  return readHistory();
}

module.exports = { propose, apply, history };
