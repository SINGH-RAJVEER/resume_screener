import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "./App";
import { StructureFlow } from "./components/StructureFlow";
import { InvitationUpload } from "./pages/InvitationUpload";
import { SignIn } from "./pages/SignIn";
import { SignUp } from "./pages/SignUp";
import "@resume-screener/ui/globals.css";
import "./styles.css";

const root = document.getElementById("root");

if (!root) throw new Error("Root element not found");

createRoot(root).render(
	<StrictMode>
		<StructureFlow />
		<BrowserRouter>
			<Routes>
				<Route path="/" element={<App />} />
				<Route path="/sign-in" element={<SignIn />} />
				<Route path="/sign-up" element={<SignUp />} />
				<Route path="/apply/:token" element={<InvitationUpload />} />
			</Routes>
		</BrowserRouter>
	</StrictMode>,
);
