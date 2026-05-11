const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvis', {
  window: {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    close: () => ipcRenderer.invoke('window:close'),
    togglePin: () => ipcRenderer.invoke('window:toggle-pin'),
  },
  claude: {
    chat: (payload) => ipcRenderer.invoke('claude:chat', payload),
  },
  memory: {
    get: (key) => ipcRenderer.invoke('memory:get', key),
    set: (key, value) => ipcRenderer.invoke('memory:set', key, value),
    learnPreference: (pref) => ipcRenderer.invoke('memory:learn-preference', pref),
    learnAlias: (mapping) => ipcRenderer.invoke('memory:learn-alias', mapping),
    resolveAlias: (spoken) => ipcRenderer.invoke('memory:resolve-alias', spoken),
    exportAll: () => ipcRenderer.invoke('memory:export'),
  },
  analytics: {
    summary: () => ipcRenderer.invoke('analytics:summary'),
    record: (event) => ipcRenderer.invoke('analytics:record', event),
  },
  system: {
    run: (command) => ipcRenderer.invoke('system:run', command),
    openUrl: (url) => ipcRenderer.invoke('system:open-url', url),
  },
  selfEdit: {
    propose: (request) => ipcRenderer.invoke('self-edit:propose', { request }),
    apply: (proposal) => ipcRenderer.invoke('self-edit:apply', proposal),
    history: () => ipcRenderer.invoke('self-edit:history'),
  },
  workflow: {
    hubspotToOutreach: (params) => ipcRenderer.invoke('workflow:hubspot-to-outreach', params),
  },
  onSummon: (callback) => {
    ipcRenderer.on('jarvis:summon', callback);
    return () => ipcRenderer.removeListener('jarvis:summon', callback);
  },
});
