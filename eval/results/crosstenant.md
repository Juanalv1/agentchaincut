# Cross-tenant benchmark

Held-out sessions from 80 customers never seen in training (seed 26).

| Defense | Attack success ↓ | Utility ↑ | False denies ↓ | Label |
|---|---|---|---|---|
| No defense | 100.0% (300/300, n=300) | 100.0% (200/200, n=200) | 0.0% (0/200, n=200) | measured |
| Taint-only (Ikarus-like) | 33.3% (100/300, n=300) | 83.0% (166/200, n=200) | 17.0% (34/200, n=200) | measured |
| Static allowlist (Progent-manual-like) | 58.3% (175/300, n=300) | 100.0% (200/200, n=200) | 0.0% (0/200, n=200) | measured |
| AgentChainCut | 0.0% (0/300, n=300) | 100.0% (200/200, n=200) | 0.0% (0/200, n=200) | measured |

Attack success by family (count / n):

| Defense | bulk_exfil | cross_tenant_recipient | cross_ticket | excess_refund | foreign_list | foreign_object_id | foreign_recipient | foreign_refund | injected_context |
|---|---|---|---|---|---|---|---|---|---|
| No defense | 33/33 | 34/34 | 33/33 | 33/33 | 33/33 | 34/34 | 34/34 | 33/33 | 33/33 |
| Taint-only (Ikarus-like) | 33/33 | 0/34 | 0/33 | 0/33 | 33/33 | 34/34 | 0/34 | 0/33 | 0/33 |
| Static allowlist (Progent-manual-like) | 0/33 | 34/34 | 33/33 | 8/33 | 33/33 | 34/34 | 0/34 | 33/33 | 0/33 |
| AgentChainCut | 0/33 | 0/34 | 0/33 | 0/33 | 0/33 | 0/34 | 0/34 | 0/33 | 0/33 |


## Stratified sample with the LLM-written-policy baseline (n=24)

| Defense | Attack success ↓ | Utility ↑ | False denies ↓ | Label |
|---|---|---|---|---|
| No defense | 100.0% (12/12, n=12) | 100.0% (12/12, n=12) | 0.0% (0/12, n=12) | measured |
| Taint-only (Ikarus-like) | 33.3% (4/12, n=12) | 83.3% (10/12, n=12) | 16.7% (2/12, n=12) | measured |
| Static allowlist (Progent-manual-like) | 66.7% (8/12, n=12) | 100.0% (12/12, n=12) | 0.0% (0/12, n=12) | measured |
| AgentChainCut | 0.0% (0/12, n=12) | 100.0% (12/12, n=12) | 0.0% (0/12, n=12) | measured |
| LLM-written policy (Progent-LLM-like, claude-opus-5-5) | 0.0% (0/12, n=12) | 66.7% (8/12, n=12) | 33.3% (4/12, n=12) | measured |

Attack success by family (count / n):

| Defense | bulk_exfil | cross_tenant_recipient | cross_ticket | excess_refund | foreign_list | foreign_object_id | foreign_recipient | foreign_refund | injected_context |
|---|---|---|---|---|---|---|---|---|---|
| No defense | 2/2 | 2/2 | 2/2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Taint-only (Ikarus-like) | 2/2 | 0/2 | 0/2 | 0/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| Static allowlist (Progent-manual-like) | 0/2 | 2/2 | 2/2 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| AgentChainCut | 0/2 | 0/2 | 0/2 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| LLM-written policy (Progent-LLM-like, claude-opus-5-5) | 0/2 | 0/2 | 0/2 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |


LLM policy variance: 0 of 5 sessions got different policies across 3 runs (mean distinct policies 1.0).
