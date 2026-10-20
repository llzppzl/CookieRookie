# Debug mode demo

A tiny program with one bug, to try debug mode on.

`app.py` should print `Hello, Ada!`, but it crashes:

```
$ python examples/debug-demo/app.py
AttributeError: 'User' object has no attribute 'nmae'. Did you mean: 'name'?
```

Ask CookieRookie to fix it, from the repository root:

```bash
python main.py "python examples/debug-demo/app.py should print 'Hello, Ada!' but crashes with an AttributeError"
```

The agent reads the files, finds the typo in `user.py`, edits it (asking you first) and runs `app.py` again to check.

The fix changes the files in this folder. To get the bug back for another try:

```bash
git checkout -- examples/debug-demo
```
