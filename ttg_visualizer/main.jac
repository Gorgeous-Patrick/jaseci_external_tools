"""TTG Explorer. Jac client UI; compiler/evidence adapters emit versioned JSON."""
import "./style.css";
import from "./model.js" {
    loadDefault, loadExample, loadFile, firstNode, getEvent, getRequest, neighborhood,
    cards, miniEvents, miniEdges, sourceRows, selectedHooks, sqlItems, counts,
    sqlLabel, sqlDetails, pretty, short, timebar, graphHeight, abilityNames, selectedRegion, nestedRegion, graphOverview, finiteDagView
}

import from "./sql_explainer.js" { explainQuery, walkthroughStep, walkthroughFragment, highlightedSQL, symbolInfo }

def:pub app -> JsxElement {
    has bundle: any = None,
        error: str = "",
        example: str = "jdrive",
        focus: str = "",
        nodeHistory: any = [],
        page: int = 0,
        eventId: int = 0,
        selectedAbility: str = "",
        graphMode: str = "region",
        requestId: str = "",
        queryId: str = "",
        templateId: str = "",
        tab: str = "graph",
        sqlStep: str = "",
        sqlPart: str = "all",
        sqlSymbol: str = "",
        edgeKind: str = "order",
        zoom: int = 100,
        showControl: bool = False,
        search: str = "";

    def install(data: any) {
        bundle = data;
        sqlStep = "";
        sqlPart = "all";
        sqlSymbol = "";
        example = "littlex" if data.`walker == "load_feed" else ("jdrive" if data.`walker == "VisibleFolderTree" else "");
        focus = firstNode(data);
        nodeHistory = [];
        eventId = data.compiler.events[0].id;
        selectedAbility = data.compiler.events[0].ability;
        requestId = data.requests[0].id if len(data.requests) else "";
        page = 0;
        queryId = "";
        templateId = "";
        error = "";
    }

    async can with entry {
        try { install(await loadDefault()); }
        except Exception as e { error = str(e); }
    }

    async def chooseExample(name: str) {
        try { install(await loadExample(name)); }
        except Exception as e { error = str(e); }
    }

    async def upload(e: any) {
        try {
            loaded = await loadFile(e);
            if loaded { install(loaded); }
        } except Exception as err { error = str(err); }
    }

    def selectEvent(id: int) {
        eventId = id;
        selectedAbility = getEvent(bundle, id).ability;
        templateId = "";
        queryId = "";
    }

    def selectNode(id: str) {
        if id != focus {
            nodeHistory = nodeHistory.concat([{"id": focus, "page": page}]);
            focus = id;
            page = 0;
        }
    }

    def goBack() {
        if len(nodeHistory) {
            previous = nodeHistory.at(-1);
            focus = previous.id;
            page = previous.page;
            nodeHistory = nodeHistory.slice(0, -1);
        }
    }

    if not bundle {
        return <main className="loading"><div className="brand">TTG / EXPLORER</div>
            <h1>Loading compiler evidence</h1><p>{error or "Opening the recorded JDrive bundle…"}</p>
            <label className="button">Open JSON bundle<input type="file" accept=".json" onChange={upload}/></label>
        </main>;
    }
    ev = getEvent(bundle, eventId);
    hood = neighborhood(bundle, focus, page);
    totals = counts(bundle, requestId);
    detail = sqlDetails(bundle, requestId, queryId, templateId);
    req = getRequest(bundle, requestId);
    dag = finiteDagView(bundle, focus, requestId);
    region = selectedRegion(bundle, eventId);
    canvasHeight = graphHeight(bundle, focus, page, requestId, selectedAbility);
    expansion = nestedRegion(bundle, focus, page, requestId, selectedAbility);
    overview = graphOverview(bundle, focus, requestId);
    walkthrough = explainQuery(bundle, requestId);
    sqlBlock = walkthroughStep(walkthrough, sqlStep);
    sqlFragment = walkthroughFragment(sqlBlock, sqlPart);

    return <div className="shell">
        <header>
            <div className="brand"><span className="brand-mark">⊞</span> TTG / EXPLORER</div>
            <span className="header-sep"></span><span className="capture-title">{bundle.title}</span>
            <span className="grow"></span><span className="badge">RECORDED EVIDENCE</span>
            <select aria-label="Example app" value={example} onChange={lambda (e: any) { chooseExample(e.target.value); }}>
                <option value="jdrive">JDrive</option><option value="littlex">LittleX</option>
                {if not example { <option value="">Imported bundle</option> }}
            </select>
            <label className="button">Open bundle<input type="file" accept=".json" onChange={upload}/></label>
        </header>
        {if error { <div className="error" role="alert">{error}</div> }}
        <div className="intro">
            <div><div className="eyebrow">SOURCE → DEPENDENCIES → SQL → EXECUTION</div>
                <h1>See where prefetch begins.</h1>
                <p>Explore the Jac graph, inspect the hooks inside an ability, and follow an access region into real SQL.</p>
            </div>
            <div className="stats">
                <div><strong>{len(bundle.compiler.hooks)}</strong><span>emitted hooks</span></div>
                <div><strong>{len(bundle.compiler.regions)}</strong><span>SQL region</span></div>
                <div><strong>{totals.data}</strong><span>data SQL / request</span></div>
                <div><strong>{totals.background}</strong><span>background data SQL</span></div>
            </div>
        </div>
        <nav className="tabs">
            <button className={"active" if tab == "graph" else ""} onClick={lambda { tab = "graph"; }}>01 · Graph & hooks</button>
            <button className={"active" if tab == "sql" else ""} onClick={lambda { tab = "sql"; }}>02 · SQL & timeline</button>
            <button className={"active" if tab == "walkthrough" else ""} onClick={lambda { tab = "walkthrough"; }}>03 · SQL walkthrough</button>
            <button className={"active" if tab == "evidence" else ""} onClick={lambda { tab = "evidence"; }}>04 · Evidence</button>
            <span className="grow"></span>
            <label>Request <select value={requestId} onChange={lambda (e: any) { requestId = e.target.value; queryId = ""; }}>
                {for r in bundle.requests { <option key={r.id} value={r.id}>{r.id}</option> }}
            </select></label>
        </nav>
        {if tab == "graph" {
            <div className={"workspace region-workspace" if graphMode == "region" else "workspace"}>
                <aside className="source-panel panel">
                    <div className="panel-title"><span>JAC SOURCE</span><span className="muted">click a graph event</span></div>
                    <div className="file-label">{ev.location.file}:{ev.location.line}</div>
                    <div className="source-code">
                        {for row in sourceRows(bundle, eventId, "") {
                            <div key={row.line} className={"source-line selected" if row.selected else "source-line"}>
                                <span className="line-number">{row.line}</span><code>{row.text or " "}</code>
                                {for h in row.hooks {
                                    <div className="hook-inline" key={h.id}>↳ {h.function} · {h.placement}</div>
                                }}
                            </div>
                        }}
                    </div>
                    <div className="source-note">Source positions retain compiler event IDs. Annex-body positions are resolved by ability name.</div>
                    <div className="panel-title">EMITTED HOOKS</div>
                    {for h in bundle.compiler.hooks {
                        <button className="hook-button" key={h.id} onClick={lambda { selectEvent(h.event); }}>
                            <b>{h.function}</b><span>event {h.event} · {h.placement}</span>
                        </button>
                    }}
                </aside>
                <section className="graph-panel panel">
                    <div className="panel-title"><span>JAC GRAPH · ABILITY GRAPHS INSIDE NODES</span>
                        <span className="muted">{len(bundle.graph.nodes)} nodes · {len(bundle.graph.edges)} edges</span>
                    </div>
                    <div className="graph-tools">
                        <div className="view-switch">
                            <button className={"active" if graphMode == "region" else ""} onClick={lambda { graphMode = "region"; page = 0; }}>Multi-level SQL region</button>
                            <button className={"active" if graphMode == "detail" else ""} onClick={lambda { graphMode = "detail"; page = 0; }}>Complete dependencies</button>
                        </div>
                        <button disabled={not len(nodeHistory)} title="Return to the previously viewed node" onClick={goBack}>← Back</button>
                        <input aria-label="Find graph node" placeholder="Find node by ID or name" value={search} onChange={lambda (e: any) { search = e.target.value; }}/>
                        <select aria-label="Graph node" value={focus} onChange={lambda (e: any) { selectNode(e.target.value); }}>
                            {for n in bundle.graph.nodes {
                                if not search or search.lower() in n.id.lower() {
                                    <option key={n.id} value={n.id}>{n.id}</option>
                                }
                            }}
                        </select>
                        <select aria-label="Dependency edge kind" value={edgeKind} onChange={lambda (e: any) { edgeKind = e.target.value; }}>
                            <option value="order">Order edges</option><option value="data">Data edges</option>
                            <option value="control">Control edges</option><option value="all">All edges</option>
                        </select>
                        <select aria-label="Ability" value={selectedAbility} onChange={lambda (e: any) { selectEvent(bundle.compiler.plan.entries[e.target.value]); }}>
                            {for name in abilityNames(bundle) { <option key={name} value={name}>{name}</option> }}
                        </select>
                        <button aria-label="Zoom out" disabled={zoom <= 75} onClick={lambda { zoom = zoom - 25; }}>−</button>
                        <span className="muted">{zoom}%</span>
                        <button aria-label="Zoom in" disabled={zoom >= 200} onClick={lambda { zoom = zoom + 25; }}>+</button>
                    </div>
                    {if graphMode == "region" and dag.supported {
                        <div className="region-explanation">
                            <strong>One finite SQL region: {bundle.`walker}.run → collect</strong>
                            <span>Three actual compiler visit sites share one emitted SQL template. Blue follows path / ID dependencies; native gather and output stay outside.</span>
                        </div>
                        <div className="graph-scroll">
                            <svg className="jac-graph finite-dag" viewBox="0 0 1180 1060" style={{"width": str(zoom) + "%"}} role="img" aria-label="LittleX finite SQL region crossing Root run and Profile collect abilities">
                                <defs><marker id="dag-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L7,4 L0,8" fill="#117ab0"/></marker><marker id="dag-native-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L7,4 L0,8" fill="#344e65"/></marker></defs>
                                {for c in dag.cards {
                                    <g key={c.key} className="dag-node" data-node-id={c.`node.id}>
                                        <rect x={c.x} y={c.y} width={c.w} height={c.h} rx="12" fill="#fff" stroke="#344e65" strokeWidth="2"/>
                                        <text x={c.x + 20} y={c.y + 29} className="nested-node-name">{c.title}</text>
                                        <text x={c.x + 20} y={c.y + 53} className="nested-ability">{c.subtitle}</text>
                                        <text x={c.x + 20} y={c.y + 66} className="nested-small">{c.note}</text>
                                    </g>
                                }}
                                {for link in dag.links {
                                    <g key={link.path}><path d={link.path} fill="none" stroke="#344e65" strokeWidth="2" markerEnd="url(#dag-native-arrow)"/><text x={link.x} y={link.y} className="nested-small">{link.label}</text></g>
                                }}
                                <g className="shared-sql-region finite-region" data-region-id={dag.region.id}>
                                    <path d={dag.regionPath} fill="#e8f3fb" stroke="#117ab0" strokeDasharray="9 5" strokeWidth="2"/>
                                    {for op in dag.operations {
                                        <g key={str(op.x) + ":" + str(op.y)} className="dag-operation" data-event-id={op.event} onClick={lambda { selectEvent(op.event); }}>
                                            <rect x={op.x} y={op.y} width={op.w} height={op.h} rx="7" fill="#fff" stroke="#117ab0"/>
                                            <text x={op.x + 12} y={op.y + 23} className="nested-text">{op.title}</text>
                                            <text x={op.x + 12} y={op.y + 45} className="nested-small">{op.sub}</text>
                                        </g>
                                    }}
                                    {for path in dag.dependencies { <path key={path} d={path} fill="none" stroke="#117ab0" strokeWidth="2" markerEnd="url(#dag-arrow)"/> }}
                                </g>
                                <text x="43" y="225" className="nested-region-title">R1 · one finite DAG template</text>
                                <g className="dag-entry-hook" onClick={lambda { selectEvent(dag.region.`entry); }}>
                                    <rect x="40" y="241" width="375" height="38" rx="5" fill="#f2edff" stroke="#b5a0de"/>
                                    <text x="50" y="265" className="nested-small">Entry hook · event {dag.region.`entry} · inspect source ↗</text>
                                </g>
                                <rect x="620" y="335" width="310" height="42" rx="6" fill="#f3f5f7" stroke="#ccd6df"/>
                                <text x="631" y="360" className="nested-text">Enqueue / ability execution stays native</text>
                                {for op in dag.boundaries {
                                    <g key={str(op.x)} className="dag-boundary" data-event-id={op.event} onClick={lambda { selectEvent(op.event); }}>
                                        <rect x={op.x} y={op.y} width={op.w} height={op.h} rx="7" fill="#f3f5f7" stroke="#ccd6df"/>
                                        <text x={op.x + 12} y={op.y + 23} className="nested-text">{op.title} · line {op.line}</text>
                                        <text x={op.x + 12} y={op.y + 47} className="nested-small">{op.sub}</text>
                                    </g>
                                }}
                            </svg>
                        </div>
                        <div className="region-legend"><span>Blue: run + collect path discovery</span><span>Gray: gather / to_view / output</span><span>Follow's intermediate Profile is a path hop, not an extra collect invocation.</span></div>
                        <div className="shared-region-toolbar">
                            <span><b>{len(dag.bindings)} compiled visit sites</b> · {len(dag.queries)} exact-matched SQL in selected request · representative initial-snapshot paths</span>
                            <button disabled={not dag.templateId} onClick={lambda { templateId = dag.templateId; queryId = ""; tab = "sql"; }}>View shared SQL →</button>
                        </div>
                        <div className="graph-footer">{len(bundle.graph.nodes)} snapshot nodes · {len(bundle.graph.edges)} edges. All nodes remain selectable above; pictured targets are examples, not the complete feed.</div>
                        <details className="excluded-branches"><summary>Compiler region and real path bindings</summary><pre>{pretty(dag.region.metadata)}</pre></details>
                    }}
                    {if graphMode == "region" and expansion.supported {
                        <div className="region-explanation">
                            <strong>One SQL region across Jac ability instances</strong>
                            <span>Jac nodes contain dependency slices. The connected blue boundary follows ID dependencies across the origin → target visit expansions.</span>
                        </div>
                        <details className="overview-panel" open={True}>
                            <summary>Full snapshot · {expansion.totalCount} nodes · {expansion.folderCount} {expansion.nodes[0].type} nodes · click any node to inspect</summary>
                            <svg className="graph-overview" viewBox="0 0 1000 180" role="img" aria-label="All nodes in the real Jac graph snapshot">
                                {for link in overview.links { <path key={link.source + link.target} d={link.path} stroke="#d3dce6" strokeWidth="0.6" fill="none"/> }}
                                {for n in overview.nodes {
                                    <circle key={n.id} className="overview-node" data-node-id={n.id} cx={n.x} cy={n.y} r={4 if n.selected else 2.5} fill={n.color} onClick={lambda { selectNode(n.id); }}><title>{n.id} · {n.type}</title></circle>
                                }}
                            </svg>
                            <p>Blue: reported visited · purple: selected · amber: trashed in initial snapshot · gray: other nodes</p>
                        </details>
                        <div className="graph-scroll">
                            <svg className="jac-graph region-expansion" style={{"width": str(zoom) + "%"}} viewBox={"0 0 1100 " + str(expansion.viewHeight)} role="img" aria-label="Branching Jac graph with nested dependency slices and one connected blue SQL region">
                                <defs><marker id="region-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L7,4 L0,8" fill="#117ab0"/></marker>
                                    <marker id="jac-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L7,4 L0,8" fill="#344e65"/></marker></defs>
                                {for n in expansion.nodes {
                                    <g key={n.id} className="ability-container" data-node-id={n.id} data-level={n.level}>
                                        <rect x={n.x} y={n.y} width="500" height={350 if n.level == 0 else 360} rx="12" fill="#fff" stroke="#344e65" strokeWidth="2"/>
                                        <text x={n.x + 20} y={n.y + 29} className="nested-node-name" onClick={lambda { selectNode(n.id); }}>{n.id}</text>
                                        <text x={n.x + 20} y={n.y + 51} className="nested-ability">{bundle.`walker}.{n.ability} · dependency slice</text>
                                        {if n.level == 0 {
                                            <rect x={n.x + 20} y={n.y + 66} width="210" height="48" rx="7" fill="#f2edff" stroke="#b5a0de"/>
                                            <g className="entry-hook" onClick={lambda { selectEvent(expansion.entryId); }}>
                                                <text x={n.x + 30} y={n.y + 86} className="nested-text">Known input: here.id</text>
                                                <text x={n.x + 30} y={n.y + 104} className="nested-small">Entry hook · event {expansion.entryId}</text>
                                            </g>
                                            <path d="M425,134 V149 H300 V216 H318" fill="none" stroke="#344e65" strokeWidth="2" markerEnd="url(#jac-arrow)"/>
                                        }}
                                        <rect x={n.x + 285 if n.level == 0 else n.x + 20} y={n.y + 257} width={195 if n.level == 0 else 460} height="67" rx="7" fill="#f3f5f7" stroke="#ccd6df"/>
                                        <text x={n.x + 297 if n.level == 0 else n.x + 34} y={n.y + 280} className="nested-text">{ "Native enqueue" if n.level == 0 else "Native: depth / path / output + enqueue" }</text>
                                        <text x={n.x + 297 if n.level == 0 else n.x + 34} y={n.y + 301} className="nested-small">{ "Depth / path / output" if n.level == 0 else ("Reported visited in selected request" if n.visited else "Static instance · not reported visited") }</text>
                                        {if n.level > 0 {
                                            <text x={n.x + 20} y={n.y + 345} className="expand-branch" onClick={lambda { selectNode(n.id); }}>Explore from here → {n.childCount} outgoing edges · {n.descendants} reachable nodes</text>
                                        }}
                                    </g>
                                }}
                                {for link in expansion.links {
                                    <g key={link.source + link.target}>
                                        <path className="jac-topology-edge" d={link.jacPath} fill="none" stroke="#344e65" strokeWidth="2.5" markerEnd="url(#jac-arrow)"/>
                                        <text x={link.labelX} y="404" className="nested-edge-label">Jac edge · {link.type}</text>
                                    </g>
                                }}
                                <g className="shared-sql-region" data-region-id={expansion.region.id}>
                                    <path d={expansion.regionPath} fill="#e8f3fb" fillOpacity="0.95" stroke="#117ab0" strokeWidth="2" strokeDasharray="9 5"/>
                                    <text x="325" y="181" className="nested-region-title">R1 · ONE COMPILED RECURSIVE SQL REGION</text>
                                    {for n in expansion.nodes {
                                        <g key={n.key} className="region-visit" data-node-id={n.id} data-event-id={n.event} onClick={lambda { selectEvent(n.event); }}>
                                            <rect className="region-hit" x={n.x + 20} y={190 if n.level == 0 else 568} width="460" height="75" fill="transparent"/>
                                            <rect x={n.x + 20} y={190 if n.level == 0 else 568} width="208" height="52" rx="7" fill="#fff" stroke="#117ab0" strokeWidth="1.5"/>
                                            <text x={n.x + 32} y={211 if n.level == 0 else 589} className="nested-text">{ "Resolve Contains → Folder" if n.level == 0 else "ID from previous expansion" }</text>
                                            <text x={n.x + 32} y={230 if n.level == 0 else 608} className="nested-small">{expansion.predicateLabel if n.level == 0 else n.id}</text>
                                            <path d={"M" + str(n.x + 230) + "," + str(216 if n.level == 0 else 594) + " h26"} fill="none" stroke="#117ab0" strokeWidth="2" markerEnd="url(#region-arrow)"/>
                                            <rect x={n.x + 260} y={190 if n.level == 0 else 568} width="220" height="52" rx="7" fill="#fff" stroke="#117ab0" strokeWidth="1.5"/>
                                            <text x={n.x + 271} y={211 if n.level == 0 else 589} className="nested-text">{ "Ordered target IDs" if n.level == 0 else "Resolve Contains → Folder" }</text>
                                            <text x={n.x + 271} y={230 if n.level == 0 else 608} className="nested-small">{ "Feed the next recursive expansion" if n.level == 0 else expansion.predicateLabel }</text>
                                            <text x={n.x + 25} y={258 if n.level == 0 else 643} className="nested-small">Visit event {n.event} · source line {expansion.region.metadata.visit_line} · inspect source ↗</text>
                                        </g>
                                    }}
                                    {for link in expansion.links {
                                        <path key={link.source + link.target} className="region-id-dependency" d={link.dependencyPath} stroke="#117ab0" strokeWidth="2" fill="none" markerEnd="url(#region-arrow)"/>
                                    }}
                                    {if len(expansion.links) { <text x="576" y="422" className="nested-small">R1 · target-ID dependency</text> }}
                                </g>
                                <path d="M425,134 V149 H300 V216 H318" fill="none" stroke="#344e65" strokeWidth="2" markerEnd="url(#jac-arrow)"/>
                                {for n in expansion.nodes {
                                    <path d={"M" + str(n.x + 370) + "," + str(265 if n.level == 0 else 654) + " V" + str(n.y + 255)} fill="none" stroke="#344e65" strokeWidth="1.5" markerEnd="url(#jac-arrow)"/>
                                }}
                            </svg>
                        </div>
                        <div className="region-legend"><span>Blue: compiled path / predicate / ID dependencies</span><span>Gray: native effects and traversal order</span><span>Payload loading remains a separate SQL query.</span></div>
                        <div className="shared-region-toolbar">
                            <span><b>{len(expansion.nodes)} illustrated ability instances</b> · 1 shared compiler region · {len(expansion.queries)} exact-matched SQL in this request</span>
                            <button disabled={not expansion.templateId} onClick={lambda { templateId = expansion.templateId; queryId = ""; tab = "sql"; }}>View shared SQL →</button>
                        </div>
                        <div className="graph-footer"><span>{expansion.eligibleCount} eligible targets · showing up to 2 · select a target to continue</span><span className="grow"></span>
                            <button disabled={expansion.pages < 2} onClick={lambda { page = page - 1; }}>←</button>
                            <span>{expansion.branch + 1} / {expansion.pages}</span>
                            <button disabled={expansion.pages < 2} onClick={lambda { page = page + 1; }}>→</button>
                        </div>
                        if len(expansion.excluded) {
                            <details className="excluded-branches"><summary>{len(expansion.excluded)} outgoing edges outside this illustrated expansion</summary>
                                {for n in expansion.excluded { <button key={n.id} onClick={lambda { selectNode(n.id); }}>{n.id} · {n.reason}</button> }}
                            </details>
                        }
                    } elif graphMode == "region" and not dag.supported {
                        <div className="empty"><h2>No region projection for this selection</h2><p>Choose a supported origin or open the complete dependency graph. The current projection covers output-tree and root / two-branch finite-DAG certificates.</p><button onClick={lambda { graphMode = "detail"; }}>Open complete dependencies</button></div>
                    }}
                    {if graphMode == "detail" {
                    <div className="graph-scroll">
                        <svg className="jac-graph" style={{"width": str(zoom) + "%"}} viewBox={"0 0 1060 " + str(canvasHeight)} role="img" aria-label="Real Jac nodes with nested ability dependency graphs">
                            <defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#8594aa"/></marker>
                                <marker id="green-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#0a866e"/></marker></defs>
                            {for c in cards(bundle, focus, page, requestId, selectedAbility) {
                                if c.id != focus {
                                    <path d={"M180,89 Q180,25 " + str(c.x + 150) + ",25 L" + str(c.x + 150) + ",88"} fill="none" stroke="#8594aa" strokeWidth="1.5" markerEnd="url(#arrow)"/>
                                    <text x={c.x + 100} y="19" className="edge-label">{c.`edge.type}</text>
                                }
                                <g key={c.id}>
                                    <rect x={c.x} y="90" width="320" height={c.height} rx="12" fill="#ffffff" stroke={"#0a866e" if c.id == focus else "#d5deea"} strokeWidth={2 if c.id == focus else 1}/>
                                    <text x={c.x + 18} y="117" className="node-type">{c.type} <tspan className="node-status">{ "· reported visited" if c.visited else "· initial fixture" }</tspan></text>
                                    <text x={c.x + 18} y="141" className="node-name" onClick={lambda { selectNode(c.id); }}>{short(c.id, 32)}</text>
                                    <text x={c.x + 18} y="173" className="ability-label">{(bundle.`walker + "." + c.ability) if c.ability else "No selected-walker region"}</text>
                                    {for dep in miniEdges(bundle, c, edgeKind) {
                                        <path key={dep.key} d={dep.path} fill="none" stroke={"#b38a3d" if dep.kind == "data" else "#a5b6ca"} strokeWidth="1" opacity="0.75"/>
                                    }}
                                    {for e in miniEvents(bundle, c) {
                                        <g key={str(e.id)} className="event-node" onClick={lambda { selectEvent(e.id); }}>
                                            <rect x={e.x} y={e.y} width="270" height="21" rx="4" fill={"#dbf4eb" if e.access else ("#ece8ff" if e.hook else "#f2f5fa")} stroke={"#7355c8" if e.id == eventId else "none"}/>
                                            <text x={e.x + 8} y={e.y + 14} className="event-label">{short(e.label, 36)}</text>
                                            {if e.hook { <circle cx={e.x - 8} cy={e.y + 10} r="4" fill="#7855ce"/> }}
                                        </g>
                                    }}
                                    {if c.region {
                                        <rect x={c.x + 12} y={c.regionY} width="296" height="43" rx="6" fill="#ecf8f3" stroke="#0a866e" strokeDasharray="5 3"/>
                                        <text x={c.x + 22} y={c.regionY + 18} className="region-label">SQL ACCESS REGION · {c.regionKind}</text>
                                        <text x={c.x + 22} y={c.regionY + 34} className="region-subtitle">{c.predicate} · visit line {c.visitLine}</text>
                                    }}
                                </g>
                            }}
                            {if len(hood.children) and region {
                                <text x="40" y={canvasHeight - 10} className="region-label">SQL ACCESS REGION · static certificate, shared across applicable node instances</text>
                            }}
                        </svg>
                    </div>
                    <div className="graph-footer"><span><i className="dot purple"></i> emitted hook <i className="dot green"></i> certified access · output remains native</span>
                        <span className="grow"></span><button disabled={page == 0} onClick={lambda { page = page - 1; }}>←</button>
                        <span>Targets {page + 1} / {hood.pages}</span><button disabled={page + 1 >= hood.pages} onClick={lambda { page = page + 1; }}>→</button>
                    </div>
                    }}
                    <p className="graph-caption">{bundle.graph.state}. Node interiors reuse the static ability graph; they are not a per-node hook-firing trace.</p>
                </section>
                <aside className="inspector panel">
                    <div className="panel-title">EVENT INSPECTOR</div>
                    <h2>#{ev.id} · {ev.kind}</h2><p className="mono">{bundle.`walker}.{ev.ability}</p>
                    <dl><dt>Expression</dt><dd>{ev.expression or "—"}</dd><dt>Reads</dt><dd>{pretty(ev.reads)}</dd><dt>Writes</dt><dd>{ev.writes or "—"}</dd></dl>
                    {for h in selectedHooks(bundle, eventId) {
                        <div className="callout purple-box" key={h.id}><b>{h.function}</b><p>{h.placement}</p><small>Verified bytecode callsite · offset {h.bytecode_offset}</small></div>
                    }}
                    {if region {
                        <div className="panel-title section-gap">REGION CERTIFICATE</div>
                        <h3>{region.metadata.kind}</h3><p>{region.metadata.dependency_proof or "See compiler certificate below."}</p>
                        <div className="callout">Access is compiled; native effects and walker execution remain in Jac.</div>
                        for tid in region.templates {
                            <button key={tid} className="template-button" onClick={lambda { templateId = tid; queryId = ""; tab = "sql"; }}>{short(tid.split("/")[-1], 20)} SQL ↗</button>
                        }
                        <details><summary>Full region metadata</summary><pre>{pretty(region.metadata)}</pre></details>
                    } else {
                        <div className="callout">This ability has no selected SQL access region. Its dependency graph and native effects remain visible.</div>
                    }}
                    <details className="section-gap"><summary>Generic analysis & rejection reasons</summary><pre>{pretty(bundle.compiler.plan.interability_regions.summaries)}</pre></details>
                </aside>
            </div>
        }}
        {if tab == "sql" {
            <div className="sql-workspace">
                <section className="panel sql-list">
                    <div className="panel-title"><span>ACTUAL REQUEST · {requestId}</span><label><input type="checkbox" checked={showControl} onChange={lambda (e: any) { showControl = e.target.checked; }}/> Control SQL</label></div>
                    <div className="sql-summary"><strong>{totals.data} data</strong> + {totals.control} control · protocol sum {totals.ms} ms</div>
                    <p className="muted pad">Bars preserve send→ready coordinates. Select a row to inspect the exact captured SQL.</p>
                    {for q in sqlItems(bundle, requestId, showControl) {
                        <button className={"query-row chosen" if queryId == q.id else "query-row"} key={q.id} onClick={lambda { queryId = q.id; templateId = ""; }}>
                            <div><b>{sqlLabel(q)}</b><span>{q.duration_ms.toFixed(3)} ms · {q.rows} rows</span></div>
                            <div className="timeline"><span className={"bar bg" if q.role == "background_prefetch" else "bar"} style={timebar(bundle, requestId, q)}></span></div>
                            <small>{q.role} · backend {q.backend_pid} · {q.template_match}</small>
                        </button>
                    }}
                    <div className="panel-title section-gap">COMPILER TEMPLATES · NOT ALL EXECUTED</div>
                    {for t in bundle.compiler.templates {
                        <button className="template-list" key={t.id} onClick={lambda { templateId = t.id; queryId = ""; }}>{t.id}</button>
                    }}
                </section>
                <section className="panel sql-detail">
                    {if detail {
                        <div className="panel-title">{detail.title}{if walkthrough.supported { <button onClick={lambda { tab = "walkthrough"; }}>Walk through this request’s region SQL →</button> }}</div>
                        <p className="mono pad">SHA256 {detail.sql_sha256}</p>
                        <pre className="sql-code">{detail.sql}</pre>
                        <div className="detail-grid"><div><h3>Parameters / slots</h3><pre>{pretty(detail.parameters)}</pre></div><div><h3>Evidence</h3><pre>{pretty(detail.evidence)}</pre></div></div>
                    } else {
                        <div className="empty"><h2>From a region to an actual query</h2><p>Select a captured SQL row or a compiler template.</p><p>Only exact SQL text matches link the two. Unmatched queries stay visible.</p></div>
                    }}
                </section>
            </div>
        }}
        {if tab == "walkthrough" {
            if walkthrough.supported {
                <section className="walkthrough-header panel">
                    <div><div className="eyebrow">ONE SQL STATEMENT · LOGICAL DATAFLOW</div><h2>{"LittleX: three visits, one finite SQL DAG" if walkthrough.finite else "JDrive: recursion first, ordered path records second"}</h2>
                        <p>Click a block, then inspect its Jac source, table aliases and exact SQL clauses. Arrows show dependencies, not PostgreSQL's physical execution plan.</p></div>
                    <div className="walkthrough-facts"><b>{walkthrough.characters} characters</b><span>{walkthrough.constants} compiler constants · {len(walkthrough.inputSlots)} runtime slots</span><span>Captured: {walkthrough.query.rows} result rows · {walkthrough.query.duration_ms.toFixed(3)} ms</span></div>
                </section>
                <section className="panel walkthrough-flow">
                    <div className="walkthrough-inputs"><b>Runtime input</b>{for slot in walkthrough.inputSlots { <span key={slot.name}>:{slot.name} <small>{slot.type}</small></span> }}<em>Concrete Bind values were not retained.</em></div>
                    <div className="graph-scroll">
                        <svg className="sql-flow" viewBox="0 0 1100 440" role="img" aria-label="Logical SQL block dependency graph">
                            <defs><marker id="sql-flow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L7,4 L0,8" fill="#117ab0"/></marker></defs>
                            {for link in walkthrough.links { <path key={link.path} className="sql-flow-edge" d={link.path} fill="none" stroke="#6796b4" strokeWidth="2" markerEnd="url(#sql-flow-arrow)"/> }}
                            {for item in walkthrough.graph {
                                <g key={item.id} className="sql-flow-node" data-step={item.id} onClick={lambda { sqlStep = item.id; sqlPart = "all"; sqlSymbol = ""; }}>
                                    <rect x={item.x} y={item.y} width={item.w} height={item.h} rx="10" fill={"#e4f3fc" if sqlBlock.id == item.id else "#fff"} stroke={"#117ab0" if sqlBlock.id == item.id else "#c8d6e2"} strokeWidth="2"/>
                                    <text x={item.x + 16} y={item.y + 28} className="sql-block-key">{item.id}</text>
                                    <text x={item.x + 16} y={item.y + 53} className="nested-text">{short(item.title, 37)}</text>
                                    <text x={item.x + 16} y={item.y + 76} className="nested-small">Inspect exact SQL →</text>
                                </g>
                            }}
                        </svg>
                    </div>
                    <div className="sql-flow-caption">{ "CTE 1 and CTE 2 both consume CTE 0. Neither consumes the other’s Tweet results. The −1 branch returns type metadata." if walkthrough.finite else "UNION removes repeated origin IDs. The loop stops when it adds no new origins. The outer row LIMIT is not a recursion depth limit." }</div>
                </section>
                <div className="walkthrough-content">
                    <section className="panel sql-meaning">
                        <div className="panel-title">READ THIS BLOCK</div><h2>{sqlBlock.title}</h2><p>{sqlBlock.description}</p><p className="meaning-why">{sqlBlock.why}</p>
                        {if sqlBlock.jac {
                            <div className="panel-title">JAC VISIT</div><pre className="jac-excerpt">{sqlBlock.jac}</pre>
                            <button onClick={lambda { selectEvent(sqlBlock.event); tab = "graph"; }}>{sqlBlock.location} · event {sqlBlock.event} ↗</button>
                        }}
                        <div className="panel-title section-gap">WHAT DO THE TABLE ALIASES MEAN?</div>
                        {if len(sqlBlock.aliases) {
                            <table className="explain-table"><thead><tr><th>Alias</th><th>Table</th><th>Role</th></tr></thead><tbody>
                                {for alias in sqlBlock.aliases { <tr key={alias.name}><td><button className={"symbol-button chosen" if sqlSymbol == alias.name else "symbol-button"} onClick={lambda { sqlSymbol = alias.name; }}>{alias.name}</button></td><td><code>{alias.table}</code></td><td>{alias.role}{if alias.type { <small>type constraint: {alias.type}</small> }}</td></tr> }}
                            </tbody></table>
                        } else { <p>This block introduces no base-table alias.</p> }}
                        <details className="sql-parameters"><summary>Parameters used here · {len(sqlBlock.parameters)}</summary>
                            <table className="explain-table"><thead><tr><th>Name</th><th>Value / binding</th></tr></thead><tbody>
                                {for param in sqlBlock.parameters { <tr key={param.name}><td><button className="symbol-button" onClick={lambda { sqlSymbol = param.name; }}>{":" + param.name}</button></td><td><code>{param.value}</code><small>{param.type}</small></td></tr> }}
                            </tbody></table>
                        </details>
                    </section>
                    <section className="panel sql-fragment-panel">
                        <div className="panel-title"><span>EXACT SQL · EXPLANATION BY CLAUSE</span><span className="muted">Click an alias or parameter to highlight it</span></div>
                        <div className="fragment-tabs">{for frag in sqlBlock.fragments {
                            <button key={frag.id} className={"active" if sqlFragment.id == frag.id else ""} onClick={lambda { sqlPart = frag.id; }}>{frag.title}</button>
                        }}</div>
                        <p className="fragment-note">{sqlFragment.note}</p>
                        {if sqlSymbol { <div className="symbol-info">{symbolInfo(sqlBlock, sqlSymbol) or sqlSymbol}<button onClick={lambda { sqlSymbol = ""; }}>Clear highlight</button></div> }}
                        <pre className="explained-sql">{for token in highlightedSQL(sqlFragment.sql, sqlSymbol) { <span key={str(token.key)} className={"sql-token " + token.kind + (" selected" if token.active else "")} onClick={lambda { sqlSymbol = token.symbol; }}>{token.text}</span> }}</pre>
                        <div className="snippet-proof">Original SQL characters [{sqlBlock.start + sqlFragment.start}, {sqlBlock.start + sqlFragment.end}) · whitespace-only display formatting</div>
                        <details className="original-snippet"><summary>Original fragment bytes</summary><pre>{sqlFragment.sql}</pre></details>
                    </section>
                </div>
                <section className="panel sql-result-contract">
                    <div className="panel-title">WHAT COMES BACK?</div>
                    <p>These are path / validation records. They are not the application's final JSON response.</p>
                    <table className="explain-table"><thead><tr><th>Output column</th><th>Meaning</th></tr></thead><tbody>{for col in walkthrough.columns { <tr key={col[0]}><td><code>{col[0]}</code></td><td>{col[1]}</td></tr> }}</tbody></table>
                    <div className="result-stages"><span>SQL path records</span><b>→</b><span>Runtime contract checks + path cache</span><b>→</b><span>Separate payload hydration</span><b>→</b><span>Native visits + output</span></div>
                    <p>Selected request also records {len(walkthrough.payloadQueries)} background data query. No per-CTE result rows or full Bind values were retained, so this page does not invent intermediate row samples.</p>
                    <button onClick={lambda { queryId = walkthrough.query.id; templateId = ""; tab = "sql"; }}>Open exact captured query & timeline →</button>
                    <details className="original-snippet"><summary>Full original SQL and provenance</summary><p className="mono">SQL SHA256 {walkthrough.query.sql_sha256}</p><pre>{pretty(walkthrough.query.evidence)}</pre><pre>{walkthrough.template.sql}</pre></details>
                </section>
            } else {
                <section className="panel walkthrough-header"><h2>SQL walkthrough unavailable</h2><p>{walkthrough.reason}</p><button onClick={lambda { tab = "sql"; }}>Open exact SQL & timeline</button></section>
            }
        }}
        {if tab == "evidence" {
            <section className="panel evidence-panel"><div className="panel-title">PROVENANCE & SCOPE</div>
                <h2>Inspectable data, not a hand-drawn execution.</h2>
                {for note in bundle.limitations { <p key={note} className="callout">{note}</p> }}
                <h3>Compiler artifact</h3><pre>{pretty(bundle.provenance.compiler_artifact)}</pre>
                <h3>Verified source and capture files</h3><pre>{pretty(bundle.provenance.verified_files)}</pre>
                <h3>Extensible contract</h3><p>jac.ttg.visualization / version 1 · Sources, compiler events, hooks, regions, templates, graph and requests have separate identities. Import another bundle without changing this UI.</p>
            </section>
        }}
        <footer>TTG Explorer · Jac client · compiler facts + recorded execution · no database required for viewing</footer>
    </div>;
}
