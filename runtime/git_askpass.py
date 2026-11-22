#!/usr/bin/python3
"""OpenSSH askpass helper; the secret exists only in the requesting child env."""
import os
import sys

# OpenSSH retries an incorrect non-empty passphrase indefinitely. Cancel its
# retry prompt so a failed unlock is one bounded request, not a retry loop.
if 'bad passphrase' in ' '.join(sys.argv[1:]).lower():
    raise SystemExit(1)
sys.stdout.write(os.environ.get('LAKEHOUSE_SSH_PASSPHRASE', '') + '\n')
