import { useEffect, useRef } from "react";
import * as THREE from "three";

// Dome particle field adapted from ThreeUI's StructureFlowBackground:
// points distributed over a hemisphere rising from below the viewport and
// rotated slowly around two axes. Tones follow the app's ink-on-bone palette,
// so the reference's additive white-on-dark blending becomes normal ink dots.
const COUNT_DESKTOP = 15000;
const COUNT_MOBILE = 6000;
const RADIUS = 25;
const DOME_OFFSET = -20;
const CAMERA_DISTANCE = 30;
const CAMERA_HEIGHT = 5;
const POINT_SIZE = 0.08;
const OPACITY = 0.28;
const SPIN_Y = 0.0008;
const SPIN_Z = 0.0002;

export const StructureFlow = () => {
	const canvasRef = useRef<HTMLCanvasElement>(null);

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return undefined;

		const scene = new THREE.Scene();
		const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
		camera.position.z = CAMERA_DISTANCE;
		camera.position.y = CAMERA_HEIGHT;

		const renderer = new THREE.WebGLRenderer({
			canvas,
			alpha: true,
			antialias: true,
		});
		renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

		const count = window.innerWidth < 768 ? COUNT_MOBILE : COUNT_DESKTOP;
		const positions = new Float32Array(count * 3);
		for (let index = 0; index < count; index += 1) {
			const theta = Math.random() * Math.PI * 2;
			// acos over [0.2, 1] concentrates points near the dome's crown so the
			// horizon line reads denser than its edges.
			const phi = Math.acos(Math.random() * 0.8 + 0.2);
			positions[index * 3] = RADIUS * Math.sin(phi) * Math.cos(theta);
			positions[index * 3 + 1] = RADIUS * Math.cos(phi) + DOME_OFFSET;
			positions[index * 3 + 2] = RADIUS * Math.sin(phi) * Math.sin(theta);
		}
		const geometry = new THREE.BufferGeometry();
		geometry.setAttribute(
			"position",
			new THREE.BufferAttribute(positions, 3),
		);

		const material = new THREE.PointsMaterial({
			size: POINT_SIZE,
			color: 0x111111,
			transparent: true,
			opacity: OPACITY,
			depthWrite: false,
		});
		const dome = new THREE.Points(geometry, material);
		scene.add(dome);

		let frame = 0;
		let visible = true;
		const reducedMotion = window.matchMedia(
			"(prefers-reduced-motion: reduce)",
		).matches;

		const render = () => {
			dome.rotation.y += SPIN_Y;
			dome.rotation.z += SPIN_Z;
			renderer.render(scene, camera);
		};
		const tick = () => {
			render();
			frame =
				visible && !document.hidden ? requestAnimationFrame(tick) : 0;
		};

		const resize = () => {
			// Size from the viewport rather than the canvas rect: the renderer
			// updates the buffer without touching CSS, so the element's layout
			// size must never depend on its own buffer dimensions.
			camera.aspect = window.innerWidth / Math.max(1, window.innerHeight);
			camera.updateProjectionMatrix();
			renderer.setSize(window.innerWidth, window.innerHeight, false);
			renderer.render(scene, camera);
		};

		const resizeObserver = new ResizeObserver(resize);
		const intersection = new IntersectionObserver(([entry]) => {
			visible = entry?.isIntersecting ?? true;
			if (visible && !frame)
				frame = reducedMotion ? 0 : requestAnimationFrame(tick);
			if (!visible && frame) {
				cancelAnimationFrame(frame);
				frame = 0;
			}
		});

		resize();
		if (reducedMotion) render();
		else frame = requestAnimationFrame(tick);
		resizeObserver.observe(canvas);
		intersection.observe(canvas);

		return () => {
			if (frame) cancelAnimationFrame(frame);
			resizeObserver.disconnect();
			intersection.disconnect();
			geometry.dispose();
			material.dispose();
			renderer.dispose();
		};
	}, []);

	return <canvas ref={canvasRef} className="structure-flow" />;
};
