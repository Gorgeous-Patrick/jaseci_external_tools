import React from "react";
import { createRoot } from "react-dom/client";
import { app as App } from "./main.js";
import { JacClientErrorBoundary, ErrorFallback, __jacInstallErrorHandlers, __jacReactErrorHandler } from "@jac/runtime";

__jacInstallErrorHandlers();
const root = createRoot(document.getElementById("root"));
root.render(
	React.createElement(
		JacClientErrorBoundary,
		{ FallbackComponent: ErrorFallback, onError: __jacReactErrorHandler },
		React.createElement(App, null)
	)
);
