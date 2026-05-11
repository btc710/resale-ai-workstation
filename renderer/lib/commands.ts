'use client';

export type CommandResult = {
  handled: boolean;
  reply: string;
  intent?: string;
  ok?: boolean;
};

type Matcher = {
  intent: string;
  patterns: RegExp[];
  handle: (match: RegExpMatchArray, raw: string) => Promise<CommandResult>;
};

const matchers: Matcher[] = [
  {
    intent: 'open-url',
    patterns: [
      /\bopen\s+(?:the\s+)?(?:website\s+|site\s+|url\s+)?(https?:\/\/\S+)/i,
      /\bgo\s+to\s+(https?:\/\/\S+)/i,
    ],
    async handle(match) {
      await window.jarvis.system.openUrl(match[1]);
      return { handled: true, reply: `Opening ${match[1]}, sir.`, ok: true };
    },
  },
  {
    intent: 'search-web',
    patterns: [/^(?:search|google|look\s+up)\s+(?:for\s+)?(.+)/i],
    async handle(match) {
      const query = encodeURIComponent(match[1]);
      await window.jarvis.system.openUrl(`https://www.google.com/search?q=${query}`);
      return { handled: true, reply: `Searching for ${match[1]}.`, ok: true };
    },
  },
  {
    intent: 'system-status',
    patterns: [/\b(?:system\s+status|how\s+are\s+you|status\s+report)\b/i],
    async handle() {
      const summary = await window.jarvis.analytics.summary();
      const lines = [
        `${summary.totalEvents} events tracked total, ${summary.last24h} in the last twenty-four hours.`,
      ];
      const chat = summary.byKind.chat;
      if (chat) {
        lines.push(
          `Chat: ${chat.total} interactions, ${Math.round(chat.successRate * 100)} percent success, ${chat.avgMs} milliseconds average response.`,
        );
      }
      return { handled: true, reply: lines.join(' '), intent: 'system-status', ok: true };
    },
  },
  {
    intent: 'remember-preference',
    patterns: [/^(?:remember|note)\s+that\s+(.+)/i, /^my\s+(.+?)\s+is\s+(.+)/i],
    async handle(match, raw) {
      const key = match[1] ? match[1].split(/\s+/).slice(0, 3).join('-').toLowerCase() : 'note';
      await window.jarvis.memory.learnPreference({ [key]: match[2] || match[1] });
      return { handled: true, reply: `Noted. I'll remember that.`, ok: true };
    },
  },
  {
    intent: 'workflow-hubspot-outreach',
    patterns: [
      /\b(?:run|trigger|kick\s+off|start)\s+(?:the\s+)?(?:hubspot.{0,20}outreach|outreach\s+workflow)/i,
      /\bpush\s+(?:hubspot\s+)?contacts?\s+(?:to\s+)?outreach/i,
    ],
    async handle() {
      const result = await window.jarvis.workflow.hubspotToOutreach({
        limit: 25,
        withCall: true,
        withPostcard: true,
      });
      if (!result.ok) {
        return {
          handled: true,
          reply: `The workflow stalled — ${result.error}`,
          intent: 'workflow-hubspot-outreach',
          ok: false,
        };
      }
      return {
        handled: true,
        reply: `Workflow run complete. Processed ${result.processed} contacts, ${result.succeeded} succeeded.`,
        intent: 'workflow-hubspot-outreach',
        ok: true,
      };
    },
  },
  {
    intent: 'self-edit',
    patterns: [/^(?:edit\s+yourself|modify\s+your\s+code|self.?edit)[:\s]+(.+)/i],
    async handle(match) {
      const result = await window.jarvis.selfEdit.propose(match[1]);
      if (!result.ok) {
        return { handled: true, reply: result.error, intent: 'self-edit', ok: false };
      }
      return {
        handled: true,
        reply: `Proposal drafted: ${result.proposal.summary}. Review and approve in the panel before I apply it.`,
        intent: 'self-edit',
        ok: true,
      };
    },
  },
];

export async function routeCommand(text: string): Promise<CommandResult> {
  // Check learned aliases first
  if (window.jarvis) {
    const alias = await window.jarvis.memory.resolveAlias(text);
    if (alias) {
      return routeCommand(alias);
    }
  }

  for (const matcher of matchers) {
    for (const pattern of matcher.patterns) {
      const m = text.match(pattern);
      if (m) {
        try {
          const result = await matcher.handle(m, text);
          return { ...result, intent: result.intent || matcher.intent };
        } catch (err) {
          return {
            handled: true,
            reply: `Something went wrong handling that command: ${(err as Error).message}`,
            intent: matcher.intent,
            ok: false,
          };
        }
      }
    }
  }

  return { handled: false, reply: '' };
}
