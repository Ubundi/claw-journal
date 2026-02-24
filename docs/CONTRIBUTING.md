# Contributing to Claw Journal

First off, thank you for considering contributing to Claw Journal! It's people like you that make Claw Journal such a great tool.

## Where do I go from here?

If you've noticed a bug or have a feature request, make one! It's generally best if you get confirmation of your bug or approval for your feature request this way before starting to code.

If you have a general question about Claw Journal, you can post it on our Discord or GitHub Discussions.

## Fork & create a branch

If this is something you think you can fix, then fork Claw Journal and create a branch with a descriptive name.

A good branch name would be (where issue #325 is the ticket you're working on):

```sh
git checkout -b 325-add-new-feature
```

## Get the test suite running

Make sure you have Python 3.9+ installed.

```sh
# Create a virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Implement your fix or feature

At this point, you're ready to make your changes. Feel free to ask for help; everyone is a beginner at first.

### Code Style Guidelines

- **Type Hints**: Always use strict type hints for function arguments and return values.
  - Use modern syntax: `list[str] | None` instead of `List[str], Optional[str]`.
  - Always include `from __future__ import annotations` at the top of every file.
- **Dataclasses**: Prefer standard library `@dataclass` for internal data structures over Pydantic or raw dictionaries.
- **Imports**: Organize imports: standard library first, then third-party, then local application imports.
- **Database Access**: Write raw SQL queries. Do NOT introduce an ORM.

## Make a Pull Request

At this point, you should switch back to your master branch and make sure it's up to date with Claw Journal's master branch:

```sh
git remote add upstream git@github.com:Ubundi/claw-journal.git
git checkout main
git pull upstream main
```

Then update your feature branch from your local copy of master, and push it!

```sh
git checkout 325-add-new-feature
git rebase main
git push --set-upstream origin 325-add-new-feature
```

Finally, go to GitHub and make a Pull Request :D
