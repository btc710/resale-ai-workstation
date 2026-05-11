# Jarvis Workstation

A voice-driven, self-improving desktop assistant in the spirit of Iron Man's J.A.R.V.I.S. Built on Electron + Next.js, powered by Claude Opus 4.7, with browser-native speech recognition.

## What it does

- **Voice-in, voice-out** — Web Speech API for STT, SpeechSynthesis for TTS. No API costs for voice.
- **Claude brain** — Adaptive thinking, prompt caching, tool use. Conversation memory persisted across sessions.
- **Self-improvement**
  - Learns user preferences (frequently-used commands, vocabulary, style)
  - Command alias learning — if a command fails, learns the mapping for next time
  - Self-editing code — Jarvis can propose and apply diffs to its own source (guarded; off by default)
  - Usage analytics dashboard — surfaces which commands you use, response times, failure rates
- **Built-in commands**
  - General Q&A and chat with Claude
  - System control (open apps, run shell commands, web search)
  - Workflow: HubSpot → Outreach with BlueSend / thanks.io (stub — wire your API keys)

## Setup

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
npm install
npm run dev
```

Then say "Jarvis" (or click the orb) to start listening.

## Architecture

```
electron/             Main process — IPC, file system, Claude SDK, OS integration
  main.js             Window + global hotkeys + IPC routing
  preload.js          Safe IPC bridge exposed to renderer as window.jarvis
  handlers/           One module per capability
renderer/             Next.js renderer (the HUD)
  app/                Routes
  components/         Voice orb, transcript, analytics, command log
  lib/                Voice loop hook, command router (client-side)
data/                 Persisted state (gitignored): memory, aliases, analytics
```

## Self-editing safety

`JARVIS_SELF_EDIT_ENABLED=false` by default. When enabled, every self-edit:

1. Generates a diff via Claude
2. Shows it in the HUD for approval
3. Writes only after explicit user confirmation
4. Logs to `data/self-edit-history.json` for rollback

## Status

v0 scaffold. Voice loop, Claude chat, memory, analytics, alias learning, and self-edit pipeline are wired. System control and the HubSpot→Outreach workflow are stubs with the contract defined — wire your specific APIs in `electron/handlers/system.js` and `electron/handlers/workflow.js`.
