# Notes for the release being written

A note lands here while its version is still unreleased, and moves to `../v<major>/`
when the version is cut. Frappe keeps the same folder for the same reason
(`frappe/change_log/current/`), so anyone who has read one app's history can read this
one.

A note is named `vX_Y_Z.md` and opens with two lines a reader never sees, because
markdown hides an HTML comment:

```
<!-- released: 2026-08-02 18:57:34 -->
<!-- link: /driver -->
# Apex 2.2.4

The one-line subtitle the bell feed shows beside the version.
```

`released` is the moment the in-app bell reports; it is required, and it is what keeps
"since you last looked" honest on a machine that only checked the repository out today.
`link` is optional and defaults to the desk — set it when the release is about a portal
the reader should open instead.

Nothing else is needed: `apex_core/utils/changelog.py` reads the folder, so a release is
described once, here.
