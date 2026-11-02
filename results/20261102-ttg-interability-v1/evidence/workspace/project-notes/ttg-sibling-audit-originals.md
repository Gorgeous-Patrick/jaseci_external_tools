# Original-app future-access sibling dependence audit

4 original registered readers; additional original read/traverse/business exceptions; contribution to main30-app audit only

This is a manual source argument under closed-world ordinary-field and builtin effect contracts; no analyzer was run or claimed. Output order/value dependence is distinct from future-access dependence.

| App / registered reader | Source conclusion | Minimal reason / source |
|---|---|---|
| linked_list / Traverse | STATIC_MAY_ACCESS_DEPENDENCE | After a common prefix of9998 entries, queued B and C share visited. B increments to9999 and enqueues its child; C increments to10000 and cancels the walk, suppressing further queued access. A sibling changes the remaining visit/cancellation budget. originals/linked_list/main.jac:31-42 |
| littlex / load_feed | STATIC_NO_AFTER_CLOSED_WORLD_SUMMARY | run and collect issue fixed relative paths. Tweet.to_view reads root->Profile and ordinary Tweet fields; neither helper nor abilities mutate graph or read feed/search-result state to choose any graph access. search_query is immutable input and applies only after views are built. originals/littlex/server.jac:259-292; originals/littlex/server.jac:122-133 |
| jacord / load_channel | STATIC_NO_AFTER_CLOSED_WORLD_SUMMARY | _message_view reads AuthoredBy/reply-count and plain fields; _resolve_author local loop returns a username. Message siblings do not share mutable access-control state; incoming ReplyTo visit is unconditional. Recursive reply graph may branch/cycle; independence alone proves neither chain cardinality nor termination. originals/jacord/server.jac:172-175; originals/jacord/server.impl.jac:22-39; originals/jacord/server.impl.jac:238-250 |
| jdrive / VisibleFolderTree | STATIC_NO_AFTER_OUTPUT_DATAFLOW_SUMMARY | depths/paths are genuinely read after other nodes write them; shared/reconvergent child IDs can change OUTPUT path/depth. Those values never choose the two graph reads or final visit. Both use here->Contains->Folder with immutable node-field predicate trashed==False. start_id only initializes output context and selects final report. originals/jdrive/server.jac:103-112; originals/jdrive/server.impl.jac:44-68 |

## Additional walkers and exceptions

