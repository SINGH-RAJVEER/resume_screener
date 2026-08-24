import { useLocation } from "react-router-dom";
import { ParticleField } from "./ParticleField";
import { StructureFlow } from "./StructureFlow";

// The landing page carries the Three.js dome; every other page keeps the
// original constellation streaks.
export const PageBackground = () => {
	const { pathname } = useLocation();
	return pathname === "/" ? <StructureFlow /> : <ParticleField />;
};
