#!/usr/bin/env python3

# The MIT License (MIT)
#
# Copyright (C) 2022 Bernhard Ehlers
# Copyright (C) 2021 Fiona Klute
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
ghcr_prune.py - Prune old versions of GHCR container.

Discussion:
https://github.com/orgs/community/discussions/26716

Based on:
https://github.com/airtower-luna/hello-ghcr/blob/main/ghcr-prune.py

GitHub API Documentation:
https://docs.github.com/en/rest/packages


usage: ghcr_prune.py [-h] [--dry-run] --prune-age DAYS [--user USER]
                     container [container ...]

positional arguments:
  container             images to prune

optional arguments:
  -h, --help            show this help message and exit
  --dry-run, -n         do not actually prune images, just list them
  --prune-age DAYS      delete untagged images older than DAYS days
  --user USER, -u USER  container is owned by another user/organization
"""

import os
import sys
import argparse
import base64
import json
import re
from datetime import datetime, timedelta, timezone
import dateutil.parser
import requests


parser = argparse.ArgumentParser(
             description='%(prog)s - Prune old versions of GHCR container.')
parser.add_argument('--dry-run', '-n', action='store_true',
                    help='do not actually prune images, just list them')
parser.add_argument('--prune-age', type=float, metavar='DAYS', required=True,
                    help='delete untagged images older than DAYS days')
parser.add_argument('--user', '-u', action='store',
                    help='container is owned by another user/organization')
parser.add_argument('container', nargs="+",
                    help='images to prune')

sess = requests.Session()
sess.headers.update({'Accept': 'application/vnd.github+json'})


class GithubContainer:
    """ query Github container """
    _sess = requests.Session()

    def __init__(self, repo):
        self._auth = None
        self.repo = repo

    def auth(self):
        """ authorization """
        if not self._auth:
            auth_header = {"Authorization": "Basic " + \
                           base64.b64encode(("user:" + token)
                                            .encode()).decode('ascii')}
            resp = GithubContainer._sess.get(
                       "https://ghcr.io/token",
                       headers=auth_header,
                       params={"scope": f"repository:{self.repo}:pull",
                               "service": "ghcr.io"})
            resp.raise_for_status()
            data = json.loads(resp.content)
            self._auth = {"Authorization": "Bearer " + data["token"]}
        return self._auth

    def manifest(self, tag):
        """ get manifest """
        resp = GithubContainer._sess.get(
                   f"https://ghcr.io/v2/{self.repo}/manifests/{tag}",
                   headers={**self.auth(),
                            "Accept": ",".join((
                                "application/vnd.oci.image.manifest.v1+json",
                                "application/vnd.oci.image.index.v1+json",
                                "application/vnd.docker."
                                    "distribution.manifest.v2+json",
                                "application/vnd.docker."
                                    "distribution.manifest.list.v2+json"))
                           })
        resp.raise_for_status()
        return json.loads(resp.content)

    def platform_digests(self, tag):
        """ get list of platform manifest digests """
        manifest = self.manifest(tag)
        if "manifests" in manifest:
            digests = [mani["digest"] for mani in manifest["manifests"]]
        else:
            digests = []
        return digests


def del_package_version(version, url):
    """ delete package version """
    resp = sess.delete(url)
    if resp.status_code == 403 or \
       resp.status_code == 404 and sess.get(url).ok:
        # 403 or a 404 with successful get -> missing privileges
        raise ValueError(f"Insufficient privileges to delete {version}")
    resp.raise_for_status()


def keep_versions(repo, versions, prune_date):
    """ keep tagged versions and versions created just before prune_date """
    keep_digest = set()
    ghcr = GithubContainer(repo)
    for version in versions:
        created_date = dateutil.parser.parse(version['created_at'])
        if created_date < prune_date:
            if version['metadata']['container']['tags']:
                keep_digest.add(version['name'])
                keep_digest.update(ghcr.platform_digests(version['name']))
        elif created_date < prune_date + timedelta(hours=1) and \
             version['name'] not in keep_digest:
            keep_digest.update(ghcr.platform_digests(version['name']))
    return keep_digest


def container_prune(containers, user, prune_age, dry_run=False):
    """ prune old versions of GHCR container """

    if user:
        api_user = "users/" + user
    else:
        api_user = "user"
        resp = sess.get('https://api.github.com/user')
        resp.raise_for_status()
        user = json.loads(resp.content)["login"]

    # all: get names of all containers
    if len(containers) == 1 and containers[0] == "all":
        resp = sess.get(f'https://api.github.com/{api_user}/packages',
                        params={'package_type': 'container', 'per_page': 100})
        resp.raise_for_status()
        containers = sorted([pkg["name"] for pkg in json.loads(resp.content)])

    # prune each container
    prune_date = datetime.now(tz=timezone.utc) - timedelta(days=prune_age)
    for container in containers:
        containerq = requests.utils.quote(container, safe="")
        print(f"Pruning images of {container}...")

        # get container versions
        resp = sess.get(f'https://api.github.com/{api_user}/packages/'
                        f'container/{containerq}/versions',
                        params={'per_page': 100})
        if resp.status_code == 404:
            raise ValueError(f"Unknown container {container}")
        resp.raise_for_status()
        versions = json.loads(resp.content)

        del_cnt = 0
        del_header = "Would delete" if dry_run else "Deleted"
        keep_digest = keep_versions(user + "/" + container,
                                    versions, prune_date)
        for version in sorted(versions, key=lambda k: k["id"]):
            # prune old untagged images if requested
            if dateutil.parser.parse(version['created_at']) < prune_date and \
               version['name'] not in keep_digest:
                if not del_cnt:
                    print(f"  {del_header}:")
                print(f"  {version['name']}")
                if not dry_run:		# delete version
                    del_package_version(version["name"],
                                        'https://api.github.com/'
                                        f'{api_user}/packages/'
                                        f'container/{containerq}/'
                                        f'versions/{version["id"]}')
                del_cnt += 1


if __name__ == "__main__":
    args = parser.parse_args()

    if 'GH_TOKEN' in os.environ:
        token = os.environ['GH_TOKEN']
    else:
        sys.exit('missing authentication token (GH_TOKEN)')
    sess.headers.update({'Authorization': 'token ' + token})

    prog = os.path.basename(sys.argv[0])
    try:
        container_prune(args.container, args.user, args.prune_age, args.dry_run)
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
