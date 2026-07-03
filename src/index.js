import { loadConfig } from "./config.js";
import { createApp } from "./app.js";
import { log } from "./logger.js";

const args = process.argv.slice(2);

function parseArgs() {
  const opts = { host: null, port: null, config: null };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--host" && args[i + 1]) opts.host = args[++i];
    else if (args[i] === "--port" && args[i + 1]) opts.port = parseInt(args[++i], 10);
    else if (args[i] === "--config" && args[i + 1]) {
      process.env.CAPSOLVER_CONFIG_PATH = args[++i];
    } else if (args[i] === "--install-browsers") {
      opts.installBrowsers = true;
    }
  }
  return opts;
}

async function main() {
  const opts = parseArgs();

  if (opts.installBrowsers) {
    const { execSync } = await import("child_process");
    execSync("npx playwright install chromium", { stdio: "inherit" });
    return;
  }

  if (opts.config) process.env.CAPSOLVER_CONFIG_PATH = opts.config;

  const config = loadConfig();
  const { server, manager } = await createApp();

  const host = opts.host || config.server.host;
  const port = opts.port || config.server.port;

  const shutdown = async () => {
    log("INFO", "cap_solver_stopped");
    await manager.stop();
    server.close();
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  server.listen(port, host, () => {
    log("INFO", "server_listening", "", { host, port });
    console.log(`Cap-Solver listening on http://${host}:${port}`);
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
