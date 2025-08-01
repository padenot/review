# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock

from mozphab.jujutsu import Jujutsu


def _jj_instance():
    """Build a bare `Jujutsu` instance, without touching a real repo.

    The colocated Git backend is replaced with a `Mock` so delegation to it
    can be asserted directly.
    """
    jj = object.__new__(Jujutsu)
    jj._Jujutsu__git_repo = mock.Mock()
    return jj


def test_get_public_node_delegates_to_git():
    jj = _jj_instance()
    jj._Jujutsu__git_repo.get_public_node.return_value = "hg_sha"

    assert jj.get_public_node("git_sha") == "hg_sha"
    jj._Jujutsu__git_repo.get_public_node.assert_called_once_with("git_sha")


def test_is_public_delegates_to_git():
    jj = _jj_instance()
    jj._Jujutsu__git_repo.is_public.return_value = True

    assert jj.is_public("sha111") is True
    jj._Jujutsu__git_repo.is_public.assert_called_once_with("sha111")


def test_get_latest_landing_node_delegates_to_git():
    jj = _jj_instance()
    jj._Jujutsu__git_repo.get_latest_landing_node.return_value = "landing_sha"

    assert jj.get_latest_landing_node(before=1547806078) == "landing_sha"
    jj._Jujutsu__git_repo.get_latest_landing_node.assert_called_once_with(
        before=1547806078
    )


@mock.patch.object(Jujutsu, "_Jujutsu__cli_log")
def test_get_current_node_queries_working_copy_commit(m_cli_log):
    m_cli_log.return_value = "wc_commit_id"
    jj = _jj_instance()

    assert jj.get_current_node() == "wc_commit_id"
    m_cli_log.assert_called_once_with(
        template='commit_id ++ "\\n"', revset="@", split=False
    )
