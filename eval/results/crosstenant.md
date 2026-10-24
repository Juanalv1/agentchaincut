# Cross-tenant benchmark

Held-out sessions from 80 customers never seen in training (seed 26).

| Defense | Attack success ↓ | Utility ↑ | False denies ↓ | Label |
|---|---|---|---|---|
| No defense | 100.0% (300/300, n=300) | 100.0% (200/200, n=200) | 0.0% (0/200, n=200) | measured |
| Taint-only (Ikarus-like) | 25.0% (75/300, n=300) | 83.0% (166/200, n=200) | 17.0% (34/200, n=200) | measured |
| Static allowlist (Progent-manual-like) | 52.3% (157/300, n=300) | 100.0% (200/200, n=200) | 0.0% (0/200, n=200) | measured |
| AgentChainCut | 0.0% (0/300, n=300) | 100.0% (200/200, n=200) | 0.0% (0/200, n=200) | measured |

Attack success by family (count / n):

| Defense | bulk_exfil | cross_tenant_recipient | cross_ticket | excess_refund | foreign_object_id | foreign_recipient | foreign_refund | injected_context |
|---|---|---|---|---|---|---|---|---|
| No defense | 37/37 | 38/38 | 38/38 | 37/37 | 38/38 | 38/38 | 37/37 | 37/37 |
| Taint-only (Ikarus-like) | 37/37 | 0/38 | 0/38 | 0/37 | 38/38 | 0/38 | 0/37 | 0/37 |
| Static allowlist (Progent-manual-like) | 0/37 | 38/38 | 38/38 | 6/37 | 38/38 | 0/38 | 37/37 | 0/37 |
| AgentChainCut | 0/37 | 0/38 | 0/38 | 0/37 | 0/38 | 0/38 | 0/37 | 0/37 |


## Stratified sample with the LLM-written-policy baseline (n=24)

| Defense | Attack success ↓ | Utility ↑ | False denies ↓ | Label |
|---|---|---|---|---|
| No defense | 100.0% (12/12, n=12) | 100.0% (12/12, n=12) | 0.0% (0/12, n=12) | measured |
| Taint-only (Ikarus-like) | 25.0% (3/12, n=12) | 83.3% (10/12, n=12) | 16.7% (2/12, n=12) | measured |
| Static allowlist (Progent-manual-like) | 50.0% (6/12, n=12) | 100.0% (12/12, n=12) | 0.0% (0/12, n=12) | measured |
| AgentChainCut | 0.0% (0/12, n=12) | 100.0% (12/12, n=12) | 0.0% (0/12, n=12) | measured |
| LLM-written policy (Progent-LLM-like, claude-opus-5-5) | not measured | not measured | not measured | not-measured |

Attack success by family (count / n):

| Defense | bulk_exfil | cross_tenant_recipient | cross_ticket | excess_refund | foreign_object_id | foreign_recipient | foreign_refund | injected_context |
|---|---|---|---|---|---|---|---|---|
| No defense | 2/2 | 2/2 | 2/2 | 2/2 | 1/1 | 1/1 | 1/1 | 1/1 |
| Taint-only (Ikarus-like) | 2/2 | 0/2 | 0/2 | 0/2 | 1/1 | 0/1 | 0/1 | 0/1 |
| Static allowlist (Progent-manual-like) | 0/2 | 2/2 | 2/2 | 0/2 | 1/1 | 0/1 | 1/1 | 0/1 |
| AgentChainCut | 0/2 | 0/2 | 0/2 | 0/2 | 0/1 | 0/1 | 0/1 | 0/1 |

