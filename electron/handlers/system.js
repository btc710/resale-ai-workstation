const { exec } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);

const ALLOWLIST = [
  /^echo /,
  /^ls\b/,
  /^pwd$/,
  /^date$/,
  /^whoami$/,
  /^uname/,
  /^df\b/,
  /^free\b/,
  /^uptime$/,
  /^open https?:\/\//,
  /^xdg-open https?:\/\//,
  /^start https?:\/\//,
];

function isAllowed(command) {
  return ALLOWLIST.some((re) => re.test(command.trim()));
}

async function run(command) {
  if (!isAllowed(command)) {
    return {
      ok: false,
      error: `Command not in allowlist. Add it to electron/handlers/system.js if intentional.`,
      command,
    };
  }
  try {
    const { stdout, stderr } = await execAsync(command, { timeout: 10_000 });
    return { ok: true, stdout: stdout.trim(), stderr: stderr.trim(), command };
  } catch (err) {
    return { ok: false, error: err.message, command };
  }
}

module.exports = { run };
