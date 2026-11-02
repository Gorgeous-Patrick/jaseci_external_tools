# SNB29 sibling future-access source audit

All 29 supported operations classified. Seventeen contain actual `visit`; twelve have one Root ability and no sibling traversal. Under explicit ordinary-field, stable-valid-graph and builtin/framework summaries, fifteen traversal operations have no cross-sibling future-access state; IS2 and IC3 need the distinctions below. This is source reasoning, not implemented analyzer coverage, a speedup claim or theoretical impossibility.

| Operation / lines | Literal traversal | Decision and evidence |
|---|---|---|
|IC1 [201, 231]|visit|NO: _near builds candidate/distances before visit206. Read-only first_name controls local return209; output rows do not alter sibling city/organization queries210–218.|
|IC2 [232, 247]|visit|NO: Unchanged max_date gates author read238 per message; rows only controls sort/report245. No counter threshold changes visits235.|
|IC3 [248, 277]|visit|NO_VISIT_DEPENDENCE_BUT_MAY_FINAL_PAYLOAD_ACCESS: People initialization255 and message count increments262–263 do not guard later visit targets. However final counts>0 condition269 controls people[key] lookup and person first/last-name reads270–272. One X message plus one Y message enables those later fields; removing the Y sibling suppresses them. This is real final materialization access, not merely plain-dict output.|
|IC4 [278, 292]|visit|NO: old/counts writes284–285 affect final plain tag-name/count output289, not subsequent _tags(here) queries283 or visits281.|
|IC5 [293, 310]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root ability295; _near controls procedural candidate reads. forums key/count mutations302–303 feed aggregation, while eligible membership join_date300 gates forum message/author reads303. No Jac visit or sibling ability.|
|IC6 [311, 325]|visit|NO: Read-only tag_name gates per-message arithmetic317–318; counts never chooses future visits/graph queries. _near remains a procedural precursor.|
|IC7 [326, 343]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root ability328; each row reads Likes/liker/friends before latest comparison338. latest chooses output, not later graph accesses. Ordinary loops and like-date selection are not sibling visits.|
|IC8 [344, 357]|visit|NO: Root loop348 enqueues reply visits from graph only; each reply _author351 and output append352 is independent of prior rows.|
|IC9 [358, 371]|visit|NO: _near precalculates visits360; message date is immutable request/node state363, not prior output, before author364.|
|IC10 [372, 391]|visit|NO: Direct/_near determine candidates before376. Birthday local guard380 precedes per-person interest/post/tag/city reads381–388. score is local and never changes later query targets; rows only report.|
|IC11 [392, 409]|visit|NO: Per-person WorkAt/organization-place reads396–397 depend on here/work. Request/year predicate398 only gates output; rows never feeds access.|
|IC12 [421, 440]|visit|NO: names/comments are fresh per Person425. They deduplicate output counts430/433–435, not other siblings accesses. _is_class has its own per-call DFS visited/cancellation dependence; distinguish that procedural helper from person siblings.|
|IC13 [157, 179]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root ability159. BFS frontier/seen and target early-return165 control future _friends-equivalent edge reads168. Diamond A→B,C→D suppresses a later D expansion; target found in current layer cancels all following layers. distance increments once per layer172, not per visited person.|
|IC14 [452, 478]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root ability454. Path-local membership463 suppresses cycles; solutions makes while458 stop only after the current for-path layer finishes. A solution found midlayer does not cancel remaining same-layer paths. Next layer is skipped; subsequent selected solutions drive _edge_weight472.|
|IS1 [46, 57]|visit|NO: Person profile appends rows50–54; neither rows nor a sibling-written value controls city query50 or visit48.|
|IS2 [73, 92]|visit|MAY: messages append77 → sort79/slice81 → nested message spawn84. With11 messages, changing one sibling message date can alter which10 run ReplyOf/HasCreator helper accesses. Output-state erasure alone cannot prove no future access.|
|IS3 [93, 108]|visit|NO: dates is fully initialized97 before visits98 and only read103. rows output/sort does not feed later graph reads.|
|IS4 [109, 114]|visit|NO: One initial message visit; content selects ordinary here fields, and rows is only reported. No natural multi-target sibling frontier is introduced by start111.|
|IS5 [115, 121]|visit|NO: Message→HasCreator visit118 is here-relative; author appends output119. No shared mutable state feeds access.|
|IS6 [122, 136]|visit|NO: forum_id/title writes130 feed moderator output133–134, not visit131 or another graph query. Shared output provenance may be order-sensitive under fanout; that is distinct from access dependence. Comment ancestry follows here.is_comment126; source alone proves neither arity1 nor acyclicity.|
|IS7 [137, 156]|visit|NO: author_jid initialized141 before reply siblings142; per-reply creator/neighbor queries145–146 do not depend on rows or previous replies.|
|U1 [479, 499]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root mutation484. Duplicate person guard485; writes Person486–489 before duplicate emails/languages raise493, so later tag/study/work accesses494–496 are skipped on error. No sibling queue; rollback is a runtime contract, not proven here.|
|U2 [500, 508]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root mutation502. Post type/duplicate Likes guards504–505 control edge creation506. Existing Likes from prior operation changes this control path; no visit.|
|U3 [509, 517]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root mutation511. Comment type/duplicate Likes guards513–514 control515. Ordinary persistent read/write dependence, no sibling visit.|
|U4 [518, 527]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root mutation520. Duplicate forum guard521 precedes creation522 and moderator/tag resolution523–524. No visit.|
|U5 [528, 535]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root mutation530. HasMember duplicate query532 before edge creation533; successful earlier membership makes later duplicate raise. No sibling activation.|
|U6 [536, 551]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root mutation540. Duplicate message guard541 precedes writes542–548; creator/forum/country/tag bindings resolve procedurally. Created IDs/edges affect later operations, not siblings.|
|U7 [552, 567]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root mutation556. Duplicate message guard557 precedes writes558–565; ReplyOf links change future ancestry queries. No visit; no source proof of graph acyclicity/functional edges.|
|U8 [568, 575]|Root-only; no sibling traversal|NO_SIBLING_TRAVERSAL: Single Root mutation570. Self/duplicate check572 uses _friends; success573 adds Knows and changes future neighbors/_near/BFS operations. No sibling visit.|

