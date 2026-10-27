# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
from unittest import mock

import pytest

from mozphab.exceptions import Error
from mozphab.jujutsu import Jujutsu


@pytest.fixture
def jj():
    """A bare `Jujutsu` instance, without touching a real repo.

    The colocated Git backend is replaced with a `Mock` so delegation to it
    can be asserted directly.
    """
    jj = object.__new__(Jujutsu)
    jj._Jujutsu__git_repo = mock.Mock()  # type: ignore
    jj._Jujutsu__patch_base = ""  # type: ignore
    jj._Jujutsu__patch_tip = ""  # type: ignore
    jj._Jujutsu__patch_name = None  # type: ignore
    return jj


@pytest.mark.parametrize(
    "method,args,kwargs,return_value",
    (
        ("get_public_node", ("git_sha",), {}, "hg_sha"),
        ("is_public", ("sha111",), {}, True),
        ("get_latest_landing_node", (), {"before": 1547806078}, "landing_sha"),
    ),
)
def test_delegates_to_git(jj, method, args, kwargs, return_value):
    git_method = getattr(jj._Jujutsu__git_repo, method)
    git_method.return_value = return_value

    assert getattr(jj, method)(*args, **kwargs) == return_value
    git_method.assert_called_once_with(*args, **kwargs)


def test_set_args_shares_args_with_git_repo(jj):
    """The wrapped Git repo reads args (e.g. `upstream`) for `get_latest_landing_node`."""
    args = argparse.Namespace(upstream=None)

    jj.set_args(args)

    assert jj._Jujutsu__git_repo.args is args


def test_patch_commits_and_rebases_with_git(jj):
    git_repo = jj._Jujutsu__git_repo
    git_repo.commit_patch.side_effect = ("commit1", "commit2")
    git_repo.rebase_commits.return_value = "rebased2"

    jj.before_patch("base", "phab-D1")
    jj.apply_patch("diff1", "body1", "user <a@b.c>", 1)
    jj.apply_patch("diff2", "body2", None, None)
    jj.rebase_node("base", "dest")

    assert git_repo.commit_patch.call_args_list == [
        mock.call("base", "diff1", "body1", "user <a@b.c>", 1),
        mock.call("commit1", "diff2", "body2", None, None),
    ]
    git_repo.rebase_commits.assert_called_once_with("base", "commit2", "dest")
    assert jj._Jujutsu__patch_tip == "rebased2"
    assert jj._Jujutsu__patch_base == "dest"


@pytest.mark.parametrize("no_branch", [False, True])
@mock.patch("mozphab.jujutsu.uuid.uuid4", return_value=mock.Mock(hex="abc"))
@mock.patch.object(Jujutsu, "_Jujutsu__check_output", return_value=["phab-D1"])
@mock.patch("mozphab.jujutsu.check_call")
def test_after_patch_imports_and_checks_out_commits(
    m_check_call, m_check_output, m_uuid4, jj, no_branch
):
    jj.args = argparse.Namespace(no_branch=no_branch)
    jj._Jujutsu__patch_base = "base"
    jj._Jujutsu__patch_tip = "tip"
    jj._Jujutsu__patch_name = "phab-D1"

    jj.after_patch()

    ref_name = "mozphab-patch-abc" if no_branch else "phab-D1_1"
    jj._Jujutsu__git_repo.git_call.assert_called_once_with(
        ["update-ref", f"refs/heads/{ref_name}", "tip"]
    )
    expected = [
        mock.call(["jj", "git", "import", "--quiet"]),
        mock.call(["jj", "new", "--quiet", "tip"]),
    ]
    if no_branch:
        expected += [
            mock.call(["jj", "bookmark", "delete", "--quiet", ref_name]),
            mock.call(["jj", "git", "export", "--quiet"]),
        ]
    assert m_check_call.call_args_list == expected


@mock.patch("mozphab.jujutsu.check_call")
def test_after_patch_without_commits(m_check_call, jj):
    jj.args = argparse.Namespace(no_branch=False)
    jj._Jujutsu__patch_base = jj._Jujutsu__patch_tip = "base"

    jj.after_patch()

    jj._Jujutsu__git_repo.git_call.assert_not_called()
    m_check_call.assert_called_once_with(["jj", "new", "--quiet", "base"])


@mock.patch.object(Jujutsu, "_Jujutsu__cli_log_text")
def test_get_current_node_queries_working_copy_commit(m_cli_log_text, jj):
    m_cli_log_text.return_value = "wc_commit_id"

    assert jj.get_current_node() == "wc_commit_id"
    m_cli_log_text.assert_called_once_with(template='commit_id ++ "\\n"', revset="@")


@mock.patch.object(Jujutsu, "_Jujutsu__cli_log_text")
def test_commit_stack_raises_on_change_with_no_description(m_cli_log_text, jj):
    jj.revset = ("start_id", "end_id")

    log_line = "\n".join(
        [
            "2024-01-01T00:00:00+00:00",
            "Author Name",
            "author@example.com",
            "parent_commit_id",
            "change_id",
            "commit_id",
            "false",
            "",
        ]
    )

    # "0" * 37 required because in commit_stack, the log is trimmed with
    # log = self.__cli_log_text(...)[: -len(boundary)]. Without it we would
    # consume the log line.
    #
    # boundary = "--%s--\n" % uuid.uuid4().hex which adds up to:
    # 2 (--)  + 32 (hex uuid) + 2 (--) + 1 (\n) = 37 characters.
    m_cli_log_text.return_value = log_line + "0" * 37

    with pytest.raises(Error) as excinfo:
        jj.commit_stack()

    assert str(excinfo.value) == (
        "Change change_id has no description set, unable to continue. "
        "Run `jj describe -r change_id` and provide a commit message."
    )
