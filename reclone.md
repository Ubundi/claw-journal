# Re-clone / Resync Guide (after history rewrite)

If repository history was rewritten (for example with BFG or `git filter-repo`), old local clones will diverge and may still contain removed sensitive data.

## Recommended: fresh clone

```bash
git clone https://github.com/Ubundi/claw-journal.git
cd claw-journal
```

## Alternative: hard reset existing clone

Use this only if you understand it will discard local uncommitted work.

```bash
git fetch origin --prune
git checkout main
git reset --hard origin/main
git clean -fd
```

## Remove old unreachable objects locally

Even after reset, old objects can remain in your local `.git` database until GC.

```bash
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

## Verify sync state

```bash
git status
git rev-parse HEAD
git rev-parse origin/main
```

`HEAD` and `origin/main` should match.

## Important team note

If anyone pushed branches based on pre-rewrite history, they should:

1. Create a patch/cherry-pick from needed commits.
2. Rebase/cherry-pick onto the new `main`.
3. Avoid merging old-history branches directly.
