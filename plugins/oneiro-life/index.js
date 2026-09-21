/**
 * oneiro-life: the Oneiro organization as a guest of the OpenClaw gateway.
 *
 * The gateway is the long-life host: it stays up, so this plugin gives it two
 * narrow jobs, both about the graph and nothing else:
 *   - a service that records its own start and stop;
 *   - two gateway lifecycle hooks (gateway_start, gateway_stop).
 *
 * Records go over loopback HTTP to the project's dashboard, which owns the
 * bridge; the graph itself is only ever written by Python. The plugin spawns
 * no processes on purpose: OpenClaw's install scan blocks that pattern, and
 * the life process belongs to the host's scheduler, not to a plugin.
 */
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const RECORD_TIMEOUT_MS = 15_000;

const DEFAULTS = {
  dashboardUrl: "http://127.0.0.1:8130",
  sessionId: "oneiro-gateway",
};

function settings(api) {
  return { ...DEFAULTS, ...(api.pluginConfig ?? {}) };
}

/** One record into OSTIS through the dashboard seam; never throws. */
async function recordIntoOstis(cfg, api, kind, payload, role = "gateway") {
  const url = `${cfg.dashboardUrl.replace(/\/$/, "")}/api/gateway-record`;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kind, role, session: cfg.sessionId, payload: payload ?? {} }),
      signal: AbortSignal.timeout(RECORD_TIMEOUT_MS),
    });
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 200);
      api.logger.warn(`oneiro-life: record ${kind} refused (${response.status}): ${detail}`);
      return false;
    }
    return true;
  } catch (error) {
    api.logger.warn(`oneiro-life: record ${kind} failed: ${error.message}`);
    return false;
  }
}

export default definePluginEntry({
  id: "oneiro-life",
  name: "Oneiro Life",
  description: "Records the gateway's own lifecycle into the Oneiro OSTIS graph.",
  register(api) {
    const cfg = settings(api);

    api.registerService({
      id: "oneiro-life",
      async start(ctx) {
        await recordIntoOstis(cfg, api, "gateway_service_start", {
          state_dir: ctx.stateDir,
          project_dir: ctx.workspaceDir ?? null,
        });
        api.logger.info(`oneiro-life ready; records go to ${cfg.dashboardUrl}`);
      },
      async stop(ctx) {
        await recordIntoOstis(cfg, api, "gateway_service_stop", { state_dir: ctx.stateDir });
        api.logger.info("oneiro-life stopped");
      },
    });

    api.on("gateway_start", async (event) => {
      await recordIntoOstis(cfg, api, "gateway_start", { port: event.port });
    });
    api.on("gateway_stop", async (event) => {
      await recordIntoOstis(cfg, api, "gateway_stop", { reason: event.reason ?? null });
    });

    api.logger.info(`oneiro-life registered: dashboard=${cfg.dashboardUrl}`);
  },
});
