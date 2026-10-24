# AgentChainCut

**Calculamos y probamos el mínimo privilegio para agentes de IA conectados por MCP, y lo hacemos cumplir en un proxy que guarda las credenciales.**

## El problema

Un agente de soporte lee tickets, consulta facturas y manda correos con una credencial que alcanza a *todos* los clientes. Basta un ticket con una orden escondida para que lea la factura de otro cliente y se la envíe al atacante. No se hackea nada: el agente usa permisos que ya tenía.

## Lo que hacemos

1. **Descubrimos** las herramientas MCP y las clasificamos según si traen texto de afuera (U), tocan datos sensibles (S) o actúan hacia afuera (X).
2. **Minamos reglas** de trabajo legítimo que atan cada argumento a la sesión: `mail.send.to == ticket.customer.email`, `invoice_id ∈ customer.invoice_ids`. Las coincidencias se rechazan y se muestra el motivo.
3. **Optimizamos** con CP-SAT bajo la Regla de Dos de Meta: ninguna sesión junta U, S y X. Si no hay solución, el núcleo mínimo explica el conflicto y propone aprobación humana o dividir el agente.
4. **Verificamos** con clientes que el sistema nunca vio y con ataques.
5. **Hacemos cumplir** la política en un proxy MCP que tiene las credenciales, falla cerrado y anota cada decisión en un registro encadenado por hashes.

## Resultados medidos (semilla 26)

| Defensa | Ataques que pasan | Trabajo legítimo que sigue |
|---|---|---|
| Sin defensa | 100% (300/300) | 100% (200/200) |
| Solo taint (estilo Ikarus) | 25,0% (75/300) | 83,0% (166/200) |
| Allowlist estática (estilo Progent manual) | 52,3% (157/300) | 100% (200/200) |
| **AgentChainCut** | **0,0% (0/300)** | **100% (200/200)** |

En AgentDojo, a nivel de política y sin LLM, pasa el 11,6% de los ataques y el 75,3% queda en aprobación humana. Ahí no hay contexto confiable de sesión, y lo decimos tal cual.

**Límites declarados:** argumentos SQL libres, bugs del propio servidor, los canales residuales que reporta la verificación (cota inferior) y un mundo sintético modelado sobre APIs reales.

> Los demás equipos construyen guardias más inteligentes; nosotros construimos mejores cerraduras y probamos que encajan.
