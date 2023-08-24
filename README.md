# GitHub Tools

## Prune GitHub Actions Logs

It prunes at most 100 log entries. To delete more entries,
run it multiple times.

For authentication the environment variable `GH_TOKEN`
must contain a GitHub access token with sufficient rights.

```
export GH_TOKEN=<token>
```

```
actions_prune.py - Prune old logs from GitHub Actions.

usage: actions_prune.py [-h] [--dry-run] --prune-age DAYS [--user USER]
                        repository

positional arguments:
  repository            GitHub repository

optional arguments:
  -h, --help            show this help message and exit
  --dry-run, -n         do not actually prune logs, just list them
  --prune-age DAYS      delete logs older than DAYS days
  --user USER, -u USER  repository is owned by another user/organization
```


## Prune GitHub Container Registry

The unused/untagged container versions in the GitHub container
registry are not automatically deleted, they stick around until
they are deleted by the user.

For details, see this discussion:
[Are tag-less container images deleted?](https://github.com/orgs/community/discussions/26716)

That leads to an ever increasing space usage, which will result
in increasing costs for private repositories. The `ghcr_prune`
program is able to prune these unneeded versions. It is based on
<https://github.com/airtower-luna/hello-ghcr/blob/main/ghcr-prune.py>.

It prunes at most 100 versions per container. To delete more versions,
run it multiple times.

For authentication the environment variable `GH_TOKEN`
must contain a GitHub access token with sufficient rights.

```
export GH_TOKEN=<token>
```

```
ghcr_prune.py - Prune old versions of GHCR container.

usage: ghcr_prune.py [-h] [--dry-run] --prune-age DAYS [--user USER]
                     container [container ...]

positional arguments:
  container             images to prune

optional arguments:
  -h, --help            show this help message and exit
  --dry-run, -n         do not actually prune images, just list them
  --prune-age DAYS      delete untagged images older than DAYS days
  --user USER, -u USER  container is owned by another user/organization
```
