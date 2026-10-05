"""Who approves a person's requests (leave and the like): their Reports-to chain
up to the first Management person, then any one HR person."""
from dataclasses import dataclass, field

from app.modules.core.shared.lib.org import is_management
from app.modules.core.shared.lib.users import active_users_in


@dataclass
class ApprovalStep:
    """One step in the chain; any one of `approvers` can approve it."""
    approvers: tuple
    is_hr: bool = False


@dataclass
class ApprovalChain:
    """The steps in order, HR last. complete is False when the walk stopped at
    a missing Reports to or a loop before reaching Management."""
    steps: list = field(default_factory=list)
    complete: bool = True


def approvers_for(user):
    """The approval chain for `user`. Management people go straight to HR,
    deactivated managers are skipped, and HR always closes the chain."""
    chain = ApprovalChain()
    seen = {user.id}
    reached_management = is_management(user)
    current = user.reports_to

    while current is not None and not reached_management:
        if current.id in seen:
            break
        seen.add(current.id)
        if current.is_active:
            chain.steps.append(ApprovalStep(approvers=(current,)))
            reached_management = is_management(current)
        current = current.reports_to

    chain.complete = reached_management
    hr = tuple(person for person in active_users_in('hr') if person.id != user.id)
    chain.steps.append(ApprovalStep(approvers=hr, is_hr=True))
    return chain
