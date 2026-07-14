import Keycloak from "keycloak-js";
import React from "react";
import ReactDOM from "react-dom/client";

import { setTokenHolen } from "./api";
import App from "./App";
import "./styles.css";

async function start() {
  const url = import.meta.env.VITE_KEYCLOAK_URL;

  // Ohne VITE_KEYCLOAK_URL läuft das Frontend im Dev-Modus gegen die offene API.
  if (url) {
    const keycloak = new Keycloak({
      url,
      realm: import.meta.env.VITE_KEYCLOAK_REALM ?? "smierx",
      clientId: import.meta.env.VITE_KEYCLOAK_CLIENT ?? "smierx-queue",
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