## Relevant helpers and simplification boundary

IS2 messages are not output-only: sort/top10 chooses later nested-spawn targets. IC3 counters do not change visit siblings, but gate final person-field access; a payload snapshot rewrite could separate this phase, and is not claimed implemented. Simplifying an output dictionary alone cannot remove either access relationship.

_near, IC13 and IC14 have real procedural frontier/visited/path/cancellation state. _is_class has local DFS seen and early success. These are not reclassified as Jac sibling walks. IC14 finishes its current layer before the solutions flag stops the next while iteration. BFS distance is a hop-layer quantity, not total visited nodes. _OriginalPost/IS6 ancestry is not proven a chain or acyclic by source declarations.

- `_OriginalPost` [58, 71]: Here-dependent Message/Person traversal. original_id/creator outputs do not guard access. No seen/step bound; ReplyOf graph cycle or multiple parents are not ruled out by this source. A single-chain optimization requires separate cardinality/acyclicity evidence.

- `_content` [72, 72]: Field-only conditional image_file/content; no graph writes/visits.

- `_friends` [180, 182]: Read-only outgoing+incoming Knows concat; preserve duplicates/order; no universal uniqueness proof.

- `_near` [183, 198]: Local BFS visited-set writes190–191 affect later frontier/query origins193–195; diamond merge witness. depth is explicit hop-layer limit range185 and distance is assigned per layer, never total visited count. Called before visits; no Jac sibling abilities inside helper.

- `_author` [199, 199]: Read first HasCreator; requires nonempty typed graph, does not prove unique creator.

- `_tags` [200, 200]: Read-only HasTag targets.

- `_is_class` [410, 420]: Local DFS stack and seen414–417 control repeated SubClassOf queries; name match416 returns before further pending work. Diamond/cycle skips revisits. Procedural per-call state, reset for each tag.

- `_edge_weight` [441, 451]: Read-only two-direction comments/ReplyOf/author loops; local weight accumulator never guards later reads. Parent kind only selects arithmetic448.

- `friendship_dates` [19, 25]: Iterates person.__jac__.edges; edge kind/endpoint selects other node, stores creation_date by ref. Local result only, no graph writes. Requires summaries for Jac.object_ref, __jac__ descriptors and archetype access; opaque without those.

- `edge_rows` [28, 37]: Iterates __jac__.edges, filters kind/direction, reads target/source/archetype/getattr edge fields. No mutations except local rows. Ordinary framework/archetype summaries required; getter/descriptor effects otherwise unknown.

- `seed_graph` [7, 16]: Seed only, outside29 operation denominator. External file/JSON and Jac.save/connect/root/object_ref/diagnostics, graph mutations. This is not silently treated pure.

Python edge helpers access framework/archetype internals. Their bodies are read-only with ordinary fields, but a conservative algorithm needs explicit descriptor/framework summaries; without those the hidden-effect proof is unknown. Unknown effects or current unsupported syntax are not theoretical impossibility. Preserve output order/duplicates and defined graph-shape assumptions.

Source SHA-256:
- `reproduction/ttg-continuation-benchmarks/snb/server.jac`: `b1f367b55e6341bdcf035afa37186585018f1d02da8a41c0ce49ee3b3e025b99`.
- `reproduction/ttg-continuation-benchmarks/snb/fixture_loader.py`: `0ecee74693b7d4dc39b26c3190104949e7212537fc98fa50d79182ddc6480fe0`.
- `reproduction/ttg-continuation-benchmarks/supported_testcases.json`: `be6952d08d323d5a21b42de8028a200918b897399f142aeb2fa422ff8c8348ec`.

All29 registered source references match these Jac/helper bytes. No experiment, native claim or runtime source review was added.
