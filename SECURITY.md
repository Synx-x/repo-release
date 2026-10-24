# Security

## Report a vulnerability

Open a private security advisory at
https://github.com/Synx-x/repo-release/security/advisories/new.

Do not open a public issue for a vulnerability. A public issue tells everyone
before a fix exists.

## What this plugin does that carries risk

`hooks/guard_publish.py` runs on your machine and reads the command you are
about to run. It reads the repository path from the hook payload and passes that
path to `scripts/validate.py`.

Two properties matter for a security review:

- The hook reads files under the repository it is given. It does not read
  outside that tree, and it makes no network call.
- The hook fails open. Any error inside it allows the command. A broken gate
  must never strand the action it guards, and that trade is deliberate: this
  hook advises, it does not enforce a security boundary.

## Scope

The validator reads text files and reports patterns. It is not a
vulnerability scanner, and a clean run does not mean the repository is safe.
