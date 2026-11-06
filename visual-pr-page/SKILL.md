---
name: visual-pr-page
description: Build an interactive HTML page that explains a pull request or branch in plain language, with diagrams, a walk-through, the commits, changes from the plan, test results and a review checklist. Use whenever the user asks for a visual PR, a review page, an interactive document to review a change, or "something visual to help me review this", even when they don't say PR. Not for writing the PR description itself.
---

# Visual PR page

One self-contained HTML file a reviewer opens in a browser. It explains what changed and why, for someone who hasn't read the code. You write the content as `page.json` plus SVG diagrams, and `scripts/build.py` turns it into the page and refuses content that breaks the rules below.

## 1. Gather the facts

- The branch, its base and the commit range (`git log --oneline <base>..HEAD`).
- The issue or ticket, read with `gh` or the tracker the user uses, and any plan or notes the user points you to.
- The full diff. Read enough of the code to explain behavior, not just file names.
- Test, lint and check results you ran this session. Every number on the page comes from something you ran or read this session. If you didn't run it, leave it out or say it wasn't run.

## 2. Write `page.json`

Work in a scratch folder. `assets/example/page.json` shows every block type. Copy its shape.

The page has `id`, `title`, `why` (exactly one sentence: the problem and what becomes possible), `crumbs`, `chips` and `sections`. Each section has `id`, `title`, an optional `lead` and a list of `blocks`. Any block can take a `heading`.

| Block | Fields |
| :--- | :--- |
| `notes` | `items`: `{lead, text}` |
| `text` | `paragraphs` |
| `list` | `items`: strings |
| `glossary` | `items`: `{term, meaning}` |
| `diagram` | `svg` (a file next to `page.json`, or inline markup), `caption` |
| `steps` | `steps`: `{title, detail, skipIn?}`; optional `modes`: `{id, label, tone, outcome}` |
| `cards` | `items`: `{tag?, title, body: [paragraphs]}` |
| `table` | `columns`, `rows`; `search: false` to hide the filter |
| `stats` | `items`: `{value, label, tone?}`, where tone is `good`, `warn` or `bad` |
| `commits` | filled from git by the build |
| `changes` | `items`: `{title, planned?, built, why}` |
| `checklist` | `items`: strings. Ticks are kept in the reader's browser |

Text fields accept `` `code` ``, `**bold**` and `[label](url)`.

Include these sections, in this order, and leave out any that would be empty:

1. **Things to note.** One to three items a reviewer must not miss: what users will see, what runs after merge, anything risky.
2. **Words used here.** A glossary for any term a newcomer wouldn't know.
3. **How it works.** A diagram, then a `steps` walk-through. Use `modes` when the change has a success path and a failure path.
4. **Where the code lives.** A diagram of the structure, or of before and after, plus `cards` for the main pieces.
5. **The commits.**
6. **Changes from the plan.** Every place the work differs from the issue or plan, each with its reason.
7. **Tests.** `stats` for the counts, and a `table` when the examples are worth browsing.
8. **Review checklist.** What to read or try, in order.
9. **What comes next.**

## 3. Write for a busy reader

- Use plain words, short sentences and one idea per sentence. Follow the `unslop` skill when it's installed.
- Name what a user or the next engineer will notice before naming any code.
- The page must stand alone. Don't cite private notes or their section numbers. Link only to things the reviewer can open.
- Where something is a guess rather than something you checked, say so.

## 4. Draw the diagrams

At least two diagrams: how the change works, and where it sits (structure, before and after, or the files it writes). Write each one as an SVG file next to `page.json`, and use `assets/example/*.svg` as the model.

A diagram must show what a list can't. A single row of boxes joined by arrows only repeats the walk-through. Show the branch where success and failure part ways, what's new (`hl`) next to what stays the same (`muted`), or which part reads or writes which.

- Set a `viewBox` about 860 wide. The page scales it.
- Colour only with these classes, so diagrams follow light and dark mode: `box`, `box hl` (the new or changed part), `box good`, `box bad`, `box muted` (dashed, for unchanged or outside), `line` (gets an arrowhead), `line good`, `line bad`, `line dash`, and `text` with `title`, `muted`, `good` or `bad`.
- Show one idea per diagram, with at most about eight boxes and short labels of no more than two lines.
- Make the caption say what to notice, not what the picture is.

## 5. Build and check

```sh
python3 <skill>/scripts/build.py page.json -o "<output>.html" --repo <checkout> --range <base>..HEAD
```

Fix every problem it prints. It writes nothing until the page passes. Then open the page in a browser and click through it: the walk-through in each mode, each card and the checklist. Browser tools often refuse `file:` URLs, so serve the page on `127.0.0.1` (step 7), open that URL, and stop the server when you're done. Without any browser tool, say so and ask the user to look.

## 6. Save it

Save it where the user keeps notes for this project, such as an Obsidian project folder, as `<Project> <issue> - Visual PR - <topic>.html`. If you don't know where that is, ask once. The page holds its own data, so you don't need to keep `page.json`.

To update it later, rebuild from the page itself:

```sh
python3 <skill>/scripts/build.py page.html --dump page.json   # get the content back to edit
python3 <skill>/scripts/build.py page.json -o page.html --repo <checkout> --range <base>..HEAD
```

Rebuild after new commits, or when the PR text or the plan changes.

## 7. Share it

When the user wants to open it from another device, serve that one file, over Tailscale when it's available:

```sh
dir=$(mktemp -d) && ln -s "<page>.html" "$dir/index.html"
host=$(tailscale ip -4 2>/dev/null | head -1); host=${host:-127.0.0.1}
python3 -m http.server 8765 --bind "$host" --directory "$dir"
```

Run it in the background and give the user the URL. Never bind to `0.0.0.0`, and never serve a folder with other files in it.
