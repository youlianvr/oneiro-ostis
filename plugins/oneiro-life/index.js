/**
 * oneiro-life: the Oneiro organization as a guest of the OpenClaw gateway.
 *
 * Two jobs, both narrow on purpose:
 *   - the service supervises the life process (bounded restarts, clean stop);
 *   - two gateway hooks record the gateway's own lifecycle into OSTIS.
 *
 * The graph is Python's job (the project's bridge is the only writer), so the
 * plugin shells out to record.py instead of re-implementing the SC client in
 * Node. Nothing here touches OpenClaw's state, the owner's live profile, or
 * the project's git.
 */
import { spawn } from "node:child_process";
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const HERE = dirname(fileURLToPath(import.meta.url));
const RECORDER = join(HERE, "record.py");
const RESTART_BACKOFF_MS = [5_000, 30_000, 120_000];
const RECORD_TIMEOUT_MS = 30_000;

const DEFAULTS = {
  projectDir: resolve(HERE, "..", ".."),
  pythonPath: "python",
  autostart: false,
  cycles: 2,
  intervalSeconds: 60,
  host: "localhost",
  port: 8090,
  sessionId: "oneiro-gateway",
};

function settings(api) {
  return { ...DEFAULTS, ...(api.pluginConfig ?? {}) };
}

/** One record into OSTIS through the project's bridge; never throws. */
function recordIntoOstis(cfg, api, kind, payload, role = "gateway") {
  return new Promise((done) => {
    const child = spawn(
      cfg.pythonPath,
      [RECORDER, "--kind", kind, "--role", role, "--session", cfg.sessionId,
       "--host", cfg.host, "--port", String(cfg.port),
       "--payload", JSON.stringify(payload ?? {})],
      { cwd: cfg.projectDir },
    );
    let stderr = "";
    const timer = setTimeout(() => child.kill(), RECORD_TIMEOUT_MS);
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => {
      clearTimeout(timer);
      api.logger.warn(`oneiro-life: recorder did not start: ${error.message}`);
      done(false);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const detail = stderr.trim().split("\n").slice(-2).join(" · ");
        api.logger.warn(`oneiro-life: OSTIS record ${kind} failed (${code}): ${detail}`);
      }
      done(code === 0);
    });
  });
}

function createLifeService(api, cfg) {
  let child = null;
  let restarts = 0;
  let stopping = false;

  const startLife = (ctx, runTag) => {
    const logFile = join(ctx.stateDir, "logs", `oneiro-life-${runTag}.log`);
    mkdirSync(dirname(logFile), { recursive: true });
    const args = ["-u", "python/life_loop.py",
                  "--cycles", String(cfg.cycles),
                  "--interval", String(cfg.intervalSeconds),
                  "--run-tag", runTag];
    child = spawn(cfg.pythonPath, args, { cwd: cfg.projectDir });
    api.logger.info(`oneiro-life: life process ${runTag} started → ${logFile}`);
    child.stdout.on("data", (chunk) => appendFileSync(logFile, chunk));
    child.stderr.on("data", (chunk) => appendFileSync(logFile, chunk));
    child.on("exit", (code, signal) => {
      appendFileSync(logFile, `\n[plugin] life process exited code=${code} signal=${signal}\n`);
      child = null;
      const finished = code === 0 && !signal;
      if (finished) {
        void recordIntoOstis(cfg, api, "life_process_finished", { run_tag: runTag });
        return;
      }
      void recordIntoOstis(cfg, api, "life_process_exit",
                           { run_tag: runTag, code, signal });
      if (stopping) return;
      if (restarts >= RESTART_BACKOFF_MS.length) {
        void recordIntoOstis(cfg, api, "life_process_gave_up",
                             { run_tag: runTag, restarts });
        return;
      }
      const wait = RESTART_BACKOFF_MS[restarts];
      restarts += 1;
      void recordIntoOstis(cfg, api, "life_process_restart",
                           { run_tag: runTag, attempt: restarts, wait_ms: wait });
      setTimeout(() => { if (!stopping) startLife(ctx, `${runTag}-r${restarts}`); }, wait);
    });
  };

  const stopLife = async () => {
    const target = child;
    if (!target) return;
    child = null;
    const exited = new Promise((done) => target.once("exit", done));
    if (process.platform === "win32") {
      spawn("taskkill", ["/PID", String(target.pid), "/T", "/F"]);
    } else {
      target.kill("SIGTERM");
    }
    await Promise.race([exited, new Promise((done) => setTimeout(done, 5_000))]);
  };

  return {
    id: "oneiro-life",
    async start(ctx) {
      await recordIntoOstis(cfg, api, "gateway_service_start", {
        state_dir: ctx.stateDir,
        autostart: cfg.autostart,
        project_dir: cfg.projectDir,
      });
      api.logger.info(`oneiro-life ready (autostart=${cfg.autostart})`);
      if (cfg.autostart) {
        const stamp = `plugin-${Date.now().toString(36)}`;
        startLife(ctx, stamp);
      }
    },
    async stop(ctx) {
      stopping = true;
      await stopLife();
      await recordIntoOstis(cfg, api, "gateway_service_stop", { state_dir: ctx.stateDir });
      api.logger.info("oneiro-life stopped");
    },
  };
}

export default definePluginEntry({
  id: "oneiro-life",
  name: "Oneiro Life",
  description: "Supervises the Oneiro life process and records gateway lifecycle into OSTIS.",
  register(api) {
    const cfg = settings(api);
    api.registerService(createLifeService(api, cfg));
    api.on("gateway_start", async (event) => {
      await recordIntoOstis(cfg, api, "gateway_start", { port: event.port });
    });
    api.on("gateway_stop", async (event) => {
      await recordIntoOstis(cfg, api, "gateway_stop", { reason: event.reason ?? null });
    });
    api.logger.info(
      `oneiro-life registered: project=${cfg.projectDir} bridge=${cfg.host}:${cfg.port}`,
    );
  },
});
