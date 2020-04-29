# -*- encoding: utf-8 -*-
#
#  Copyright © 2020 Mergify SAS
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

import httpx
import jinja2.exceptions
import voluptuous

from mergify_engine import actions
from mergify_engine import config
from mergify_engine import context


class CommentAction(actions.Action):
    validator = {voluptuous.Required("message"): str}

    silent_report = True

    def deprecated_double_comment_protection(self, ctxt):
        # TODO(sileht): drop this in 2 months (February 2020)
        for comment in ctxt.client.items(f"issues/{ctxt.pull['number']}/comments"):
            if (
                comment["user"]["id"] == config.BOT_USER_ID
                and comment["body"] == self.config["message"]
            ):
                return True
        return False

    def run(self, ctxt, missing_conditions):
        try:
            message = ctxt.pull_request.jinja2_env.from_string(
                self.config["message"]
            ).render()
        except jinja2.exceptions.TemplateSyntaxError as tse:
            return (
                "failure",
                "Invalid comment message",
                f"There is an error in your comment message: {tse.message} at line {tse.lineno}",
            )
        except jinja2.exceptions.TemplateError as te:
            return (
                "failure",
                "Invalid comment message",
                f"There is an error in your comment message: {te.message}",
            )
        except context.PullRequestAttributeError as e:
            return (
                "failure",
                "Invalid comment message",
                f"There is an error in your comment message, the following variable is unknown: {e.name}",
            )

        try:
            ctxt.client.post(
                f"issues/{ctxt.pull['number']}/comments", json={"body": message},
            )
        except httpx.HTTPClientSideError as e:  # pragma: no cover
            return (
                None,
                "Unable to post comment",
                f"GitHub error: [{e.status_code}] `{e.message}`",
            )
        return ("success", "Comment posted", message)