import { useLocation } from "react-router-dom";
import { authClient } from "../lib/auth-client";
import { ParticleField } from "./ParticleField";
import { StructureFlow } from "./StructureFlow";

// The Three.js dome belongs to the public landing page only; signed-in users
// who load "/" see the workspace instead, so they keep the streaks too.
export const PageBackground = () => {
	const { pathname } = useLocation();
	const { data: session, isPending } = authClient.useSession();
	if (!isPending && (pathname !== "/" || session?.user)) {
		return <ParticleField />;
	}
	return <StructureFlow />;
};
