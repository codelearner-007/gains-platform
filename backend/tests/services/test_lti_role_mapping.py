"""A — map_lti_roles (pure function, NO DB).

Locks the privilege-mapping invariant: the IMS roles array collapses to exactly
one in-school role, MOST-PRIVILEGED wins, and anything unrecognised (or empty)
defaults to the LEAST-privileged role (student). This is the privilege-escalation
guard for the launch path — a student who smuggles an extra role must never be
upgraded past what the platform genuinely asserts, and an instructor mixed with a
learner must resolve to teacher, never be downgraded to student.
"""

from __future__ import annotations

import pytest

from app.services.lti_service import map_lti_roles

# Real IMS LIS v2 membership URIs, as Schoology/Canvas actually send them.
ADMIN = "http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator"
INSTRUCTOR = "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
CONTENT_DEV = "http://purl.imsglobal.org/vocab/lis/v2/membership#ContentDeveloper"
TA = "http://purl.imsglobal.org/vocab/lis/v2/membership#TeachingAssistant"
LEARNER = "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"


@pytest.mark.parametrize(
    "roles, expected",
    [
        # single-role happy paths
        ([ADMIN], "admin"),
        ([INSTRUCTOR], "teacher"),
        ([CONTENT_DEV], "teacher"),
        ([TA], "teacher"),
        ([LEARNER], "student"),
        # least-privilege defaults
        ([], "student"),
        (["http://purl.imsglobal.org/vocab/lis/v2/membership#Mentor"], "student"),
        (["garbage"], "student"),
        # MOST-PRIVILEGED-WINS (privilege-escalation guard): a teacher mixed with
        # a learner must resolve to teacher, never be downgraded to student.
        ([INSTRUCTOR, LEARNER], "teacher"),
        ([LEARNER, INSTRUCTOR], "teacher"),
        # admin outranks everything, order-independent.
        ([LEARNER, INSTRUCTOR, ADMIN], "admin"),
        ([ADMIN, LEARNER], "admin"),
    ],
)
def test_map_lti_roles_collapses_most_privileged(roles, expected):
    assert map_lti_roles(roles) == expected


def test_none_input_defaults_to_student():
    # A missing roles claim (None) must fail safe to least privilege, not crash.
    assert map_lti_roles(None) == "student"


def test_learner_is_never_upgraded_by_unknown_roles():
    # Padding a learner with junk roles must not escalate them past student.
    assert map_lti_roles([LEARNER, "urn:custom:some-random-role"]) == "student"
