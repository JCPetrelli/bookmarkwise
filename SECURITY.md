# Security and privacy

Bookmarkwise runs locally. The Python tool only reads the browser's `Bookmarks` and `AccountBookmarks` files and writes files only where you tell it to. It sends nothing over the network, except `bookmarkwise links`, the optional dead-link check, which you have to start yourself and which contacts each bookmarked site once.

The extension it builds asks for one permission, `bookmarks`, and has no network access of its own. It changes bookmarks only when you click **Apply**, after a backup, and only if every bookmark it touches still matches the plan.

Inventories, plans, backups and logs list your bookmarks, which say a lot about you. Keep them out of version control (`.gitignore` covers the defaults) and delete them when you are done.

If you find a way for a plan or a built extension to run unintended code, change bookmarks it shouldn't, or leak data, don't open a public issue. Email info@jacopocastellano.com with the details. You'll get a reply within a week.
