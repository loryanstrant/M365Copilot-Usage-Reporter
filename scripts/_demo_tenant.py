"""The one fictional tenant every solution in the suite seeds against.

Keep this file identical across every sibling repo — the same way
``frontend/src/lib/suite.ts`` is kept identical. The point is that when the four
solutions are demoed together, they describe *one* organisation: the same people,
in the same departments, in the same offices, with numbers that corroborate each
other. Before this existed, each seeder invented its own company (``demo.local``,
``contoso.local``, ``avanoso.com``) and a viewer watching all four saw three
unrelated fake tenants.

Not every sibling uses all of it, and that is deliberate. ``COMPANY``, ``DOMAIN``
and ``COUNTRY`` are the parts that must agree everywhere, because the company name
and the email domain are what actually reach a screen. ``ROSTER`` is for seeders
that would otherwise mash random first and last names together; a repo that has
built its own tuned persona set — with a manager hierarchy, deliberate department
sizes and per-person skill offsets — keeps it and imports only the company
identity. Avanoso having different employees in different reports is what a
1,500-person company looks like; Avanoso being called Contoso in one report is the
thing this module exists to stop.

Everything here is invented. ``avanoso.com`` is not a real domain and none of
these people exist.
"""
from __future__ import annotations

from typing import NamedTuple

#: The fictional organisation.
COMPANY = "Avanoso"
DOMAIN = "avanoso.com"
COUNTRY = "AU"

#: Copilot licences the fictional org has bought. Every solution that shows a
#: licence or seat count should reconcile to this, so the story holds across
#: products: 1,500 bought, ~1,100 actually earning their keep.
LICENCE_HEADCOUNT = 1500

#: Power Platform / Dataverse environments, for the Agent Quality Reporter.
ENVIRONMENTS = [
    f"{COMPANY} (default)",
    f"{COMPANY} — UAT",
    f"{COMPANY} — Dev",
]

DEPARTMENTS = [
    "Sales",
    "Marketing",
    "Finance",
    "Engineering",
    "People & Culture",
    "Customer Success",
    "Legal",
    "Operations",
]

OFFICES = ["Sydney", "Melbourne", "Brisbane", "Perth", "Auckland", "Singapore"]


