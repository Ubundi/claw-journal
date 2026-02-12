# BFG Cleanup Candidates

The following files are (or were likely) generated, test, or runtime artifacts that may contain sensitive data (tokens, usage details, or session information). They should be considered for removal from the existing Git history using tools like BFG Repo-Cleaner or `git filter-repo`.

## File paths to purge from history

- data/test_baseline.db
- data/test_local.db
- data/test_envelope.db
- data/test_remote_sync.db

> Before running BFG/filter-repo, verify these paths are (or were) committed with `git log -- data/<file>.db` and adjust as needed.
