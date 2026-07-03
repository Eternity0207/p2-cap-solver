import { WebSocketServer } from "ws";
import { getManager } from "./routes.js";
import { toPublicJob, isTerminal } from "../jobs/models.js";

export function attachWebSockets(server) {
  const wss = new WebSocketServer({ noServer: true });

  server.on("upgrade", (request, socket, head) => {
    const url = new URL(request.url, `http://${request.headers.host}`);
    const jobMatch = url.pathname.match(/^\/api\/v1\/ws\/jobs\/([^/]+)$/);
    const statsMatch = url.pathname === "/api/v1/ws/stats";

    if (jobMatch) {
      wss.handleUpgrade(request, socket, head, (ws) => {
        handleJobWs(ws, jobMatch[1]);
      });
    } else if (statsMatch) {
      wss.handleUpgrade(request, socket, head, (ws) => {
        handleStatsWs(ws);
      });
    } else {
      socket.destroy();
    }
  });
}

async function handleJobWs(ws, jobId) {
  const manager = getManager();
  const job = await manager.getJob(jobId);

  if (!job) {
    ws.send(JSON.stringify({ error: "Job not found" }));
    ws.close();
    return;
  }

  ws.send(JSON.stringify({ type: "snapshot", job: toPublicJob(job) }));

  if (isTerminal(job.status)) {
    ws.close();
    return;
  }

  let latest = job;
  const onUpdate = async (updated) => {
    if (updated.id !== jobId) return;
    latest = updated;
    ws.send(JSON.stringify({ type: "update", job: toPublicJob(updated) }));
    if (isTerminal(updated.status)) ws.close();
  };

  manager.subscribe(jobId, onUpdate);

  const pingInterval = setInterval(() => {
    if (ws.readyState === ws.OPEN) ws.send(JSON.stringify({ type: "ping" }));
  }, 30000);

  ws.on("close", () => {
    clearInterval(pingInterval);
    manager.unsubscribe(jobId, onUpdate);
  });
}

async function handleStatsWs(ws) {
  const manager = getManager();
  const interval = setInterval(async () => {
    if (ws.readyState !== ws.OPEN) return;
    const stats = await manager.getStats();
    ws.send(JSON.stringify({ type: "stats", data: stats }));
  }, 2000);

  ws.on("close", () => clearInterval(interval));
}
