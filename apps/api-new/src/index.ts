import { bootstrap } from "./app.ts";

const { app } = bootstrap();
const port = Number(Bun.env["PORT"] ?? 8000);
console.log(`SkillSignal API listening on ${port}`);
Bun.serve({ port, fetch: app.fetch });
