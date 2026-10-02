import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { AuthProvider } from "./auth/AuthContext";
import { applyCachedBranding } from "./branding/applyBranding";
import { BrandingProvider, PRODUCT_NAME } from "./branding/BrandingContext";
import { ThemeProvider } from "./theme/ThemeContext";

// Paint the last known customer branding before React mounts, so a return
// visit never flashes the product's blue on its way to the customer's colour.
// Same shape as ThemeContext's own localStorage read, and for the same reason.
applyCachedBranding(PRODUCT_NAME);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        {/* Inside Theme, outside Auth: the sign-in screen is branded too, and
            there is no user at that point. */}
        <BrandingProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrandingProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
