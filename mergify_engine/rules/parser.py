# -*- encoding: utf-8 -*-
#
# Copyright © 2018—2021 Mergify SAS
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import datetime
import typing

import pyparsing


git_branch = pyparsing.CharsNotIn("~^: []\\")
regexp = pyparsing.CharsNotIn("")
integer = pyparsing.Word(pyparsing.nums).setParseAction(lambda toks: int(toks[0]))
github_login = pyparsing.Word(pyparsing.alphanums + "-[]")
github_team = pyparsing.Combine(
    pyparsing.Literal("@") + github_login + pyparsing.Literal("/") + github_login
) | pyparsing.Combine(pyparsing.Literal("@") + github_login)
text = (
    pyparsing.QuotedString('"') | pyparsing.QuotedString("'") | pyparsing.CharsNotIn("")
)
milestone = pyparsing.CharsNotIn(" ")

_match_time = (
    pyparsing.Word(pyparsing.nums).addCondition(
        lambda tokens: int(tokens[0]) >= 0 and int(tokens[0]) < 24
    )
    + pyparsing.Literal(":")
    + pyparsing.Word(pyparsing.nums).addCondition(
        lambda tokens: int(tokens[0]) >= 0 and int(tokens[0]) < 60
    )
).setParseAction(
    lambda toks: datetime.time(
        hour=int(toks[0]), minute=int(toks[2]), tzinfo=datetime.timezone.utc
    )
)

regex_operators = pyparsing.Literal("~=")


equality_operators = (
    pyparsing.Literal(":").setParseAction(pyparsing.replaceWith("="))
    | pyparsing.Literal("=")
    | pyparsing.Literal("==").setParseAction(pyparsing.replaceWith("="))
    | pyparsing.Literal("!=")
    | pyparsing.Literal("≠").setParseAction(pyparsing.replaceWith("!="))
)

range_operators = (
    pyparsing.Literal(">=")
    | pyparsing.Literal("≥").setParseAction(pyparsing.replaceWith(">="))
    | pyparsing.Literal("<=")
    | pyparsing.Literal("≤").setParseAction(pyparsing.replaceWith("<="))
    | pyparsing.Literal("<")
    | pyparsing.Literal(">")
)
simple_operators = equality_operators | range_operators


def _match_boolean(literal: str) -> pyparsing.Token:
    return (
        literal
        + pyparsing.Empty().setParseAction(pyparsing.replaceWith("="))
        + pyparsing.Empty().setParseAction(pyparsing.replaceWith(True))
    )


match_integer = simple_operators + integer


def _match_with_operator(token: pyparsing.Token) -> pyparsing.Token:
    return (simple_operators + token) | (regex_operators + regexp)


def _token_to_dict(
    s: str, loc: int, toks: typing.List[pyparsing.Token]
) -> typing.Dict[str, typing.Any]:
    if len(toks) == 3:
        # datetime attributes
        key_op = ""
        not_ = False
        key, op, value = toks
    elif len(toks) == 5:
        # quantifiable_attributes
        not_, key_op, key, op, value = toks
    elif len(toks) == 4:
        # non_quantifiable_attributes
        key_op = ""
        not_, key, op, value = toks
    else:
        raise RuntimeError("unexpected search parser format")

    if key_op == "#":
        value = int(value)
    d = {op: (key_op + key, value)}
    if not_:
        return {"-": d}
    return d


_match_login_or_teams = _match_with_operator(github_login) | (
    simple_operators + github_team
)

head = "head" + _match_with_operator(git_branch)
base = "base" + _match_with_operator(git_branch)
author = "author" + _match_login_or_teams
merged_by = "merged-by" + _match_login_or_teams
body = "body" + _match_with_operator(text)
assignee = "assignee" + _match_login_or_teams
label = "label" + _match_with_operator(text)
title = "title" + _match_with_operator(text)
files = "files" + _match_with_operator(text)
milestone = "milestone" + _match_with_operator(milestone)
number = "number" + match_integer
review_requests = "review-requested" + _match_login_or_teams
review_approved_by = "approved-reviews-by" + _match_login_or_teams
review_dismissed_by = "dismissed-reviews-by" + _match_login_or_teams
review_changes_requested_by = "changes-requested-reviews-by" + _match_login_or_teams
review_commented_by = "commented-reviews-by" + _match_login_or_teams
status_success = "status-success" + _match_with_operator(text)
status_failure = "status-failure" + _match_with_operator(text)
status_neutral = "status-neutral" + _match_with_operator(text)
check_success = "check-success" + _match_with_operator(text)
check_success_or_neutral = "check-success-or-neutral" + _match_with_operator(text)
check_failure = "check-failure" + _match_with_operator(text)
check_neutral = "check-neutral" + _match_with_operator(text)
check_skipped = "check-skipped" + _match_with_operator(text)
check_pending = "check-pending" + _match_with_operator(text)
check_stale = "check-stale" + _match_with_operator(text)
current_time = "current-time" + range_operators + _match_time

quantifiable_attributes = (
    head
    | base
    | author
    | merged_by
    | body
    | assignee
    | label
    | title
    | files
    | milestone
    | number
    | review_requests
    | review_approved_by
    | review_dismissed_by
    | review_changes_requested_by
    | review_commented_by
    | status_success
    | status_neutral
    | status_failure
    | check_success
    | check_neutral
    | check_success_or_neutral
    | check_failure
    | check_skipped
    | check_pending
    | check_stale
)

locked = _match_boolean("locked")
merged = _match_boolean("merged")
closed = _match_boolean("closed")
conflict = _match_boolean("conflict")
draft = _match_boolean("draft")

non_quantifiable_attributes = locked | closed | conflict | draft | merged

datetime_attributes = current_time

search = (
    (
        pyparsing.Optional(
            (
                pyparsing.Literal("-").setParseAction(pyparsing.replaceWith(True))
                | pyparsing.Literal("¬").setParseAction(pyparsing.replaceWith(True))
                | pyparsing.Literal("+").setParseAction(pyparsing.replaceWith(False))
            ),
            default=False,
        )
        + (
            (pyparsing.Optional("#", default="") + quantifiable_attributes)
            | non_quantifiable_attributes
        )
    )
    | datetime_attributes
).setParseAction(_token_to_dict)
