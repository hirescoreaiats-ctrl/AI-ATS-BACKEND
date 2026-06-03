import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { App } from "../app/App.jsx";
import "./styles/app.css";

function Root() {
  useEffect(() => {
    document.title = "HireScore AI Enterprise";
  }, []);

  return <App />;
}

createRoot(document.getElementById("root")).render(<Root />);
