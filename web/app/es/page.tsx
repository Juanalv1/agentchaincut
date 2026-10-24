import type { Metadata } from "next";
import { Dashboard } from "@/components/Dashboard";

export const metadata: Metadata = {
  description: "Compila y demuestra políticas de mínimo privilegio para agentes de IA conectados por MCP.",
};

export default function Page() {
  return <Dashboard lang="es" />;
}
