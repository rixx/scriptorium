# Testing

This guide is lifted from pretalx's contributor docs. Scriptorium is a much
smaller project, but the same philosophy applies: tests are documentation,
tests are fast, and tests verify behaviour. The wording below is preserved
verbatim from the source; sections that talk about pretalx-specific
infrastructure (event fixtures, scopes middleware, DRF, Celery, etc.) are
omitted because they don't exist here.

## Philosophy

Our CI gate is [100% test coverage](https://jml.io/galahad-principle/).
This is a forcing function, not a goal in itself — coverage without meaningful
assertions is worse than no coverage because it creates false confidence. Every
test verifies **behaviour**, not just that code runs without exceptions.

Tests are documentation. A developer reading a test should understand what the
code under test is supposed to do, including edge cases. Docstrings explaining
*why* a test exists and *why* it's set up a particular way are welcome,
especially for non-obvious arrangements — but a test called
`test_dictionary_not_empty` does not need a docstring that says
`"""Make sure the dictionary is not empty."""`.

Tests are fast. Slow tests don't get run locally.

## Testing layers

We separate our tests into three layers: *Unit tests*, *Integration tests* and
*End-to-End tests*.

**Unit tests:** Every function, method, property, or class has at least one
test or one parameterisation per exit condition. This includes particularly
models, forms, serializers, and all service and utility methods.

Unit testing for views is more tricky: we *include* methods and properties on
view classes that do not handle the actual request/response flow, except
trivial `@context` decorated properties. We *exclude* the request/response
handlers on view classes as well as plain view functions, as we test these in
integration tests. We use `RequestFactory` instances to replace requests in
unit tests (as opposed to the pytest `client` fixture in integration tests).

**Integration tests:** Every view has at least one integration test covering
the happy path, using the various `client` fixtures. Integration tests make
sure that views work in their full context of middlewares, rendering, routing,
etc.

**End-to-end tests:** Multi-step user flows that cross view boundaries, still
using pytest and the Django test client (no browser automation). These encode
the critical paths through pretalx — like the CfP submission process, event
creation, sending and accepting invites, building and releasing schedules, and
so on — by calling multiple views in sequence and following the resulting
redirects and state changes. These tests are expected to be slower than unit or
even integration tests.

## Assertion quality

**Every test asserts something meaningful about the system's behaviour.**
Checking only `response.status_code == 200` does not count.

When we test for a negative — for example, data that is *not* leaking — we
make sure there is data that *could* leak.

View tests assert at least one of:

- Response context contains the expected data
  (`assert response.context['form'].instance == expected_obj`)
- Database state changed as expected
  (`assert Submission.objects.filter(state='accepted').count() == 1`, plus
  checking that the accepted submission is the one that **should** be accepted)
- The correct template was used
  (`assert 'agenda/schedule.html' in [t.name for t in response.templates]`)
  if the view does complex template handling rather than having a fixed template
  assigned
- Redirects go to the right place with the right state
  (`assert response.url == expected_url`)
- Response body contains expected content for API views
  (`assert response.json()['results'][0]['title'] == expected`)

Model/method tests assert:

- Return values match expected output for given input
- Side effects occurred (objects created, signals sent, state changed)
- Edge cases are handled (empty inputs, boundary values, `None` where
  applicable)
- Exceptions are raised for invalid states
  (`with pytest.raises(SpecificException):`)

Form tests assert:

- `form.is_valid()` returns the expected boolean *and* `form.errors`
  contains the specific field and error
- `form.save()` creates/modifies the correct objects with the correct field
  values
- If choice fields have complex setups for the available options, the choices
  match expectations (e.g. only including objects the user is permitted to see)

**We prefer equality over membership checks.** Membership checks (`in`) hide
unexpected extras — we use `==` on lists or sets instead:

```python
# Bad – passes even if other users snuck in
assert user in mail.to_users.all()

# Good – verifies the exact set
assert list(mail.to_users.all()) == [user]
assert set(mail.submissions.all()) == {sub1, sub2}
```

The same applies to dicts and strings — we compare the full value, not just a
fragment. When full equality is unwieldy, we compare the important fields
individually with `==`.

**Anti-patterns:**

- `assert response.status_code == 200` as the sole assertion (unless
  explicitly testing permission/routing *only*, with a separate test for the
  behaviour)
- `assert obj is not None` or similar existence checks without checking
  *what* the object is
- Testing implementation details (e.g. asserting a specific SQL query) rather
  than behaviour
- Exact string matching on error messages — we match on error code or field
  name instead. If there is not enough structural data to do so, that's a sign
  to improve the structure.
- Asserting that another method was called — we test results, not call graphs.
- Unnecessary database saves — we avoid `save()` in unit tests when we can.
- Mocks and monkeypatches — we use real factories and `RequestFactory` instead.

In the rare case that a line truly cannot be covered, we mark it with
`pragma: no cover` and a comment explaining why.

## Test layout

Tests live in `src/tests/`, split into Django apps. Inside each app, the
tests are further split along the code structure and are named to match the
file they test. For example, the views in
`src/pretalx/agenda/views/talk.py` are tested in
`src/tests/agenda/views/test_talk.py`.

Test files are marked with their testing layer at the top of the file,
directly after imports, e.g. `pytestmark = pytest.mark.unit`, with possible
values being `unit`, `integration` and `e2e`.

When a directory contains tests at multiple layers (most commonly `views/`),
we use subdirectories named after the layer instead of filename suffixes:
`src/tests/agenda/views/unit/test_talk.py` and
`src/tests/agenda/views/integration/test_talk.py` rather than
`test_talk.py` and `test_talk_integration.py`. This keeps filenames clean
and makes it easy to run an entire layer at once
(`just test src/tests/agenda/views/integration/`).

Test functions are named `test_<thing>_<condition_or_behaviour>`:

- `test_slot_overlaps_when_same_room_and_time`
- `test_cfp_submit_without_permission_returns_403`
- `test_schedule_release_sends_speaker_notifications`

Not beautiful, but consistent, predictable, and friendly both for grep and for
running selected tests with `-k`. We do not use test classes — all tests are
top-level functions.

We use the Arrange/Act/Assert pattern for organising code within a test.
Visually separate the three sections with blank lines when the test is longer
than a few lines.

## Tooling

[pytest](https://docs.pytest.org/) as the test runner and
[coverage.py](https://coverage.readthedocs.io/) for
coverage tracking. 100% coverage is required for CI to pass.

[FactoryBoy](https://factoryboy.readthedocs.io/) for model factories. All
factories live in `tests/factories/` and are importable from
`tests.factories`. Every model that appears in tests has a factory.
Factories produce minimal valid instances — we don't set optional fields unless
the factory's purpose requires it.

[pytest-django](https://pytest-django.readthedocs.io/) bridges pytest and
Django, exposing `client`, `rf` (RequestFactory), `admin_client`, `db`,
`transactional_db` etc. as fixtures, and importantly
`pytest.mark.django_db`. We also use Django testing helpers like
`django.test.override_settings` or `django.core.mail.outbox` (as
`djmail.outbox`).

**pytest fixtures** for composing test setups. Complex arrangements (e.g. an
event with a CfP, three submissions in different states, and a partial
schedule) live as fixtures in `conftest.py` at the appropriate level. For
example, we use fixtures for a base `event` object that requires a lot of
other objects to get set up. We do **not** use fixtures to wrap a single
factory call — those go directly in the test. `conftest.py` fixtures are
reserved for setups that involve multiple objects, relationships, or teardown
logic, or that are used very frequently across many tests.

## Parametrisation

We use `pytest.mark.parametrize` to collapse related scenarios into a single
test function rather than writing near-duplicate tests. If two tests share the
same arrange/act structure and only differ in inputs and expected outputs, they
become one parametrized test. If the *setup* differs significantly between
cases, they stay separate.

## N+1 query prevention

List views and other views that render collections are parameterised with
`item_count` values of **1 and 3** and wrapped in
`django_assert_num_queries` with a literal integer. This ensures the query
count stays constant regardless of data size — when a middleware, signal, or
queryset change adds queries, the test breaks early.

## Running tests

Run tests with:

```
just test
```

Standard pytest flags all work:

- `just test -k <pattern>`: run only tests matching a name pattern. Working
  on CfP views? `just test -k cfp_submit`.
- `just test --lf`: re-run only tests that failed last time.
- `just test -x`: stop at first failure.
- `just test --no-header -rN`: minimal output, useful when running the full
  suite.
- `just test tests/schedule/`: run all tests for one app.
- `just test -m "not e2e"`: run all tests except for e2e tests.

> For faster runs, `just test-parallel` uses multiple CPU cores (with
> an optional `NUM` parameter to specify the number of threads, or
> leave empty for an automatic choice).
