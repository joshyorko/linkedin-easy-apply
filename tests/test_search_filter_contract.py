import ast
from pathlib import Path

import pytest
from actions import ActionError
from linkedin.search_actions.filters import _apply_search_filters
from playwright.sync_api import Error as PlaywrightError

SEARCH_ACTIONS = Path(__file__).parents[1] / "src" / "linkedin" / "search_actions"


class FakeLocator:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind

    @property
    def first(self):
        return self

    def count(self):
        return 0 if self.kind == "unsupported" else 1

    def click(self, **_kwargs):
        if self.kind == "unsupported":
            raise PlaywrightError("synthetic selector did not match")
        self.page.events.append(("click", self.kind))
        if self.kind == "easy_apply":
            self.page.easy_apply_clicks += 1
            if self.page.confirm_easy_apply:
                self.page.url = "https://www.linkedin.com/jobs/search/?f_AL=true"

    def get_attribute(self, name):
        if name == "aria-checked" and self.kind == "easy_apply":
            return "false"
        return None

    def is_checked(self):
        return False

    def filter(self, **_kwargs):
        return self

    def locator(self, selector):
        self.page.events.append(("nested-locator", selector))
        return FakeLocator(self.page, "other")

    def get_by_text(self, text, **_kwargs):
        self.page.events.append(("nested-text", text))
        return FakeLocator(self.page, "other")

    def get_by_role(self, role, **_kwargs):
        self.page.events.append(("nested-role", role))
        return FakeLocator(self.page, "other")


class FakePage:
    def __init__(self, *, confirm_easy_apply=False):
        self.confirm_easy_apply = confirm_easy_apply
        self.easy_apply_clicks = 0
        self.events = []
        self.url = "https://www.linkedin.com/jobs/search/"

    def get_by_role(self, role, name=None):
        self.events.append(("role", role, name))
        if name and "Easy Apply" in name:
            return FakeLocator(self, "easy_apply")
        if name in {"Show all filters. Clicking", "Show all filters", "All filters"}:
            return FakeLocator(self, "open_filters")
        return FakeLocator(self, "unsupported")

    def get_by_label(self, label, **_kwargs):
        self.events.append(("label", label))
        return FakeLocator(self, "filter_container")

    def locator(self, selector):
        self.events.append(("locator", selector))
        if "easyApply" in selector or "Easy Apply" in selector:
            return FakeLocator(self, "easy_apply")
        return FakeLocator(self, "unsupported")

    def get_by_text(self, text, **_kwargs):
        self.events.append(("text", text))
        return FakeLocator(self, "easy_apply" if "Easy Apply" in text else "unsupported")


def _load_action_function(path, name):
    tree = ast.parse((SEARCH_ACTIONS / path).read_text())
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_default_filtering_never_touches_easy_apply():
    apply_filters = _apply_search_filters
    page = FakePage()

    filters = apply_filters(
        page,
        easy_apply_only=False,
        remote=False,
        hybrid=False,
        onsite=False,
    )

    assert filters == {
        "remote": False,
        "hybrid": False,
        "onsite": False,
        "easy_apply_only": False,
        "active": {
            "remote": False,
            "hybrid": False,
            "onsite": False,
            "easy_apply_only": False,
        },
    }
    assert page.easy_apply_clicks == 0
    assert not any("easy" in str(event).lower() for event in page.events)


def test_easy_apply_filter_attempts_toggle_and_requires_confirmation():
    apply_filters = _apply_search_filters
    page = FakePage(confirm_easy_apply=True)

    filters = apply_filters(
        page,
        easy_apply_only=True,
        remote=True,
        hybrid=False,
        onsite=False,
    )

    assert page.easy_apply_clicks == 1
    assert filters["easy_apply_only"] is True
    assert filters["remote"] is True
    assert filters["active"] == {
        "remote": False,
        "hybrid": False,
        "onsite": False,
        "easy_apply_only": True,
    }


def test_easy_apply_filter_fails_when_not_confirmed():
    apply_filters = _apply_search_filters

    with pytest.raises(ActionError, match="Easy Apply.*confirm"):
        apply_filters(
            FakePage(confirm_easy_apply=False),
            easy_apply_only=True,
            remote=False,
            hybrid=False,
            onsite=False,
        )


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("search.py", "search_linkedin_easy_apply"),
        ("parallel_search.py", "parallel_search_linkedin_easy_apply"),
    ],
)
def test_search_actions_keep_public_names_and_add_defaulted_filter(path, name):
    action = _load_action_function(path, name)
    parameters = {parameter.arg: parameter for parameter in action.args.args}

    assert name in {"search_linkedin_easy_apply", "parallel_search_linkedin_easy_apply"}
    assert "easy_apply_only" in parameters
    default = dict(zip([arg.arg for arg in action.args.args[-len(action.args.defaults):]], action.args.defaults))["easy_apply_only"]
    assert isinstance(default, ast.Constant) and default.value is True

    helper_calls = [
        node
        for node in ast.walk(action)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_apply_search_filters"
    ]
    assert len(helper_calls) == 1
    keyword_names = {keyword.arg for keyword in helper_calls[0].keywords}
    assert keyword_names >= {
        "easy_apply_only",
        "remote",
        "hybrid",
        "onsite",
    }


@pytest.mark.parametrize("path", ["search.py", "parallel_search.py"])
def test_search_actions_preserve_all_jobs_and_easy_apply_subset(path):
    source = (SEARCH_ACTIONS / path).read_text()

    assert "job_ids_found=successful_job_ids" in source
    assert "easy_apply_job_ids=easy_apply_job_ids" in source
    assert "pending_enrichment_job_ids=easy_apply_job_ids" in source
    assert "easy_apply_only" in source
    assert 'filters=active_filters["active"]' in source
    assert "active_filters" in source
