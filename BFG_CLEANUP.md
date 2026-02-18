# BFG Cleanup Candidates

The following files are (or were likely) generated, test, or runtime artifacts that may contain sensitive data (tokens, usage details, or session information). They should be considered for removal from the existing Git history using tools like BFG Repo-Cleaner or `git filter-repo`.

## File paths to purge from history

- data/test_baseline.db
- data/test_local.db
- data/test_envelope.db
- data/test_remote_sync.db

> Before running BFG/filter-repo, verify these paths are (or were) committed with `git log -- data/<file>.db` and adjust as needed.

## Mandatory pre-OSS history rewrite workflow

Run these steps from a fresh clone (or a clean working tree) before making the repository public.

### 1) Safety checks

```bash
git status --porcelain
git branch --show-current
git fetch origin
```

If `git status` is not clean, commit or stash first.

### 2) Ensure BFG is available

```bash
bfg --version
```

If unavailable, install BFG (example for macOS):

```bash
brew install bfg
```

### 3) Run BFG against known sensitive DB artifacts

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk PATH="/opt/homebrew/opt/openjdk/bin:$PATH" \
bfg -D '{test_baseline.db,test_local.db,test_envelope.db,test_remote_sync.db}' --no-blob-protection .
```

### 4) Expire reflog + aggressively gc

```bash
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

### 5) Verify history no longer contains purged files

```bash
git log --name-only --pretty=format: -- 'data/*.db' | sed '/^$/d' | sort -u
```

Expected output after cleanup: no deleted DB artifact paths.

### 6) Force-push rewritten history

```bash
git push --force --all origin
git push --force --tags origin
```

### 7) Team resync

After force-push, all collaborators must re-clone or hard-reset local clones.
See `reclone.md` in this repository for exact teammate instructions.
