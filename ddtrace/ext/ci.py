"""
Tags for common CI attributes
"""
from collections import OrderedDict
import json
import logging
import os
import platform
import re
from typing import Dict
from typing import MutableMapping
from typing import Optional

from ddtrace.ext import git
from ddtrace.internal.logger import get_logger


# CI app dd_origin tag
CI_APP_TEST_ORIGIN = "ciapp-test"

# Stage Name
STAGE_NAME = "ci.stage.name"

# Job Name
JOB_NAME = "ci.job.name"

# Job URL
JOB_URL = "ci.job.url"

# Pipeline ID
PIPELINE_ID = "ci.pipeline.id"

# Pipeline Name
PIPELINE_NAME = "ci.pipeline.name"

# Pipeline Number
PIPELINE_NUMBER = "ci.pipeline.number"

# Pipeline URL
PIPELINE_URL = "ci.pipeline.url"

# Provider
PROVIDER_NAME = "ci.provider.name"

# Workspace Path
WORKSPACE_PATH = "ci.workspace_path"

# Architecture
OS_ARCHITECTURE = "os.architecture"

# Platform
OS_PLATFORM = "os.platform"

# Version
OS_VERSION = "os.version"

# Runtime Name
RUNTIME_NAME = "runtime.name"

# Runtime Version
RUNTIME_VERSION = "runtime.version"

# Version of the ddtrace library
LIBRARY_VERSION = "library_version"

# CI Visibility env vars used for pipeline correlation ID
_CI_ENV_VARS = "_dd.ci.env_vars"

_RE_URL = re.compile(r"(https?://)[^/]*@")


log = get_logger(__name__)


def _filter_sensitive_info(url):
    # type: (Optional[str]) -> Optional[str]
    return _RE_URL.sub("\\1", url) if url is not None else None


def _get_runtime_and_os_metadata():
    """Extract configuration facet tags for OS and Python runtime."""
    return {
        OS_ARCHITECTURE: platform.machine(),
        OS_PLATFORM: platform.system(),
        OS_VERSION: platform.release(),
        RUNTIME_NAME: platform.python_implementation(),
        RUNTIME_VERSION: platform.python_version(),
    }


def tags(env=None, cwd=None):
    # type: (Optional[MutableMapping[str, str]], Optional[str]) -> Dict[str, str]
    """Extract and set tags from provider environ, as well as git metadata."""
    env = os.environ if env is None else env
    tags = {}  # type: Dict[str, Optional[str]]
    for key, extract in PROVIDERS:
        if key in env:
            tags = extract(env)
            break

    git_info = git.extract_git_metadata(cwd=cwd)
    try:
        git_info[WORKSPACE_PATH] = git.extract_workspace_path(cwd=cwd)
    except git.GitNotFoundError:
        log.error("Git executable not found, cannot extract git metadata.")
    except ValueError as e:
        debug_mode = log.isEnabledFor(logging.DEBUG)
        stderr = str(e)
        log.error("Error extracting git metadata: %s", stderr, exc_info=debug_mode)

    # Tags collected from CI provider take precedence over extracted git metadata, but any CI provider value
    # is None or "" should be overwritten.
    tags.update({k: v for k, v in git_info.items() if not tags.get(k)})

    user_specified_git_info = git.extract_user_git_metadata(env)

    # Tags provided by the user take precedence over everything
    tags.update({k: v for k, v in user_specified_git_info.items() if v})

    # if git.BRANCH is a tag, we associate its value to TAG instead of BRANCH
    if git.is_ref_a_tag(tags.get(git.BRANCH)):
        if not tags.get(git.TAG):
            tags[git.TAG] = git.normalize_ref(tags.get(git.BRANCH))
        else:
            tags[git.TAG] = git.normalize_ref(tags.get(git.TAG))
        del tags[git.BRANCH]
    else:
        tags[git.BRANCH] = git.normalize_ref(tags.get(git.BRANCH))
        tags[git.TAG] = git.normalize_ref(tags.get(git.TAG))

    tags[git.REPOSITORY_URL] = _filter_sensitive_info(tags.get(git.REPOSITORY_URL))

    workspace_path = tags.get(WORKSPACE_PATH)
    if workspace_path:
        tags[WORKSPACE_PATH] = os.path.expanduser(workspace_path)

    tags.update(_get_runtime_and_os_metadata())

    return {k: v for k, v in tags.items() if v is not None}


