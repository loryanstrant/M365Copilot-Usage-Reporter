"""Shared metric filter model (Phase 9).

Every report page slices by the same dimensions. ``MetricFilters`` turns those
optional query params into SQLAlchemy conditions and tells callers whether a join
to ``entra_users`` is required (only when a directory dimension is used).

Categorical dimensions are **multi-select**: each is a list of accepted values
(empty list = no filter = all). This lets the UI deselect individual options
(e.g. hide "Copilot Chat") and have every chart update.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import or_

from shared.models import EntraUser, Prompt


def _clean(values: list[str] | None) -> list[str]:
    return [v for v in (values or []) if v not in (None, "")]


@dataclass
class MetricFilters:
    date_from: date | None = None
    date_to: date | None = None
    apps: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    manager_ids: list[str] = field(default_factory=list)
    offices: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    job_titles: list[str] = field(default_factory=list)
    chat_types: list[str] = field(default_factory=list)
    conversation_locations: list[str] = field(default_factory=list)
    user_search: str | None = None

    def prompt_conds(self) -> list[Any]:
        """Conditions applied directly to the ``prompts`` table."""
        conds: list[Any] = []
        if self.date_from is not None:
            conds.append(Prompt.prompt_date >= self.date_from)
        if self.date_to is not None:
            conds.append(Prompt.prompt_date <= self.date_to)
        if _clean(self.apps):
            conds.append(Prompt.app_name.in_(_clean(self.apps)))
        if _clean(self.chat_types):
            conds.append(Prompt.chat_type.in_(_clean(self.chat_types)))
        if _clean(self.conversation_locations):
            conds.append(
                Prompt.conversation_location.in_(_clean(self.conversation_locations))
            )
        return conds

    def user_conds(self) -> list[Any]:
        """Conditions that require a join to ``entra_users``."""
        conds: list[Any] = []
        if _clean(self.departments):
            conds.append(EntraUser.department.in_(_clean(self.departments)))
        if _clean(self.manager_ids):
            conds.append(EntraUser.manager_id.in_(_clean(self.manager_ids)))
        if _clean(self.offices):
            conds.append(EntraUser.office_location.in_(_clean(self.offices)))
        if _clean(self.companies):
            conds.append(EntraUser.company_name.in_(_clean(self.companies)))
        if _clean(self.job_titles):
            conds.append(EntraUser.job_title.in_(_clean(self.job_titles)))
        if self.user_search:
            like = f"%{self.user_search}%"
            conds.append(
                or_(
                    EntraUser.display_name.ilike(like),
                    EntraUser.upn.ilike(like),
                    EntraUser.email.ilike(like),
                )
            )
        return conds

    @property
    def needs_user_join(self) -> bool:
        return bool(self.user_conds())

    def all_conds(self) -> list[Any]:
        return [*self.prompt_conds(), *self.user_conds()]
