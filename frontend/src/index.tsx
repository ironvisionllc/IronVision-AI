import React from "react";
import ReactDOM from "react-dom/client";
import "@/styles/tokens.css";
import "@/index.css";
import App from "@/App";
import { applyTheme, initialTheme, ThemeProvider } from "@/context/ThemeContext";

applyTheme(initialTheme());

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement);
root.render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
