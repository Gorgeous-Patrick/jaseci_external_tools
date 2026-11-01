# Old 866222 runtime copies: archival relocation

This verified archive preserves exactly:

- `reproduction/ttg-continuation-performance/runtime-clean-866222f90-v1`
- `reproduction/ttg-continuation-performance/runtime-direct-866222f90-v1`

Main authorized these two historical runtime copies after capacity forecasting.
Perf confirmed no reader, current formal executable/import source or live
bootstrap/admin/observer/type-stub dependency requires them. The current formal
comparison uses the already frozen85026d snapshots. Each member was read back
through gzip/tar and compared with its original file hash, byte count, mode or
symlink target before removing only the two approved directories. Verification
JSON binds all members and the stopped host proof; `reclamation.json` records
actual recovery. Adjacent manifests/overlays, current85026d snapshots, corpus,
runtime worktrees and published data remain untouched.

## Future snapshot.freeze dependency

The snapshot builder `reproduction/ttg-plus-performance/snapshot.py:46-49`
reads `runtime-clean-866222f90-v1/jac/jaclang/vendor/typeshed/stdlib` as the
source of previously ignored type-stub files. This archival relocation does
not change that source code or redirect imports. Before any future freeze or
rebuild requiring either old path, coordinate storage with perf and restore the
archive to its exact original paths. The currently frozen comparison does not
need a new freeze or those online copies.

With sufficient space and both original paths absent:

```sh
sha256sum obsolete-866222f90-v1.tar.gz
tar -xzf obsolete-866222f90-v1.tar.gz -C /home/baichuan/jaseci
```

Compare the archive hash with `obsolete-866222f90-v1-verification.json`, and
restored regular files against `obsolete-866222f90-v1-members.jsonl.gz`. Reserve
room for the entire uncompressed group. Restoration starts no services.
Historical adjacent metadata remains unchanged and refers to these same bytes;
this archive and its path mapping preserve that lineage.
