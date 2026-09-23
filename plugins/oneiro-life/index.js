/**
 * oneiro-life: the Oneiro organization as a guest of the OpenClaw gateway.
 *
 * The gateway is the long-life host: it stays up, so this plugin gives it two
 * narrow jobs, both about the graph and nothing else:
 *   - a service that records its own start and stop;
 *   - two gateway lifecycle hooks (gateway_start, gateway_stop).
 *
 * Records are written by Python, as everywhere else in the project: the plugin
 * runs the recorder sitting next to this file through execFile with an
 * argument array, never a shell string. Installing a plugin that spawns
 * processes needs the host's own acknowledgment flag:
 *
 *   openclaw plugins install --dangerously-force-unsafe-install <path>
 */
import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { buildRecordCommand } from "./command.js";

const RECORD_TIMEOUT_MS = 20_000;
const RECORDER_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), "record.py");

const DEFAULTS = {
  pythonPath: "python",
  sessionId: "oneiro-gateway",
  ostisPort: 8090,
};

function settings(api) {
  return { ...DEFAULTS, ...(api.pluginConfig ?? {}), recorderPath: RECORDER_PATH };
}

/** One record into OSTIS through the recorder; never throws. */
function recordIntoOstis(cfg, api, kind, payload) {
  const { command, args } = buildRecordCommand(cfg, kind, payload ?? {});
  return new Promise((resolve) => {
    execFile(command, args, { timeout: RECORD_TIMEOUT_MS, windowsHide: true },
      (error, stdout, stderr) => {
        if (error) {
          const detail = String(stderr || error.message).trim().slice(0, 200);
          api.logger.warn(`Oneiro: не удалось записать событие ${kind}: ${detail}`);
          resolve(false);
          return;
        }
        resolve(true);
      });
  });
}

export default definePluginEntry({
  id: "oneiro-life",
  name: "Oneiro",
  description: "Записывает в память Oneiro сведения о собственном запуске и остановке помощника.",
  register(api) {
    const cfg = settings(api);

    api.registerService({
      id: "oneiro-life",
      async start(ctx) {
        await recordIntoOstis(cfg, api, "gateway_service_start", {
          state_dir: ctx.stateDir,
          project_dir: ctx.workspaceDir ?? null,
        });
        api.logger.info(`Oneiro: служба готова, запись идёт через ${cfg.pythonPath}`);
      },
      async stop(ctx) {
        await recordIntoOstis(cfg, api, "gateway_service_stop", { state_dir: ctx.stateDir });
        api.logger.info("Oneiro: служба остановлена");
      },
    });

    api.on("gateway_start", async (event) => {
      await recordIntoOstis(cfg, api, "gateway_start", { port: event.port });
    });
    api.on("gateway_stop", async (event) => {
      await recordIntoOstis(cfg, api, "gateway_stop", { reason: event.reason ?? null });
    });

    api.logger.info("Oneiro: служба зарегистрирована, запись в память включена");
  },
});
