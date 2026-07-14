import Keycloak from "keycloak-js";
import React from "react";
import ReactDOM from "react-dom/client";

import { setTokenHolen } from "./api";
import App from "./App";
import "./styles.css";

interface FrontendConfig {
  keycloak_url: string | null;
  keycloak_realm: string;
  keycloak_client: string;
}

async function start() {
  // Laufzeit-Config vom Backend. Ohne keycloak_url läuft alles ohne Login (Dev-Modus).
  const config: Partial<FrontendConfig> = await fetch("/api/config")
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({}));

  if (config.keycloak_url) {
    const keycloak = new Keycloak({
      url: config.keycloak_url,
      realm: config.keycloak_realm ?? "smierx",
      clientId: config.keycloak_client ?? "smierx-queue",
    });
    await keycloak.init({ onLoad: "login-required", pkceMethod: "S256" });
    setTokenHolen(async () => {
      try {
        await keycloak.updateToken(30);
      } catch {
        await keycloak.login();
      }
      return keycloak.token ?? null;
    });
  }

  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

start();
