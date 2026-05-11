const { app, BrowserWindow, ipcMain, globalShortcut, shell } = require('electron');
const path = require('path');
require('dotenv').config();

const { chat, generateSelfEdit } = require('./handlers/claude');
const memory = require('./handlers/memory');
const analytics = require('./handlers/analytics');
const system = require('./handlers/system');
const selfEdit = require('./handlers/self-edit');
const workflow = require('./handlers/workflow');

const isDev = process.env.NODE_ENV === 'development';
const DEV_URL = 'http://localhost:3210';

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    title: 'Jarvis',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL(DEV_URL);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'out', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();

  // Global hotkey: Ctrl/Cmd+Shift+J to summon Jarvis
  globalShortcut.register('CommandOrControl+Shift+J', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.isVisible() ? mainWindow.focus() : mainWindow.show();
    mainWindow.webContents.send('jarvis:summon');
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

// IPC: window controls
ipcMain.handle('window:minimize', () => mainWindow?.minimize());
ipcMain.handle('window:close', () => mainWindow?.close());
ipcMain.handle('window:toggle-pin', () => {
  if (!mainWindow) return false;
  const next = !mainWindow.isAlwaysOnTop();
  mainWindow.setAlwaysOnTop(next);
  return next;
});

// IPC: Claude
ipcMain.handle('claude:chat', async (_evt, { messages, context }) => {
  const startedAt = Date.now();
  try {
    const result = await chat({ messages, context });
    await analytics.record({ kind: 'chat', durationMs: Date.now() - startedAt, ok: true });
    return { ok: true, ...result };
  } catch (err) {
    await analytics.record({ kind: 'chat', durationMs: Date.now() - startedAt, ok: false, error: err.message });
    return { ok: false, error: err.message };
  }
});

// IPC: memory (preferences, conversation, aliases)
ipcMain.handle('memory:get', async (_evt, key) => memory.get(key));
ipcMain.handle('memory:set', async (_evt, key, value) => memory.set(key, value));
ipcMain.handle('memory:learn-preference', async (_evt, pref) => memory.learnPreference(pref));
ipcMain.handle('memory:learn-alias', async (_evt, { spoken, intent }) => memory.learnAlias(spoken, intent));
ipcMain.handle('memory:resolve-alias', async (_evt, spoken) => memory.resolveAlias(spoken));
ipcMain.handle('memory:export', async () => memory.exportAll());

// IPC: analytics
ipcMain.handle('analytics:summary', async () => analytics.summary());
ipcMain.handle('analytics:record', async (_evt, event) => analytics.record(event));

// IPC: system control
ipcMain.handle('system:run', async (_evt, command) => system.run(command));
ipcMain.handle('system:open-url', async (_evt, url) => {
  shell.openExternal(url);
  return { ok: true };
});

// IPC: self-edit (generate diff via Claude, write only on approval)
ipcMain.handle('self-edit:propose', async (_evt, { request }) => {
  if (process.env.JARVIS_SELF_EDIT_ENABLED !== 'true') {
    return { ok: false, error: 'Self-edit is disabled. Set JARVIS_SELF_EDIT_ENABLED=true in .env to enable.' };
  }
  return selfEdit.propose({ request, generate: generateSelfEdit });
});
ipcMain.handle('self-edit:apply', async (_evt, proposal) => selfEdit.apply(proposal));
ipcMain.handle('self-edit:history', async () => selfEdit.history());

// IPC: workflow (HubSpot -> Outreach + BlueSend + thanks.io)
ipcMain.handle('workflow:hubspot-to-outreach', async (_evt, params) => workflow.hubspotToOutreach(params));
