import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
    plugins: [
        react({
            babel: {
                plugins: [["babel-plugin-react-compiler", {}]]
            }
        }),
        tailwindcss()
    ],
    envDir: path.resolve(__dirname, "../.."),
    server: {
        port: 3000
    },
    build: {
        target: "esnext"
    }
});