class Person(NamedTuple):
    """One member of the fictional directory."""

    first: str
    last: str
    department: str
    office: str
    title: str
    licensed: bool

    @property
    def display_name(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def handle(self) -> str:
        return f"{self.first}.{self.last}".lower()

    @property
    def upn(self) -> str:
        return f"{self.handle}@{DOMAIN}"


# A fixed roster of 40, five per department. Fixed rather than randomly
# generated so the same humans appear in every product — "Priya Kaur" is the
# same person with the same job in the Usage Reporter and the Prompt Analyser.
#
# ``licensed`` is set here rather than rolled at seed time for the same reason:
# 30 of the 40 hold a Copilot licence (75%), and it is always the same 30, so the
# laggards and licence views agree with each other across products.
#
# ⚠ Keep it at exactly five per department when editing. The Usage Reporter
# withholds a team's series below five peers, so a department of three makes the
# comparison the demo exists to show silently disappear. Five also guarantees
# every department yields a coaching pair — one champion and one licensed person
# who has never started.
ROSTER: list[Person] = [
    # Sales
    Person("Ava", "Bennett", "Sales", "Sydney", "Account Executive", True),
    Person("Omar", "Haddad", "Sales", "Melbourne", "Account Executive", True),
    Person("Ruby", "Nguyen", "Sales", "Brisbane", "Sales Manager", True),
    Person("Finn", "Murphy", "Sales", "Perth", "Account Executive", True),
    Person("Tara", "Osei", "Sales", "Auckland", "Sales Development Rep", False),
    # Marketing
    Person("Mia", "Silva", "Marketing", "Sydney", "Campaign Manager", True),
    Person("Leo", "Rossi", "Marketing", "Melbourne", "Content Specialist", True),
    Person("Isla", "Lindqvist", "Marketing", "Sydney", "Marketing Director", True),
    Person("Jai", "Duarte", "Marketing", "Singapore", "Brand Coordinator", True),
    Person("Elsie", "Chen", "Marketing", "Melbourne", "Events Coordinator", False),
    # Finance
    Person("Noah", "Kaur", "Finance", "Sydney", "Financial Analyst", True),
    Person("Nina", "Ferreira", "Finance", "Melbourne", "Finance Manager", True),
    Person("Sam", "Yamada", "Finance", "Sydney", "Accounts Payable Officer", True),
    Person("Zoe", "Novak", "Finance", "Brisbane", "Commercial Analyst", True),
    Person("Hugo", "Okafor", "Finance", "Perth", "Payroll Specialist", False),
    # Engineering
    Person("Ethan", "Chen", "Engineering", "Sydney", "Senior Engineer", True),
    Person("Priya", "Kaur", "Engineering", "Melbourne", "Engineering Manager", True),
    Person("Kai", "Yamada", "Engineering", "Sydney", "Platform Engineer", True),
    Person("Maya", "Silva", "Engineering", "Auckland", "Data Engineer", True),
    Person("Liam", "Novak", "Engineering", "Singapore", "QA Engineer", False),
    # People & Culture
    Person("Elsie", "Bennett", "People & Culture", "Sydney", "People Partner", True),
    Person("Omar", "Osei", "People & Culture", "Melbourne", "Recruiter", True),
    Person("Ava", "Lindqvist", "People & Culture", "Sydney", "Head of People", True),
    Person("Finn", "Rossi", "People & Culture", "Brisbane", "L&D Specialist", True),
    Person("Ruby", "Duarte", "People & Culture", "Perth", "People Coordinator", False),
    # Customer Success
    Person("Isla", "Nguyen", "Customer Success", "Sydney", "Customer Success Manager", True),
    Person("Leo", "Haddad", "Customer Success", "Melbourne", "Support Lead", True),
    Person("Tara", "Ferreira", "Customer Success", "Auckland", "Onboarding Specialist", True),
    Person("Noah", "Murphy", "Customer Success", "Singapore", "Support Engineer", True),
    Person("Mia", "Okafor", "Customer Success", "Brisbane", "Support Analyst", False),
    # Legal
    Person("Zoe", "Kaur", "Legal", "Sydney", "Legal Counsel", True),
    Person("Hugo", "Silva", "Legal", "Melbourne", "Contracts Manager", True),
    Person("Nina", "Bennett", "Legal", "Sydney", "Paralegal", True),
    Person("Jai", "Chen", "Legal", "Perth", "Compliance Analyst", False),
    Person("Kai", "Ferreira", "Legal", "Brisbane", "Privacy Officer", False),
    # Operations
    Person("Maya", "Nguyen", "Operations", "Sydney", "Operations Manager", True),
    Person("Ethan", "Duarte", "Operations", "Melbourne", "Logistics Coordinator", True),
    Person("Sam", "Lindqvist", "Operations", "Brisbane", "Facilities Lead", True),
    Person("Priya", "Rossi", "Operations", "Singapore", "Procurement Specialist", False),
    Person("Liam", "Osei", "Operations", "Perth", "Operations Analyst", False),
]


def roster(count: int | None = None) -> list[Person]:
    """The first ``count`` people, or everyone.

    The 40 in ``ROSTER`` are the canonical, hand-written ones, and they are the
    only names that realistically reach a screen — a leaderboard, a coaching
    pair, a scorecard. Asking for more fills out the tail by combining the same
    first and last names into new people, so a 200-person directory still reads
    as a plausible company. Never by suffixing a digit onto a surname: "Bennett-2"
    on a booth screen looks like a bug.
    """
    if count is None or count >= len(ROSTER):
        people = list(ROSTER)
    else:
        return list(ROSTER[:count])
    if count is None or count == len(ROSTER):
        return people

    firsts = sorted({p.first for p in ROSTER})
    lasts = sorted({p.last for p in ROSTER})
    taken = {(p.first, p.last) for p in ROSTER}

    # Deterministic walk of the first × last grid, offset per lap so the pairings
    # don't all share a surname. Every extra person is unlicensed: the fictional
    # org bought 1,500 licences for a bigger directory than it covers, which is
    # exactly the gap the Usage Reporter exists to show.
    for lap in range(1, len(lasts) + 1):
        for index, first in enumerate(firsts):
            if len(people) >= count:
                return people
            last = lasts[(index + lap) % len(lasts)]
            if (first, last) in taken:
                continue
            taken.add((first, last))
            template = ROSTER[len(people) % len(ROSTER)]
            people.append(
                Person(
                    first=first,
                    last=last,
                    department=template.department,
                    office=template.office,
                    title=template.title,
                    licensed=False,
                )
            )
    return people
