"""Source-only portfolio pages using the existing accepted Deck primitives.

No plotting imports, runtime imports, data collection, or execution entry point.
Final assembly supplies accepted input only after the coordinator's quiet release.
"""

POLICIES = ("off", "conservative", "background", "restored")
LABELS = {
    "off": "Off", "conservative": "Old Conservative",
    "background": "Previous Background", "restored": "Restored Background",
}
FIELDS = ("HTTP_response_sum_ms", "business_requests", "data_SQL", "control_SQL",
          "total_SQL", "data_SQL_per_business_request")


def _stat(cell, key):
    stat = cell["metrics"][key]
    if stat["n"] != 5 or len(stat["values"]) != 5:
        raise ValueError("Accepted primary cell must retain five samples: " + key)
    return stat


def _row(cell):
    label = LABELS[cell["policy"]]
    if not cell["timing_accepted"]:
        if cell.get("metrics") is not None:
            raise ValueError("Terminal non-timing cell must not advertise statistics")
        return [label, cell["status"], "—", "—", "—", "—", "—"]
    stats = {key: _stat(cell, key) for key in FIELDS}
    http = stats["HTTP_response_sum_ms"]
    return [label,
            f"{http['median']:.3f} [{http['min']:.3f}, {http['max']:.3f}]",
            f"{stats['business_requests']['median']:g}",
            f"{stats['data_SQL']['median']:g}",
            f"{stats['control_SQL']['median']:g}",
            f"{stats['total_SQL']['median']:g}",
            f"{stats['data_SQL_per_business_request']['median']:.3f}"]


def add_portfolio_pages(deck, data):
    if not (data["all_stages_terminal"] and data["services_stopped"]
            and data["raw_audit_quiet"] and data["assembly_released"]):
        raise ValueError("Final portfolio assembly has not been released")
    apps = data["apps"]
    cells = {(c["app"], c["policy"]): c for c in data["cells"]}
    expected = {(app["app"], policy) for app in apps for policy in POLICIES}
    if (len(apps) != 30 or len(expected) != 120 or len(cells) != 120
            or len(data["cells"]) != 120 or set(cells) != expected):
        raise ValueError("Keep exactly all30 entries and four distinct policy cells each")
    for start in range(0, 30, 2):
        figure = deck.page("All30 portfolio comparison",
                           "One LinkedList microbenchmark + 29 applications; HTTP ms: median [min, max].",
                           kind="Primary n = 5; exact terminal statuses retained")
        for offset, app in enumerate(apps[start:start + 2]):
            top = .77 if offset == 0 else .43
            deck.text(figure, .055, top, app["label"], 19, weight="bold")
            deck.text(figure, .055, top - .045, app["size_operations_support"],
                      10, width=.89)
            deck.text(figure, .055, top - .073, app["support_reason"],
                      10, width=.89)
            rows = [_row(cells[(app["app"], policy)]) for policy in POLICIES]
            deck.table(figure,
                       ["Policy", "HTTP median [range]", "HTTP", "Data", "Control", "TOTAL", "Data / HTTP"],
                       rows, widths=[.19, .29, .07, .09, .09, .09, .18],
                       area=(.055, top - .29, .89, .175), size=10.5)
            deck.text(figure, .055, top - .301, app["count_range_or_status_note"],
                      9, width=.89)
        deck.text(figure, .055, .082,
                  "All-role SQL counts; snapshot/worker setup counted. Publications are not timely hits. "
                  "SQL text/frame metadata retained; original Bind values/raw packets not retained.",
                  10, width=.89)
