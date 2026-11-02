"""Persistent entry adapter; explicit query repairs are provenance-bound."""
include loader;
include queries;
walker LoadFixture {
    has directory: str;
    can load with Root entry {
        if [-->] { report {"ok": False, "error": "Fixture root is not empty"}; return; }
        load_tpch_graph(self.directory);
        report {"ok": True};
    }
}
