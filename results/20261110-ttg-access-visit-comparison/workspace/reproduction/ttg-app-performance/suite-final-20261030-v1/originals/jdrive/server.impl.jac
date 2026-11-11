"""JDrive backend - walker bodies."""

def _folder_view(f: Folder) -> FolderView {
    entries: list[EntryView] = [];
    for c in [f ->:Contains:->[?:Folder]] {
        if not c.trashed {
            entries.append(EntryView(id=jid(c), kind="folder", name=c.name));
        }
    }
    for c in [f ->:Contains:->[?:File]] {
        if not c.trashed {
            entries.append(
                EntryView(
                    id=jid(c), kind="file", name=c.name, size=c.size, mime=c.mime
                )
            );
        }
    }
    return FolderView(id=jid(f), name=f.name, entries=entries);
}

impl GetRoot.run {
    existing = [here ->:Contains:->[?:Drive]];
    if existing {
        drive = existing[0];
    } else {
        drive = Drive(created_at=now());
        here +>: Contains :+> drive;
    }
    folders = [drive ->:Contains:->[?:Folder]];
    if folders {
        my = folders[0];
    } else {
        my = Folder(name="My Drive", created_at=now(), updated_at=now());
        drive +>: Contains :+> my;
    }
    report EntryView(id=jid(my), kind="folder", name=my.name);
}

impl ListFolder.run {
    report _folder_view(here);
}

impl VisibleFolderTree.walk {
    cur_id = jid(here);
    if not self.start_id {
        self.start_id = cur_id;
        self.depths[cur_id] = 0;
        self.paths[cur_id] = here.name;
    }
    depth = self.depths.get(cur_id, 0);
    path = self.paths.get(cur_id, here.name);
    self.entries.append(
        FolderTreeEntry(id=cur_id, name=here.name, depth=depth, path=path)
    );
    for child in [here ->:Contains:->[?:Folder, trashed == False]] {
        child_id = jid(child);
        self.depths[child_id] = depth + 1;
        self.paths[child_id] = path + "/" + child.name;
    }
    visit [here ->:Contains:->[?:Folder, trashed == False]];
}

impl VisibleFolderTree.done {
    if jid(here) == self.start_id {
        self.entries.sort(key=lambda (e: FolderTreeEntry) { e.path; });
        report FolderTreeView(id=self.start_id, entries=self.entries);
    }
}

impl NewFolder.run {
    f = Folder(name=self.name, created_at=now(), updated_at=now());
    here +>: Contains :+> f;
    report EntryView(id=jid(f), kind="folder", name=f.name);
}

impl TrashFolder.run {
    here.trashed = True;
    here.updated_at = now();
    report EntryView(id=jid(here), kind="folder", name=here.name);
}

impl Upload.run {
    fname: str = str(self.file.filename or "file");
    fmime: str = str(self.file.content_type or "application/octet-stream");
    f = File(
        name=fname, mime=fmime, size=0, created_at=now(), updated_at=now()
    );
    here +>: Contains :+> f;
    key = jid(f);                       # storage path = the file's own id
    storage.upload(self.file.file, key);
    meta = storage.get_metadata(key);
    f.blob_key = key;
    f.size = int(meta.get("size", 0)) if meta else 0;
    report EntryView(id=jid(f), kind="file", name=f.name, size=f.size, mime=f.mime);
}

impl Download.run {
    import from base64 { b64encode }
    content = "";
    if here.blob_key and storage.exists(here.blob_key) {
        data = storage.download(here.blob_key);       # bytes (destination=None)
        if data is not None {
            content = b64encode(data).decode("ascii");
        }
    }
    report {
        "name": here.name, "mime": here.mime,
        "size": here.size, "content_b64": content
    };
}