def extract_appveyor(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Appveyor environ."""
    url = "https://ci.appveyor.com/project/{0}/builds/{1}".format(
        env.get("APPVEYOR_REPO_NAME"), env.get("APPVEYOR_BUILD_ID")
    )
    if env.get("APPVEYOR_REPO_PROVIDER") == "github":
        repository = "https://github.com/{0}.git".format(env.get("APPVEYOR_REPO_NAME"))  # type: Optional[str]
        commit = env.get("APPVEYOR_REPO_COMMIT")  # type: Optional[str]
        branch = env.get("APPVEYOR_PULL_REQUEST_HEAD_REPO_BRANCH") or env.get(
            "APPVEYOR_REPO_BRANCH"
        )  # type: Optional[str]
        tag = env.get("APPVEYOR_REPO_TAG_NAME")  # type: Optional[str]
    else:
        repository = commit = branch = tag = None

    commit_message = env.get("APPVEYOR_REPO_COMMIT_MESSAGE")
    if commit_message:
        extended = env.get("APPVEYOR_REPO_COMMIT_MESSAGE_EXTENDED")
        if extended:
            commit_message += "\n" + extended

    return {
        PROVIDER_NAME: "appveyor",
        git.REPOSITORY_URL: repository,
        git.COMMIT_SHA: commit,
        WORKSPACE_PATH: env.get("APPVEYOR_BUILD_FOLDER"),
        PIPELINE_ID: env.get("APPVEYOR_BUILD_ID"),
        PIPELINE_NAME: env.get("APPVEYOR_REPO_NAME"),
        PIPELINE_NUMBER: env.get("APPVEYOR_BUILD_NUMBER"),
        PIPELINE_URL: url,
        JOB_URL: url,
        git.BRANCH: branch,
        git.TAG: tag,
        git.COMMIT_MESSAGE: commit_message,
        git.COMMIT_AUTHOR_NAME: env.get("APPVEYOR_REPO_COMMIT_AUTHOR"),
        git.COMMIT_AUTHOR_EMAIL: env.get("APPVEYOR_REPO_COMMIT_AUTHOR_EMAIL"),
    }


def extract_azure_pipelines(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Azure pipelines environ."""
    if env.get("SYSTEM_TEAMFOUNDATIONSERVERURI") and env.get("SYSTEM_TEAMPROJECTID") and env.get("BUILD_BUILDID"):
        base_url = "{0}{1}/_build/results?buildId={2}".format(
            env.get("SYSTEM_TEAMFOUNDATIONSERVERURI"), env.get("SYSTEM_TEAMPROJECTID"), env.get("BUILD_BUILDID")
        )
        pipeline_url = base_url  # type: Optional[str]
        job_url = base_url + "&view=logs&j={0}&t={1}".format(
            env.get("SYSTEM_JOBID"), env.get("SYSTEM_TASKINSTANCEID")
        )  # type: Optional[str]
    else:
        pipeline_url = job_url = None

    return {
        PROVIDER_NAME: "azurepipelines",
        WORKSPACE_PATH: env.get("BUILD_SOURCESDIRECTORY"),
        PIPELINE_ID: env.get("BUILD_BUILDID"),
        PIPELINE_NAME: env.get("BUILD_DEFINITIONNAME"),
        PIPELINE_NUMBER: env.get("BUILD_BUILDID"),
        PIPELINE_URL: pipeline_url,
        JOB_URL: job_url,
        git.REPOSITORY_URL: env.get("SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI") or env.get("BUILD_REPOSITORY_URI"),
        git.COMMIT_SHA: env.get("SYSTEM_PULLREQUEST_SOURCECOMMITID") or env.get("BUILD_SOURCEVERSION"),
        git.BRANCH: env.get("SYSTEM_PULLREQUEST_SOURCEBRANCH")
        or env.get("BUILD_SOURCEBRANCH")
        or env.get("BUILD_SOURCEBRANCHNAME"),
        git.COMMIT_MESSAGE: env.get("BUILD_SOURCEVERSIONMESSAGE"),
        git.COMMIT_AUTHOR_NAME: env.get("BUILD_REQUESTEDFORID"),
        git.COMMIT_AUTHOR_EMAIL: env.get("BUILD_REQUESTEDFOREMAIL"),
        STAGE_NAME: env.get("SYSTEM_STAGEDISPLAYNAME"),
        JOB_NAME: env.get("SYSTEM_JOBDISPLAYNAME"),
        # OrderedDict is necessary for comparing against a fixture in testing
        _CI_ENV_VARS: json.dumps(
            OrderedDict(
                [
                    ("SYSTEM_TEAMPROJECTID", env.get("SYSTEM_TEAMPROJECTID")),
                    ("BUILD_BUILDID", env.get("BUILD_BUILDID")),
                    ("SYSTEM_JOBID", env.get("SYSTEM_JOBID")),
                ]
            ),
            separators=(",", ":"),
        ),
    }


def extract_bitbucket(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Bitbucket environ."""
    url = "https://bitbucket.org/{0}/addon/pipelines/home#!/results/{1}".format(
        env.get("BITBUCKET_REPO_FULL_NAME"), env.get("BITBUCKET_BUILD_NUMBER")
    )
    return {
        git.BRANCH: env.get("BITBUCKET_BRANCH"),
        git.COMMIT_SHA: env.get("BITBUCKET_COMMIT"),
        git.REPOSITORY_URL: env.get("BITBUCKET_GIT_SSH_ORIGIN"),
        git.TAG: env.get("BITBUCKET_TAG"),
        JOB_URL: url,
        PIPELINE_ID: env.get("BITBUCKET_PIPELINE_UUID", "").strip("{}}") or None,
        PIPELINE_NAME: env.get("BITBUCKET_REPO_FULL_NAME"),
        PIPELINE_NUMBER: env.get("BITBUCKET_BUILD_NUMBER"),
        PIPELINE_URL: url,
        PROVIDER_NAME: "bitbucket",
        WORKSPACE_PATH: env.get("BITBUCKET_CLONE_DIR"),
    }


def extract_buildkite(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Buildkite environ."""
    return {
        git.BRANCH: env.get("BUILDKITE_BRANCH"),
        git.COMMIT_SHA: env.get("BUILDKITE_COMMIT"),
        git.REPOSITORY_URL: env.get("BUILDKITE_REPO"),
        git.TAG: env.get("BUILDKITE_TAG"),
        PIPELINE_ID: env.get("BUILDKITE_BUILD_ID"),
        PIPELINE_NAME: env.get("BUILDKITE_PIPELINE_SLUG"),
        PIPELINE_NUMBER: env.get("BUILDKITE_BUILD_NUMBER"),
        PIPELINE_URL: env.get("BUILDKITE_BUILD_URL"),
        JOB_URL: "{0}#{1}".format(env.get("BUILDKITE_BUILD_URL"), env.get("BUILDKITE_JOB_ID")),
        PROVIDER_NAME: "buildkite",
        WORKSPACE_PATH: env.get("BUILDKITE_BUILD_CHECKOUT_PATH"),
        git.COMMIT_MESSAGE: env.get("BUILDKITE_MESSAGE"),
        git.COMMIT_AUTHOR_NAME: env.get("BUILDKITE_BUILD_AUTHOR"),
        git.COMMIT_AUTHOR_EMAIL: env.get("BUILDKITE_BUILD_AUTHOR_EMAIL"),
        git.COMMIT_COMMITTER_NAME: env.get("BUILDKITE_BUILD_CREATOR"),
        git.COMMIT_COMMITTER_EMAIL: env.get("BUILDKITE_BUILD_CREATOR_EMAIL"),
        # OrderedDict is necessary for comparing against a fixture in testing
        _CI_ENV_VARS: json.dumps(
            OrderedDict(
                [
                    ("BUILDKITE_BUILD_ID", env.get("BUILDKITE_BUILD_ID")),
                    ("BUILDKITE_JOB_ID", env.get("BUILDKITE_JOB_ID")),
                ]
            ),
            separators=(",", ":"),
        ),
    }


def extract_circle_ci(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from CircleCI environ."""
    return {
        git.BRANCH: env.get("CIRCLE_BRANCH"),
        git.COMMIT_SHA: env.get("CIRCLE_SHA1"),
        git.REPOSITORY_URL: env.get("CIRCLE_REPOSITORY_URL"),
        git.TAG: env.get("CIRCLE_TAG"),
        PIPELINE_ID: env.get("CIRCLE_WORKFLOW_ID"),
        PIPELINE_NAME: env.get("CIRCLE_PROJECT_REPONAME"),
        PIPELINE_NUMBER: env.get("CIRCLE_BUILD_NUM"),
        PIPELINE_URL: "https://app.circleci.com/pipelines/workflows/{0}".format(env.get("CIRCLE_WORKFLOW_ID")),
        JOB_URL: env.get("CIRCLE_BUILD_URL"),
        JOB_NAME: env.get("CIRCLE_JOB"),
        PROVIDER_NAME: "circleci",
        WORKSPACE_PATH: env.get("CIRCLE_WORKING_DIRECTORY"),
        # OrderedDict is necessary for comparing against a fixture in testing
        _CI_ENV_VARS: json.dumps(
            OrderedDict(
                [
                    ("CIRCLE_WORKFLOW_ID", env.get("CIRCLE_WORKFLOW_ID")),
                    ("CIRCLE_BUILD_NUM", env.get("CIRCLE_BUILD_NUM")),
                ]
            ),
            separators=(",", ":"),
        ),
    }


def extract_github_actions(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Github environ."""

    pipeline_url = "{0}/{1}/actions/runs/{2}".format(
        env.get("GITHUB_SERVER_URL"),
        env.get("GITHUB_REPOSITORY"),
        env.get("GITHUB_RUN_ID"),
    )
    run_attempt = env.get("GITHUB_RUN_ATTEMPT")
    if run_attempt:
        pipeline_url = "{0}/attempts/{1}".format(pipeline_url, run_attempt)

    # OrderedDict is necessary for comparing against a fixture in testing
    env_vars = OrderedDict(
        [
            ("GITHUB_SERVER_URL", env.get("GITHUB_SERVER_URL")),
            ("GITHUB_REPOSITORY", env.get("GITHUB_REPOSITORY")),
            ("GITHUB_RUN_ID", env.get("GITHUB_RUN_ID")),
        ]
    )
    if env.get("GITHUB_RUN_ATTEMPT") is not None:
        env_vars["GITHUB_RUN_ATTEMPT"] = env["GITHUB_RUN_ATTEMPT"]

    return {
        git.BRANCH: env.get("GITHUB_HEAD_REF") or env.get("GITHUB_REF"),
        git.COMMIT_SHA: env.get("GITHUB_SHA"),
        git.REPOSITORY_URL: "{0}/{1}.git".format(env.get("GITHUB_SERVER_URL"), env.get("GITHUB_REPOSITORY")),
        JOB_URL: "{0}/{1}/commit/{2}/checks".format(
            env.get("GITHUB_SERVER_URL"), env.get("GITHUB_REPOSITORY"), env.get("GITHUB_SHA")
        ),
        PIPELINE_ID: env.get("GITHUB_RUN_ID"),
        PIPELINE_NAME: env.get("GITHUB_WORKFLOW"),
        PIPELINE_NUMBER: env.get("GITHUB_RUN_NUMBER"),
        PIPELINE_URL: pipeline_url,
        JOB_NAME: env.get("GITHUB_JOB"),
        PROVIDER_NAME: "github",
        WORKSPACE_PATH: env.get("GITHUB_WORKSPACE"),
        # OrderedDict is necessary for comparing against a fixture in testing
        _CI_ENV_VARS: json.dumps(env_vars, separators=(",", ":")),
    }


def extract_gitlab(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Gitlab environ."""
    author = env.get("CI_COMMIT_AUTHOR")
    author_name = None  # type: Optional[str]
    author_email = None  # type: Optional[str]
    if author:
        # Extract name and email from `author` which is in the form "name <email>"
        author_name, author_email = author.strip("> ").split(" <")
    commit_timestamp = env.get("CI_COMMIT_TIMESTAMP")
    url = env.get("CI_PIPELINE_URL")
    if url:
        url = re.sub("/-/pipelines/", "/pipelines/", url)
    return {
        git.BRANCH: env.get("CI_COMMIT_REF_NAME"),
        git.COMMIT_SHA: env.get("CI_COMMIT_SHA"),
        git.REPOSITORY_URL: env.get("CI_REPOSITORY_URL"),
        git.TAG: env.get("CI_COMMIT_TAG"),
        STAGE_NAME: env.get("CI_JOB_STAGE"),
        JOB_NAME: env.get("CI_JOB_NAME"),
        JOB_URL: env.get("CI_JOB_URL"),
        PIPELINE_ID: env.get("CI_PIPELINE_ID"),
        PIPELINE_NAME: env.get("CI_PROJECT_PATH"),
        PIPELINE_NUMBER: env.get("CI_PIPELINE_IID"),
        PIPELINE_URL: url,
        PROVIDER_NAME: "gitlab",
        WORKSPACE_PATH: env.get("CI_PROJECT_DIR"),
        git.COMMIT_MESSAGE: env.get("CI_COMMIT_MESSAGE"),
        git.COMMIT_AUTHOR_NAME: author_name,
        git.COMMIT_AUTHOR_EMAIL: author_email,
        git.COMMIT_AUTHOR_DATE: commit_timestamp,
        # OrderedDict is necessary for comparing against a fixture in testing
        _CI_ENV_VARS: json.dumps(
            OrderedDict(
                [
                    ("CI_PROJECT_URL", env.get("CI_PROJECT_URL")),
                    ("CI_PIPELINE_ID", env.get("CI_PIPELINE_ID")),
                    ("CI_JOB_ID", env.get("CI_JOB_ID")),
                ]
            ),
            separators=(",", ":"),
        ),
    }


def extract_jenkins(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Jenkins environ."""
    branch = env.get("GIT_BRANCH", "")
    name = env.get("JOB_NAME")
    if name and branch:
        name = re.sub("/{0}".format(git.normalize_ref(branch)), "", name)
    if name:
        name = "/".join((v for v in name.split("/") if v and "=" not in v))

    return {
        git.BRANCH: env.get("GIT_BRANCH"),
        git.COMMIT_SHA: env.get("GIT_COMMIT"),
        git.REPOSITORY_URL: env.get("GIT_URL", env.get("GIT_URL_1")),
        PIPELINE_ID: env.get("BUILD_TAG"),
        PIPELINE_NAME: name,
        PIPELINE_NUMBER: env.get("BUILD_NUMBER"),
        PIPELINE_URL: env.get("BUILD_URL"),
        PROVIDER_NAME: "jenkins",
        WORKSPACE_PATH: env.get("WORKSPACE"),
        # OrderedDict is necessary for comparing against a fixture in testing
        _CI_ENV_VARS: json.dumps(
            OrderedDict(
                [
                    ("DD_CUSTOM_TRACE_ID", env.get("DD_CUSTOM_TRACE_ID")),
                ]
            ),
            separators=(",", ":"),
        ),
    }


def extract_teamcity(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Teamcity environ."""
    return {
        git.COMMIT_SHA: env.get("BUILD_VCS_NUMBER"),
        git.REPOSITORY_URL: env.get("BUILD_VCS_URL"),
        PIPELINE_ID: env.get("BUILD_ID"),
        PIPELINE_NUMBER: env.get("BUILD_NUMBER"),
        PIPELINE_URL: (
            "{0}/viewLog.html?buildId={1}".format(env.get("SERVER_URL"), env.get("BUILD_ID"))
            if env.get("SERVER_URL") and env.get("BUILD_ID")
            else None
        ),
        PROVIDER_NAME: "teamcity",
        WORKSPACE_PATH: env.get("BUILD_CHECKOUTDIR"),
    }


def extract_travis(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Travis environ."""
    return {
        git.BRANCH: env.get("TRAVIS_PULL_REQUEST_BRANCH") or env.get("TRAVIS_BRANCH"),
        git.COMMIT_SHA: env.get("TRAVIS_COMMIT"),
        git.REPOSITORY_URL: "https://github.com/{0}.git".format(env.get("TRAVIS_REPO_SLUG")),
        git.TAG: env.get("TRAVIS_TAG"),
        JOB_URL: env.get("TRAVIS_JOB_WEB_URL"),
        PIPELINE_ID: env.get("TRAVIS_BUILD_ID"),
        PIPELINE_NAME: env.get("TRAVIS_REPO_SLUG"),
        PIPELINE_NUMBER: env.get("TRAVIS_BUILD_NUMBER"),
        PIPELINE_URL: env.get("TRAVIS_BUILD_WEB_URL"),
        PROVIDER_NAME: "travisci",
        WORKSPACE_PATH: env.get("TRAVIS_BUILD_DIR"),
        git.COMMIT_MESSAGE: env.get("TRAVIS_COMMIT_MESSAGE"),
    }


def extract_bitrise(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Bitrise environ."""
    commit = env.get("BITRISE_GIT_COMMIT") or env.get("GIT_CLONE_COMMIT_HASH")
    branch = env.get("BITRISEIO_GIT_BRANCH_DEST") or env.get("BITRISE_GIT_BRANCH")
    if env.get("BITRISE_GIT_MESSAGE"):
        message = env.get("BITRISE_GIT_MESSAGE")  # type: Optional[str]
    elif env.get("GIT_CLONE_COMMIT_MESSAGE_SUBJECT") or env.get("GIT_CLONE_COMMIT_MESSAGE_BODY"):
        message = "{0}:\n{1}".format(
            env.get("GIT_CLONE_COMMIT_MESSAGE_SUBJECT"), env.get("GIT_CLONE_COMMIT_MESSAGE_BODY")
        )
    else:
        message = None

    return {
        PROVIDER_NAME: "bitrise",
        PIPELINE_ID: env.get("BITRISE_BUILD_SLUG"),
        PIPELINE_NAME: env.get("BITRISE_TRIGGERED_WORKFLOW_ID"),
        PIPELINE_NUMBER: env.get("BITRISE_BUILD_NUMBER"),
        PIPELINE_URL: env.get("BITRISE_BUILD_URL"),
        WORKSPACE_PATH: env.get("BITRISE_SOURCE_DIR"),
        git.REPOSITORY_URL: env.get("GIT_REPOSITORY_URL"),
        git.COMMIT_SHA: commit,
        git.BRANCH: branch,
        git.TAG: env.get("BITRISE_GIT_TAG"),
        git.COMMIT_MESSAGE: message,
        git.COMMIT_AUTHOR_NAME: env.get("GIT_CLONE_COMMIT_AUTHOR_NAME"),
        git.COMMIT_AUTHOR_EMAIL: env.get("GIT_CLONE_COMMIT_AUTHOR_EMAIL"),
        git.COMMIT_COMMITTER_NAME: env.get("GIT_CLONE_COMMIT_COMMITER_NAME"),
        git.COMMIT_COMMITTER_EMAIL: env.get("GIT_CLONE_COMMIT_COMMITER_NAME"),
    }


def extract_buddy(env):
    # type: (MutableMapping[str, str]) -> Dict[str, Optional[str]]
    """Extract CI tags from Buddy environ."""
    return {
        PROVIDER_NAME: "buddy",
        PIPELINE_ID: "{0}/{1}".format(env.get("BUDDY_PIPELINE_ID"), env.get("BUDDY_EXECUTION_ID")),
        PIPELINE_NAME: env.get("BUDDY_PIPELINE_NAME"),
        PIPELINE_NUMBER: env.get("BUDDY_EXECUTION_ID"),
        PIPELINE_URL: env.get("BUDDY_EXECUTION_URL"),
        git.REPOSITORY_URL: env.get("BUDDY_SCM_URL"),
        git.COMMIT_SHA: env.get("BUDDY_EXECUTION_REVISION"),
        git.BRANCH: env.get("BUDDY_EXECUTION_BRANCH"),
        git.TAG: env.get("BUDDY_EXECUTION_TAG"),
        git.COMMIT_MESSAGE: env.get("BUDDY_EXECUTION_REVISION_MESSAGE"),
        git.COMMIT_COMMITTER_NAME: env.get("BUDDY_EXECUTION_REVISION_COMMITTER_NAME"),
        git.COMMIT_COMMITTER_EMAIL: env.get("BUDDY_EXECUTION_REVISION_COMMITTER_EMAIL"),
    }


PROVIDERS = (
    ("APPVEYOR", extract_appveyor),
    ("TF_BUILD", extract_azure_pipelines),
    ("BITBUCKET_COMMIT", extract_bitbucket),
    ("BUILDKITE", extract_buildkite),
    ("CIRCLECI", extract_circle_ci),
    ("GITHUB_SHA", extract_github_actions),
    ("GITLAB_CI", extract_gitlab),
    ("JENKINS_URL", extract_jenkins),
    ("TEAMCITY_VERSION", extract_teamcity),
    ("TRAVIS", extract_travis),
    ("BITRISE_BUILD_SLUG", extract_bitrise),
    ("BUDDY", extract_buddy),
)
