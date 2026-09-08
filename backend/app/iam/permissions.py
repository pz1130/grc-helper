from enum import StrEnum


class Role(StrEnum):
    """四个角色，权限自高向低（spec §8.1）。"""

    ADMIN = "admin"
    GRC_LEAD = "grc_lead"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"
