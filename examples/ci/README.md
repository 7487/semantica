# CI templates

Copy-paste starting points for wiring `semantica` into your own project's CI. Each file is a
complete, working config — rename it into your project (see the comment at the top of each file
for the target path) and swap the smoke-test / test step for whatever your project does with
Semantica.

| File | Target path in your repo |
| ---- | ------------------------- |
| [`github-actions.yml`](github-actions.yml) | `.github/workflows/semantica.yml` |
| [`gitlab-ci.yml`](gitlab-ci.yml) | `.gitlab-ci.yml` |
| [`circleci-config.yml`](circleci-config.yml) | `.circleci/config.yml` |

If your own project is hosted on GitHub, you can skip the setup boilerplate entirely and use
Semantica's reusable composite action instead:

```yaml
- uses: semantica-agi/semantica/.github/actions/setup-semantica@main
  with:
    python-version: '3.11'
    # extras: 'explorer,all'   # optional
    # version: '==0.6.7'       # optional, pin an exact release
```

It installs Python, caches pip, installs `semantica`, and verifies the import — see
[`.github/actions/setup-semantica/action.yml`](../../.github/actions/setup-semantica/action.yml).
