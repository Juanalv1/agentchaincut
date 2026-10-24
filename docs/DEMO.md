# Guion operativo de la demo (3:00)

Cómo levantar todo y qué tocar en cada momento. El guion narrativo está en `odd/tasks/agentchaincut.md` (sección Demo).

## Antes de subir al escenario

```bash
source .venv/bin/activate
acc run world/ --out artifacts            # política, verificación y exportaciones (~1 s)
python -m eval.crosstenant                # tabla contra las líneas base
python -m api                             # API en http://127.0.0.1:8000 (proxy en vivo + SSE)
cd web && NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run build && npx serve out
```

Sin red o si falla la API: `cd web && npm run build && npx serve out`. El dashboard entra en **modo replay**: usa la corrida grabada en `web/public/demo` y recalcula la cadena de hashes en el navegador.

## Minuto a minuto

| Tiempo | Pantalla | Acción |
|---|---|---|
| 0:00–0:20 | Arriba: ticket envenenado y pantalla dividida | En vivo: "Run the attack again". Izquierda: la factura de otro cliente llega al atacante. Derecha: se niega en `billing.invoice_read` |
| 0:20–0:45 | Map, en "Before" | El camino rojo `tickets.get → billing.invoice_read → mail.send` se ejecutó con llamadas guionadas, sin LLM |
| 0:45–1:25 | Rules, después Solver | Las reglas rechazadas aparecen tachadas con su motivo. OPTIMAL, 0 tareas rotas y el conflicto de `refund_request` resuelto con aprobación |
| 1:25–2:00 | Map en "After policy"; Verify; Ledger | 200/200 y 300/300 medidos. "Tamper with entry 1" pone la cadena en rojo y "Restore" la arregla |
| 2:00–2:30 | Results | Contra solo taint, la allowlist estática y la política del LLM. En AgentDojo se dice tal cual que ahí cae en aprobación |
| 2:30–3:00 | Exports | Hook de Claude Code, Progent y Assay. Frase de cierre |

## Si algo falla

- **La API no responde:** se usa el modo replay (mismo dashboard, sin red).
- **Sin key de Claude:** la fila del LLM y el agente en vivo muestran *not-measured*. No se inventan números.
- **Video grabado de respaldo:** pendiente (T17).
