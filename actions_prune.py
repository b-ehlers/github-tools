#!/usr/bin/env python3

# Copyright (C) 2022 Bernhard Ehlers
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
actions_prune.py - Prune old logs from GitHub Actions.

GitHub API Documentation:
https://docs.github.com/en/rest/actions/workflow-runs

usage: actions_prune.py [-h] [--dry-run] --prune-age DAYS [--user USER]
                        repository

positional arguments:
  repository            GitHub repository

optional arguments:
  -h, --help            show this help message and exit
  --dry-run, -n         do not actually prune logs, just list them
  --prune-age DAYS      delete logs older than DAYS days
  --user USER, -u USER  repository is owned by another user/organization
"""

import os
import sys
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
import requests


parser = argparse.ArgumentParser(
             description='%(prog)s - Prune old logs from GitHub Actions.')
parser.add_argument('--dry-run', '-n', action='store_true',
                    help='do not actually prune logs, just list them')
parser.add_argument('--prune-age', type=float, metavar='DAYS', required=True,
                    help='delete logs older than DAYS days')
parser.add_argument('--user', '-u', action='store',
                    help='repository is owned by another user/organization')
parser.add_argument('repository', help='GitHub repository')

sess = requests.Session()
sess.headers.update({'Accept': 'application/vnd.github+json'})


def actions_prune(repo, user, prune_age, dry_run=False):
    """ prune old logs from GitHub Actions """

    prune_date = datetime.now(tz=timezone.utc) - timedelta(days=prune_age)
    prune_date = prune_date.isoformat(timespec='seconds')
    if not user:
        resp = sess.get('https://api.github.com/user')
        resp.raise_for_status()
        user = json.loads(resp.content)["login"]
    resp = sess.get(f'https://api.github.com/repos/{user}/{repo}/actions/runs',
                    params={'created': "<" + prune_date, 'per_page': 100})
    if resp.status_code == 404:
        raise ValueError(f"Unknown repository {user}/{repo}")
    resp.raise_for_status()
    workflow_runs = json.loads(resp.content)["workflow_runs"]
    if not workflow_runs:
        return
    if dry_run:
        print("Would delete:")
    else:
        print("Deleted:")
    for run in sorted(workflow_runs, key=lambda k: k["id"]):
        print(f"{run['name']} #{run['run_number']}    {run['created_at']}")
        if not dry_run:
            resp = sess.delete(f'https://api.github.com/repos/{user}/{repo}/'
                               f'actions/runs/{run["id"]}')
            if resp.status_code == 403:
                raise ValueError("Insufficient privileges to delete "
                                 f"{run['name']} #{run['run_number']}")
            resp.raise_for_status()


if __name__ == "__main__":
    args = parser.parse_args()

    if 'GH_TOKEN' in os.environ:
        token = os.environ['GH_TOKEN']
    else:
        sys.exit('missing authentication token (GH_TOKEN)')
    sess.headers.update({'Authorization': 'token ' + token})

    prog = os.path.basename(sys.argv[0])
    try:
        actions_prune(args.repository, args.user, args.prune_age, args.dry_run)
    except json.JSONDecodeError:
        sys.exit(f"{prog}: Invalid JSON")
    except (requests.exceptions.RequestException, ValueError) as err:
        msg = str(err)
        match = re.search(r"\(Caused by ([a-zA-Z0-9_]+)\('?[^:']*[:'] *(.*)'\)",
                          msg)
        if match:
            msg = match.group(2)
        sys.exit(f"{prog}: {msg}")
    except KeyboardInterrupt:
        sys.exit(128+2)
