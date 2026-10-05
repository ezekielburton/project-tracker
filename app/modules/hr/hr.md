# hr

Staff records and approvals. The HR pages (staff records, leave, sick days,
reimbursements) arrive in 2.8; today the module is one service.

## Services
- `services/approvers.py::approvers_for(user)` → `ApprovalChain`: the
  Reports-to chain up to and including the first Management person, then one HR
  step any active HR person can approve. Management people go straight to HR.
  Deactivated people are skipped and the requester is never their own approver.
  `complete` is False when the walk hit a missing Reports to or a loop, or when
  no HR person is left to approve (none active, or the requester is the only
  one); HR is still added, so the HR pages can flag it.

## Data it reads
The org fields on the shared user record (`core/shared`): department, seniority,
Reports to. Editing them lives in Admin → Accounts until the HR pages arrive.
