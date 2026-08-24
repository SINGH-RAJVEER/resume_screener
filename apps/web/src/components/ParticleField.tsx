import { useEffect, useRef } from "react";

// Perspective particle field adapted from ThreeUI's ConstellationField
// (particle network variant): particles fly out of a vanishing point and are
// drawn as hairline streaks over a fading trail buffer. Tones follow the
// app's ink-on-bone palette instead of the reference's dark blue theme.
const PARTICLE_COUNT_DESKTOP = 140;
const PARTICLE_COUNT_MOBILE = 70;
const DEPTH = 1000;
const FOV = 300;
const SPEED = 1.1;
const TRAIL_FADE = 0.4;
const INK_TONES = ["17, 17, 17", "128, 128, 128"];

class Particle {
	x = 0;
	y = 0;
	z = 0;
	speed = 0;
	tone = "";
	length = 1;

	constructor() {
		this.reset();
		this.z = Math.random() * DEPTH;
	}

	reset() {
		const angle = Math.random() * Math.PI * 2;
		const radius = Math.random() * 600;

		this.x = Math.cos(angle) * radius;
		this.y = Math.sin(angle) * radius - 150;
		this.z = DEPTH;
		this.speed = (Math.random() * 2 + 1) * SPEED;
		this.tone =
			INK_TONES[Math.random() > 0.5 ? 0 : 1] ??
			INK_TONES[0] ??
			"17, 17, 17";
		this.length = Math.random() * 2 + 0.5;
	}

	update() {
		this.z -= this.speed;
		if (this.z <= 0) this.reset();
	}

	draw(ctx: CanvasRenderingContext2D, originX: number, originY: number) {
		const scale = FOV / this.z;
		const px = originX + this.x * scale;
		const py = originY + this.y * scale;

		const prevZ = this.z + this.speed * this.length;
		const prevScale = FOV / prevZ;
		const prevPx = originX + this.x * prevScale;
		const prevPy = originY + this.y * prevScale;

		let opacity = 1 - this.z / DEPTH;
		if (this.z < 100) opacity = this.z / 100;
		if (opacity <= 0) return;

		ctx.beginPath();
		ctx.moveTo(prevPx, prevPy);
		ctx.lineTo(px, py);
		ctx.strokeStyle = `rgba(${this.tone}, ${opacity * 0.65})`;
		ctx.lineWidth = Math.max(0.3, opacity * 0.5);
		ctx.lineCap = "butt";
		ctx.stroke();
	}
}

export const ParticleField = () => {
	const canvasRef = useRef<HTMLCanvasElement>(null);

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		let width = 0;
		let height = 0;
		let originX = 0;
		let originY = 0;
		let frame = 0;
		const particles: Particle[] = [];

		const resize = () => {
			const dpr = Math.min(window.devicePixelRatio || 1, 2);
			width = window.innerWidth;
			height = window.innerHeight;
			canvas.width = Math.max(1, Math.floor(width * dpr));
			canvas.height = Math.max(1, Math.floor(height * dpr));
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			originX = width / 2;
			originY = height * 0.7;
		};

		const animate = () => {
			frame = requestAnimationFrame(animate);
			ctx.fillStyle = `rgba(255, 255, 255, ${TRAIL_FADE})`;
			ctx.fillRect(0, 0, width, height);
			for (const particle of particles) {
				particle.update();
				particle.draw(ctx, originX, originY);
			}
		};

		resize();
		const count =
			width < 768 ? PARTICLE_COUNT_MOBILE : PARTICLE_COUNT_DESKTOP;
		for (let i = 0; i < count; i++) particles.push(new Particle());

		const onResize = () => resize();
		window.addEventListener("resize", onResize);
		animate();

		return () => {
			cancelAnimationFrame(frame);
			window.removeEventListener("resize", onResize);
		};
	}, []);

	return <canvas ref={canvasRef} className="particle-field" />;
};
