"""Which dashboard rail each person gets, picked from the org model. A rail is
an ordered list of page keys; the first is the landing page."""
from collections import namedtuple

from app.modules.core.shared.lib import org

# endpoint None means the page has no route (My hub, owned by HR).
Page = namedtuple('Page', 'key label endpoint icon')


class Rail(namedtuple('Rail', 'key pages')):
    """A rail's name and its page keys, landing page first."""

    @property
    def landing(self):
        return self.pages[0]


# Icons are SVG path data for the shared module_rail macro.
_PAGE_LIST = (
    Page('overview', 'Overview', 'projects.overview',
         'M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 8h6V4h-6z'),
    Page('calendar', 'Calendar', 'projects.calendar',
         'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01'),
    Page('my_projects', 'My projects', 'projects.my_projects', 'M3 7h6l2 2h10v10H3z'),
    Page('site_visits', 'Site visits', 'projects.site_visits',
         'M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5'),
    Page('approvals', 'Approvals', 'projects.approvals',
         'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6'),
    Page('my_clients', 'My clients', 'projects.my_clients', 'M4 7h16v13H4zM9 7V4h6v3M4 12h16'),
    Page('assignments', 'Assignments', 'projects.assignments',
         'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21v-1a6 6 0 0 1 12 0v1M19 8v6M16 11h6'),
    Page('team', 'Team', 'projects.team',
         'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21v-1a6 6 0 0 1 12 0v1M16 3.5a4 4 0 0 1 0 7M22 21v-1a6 6 0 0 0-3-5.2'),
    Page('design_workload', 'Design workload', 'projects.design_workload',
         'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5'),
    Page('needs_attention', 'Needs attention', 'projects.needs_attention',
         'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8v5M12 16h.01'),
    Page('escalations', 'Escalations', 'projects.escalations', 'M12 19V5M5 12l7-7 7 7'),
    Page('delivery', 'Delivery', 'projects.delivery', 'M4 19h16M5 15l4-4 4 3 6-7'),
    Page('teams', 'Teams', 'projects.teams', 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z'),
    Page('clients', 'Clients', 'projects.clients', 'M3 21V7l9-4 9 4v14M9 21v-6h6v6M8 10h.01M16 10h.01'),
    Page('adoption', 'Adoption', 'projects.adoption', 'M4 19V10M9.5 19V5M15 19v-7M20.5 19v-4'),
    Page('system', 'System', 'projects.admin_system', 'M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01'),
    Page('database', 'Database', 'projects.admin_database',
         'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6'
         'M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3'),
    Page('performance', 'Performance', 'projects.admin_performance', 'M12 14l4-4M3.5 17a9 9 0 1 1 17 0'),
    Page('usage', 'Usage', 'projects.admin_usage', 'M3 12h4l3-8 4 16 3-8h4'),
    Page('errors', 'Errors', 'projects.admin_errors', 'M12 3l9 16H3zM12 9v5M12 17.2v.1'),
    Page('uptime', 'Uptime', 'projects.admin_uptime',
         'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 3'),
    Page('jobs', 'Jobs', 'projects.admin_jobs',
         'M10 6h10M10 12h10M10 18h10M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2'),
    Page('my_hub', 'My hub', None, 'M3 11l9-7 9 7M5 9v11h14V9'),
)
PAGES = {page.key: page for page in _PAGE_LIST}

# Every rail ends with My hub. The order is the order on screen.
RAILS = {
    'admin': ('overview', 'system', 'database', 'performance', 'usage', 'errors',
              'uptime', 'jobs', 'my_hub'),
    'management': ('overview', 'escalations', 'needs_attention', 'design_workload',
                   'delivery', 'teams', 'clients', 'adoption', 'my_hub'),
    'design_head': ('design_workload', 'overview', 'assignments', 'team', 'calendar', 'my_hub'),
    'design_lead': ('overview', 'assignments', 'team', 'calendar', 'my_hub'),
    'designer': ('overview', 'my_projects', 'site_visits', 'calendar', 'my_hub'),
    'cs_head': ('needs_attention', 'overview', 'approvals', 'my_clients', 'calendar', 'my_hub'),
    'cs': ('overview', 'approvals', 'my_clients', 'calendar', 'my_hub'),
    'project_owner': ('overview', 'approvals', 'my_projects', 'site_visits', 'calendar', 'my_hub'),
    'basic': ('overview', 'my_hub'),
}


def _rail_key(user):
    # Branch checks, not can(): admin's wildcard would match every rail.
    if org.is_admin(user):
        return 'admin'
    if org.is_management(user):
        return 'management'
    if org.is_designer(user):
        if org.is_department_head(user):
            return 'design_head'
        return 'design_lead' if org.is_design_lead(user) else 'designer'
    if org.is_cs(user):
        return 'cs_head' if org.is_department_head(user) else 'cs'
    if org.is_project_owner(user):
        return 'project_owner'
    return 'basic'


def rail_for(user):
    """The rail `user` gets, from department, seniority and the admin switch only."""
    key = _rail_key(user)
    return Rail(key, RAILS[key])
