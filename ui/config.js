// Where the two services live. The deploy pipeline overwrites this file with the Azure URLs;
// this copy points at the ports docker compose publishes on this machine.
window.PK_CONFIG = {
  ideasUrl: "http://localhost:8001",
  reviewUrl: "http://localhost:8002",
};
