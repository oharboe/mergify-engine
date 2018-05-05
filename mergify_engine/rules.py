# -*- encoding: utf-8 -*-
#
# Copyright © 2018 Mehdi Abaakouk <sileht@sileht.net>
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

import collections
import copy
import logging
import re

import github
import voluptuous
import yaml

LOG = logging.getLogger(__name__)

with open("default_rule.yml", "r") as f:
    DEFAULT_RULE = yaml.load(f.read())


Protection = {
    'required_status_checks': voluptuous.Any(
        None, {
            'strict': bool,
            'contexts': [str],
        }),
    'required_pull_request_reviews': voluptuous.Any(
        None, {
            'dismiss_stale_reviews': bool,
            'require_code_owner_reviews': bool,
            'required_approving_review_count': voluptuous.All(
                int, voluptuous.Range(min=1, max=6)),
        }),
    'restrictions': voluptuous.Any(None, []),
    'enforce_admins': voluptuous.Any(None, bool),
}

# TODO(sileht): We can add some otherthing like
# automatic backport tag
# option to disable mergify on a particular PR
Rule = {
    'protection': Protection,
    'disabling_label': str,
    voluptuous.Optional('automated_backport_labels'): {str: str},
}

UserConfigurationSchema = {
    voluptuous.Required('rules'): voluptuous.Any({
        'default': Rule,
        'branches': {str: voluptuous.Any(Rule, None)},
    }, None)
}


class NoRules(Exception):
    pass


def validate_user_config(content):
    # NOTE(sileht): This is just to check the syntax some attributes can be
    # missing, the important thing is that once merged with the default.
    # Everything need by Github is set
    return voluptuous.Schema(UserConfigurationSchema)(yaml.load(content))


def validate_merged_config(config):
    # NOTE(sileht): To be sure the POST request to protect branch works
    # we must have all keys set, so we set required=True here.
    # Optional key in Github API side have to be explicitly Optional with
    # voluptuous
    return voluptuous.Schema(Rule, required=True)(config)


def dict_merge(dct, merge_dct):
    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], collections.Mapping)):
            dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]


def get_branch_rule(g_repo, incoming_pull):
    rule = copy.deepcopy(DEFAULT_RULE)

    branch = incoming_pull.base.ref

    ref = github.GithubObject.NotSet
    if g_repo.default_branch == branch:
        # FIXME(sileht): This is not an ideal solution, because changing the
        # file means changing the branch protection, for now we run only one
        # worker, we don't have concurrency issue, each PR reconfigure the
        # branch protection safely. But with multiple workers
        # this will change the protection while maybe an other worker will try
        # to merge a PR...

        # NOTE(sileht): If the PR on the default branch change the .mergify.yml
        # we use it, otherwise we the file on the default branch
        for f in incoming_pull.get_files():
            if f.filename == ".mergify.yml":
                ref = f.contents_url.split("?ref=")[1]

    try:
        content = g_repo.get_contents(".mergify.yml", ref=ref).decoded_content
        LOG.info("found mergify.yml")
    except github.UnknownObjectException:
        raise NoRules(".mergify.yml is missing")

    try:
        rules = validate_user_config(content)["rules"] or {}
    except yaml.YAMLError as e:
        if hasattr(e, 'problem_mark'):
            raise NoRules(".mergify.yml is invalid at position: (%s:%s)" %
                          (e.problem_mark.line+1, e.problem_mark.column+1))
        else:
            raise NoRules(".mergify.yml is invalid: %s" % str(e))
    except voluptuous.MultipleInvalid as e:
        raise NoRules(".mergify.yml is invalid: %s" % str(e))

    dict_merge(rule, rules.get("default", {}))

    for branch_re in rules.get("branches", []):
        if re.match(branch_re, branch):
            if rules["branches"][branch_re] is None:
                LOG.info("Rule for %s branch: %s" % (branch, rule))
                return None
            else:
                dict_merge(rule, rules["branches"][branch_re])
    try:
        rule = validate_merged_config(rule)
    except voluptuous.MultipleInvalid as e:
        raise NoRules("mergify configuration invalid: %s" % str(e))

    LOG.info("Rule for %s branch: %s" % (branch, rule))
    return rule
