# First push from the current local repository state

You already have a local root commit, but it accidentally contains `dist/`. Nothing has been pushed, so fix the existing commit before adding a remote.

## 1. Add the repository files from this package

Make sure `.gitignore`, `LICENSE`, `LICENSES.md`, `LICENSES/`, `NOTICE.md`, `.github/`, `scripts/`, and `docs/` are in the repository root.

## 2. Remove generated `dist/` from Git tracking

`dist/` stays on disk but disappears from the commit:

```bash
git rm -r --cached dist
```

Check:

```bash
git status
```

## 3. Amend the existing first commit

Stage the new repository files and rewrite the local root commit:

```bash
git add .
git commit --amend --no-edit
```

Because the commit has never been pushed, rewriting it is harmless.

Verify that `dist/` is ignored:

```bash
git status --ignored --short
```

You should see `!! dist/` rather than tracked files under `dist/`.

## 4. Create an empty GitHub repository

Create `wratixor/node06` in the GitHub web UI. Do not add a README, `.gitignore`, or license there because the local repository already has them.

The GitHub CLI is not required. SSH authentication already works if:

```bash
ssh -T git@github.com
```

prints a successful authentication message.

## 5. Add GitHub as `origin`

```bash
git remote add origin git@github.com:wratixor/node06.git
git remote -v
```

Then push:

```bash
git push -u origin main
```

After this first push, `scripts/publish.sh` can build, commit, and push changes for you.

## 6. Add the Neocities API token to GitHub

In Neocities, open the settings for the `node06` site and copy/generate its API key.

In GitHub open:

`node06 -> Settings -> Secrets and variables -> Actions -> New repository secret`

Create:

- Name: `NEOCITIES_API_TOKEN`
- Value: the Neocities API key

Do not put this token in `.env`, source files, issues, commits, or screenshots.

## 7. Deployment

Every push to `main` runs `.github/workflows/deploy.yml`:

1. checks out the source;
2. runs `python build.py` (which also validates reciprocal `md://` links);
3. deploys generated `dist/` to Neocities.

Pull requests build and validate, but do not deploy.

## Daily use

From the repository root:

```bash
./scripts/publish.sh "add root point"
```

Or simply:

```bash
./scripts/publish.sh
```

and enter a commit message when prompted.
