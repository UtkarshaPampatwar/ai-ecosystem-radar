Follow the TDD workflow below for the feature or change described in $ARGUMENTS.

## Step 1 — Understand the unit under test

Before writing any code:
- Read the relevant source file(s) to understand existing behaviour
- Read `tests/conftest.py` to understand available fixtures
- Identify which test class the new tests belong to (or whether a new class is needed)
- State clearly: what is the unit, what are the inputs, what are the expected outputs

## Step 2 — Write failing tests first (Red)

Write tests in `tests/test_scrapers.py` (or the appropriate test file) **before** touching
implementation code.

Rules:
- `from __future__ import annotations` at the top of every test file
- Full type annotations on every function signature and local variable
- Name tests as `test_<unit>_<condition>_<expected_result>`
- Every test docstring must follow the format:
  `Given [starting state], when [action], then [outcome and why it matters].`
- The test body is plain code — no `# Given / # When / # Then` comments in the body
- One logical assertion per test (or a tight group of assertions about the same thing)
- Use the `make_item` fixture from `conftest.py` for `RawItem` instances — never construct inline
- **Never use `monkeypatch`** — always use `mock.patch.object`, `MagicMock`, `AsyncMock`
- Async methods must always use `AsyncMock`, never `MagicMock`
- **All imports at the top of the file** — never inside a function or class (PEP 8 / ruff E402)

```python
@pytest.mark.asyncio
async def test_proxy_service_mentioning_model_names_is_tool_not_model(
    self, make_item: Callable[..., RawItem]
) -> None:
    """Given a relay/proxy repo whose description lists supported model names,
    when classified, it must be TOOL not MODEL so that proxy services don't
    pollute the model feed."""
    from pipeline.classify import classify_items

    # Given
    items: list[RawItem] = [
        make_item(
            url="https://github.com/example/ai-relay",
            description="Relay proxy supporting Claude, GPT-4, and Gemini.",
            source=Source.GITHUB_TRENDING,
        )
    ]

    # When
    result: list[ScoredItem] = await classify_items(items, {})

    # Then
    assert result[0].category == Category.TOOL
```

Run `poe test` and confirm the new tests **fail** before proceeding.

## Step 3 — Implement (Green)

Write the minimum code needed to make the failing tests pass. Do not add anything
beyond what the tests require.

- Follow existing patterns in the file being modified
- No new files unless absolutely necessary
- No error handling for scenarios the tests don't cover
- Run `poe test` after each logical change

## Step 4 — Verify all tests pass

```bash
poe test
```

All tests must be green. If any existing test broke, fix the implementation —
never weaken or delete an existing test.

## Step 5 — Format and lint

```bash
poe format   # sort imports + ruff format
poe lint     # ruff check — must be zero errors
```

## Step 6 — Review checklist

- [ ] New tests are in the correct class and follow the naming convention
- [ ] Every new test has a Given/When/Then docstring
- [ ] No test is skipped or marked `xfail` without an explanatory comment
- [ ] No implementation code was added that isn't covered by a new test
- [ ] `poe test` is green
- [ ] `poe lint` is clean
- [ ] Full type annotations present on all new code
