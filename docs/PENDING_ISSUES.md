# Unresolved Comments from Merged Pull Requests

This document collects review comments from merged pull requests that were
not addressed before the merge.

There are none open. The last batch (from PRs #6, #8 and #52) was closed by
the fixes for
[issue #87](https://github.com/INTO-CPS-Association/workspace/issues/87);
see `docs/CHANGELOG.md`, week of 12-Oct-2026. Two items were closed without
a code change:

- The `--path-prefix` default of `dtaas-user` is intended. It is documented
  in `workspaces/src/admin/README.md` and the container always passes
  `MAIN_USER`.
- The `PATH_PREFIX` substitution in service endpoints no longer exists:
  `load_services()` takes no prefix and the catalogue has no placeholder.
