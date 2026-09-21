/**
 * The one command this plugin runs, built as an argument array.
 *
 * It lives in its own module so a test can assert the exact argv without
 * spawning anything, and so nothing in the plugin ever builds a shell string.
 */
export function buildRecordCommand(config, kind, payload = {}) {
  const recorder = config.recorderPath;
  if (!recorder) throw new Error("recorderPath is required");
  return {
    command: config.pythonPath ?? "python",
    args: [
      recorder,
      "--kind", String(kind),
      "--session", String(config.sessionId ?? "oneiro-gateway"),
      "--port", String(config.ostisPort ?? 8090),
      "--payload", JSON.stringify(payload ?? {}),
    ],
  };
}
