# Git: Merging Branches and Cleanup

A quick-reference guide for merging changes into `main` and deleting branches.

---

## Merging a Branch into Main

### 1. Make sure your work is committed

```bash
git status
```

If there are uncommitted changes, stage and commit them first:

```bash
git add <files>
git commit -m "Your commit message"
```

### 2. Switch to main and pull latest changes

```bash
git checkout main
git pull origin main
```

### 3. Merge your branch

```bash
git merge <branch-name>
```

For example, to merge the `development` branch:

```bash
git merge development
```

If there are **merge conflicts**, Git will tell you which files need manual resolution. Open those files, resolve the conflicts (look for `<<<<<<<`, `=======`, `>>>>>>>` markers), then:

(Eller git reset --hard for a resette til det som er på github)

```bash
git add <resolved-files>
git commit
```

### 4. Push to GitHub

```bash
git push origin main
```

---

## Deleting a Branch

### Delete locally

```bash
git branch -d <branch-name>
```

Use `-d` (lowercase) for safe delete — Git will warn you if the branch has unmerged changes.

If you're sure you want to delete it even with unmerged changes:

```bash
git branch -D <branch-name>
```

### Delete on GitHub (remote)

```bash
git push origin --delete <branch-name>
```

### Delete both in one go

```bash
git branch -d <branch-name>
git push origin --delete <branch-name>
```

---

## Full Example: Merge `development` and Clean Up

```bash
# 1. Switch to main and get latest
git checkout main
git pull origin main

# 2. Merge development into main
git merge development

# 3. Push the merged main to GitHub
git push origin main

# 4. Delete the branch locally and on GitHub
git branch -d development
git push origin --delete development
```

---

## Tips

- Always `git pull` on `main` before merging to avoid unnecessary conflicts.
- Use `git log --oneline --graph` to visualize the branch history before and after merging.
- If you want a clean, linear history instead of a merge commit, use `git rebase main` on your feature branch before merging (more advanced).
