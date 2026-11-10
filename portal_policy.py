"""Persisted controls for the deliberately insecure, fictional educational lab.

These switches never affect authentication, CSRF, or administrative roles.
"""
from flask import g

RULE_IDS = (
    'student_own_grades_only', 'block_student_professor_area',
    'block_student_grade_edit', 'professor_assigned_courses_only',
    'session_inactivity_timeout', 'audit_professor_only',
)
IDLE_SECONDS = 30


def validate_rules(value):
    if not isinstance(value, dict) or set(value) != set(RULE_IDS) or any(type(v) is not bool for v in value.values()):
        raise ValueError('Provide exactly the six demo rules, each with a boolean value.')
    return {key: value[key] for key in RULE_IDS}


def policy(connection):
    if not hasattr(g, 'portal_policy'):
        row = connection.execute('SELECT rules,revision FROM lab_policy WHERE singleton=true').fetchone()
        if not row:
            raise RuntimeError('portal_policy_migration_required')
        rules = validate_rules(row['rules'])
        g.portal_policy = {'rules': rules, 'active_count': sum(rules.values()),
                           'total_controls': len(RULE_IDS), 'revision': row['revision'], 'demo': True}
    return g.portal_policy
