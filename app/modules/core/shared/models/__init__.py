"""Domain-split SQLAlchemy models. Every model shares the one db registry
from core/shared/extensions, so cross-file relationships resolve normally.
This package re-exports every model as the single import surface."""
from .users import load_user, User, RoleTitle, UserTableLayout, DEFAULT_ROLE_TITLES, ProjectTableView
from .clients import Client, Customer, Contact
from .projects import DesignType, DesignDirection, Scope, Project, ProjectDesigner, ProjectReviewer, ProjectApproval, ProjectRegion, ProjectCustomer, ProjectFile, SiteVisit, ProjectOverlaySeen, ProjectSecondaryCS, ProjectSecondaryCsRegion, ProjectPosmChannel
from .deliverables import DeliverableType, DeliverableTypeDiscipline, Deliverable, DeliverableAssignment, DeliverablePreproductionEvent
from .status_logs import ProjectStatusLog, ProjectCustomerStatusLog, DeliverableStatusLog
from .submissions import ProjectSubmission, ProjectRevision, ProjectRevisionDeliverable, ProjectSubmissionDeliverable, ProjectSubmissionEvent, ProjectSubmissionEventDeliverable, ProjectSubmissionFile, TechnicalSubmission
from .flags import BriefFlag, DecisionFlag, DecisionFlagMessage, BriefFlagMessage
from .notes import ProjectNote, ProjectNoteReaction
from .notifications import Notification, NotificationSound
from .activity import ActivityLog, SidebarClick
from .blog import BlogPost, BlogComment
from .feedback import FeatureRequest, FeatureRequestUpvote, FeatureRequestComment, BugReport, BugReportComment
from .wiki import WikiSection, WikiArticle
from .achievements import AchievementCategory, AchievementBorder, Achievement, UserAchievement, UserDisplaySettings, UserPinnedAchievement

__all__ = [
    'load_user',
    'User',
    'RoleTitle',
    'UserTableLayout',
    'DEFAULT_ROLE_TITLES',
    'ProjectTableView',
    'Client',
    'Customer',
    'Contact',
    'DesignType',
    'DesignDirection',
    'Scope',
    'Project',
    'ProjectDesigner',
    'ProjectReviewer',
    'ProjectApproval',
    'ProjectRegion',
    'ProjectCustomer',
    'ProjectFile',
    'SiteVisit',
    'ProjectOverlaySeen',
    'ProjectSecondaryCS',
    'ProjectSecondaryCsRegion',
    'ProjectPosmChannel',
    'DeliverableType',
    'DeliverableTypeDiscipline',
    'Deliverable',
    'DeliverableAssignment',
    'DeliverablePreproductionEvent',
    'ProjectStatusLog',
    'ProjectCustomerStatusLog',
    'DeliverableStatusLog',
    'ProjectSubmission',
    'ProjectRevision',
    'ProjectRevisionDeliverable',
    'ProjectSubmissionDeliverable',
    'ProjectSubmissionEvent',
    'ProjectSubmissionEventDeliverable',
    'ProjectSubmissionFile',
    'TechnicalSubmission',
    'BriefFlag',
    'DecisionFlag',
    'DecisionFlagMessage',
    'BriefFlagMessage',
    'ProjectNote',
    'ProjectNoteReaction',
    'Notification',
    'NotificationSound',
    'ActivityLog',
    'SidebarClick',
    'BlogPost',
    'BlogComment',
    'FeatureRequest',
    'FeatureRequestUpvote',
    'FeatureRequestComment',
    'BugReport',
    'BugReportComment',
    'WikiSection',
    'WikiArticle',
    'AchievementCategory',
    'AchievementBorder',
    'Achievement',
    'UserAchievement',
    'UserDisplaySettings',
    'UserPinnedAchievement',
]
