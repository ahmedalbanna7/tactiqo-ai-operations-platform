# F11 deferred feature closure backlog

Decision recorded 2026-09-23: execute F10 operational hardening now, then close the outstanding
F7/F8/F9 product and evidence gates in F11. The items below are deferred, not completed, and this
deferral is not a waiver of security requirements.

## F7 and earlier

- F7: connector synchronization, OCR/transcription, precise locators, reranking/evaluation,
  revocation drills, resumable large uploads and final Arabic/English retrieval thresholds.
- Earlier open exit gates: end-to-end Jira/Slack OAuth against a real tenant and any unchecked item
  in the master plan. Observability baseline work is now active under F10.

## F8

- All unchecked/partial F8.1-F8.3 and F8 exit-gate items in `MASTER_IMPLEMENTATION_PLAN.md`,
  including full email, Power BI, automation, image, video, meeting, data-operations and social
  execution agents; richer PDF/Office outputs; visual QA; independent positive review; real
  provider success, destination verification and reversal; complete scope certification.

## F9

- Employee/admin experience and Company Settings exit gates still open in `F9_IMPLEMENTATION.md`:
  policy preview for tools and source/resource ACLs, remaining quotas/budgets/approval settings,
  destructive/stale/concurrent tests, full Owner setup, formal accessibility/cross-browser checks,
  and real OIDC multi-role acceptance.

## Return rule

F11 follows F10 operational hardening and precedes production release certification. Close each item
only with implementation, automated evidence and required external tenant evidence. Original F7/F8
checklists remain authoritative; F11 groups their unfinished requirements without marking the
original exit gates as passed. No deferred item may bypass current authorization, classification,
human approval or tenant isolation. See `MASTER_IMPLEMENTATION_PLAN.md` F11 for the exit gates.
