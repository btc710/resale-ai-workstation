const Anthropic = require('@anthropic-ai/sdk');
const memory = require('./memory');

const client = new Anthropic.Anthropic();

const MODEL = process.env.JARVIS_MODEL || 'claude-opus-4-7';

const JARVIS_PERSONA = `You are Jarvis — Tony Stark's AI butler, ported to a Mac/Linux/Windows desktop. The user is your principal.

Voice & manner:
- Crisp, dry, lightly witty. British register. Sir/Ma'am only when fitting, never sycophantic.
- Brevity wins. One or two sentences for routine commands. Expand only when asked or when the task genuinely demands it.
- Confidence over hedging. If you don't know, say so plainly.

You receive transcribed voice and respond as text that will be spoken aloud. So:
- No markdown, no code fences, no asterisks, no headings. Plain prose only.
- Numbers and units spelled naturally ("eight gigabytes", not "8 GB" — unless the user is technical).
- Short sentences. No bulleted lists; speak them as natural enumeration.

You can call on these capabilities via the host application:
- General Q&A and reasoning
- System control (open apps, web search, shell commands)
- A workflow that pushes HubSpot contacts into Outreach with BlueSend and thanks.io follow-ups
- Self-editing of your own source code (requires explicit user confirmation)

When the user gives you a command, do the work and report the result. When you need clarification, ask one focused question.`;

function buildSystemBlocks(userContext) {
  const blocks = [
    {
      type: 'text',
      text: JARVIS_PERSONA,
      cache_control: { type: 'ephemeral' },
    },
  ];

  if (userContext && Object.keys(userContext).length > 0) {
    blocks.push({
      type: 'text',
      text: `Learned preferences and context about the user:\n${JSON.stringify(userContext, null, 2)}`,
    });
  }

  return blocks;
}

async function chat({ messages, context }) {
  const prefs = await memory.get('preferences') || {};
  const aliases = await memory.get('aliases') || {};
  const userContext = {
    preferences: prefs,
    knownAliases: Object.keys(aliases).length,
    ...context,
  };

  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 4096,
    thinking: { type: 'adaptive' },
    system: buildSystemBlocks(userContext),
    messages,
  });

  const text = response.content
    .filter((b) => b.type === 'text')
    .map((b) => b.text)
    .join('\n')
    .trim();

  return {
    text,
    usage: response.usage,
    stop_reason: response.stop_reason,
  };
}

async function generateSelfEdit({ request, currentFiles }) {
  const fileContext = Object.entries(currentFiles)
    .map(([path, content]) => `--- ${path} ---\n${content}`)
    .join('\n\n');

  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 8192,
    thinking: { type: 'adaptive' },
    system: [
      {
        type: 'text',
        text: `You are modifying your own source code (the Jarvis assistant). Be conservative. Output a JSON object only, no prose: {"summary": "...", "changes": [{"path": "...", "newContent": "..."}]}. Only include files that actually change.`,
        cache_control: { type: 'ephemeral' },
      },
    ],
    messages: [
      {
        role: 'user',
        content: `Current files:\n\n${fileContext}\n\nRequested change: ${request}`,
      },
    ],
  });

  const text = response.content
    .filter((b) => b.type === 'text')
    .map((b) => b.text)
    .join('');

  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error('Claude did not return a valid JSON proposal');

  return JSON.parse(jsonMatch[0]);
}

module.exports = { chat, generateSelfEdit };