- **linked_list.Sum** — STATIC_NO; measured. total is written at entry and read only for exit reports; unconditional Next visit never reads total. References: main.jac:45-56.
- **linked_list.Find** — STATIC_MAY; measured. found itself is output-only (never read), but a target match calls disengage before Next visit. Queued matching B suppresses later C ability/path access; explicit queue cancellation effect. References: main.jac:59-72.
- **littlex.load_feed_stepwise** — STATIC_MAY; present_only_not_native_replay. seen_profiles membership returns before Post visit (309-314); root_profile_id written by first Profile suppresses Follow visits in later Profiles (315-317). seen_tweets suppresses to_view root/Profile read for repeated Tweet (321-327). Distinct output feed is not the cause. References: server.jac:295-341.
- **littlex.get_channels** — STATIC_MAY; present_only_not_native_replay. seen[cid] gates Channel.to_view(False). A repeated Channel sibling skips root/Profile, membership and member-count graph reads. No further visit is needed for real future-access dependence. References: server.jac:345-367, server.jac:143-159.
- **littlex.get_trending** — STATIC_NO_AFTER_PURE_OUTPUT_SUMMARY; present_only_not_native_replay. seen return gates ordinary content/string tally only; no graph query, visit, graph write or disengage follows it. counts and seen affect output, unlike get_channels. allroots enumeration is a read-only builtin contract. References: server.jac:224-255.
- **littlex.get_all_profiles/get_profile** — STATIC_NO_AFTER_CALLEE_SUMMARY; get_profile_measured_helper;get_all_profiles_present_only. to_user_view pure; to_profile_view graph reads depend on current Profile and immutable with-context, not results accumulator. References: server.jac:94-111, server.jac:192-221.
- **littlex.find_profile/find_tweet/find_channel and derived business walkers** — SINGLETON_BOUNDARY_AND_EXPLICIT_EFFECTS; like_tweet/follow_user/create_tweet measured;other variants present_only. jobj(input_id) then visit[target] has at most one target; resolved actor is fixed context for that target, not sibling feedback. Derived walkers write likes/comments/edges/delete nodes and often disengage: retain graph-write/cancel effects, never summarize as read-only. Their changes affect later requests; this is not evidence of two sibling entries in the singleton native invocation. _now/grant/jobj require builtin/external summaries. References: server.jac:372-407, server.jac:410-577.
- **jacord.ListChannelIds** — STATIC_MAY_LOOP_CARRIED_FUTURE_ACCESS; present_only_not_native_replay. ids length reaches limit inside first workspace channels loop; return suppresses HasChannel graph query of later workspace. This is iteration dependence, not two queued abilities. Prefix/order/cardinality summary needed for faithful batching. References: server.impl.jac:215-231.
- **jacord.ListWorkspaces/ListChannels** — STATIC_NO_AFTER_LOCAL_OUTPUT_SUMMARY; present_only_not_native_replay. local out appends never influence later graph access; guards use invariant input/current resolved object. References: server.impl.jac:189-212.
- **jacord.EnsureUser/CreateWorkspace/CreateChannel/PostMessage/PostReply/JoinWorkspace** — EXPLICIT_DB_EFFECTS_SINGLE_ROOT_INVOCATION; PostReply_measured;others_present_or_setup. Single Root entry, no queued child abilities. Graph writes/permission grants can affect later requests. JoinWorkspace loop read/return uses DB membership, not a mutated per-sibling accumulator. Clock/grant/jobj need effect contracts; no blanket sibling proof for arbitrary external implementations. References: server.impl.jac:45-182.
- **jdrive.ListFolder** — STATIC_NO_AFTER_HELPER_SUMMARY; measured. _folder_view reads Folder/File children. Local entries and each child trashed branch control output constructors only, with no shared-state-gated subsequent graph read. References: server.impl.jac:3-19, server.impl.jac:40-42.
- **jdrive.GetRoot/NewFolder/TrashFolder** — EXPLICIT_DB_EFFECTS_SINGLE_TARGET; NewFolder/TrashFolder_measured;GetRoot_setup_or_present. Create/attach and trashed writes affect later tree/list requests. Native endpoints invoke one Root/Folder, not sibling recursion. Do not erase DB writes or confuse cross-request dependencies with read-walker sibling dependence. References: server.impl.jac:22-37, server.impl.jac:71-80.
- **jdrive.Upload/Download** — UNKNOWN_EXTERNAL_STORAGE_EFFECTS; present_only_original_walkers;native_suite_blob_support_is_separate. Ambient storage.upload/get_metadata/exists/download and file object methods are external. Need effect/alias contracts; no theoretical impossibility claimed. Native.py replay does not invoke these walkers. References: server.jac:32, server.impl.jac:83-110.

## Interpretation

Traverse.visited counts total entered Items, not depth. Single-chain/vacuous sibling reasoning requires the generator/cardinality/acyclicity proof and bounded input; source name alone is insufficient.
Closed-world callee summaries and output slicing can prove the three registered readers access-independent even though their shared outputs or current analyzer barriers exist. MAY is a useful statically detected dependence. External storage remains unknown without contracts, not theoretically impossible.

The measured/present distinction uses immutable native.py replay and datasets/ttg/build.py session definitions, not every HTTP route or old synthetic kernel.

## Source hashes

- `app_suite/registry.json`: `3585ed5b7102c2908f622747f9361bc13c8b7cac4457cf647086c4d24922e4e9`
- `app_suite/native.py`: `f44bf3905bd248df2f7c2fe10db3c926a847d170c963e889bffac94d51435228`
- `datasets/ttg/build.py`: `a617dd95626a60babcf56dc10fba0ed3dc4a5c24ceca3033fea0b97401c129b9`
- `originals/linked_list/main.jac`: `59c9664c3cc533f2942af9a9cc7945e159a6e447d009bc76c03ec5113b62320c`
- `originals/littlex/server.jac`: `806b475b5168d7f2f35d340358a00d5368feaa53edf34f298dbea23478926357`
- `originals/jacord/server.jac`: `6a6d0c7e6cdaed6b097d2ef9d0b85bb4647a3a274b583cfa96b5d31d9d4b8576`
- `originals/jacord/server.impl.jac`: `9dcb4280fec0a7691c03dac0617d2e770fcc02020325801c9f741a98b10928ee`
- `originals/jdrive/server.jac`: `10a7f455d7ad63c44a05e7b3667d76f017f717968e6a89bae76cdcccd5859942`
- `originals/jdrive/server.impl.jac`: `0ffa9c18875036ed0eeabd40e59d94c076db7ea36601ed405be36477c2dac731`
